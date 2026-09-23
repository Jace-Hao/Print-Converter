# -*- coding: utf-8 -*-
"""水洗唛打印助手 - 处理管道: PDF -> 旋转排版 -> 打印 -> 归档"""
import datetime
import os
import re
import shutil

from .render import render_pdf_pages, compose_label
from .printutil import to_mono, print_image


def _ts():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def process_pdf(cfg, log, pdf_path, dry_run=False):
    """处理一个 PDF 文件(逐页转标签并打印)。返回结果信息。"""
    pl = cfg["pipeline"]
    pr = cfg["print"]
    cap = cfg.get("capture") or {}
    sk = cfg.get("skip_print") or {}
    skip_on = bool(sk.get("enabled", True))
    skip_kws = [re.sub(r"\s+", "", str(k)) for k in (sk.get("keywords") or []) if str(k)]
    os.makedirs(cfg.path_of("previews"), exist_ok=True)
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
        canvas, info = compose_label(page["img"], cfg)
        info["captured"] = bool(page.get("captured"))
        mono = to_mono(canvas, bool(pr["dither"]), int(pr["threshold"]))
        prev = os.path.join(cfg.path_of("previews"), "%s_%s_p%d.png" % (base, _ts(), i + 1))
        mono.save(prev)
        info["preview"] = prev
        flat = re.sub(r"\s+", "", page.get("text") or "")
        hit = next((k for k in skip_kws if k in flat), None) if (skip_on and flat) else None
        if hit:
            info["skipped"] = True
            info["skip_keyword"] = hit
            log.info("第 %d 页命中不打印关键词「%s」→ 跳过打印（仍保留预览与归档）", i + 1, hit)
        elif dry_run:
            log.info("dry_run: 跳过打印, 预览=%s", prev)
        else:
            print_image(pr["printer"], mono, doc_name="水洗唛-" + base, copies=int(pr["copies"]))
            log.info("已送出打印: 第 %d 页 -> %s", i + 1, pr["printer"])
        out["labels"].append(info)
    if not dry_run:
        arch_dir = cfg.path_of("archive")
        os.makedirs(arch_dir, exist_ok=True)
        arch = os.path.join(arch_dir, base + "_" + _ts() + ".pdf")
        n = 1
        while os.path.exists(arch):
            arch = os.path.join(arch_dir, base + "_" + _ts() + "_%02d.pdf" % n)
            n += 1
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
