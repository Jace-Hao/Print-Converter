# -*- coding: utf-8 -*-
"""水洗唛打印助手 - 自定义标签生成

字段 dict -> 120x30mm 横版标签设计稿（PIL 图）；
经既有旋转管线（旋转 90°、排版到 30x120mm）后打印，与自动打印链路完全一致。
"""
import datetime
import json
import os

from PIL import Image, ImageDraw, ImageFont

FONT_PATH = "msyh.ttc"

try:
    from barcode import Code128
    from barcode.writer import ImageWriter
    _HAS_BARCODE = True
except Exception:  # pragma: no cover
    _HAS_BARCODE = False


def _font(px):
    try:
        return ImageFont.truetype(FONT_PATH, px)
    except Exception:
        return ImageFont.load_default()


def _mm(v, dpi):
    return int(round(v / 25.4 * dpi))


def _barcode_image(value, dpi, box_w_px, box_h_px):
    """生成 Code128 条码图并缩放适配到目标像素框；失败返回 None。"""
    if not _HAS_BARCODE or not value:
        return None
    try:
        from io import BytesIO

        code = Code128(value, writer=ImageWriter())
        buf = BytesIO()
        code.write(buf, {
            "module_width": 0.3,
            "module_height": 8.0,
            "quiet_zone": 0.5,
            "write_text": False,
            "dpi": dpi,
        })
        buf.seek(0)
        img = Image.open(buf).convert("RGB")
        r = min(box_w_px / img.width, box_h_px / img.height)
        return img.resize((max(1, int(img.width * r)), max(1, int(img.height * r))), Image.LANCZOS)
    except Exception:
        return None


def render_label(fields, dpi=300):
    """将字段渲染为 120x30mm 横版标签设计稿（PIL 图）。"""
    w, h = _mm(120, dpi), _mm(30, dpi)
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)

    def g(k):
        return str((fields or {}).get(k) or "").strip()

    f_item = _font(_mm(4.4, dpi))
    f_main = _font(_mm(3.5, dpi))
    f_small = _font(_mm(3.0, dpi))

    def join(parts):
        return "  ".join([p for p in parts if p])

    x0 = _mm(2.5, dpi)
    rows = [
        (join([g("衣物名称"), g("颜色"), g("工艺")]), f_item),
        (join(["电：" + g("电话") if g("电话") else "", g("客户"),
               "单：" + g("单号") if g("单号") else "",
               "件：" + g("件数") if g("件数") else ""]), f_main),
        (join(["下单：" + g("下单日期") if g("下单日期") else "",
               "品牌：" + g("品牌") if g("品牌") else ""]), f_main),
        ("损：" + g("损坏说明"), f_main),
        ("服务：" + g("服务项目"), f_main),
    ]
    y = _mm(1.6, dpi)
    for text, font in rows:
        if text.strip():
            d.text((x0, y), text, fill="black", font=font)
        y += _mm(5.0, dpi)

    # 右侧：门店名 + 条码 + 条码号
    xr = _mm(84, dpi)
    if g("门店名"):
        d.text((xr, _mm(1.6, dpi)), g("门店名"), fill="black", font=f_main)

    barcode_value = g("条码号")
    if barcode_value:
        bc = _barcode_image(barcode_value, dpi, _mm(33, dpi), _mm(11, dpi))
        if bc:
            bx = _mm(117, dpi) - bc.width
            by = _mm(21, dpi) - bc.height
            img.paste(bc, (bx, by))
            num_w = d.textlength(barcode_value, font=f_small)
            nx = bx + (bc.width - num_w) / 2
        else:
            num_w = d.textlength(barcode_value, font=f_small)
            nx = _mm(117, dpi) - num_w
        d.text((nx, _mm(21.6, dpi)), barcode_value, fill="black", font=f_small)

    return img


def print_custom_label(cfg, log, fields, dry_run=False):
    """渲染 -> 旋转排版(与自动链路一致) -> 打印；返回存档预览路径。"""
    from app.printutil import print_image, to_mono
    from app.render import compose_label

    dpi = int(cfg["pipeline"]["render_dpi"])
    page = render_label(fields, dpi=dpi)
    canvas, _info = compose_label(page, cfg)
    mono = to_mono(canvas, bool(cfg["print"]["dither"]), int(cfg["print"]["threshold"]))

    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    prev_dir = cfg.path_of("previews")
    os.makedirs(prev_dir, exist_ok=True)
    prev = os.path.join(prev_dir, "custom-%s.png" % ts)
    mono.save(prev)
    try:
        with open(os.path.join(prev_dir, "custom-%s.json" % ts), "w", encoding="utf-8") as f:
            json.dump(fields, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    if dry_run:
        log.info("dry_run 自定义标签预览: %s", prev)
    else:
        print_image(cfg["print"]["printer"], mono, doc_name="自定义水洗唛-" + ts,
                    copies=int(cfg["print"]["copies"]))
        log.info("自定义标签已打印: %s", prev)
    return prev
