# -*- coding: utf-8 -*-
"""水洗唛打印助手 - 处理管道: PDF -> 旋转排版 -> 打印 -> 归档"""
import datetime
import os
import shutil

from .render import render_pdf_pages, compose_label
from .printutil import to_mono, print_image


def _ts():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def _layout_pages(cfg, log, pdf_path, template):
    """布局模式: 逐页识别字段 -> 用模板重新渲染(120x30 横版设计稿)。失败返回 None。"""
    import pymupdf

    from .layout import render_template
    from .recognize import recognize_fields

    dpi = int(cfg["pipeline"]["render_dpi"])
    doc = pymupdf.open(pdf_path)
    n = len(doc)
    doc.close()
    out = []
    for i in range(n):
        fields = recognize_fields(pdf_path, page_index=i)
        if not (fields.get("条码号") or fields.get("单号") or fields.get("衣物名称") or fields.get("电话")):
            log.warning("布局模式: 第 %d 页字段识别失败", i + 1)
            return None
        out.append({"img": render_template(template, fields, dpi), "w_mm": 120.0, "h_mm": 30.0,
                    "captured": False, "layout": True})
    return out


def process_pdf(cfg, log, pdf_path, dry_run=False):
    """处理一个 PDF 文件(逐页转标签并打印)。返回结果信息。"""
    pl = cfg["pipeline"]
    pr = cfg["print"]
    cap = cfg.get("capture") or {}
    os.makedirs(cfg.path_of("previews"), exist_ok=True)
    pages = None
    if str(pl.get("render_mode", "rotate")).lower() == "layout":
        from .layout import load_template
        template = load_template(cfg, pl.get("layout_template"))
        if template is not None:
            pages = _layout_pages(cfg, log, pdf_path, template)
            if pages is None:
                log.warning("布局模式不可用, 本次回退为旋转模式")
        else:
            log.warning("未找到布局模板 %r, 回退为旋转模式", pl.get("layout_template"))
    if not pages:
        pages = render_pdf_pages(
            pdf_path, int(pl["render_dpi"]),
            capture_crop=tuple(cap.get("crop_mm") or (0.0, 0.0, 120.0, 30.0)),
            capture_shift=tuple(cap.get("shift_mm") or (0.0, 0.0)))
    log.info("处理 %s: %d 页", os.path.basename(pdf_path), len(pages))
    out = {"file": pdf_path, "labels": []}
    base = os.path.splitext(os.path.basename(pdf_path))[0]
    for i, page in enumerate(pages):
        if page.get("captured"):
            log.info("第 %d 页为虚拟打印机捕获页: 已截取标签区域 %s", i + 1, cap.get("crop_mm"))
        elif page.get("layout"):
            log.info("第 %d 页按布局模板重排", i + 1)
        canvas, info = compose_label(page["img"], cfg)
        info["captured"] = bool(page.get("captured"))
        info["layout"] = bool(page.get("layout"))
        mono = to_mono(canvas, bool(pr["dither"]), int(pr["threshold"]))
        prev = os.path.join(cfg.path_of("previews"), "%s_%s_p%d.png" % (base, _ts(), i + 1))
        mono.save(prev)
        info["preview"] = prev
        if dry_run:
            log.info("dry_run: 跳过打印, 预览=%s", prev)
        else:
            print_image(pr["printer"], mono, doc_name="水洗唛-" + base, copies=int(pr["copies"]))
            log.info("已送出打印: 第 %d 页 -> %s", i + 1, pr["printer"])
        out["labels"].append(info)
    if not dry_run:
        arch_dir = cfg.path_of("archive")
        os.makedirs(arch_dir, exist_ok=True)
        arch = os.path.join(arch_dir, base + "_" + _ts() + ".pdf")
        moved = False
        for attempt in range(5):
            try:
                shutil.move(pdf_path, arch)
                moved = True
                break
            except Exception as e:
                import time
                time.sleep(1.0)
                last = e
        if moved:
            out["archived"] = arch
            log.info("已归档: %s", arch)
        else:
            log.warning("归档失败(继续保留源文件): %s", pdf_path)
    return out
