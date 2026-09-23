# -*- coding: utf-8 -*-
"""水洗唛打印助手 - PDF → 标签位图 的渲染与排版核心

流程: PDF 页面 → 渲染(300dpi) → (可选)裁剪内容 → 顺时针/逆时针旋转90°
      → 1:1 毫米映射粘贴到 30x120mm 画布 → 输出发给标签机的位图
"""
import pymupdf
from PIL import Image, ImageChops


CAPTURE_MIN_EDGE_MM = 140.0   # 页面短边超过该值 → 视为"虚拟打印机捕获页"


def render_pdf_pages(pdf_path, dpi, capture_crop=None, capture_shift=(0.0, 0.0)):
    """渲染 PDF 每页为 PIL 图像, 返回 [{img, w_mm, h_mm, captured}]。

    capture_crop: (x0,y0,x1,y1) 毫米。当某页明显大于标签纸时(虚拟打印机捕获到的
    整页打印文件, 标签内容位于页面左上角), 只渲染该区域并按 capture_shift 平移,
    以对齐旧版式。
    """
    doc = pymupdf.open(pdf_path)
    pages = []
    for page in doc:
        w_mm = page.rect.width / 72.0 * 25.4
        h_mm = page.rect.height / 72.0 * 25.4
        captured = False
        if capture_crop and min(w_mm, h_mm) > CAPTURE_MIN_EDGE_MM:
            x0, y0, x1, y1 = capture_crop
            clip = pymupdf.Rect(x0 / 25.4 * 72, y0 / 25.4 * 72, x1 / 25.4 * 72, y1 / 25.4 * 72)
            clip = clip & page.rect
            pix = page.get_pixmap(dpi=dpi, clip=clip)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            sx = int(round(capture_shift[0] / 25.4 * dpi))
            sy = int(round(capture_shift[1] / 25.4 * dpi))
            if sx or sy:
                shifted = Image.new("RGB", img.size, "white")
                shifted.paste(img, (sx, sy))
                img = shifted
            w_mm, h_mm = (x1 - x0), (y1 - y0)
            captured = True
        else:
            pix = page.get_pixmap(dpi=dpi)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        pages.append({"img": img, "w_mm": w_mm, "h_mm": h_mm, "captured": captured,
                      "text": page.get_text() or ""})
    doc.close()
    return pages


def ink_bbox(img, white_threshold=250):
    """返回内容(非白)外接框 (x0, y0, x1, y1), 全白返回 None"""
    g = img.convert("L")
    bw = g.point(lambda v: 0 if v >= white_threshold else 255)
    return bw.getbbox()


def crop_to_content(img, pad_px, white_threshold=250):
    bb = ink_bbox(img, white_threshold)
    if not bb:
        return img
    x0, y0, x1, y1 = bb
    x0 = max(0, x0 - pad_px)
    y0 = max(0, y0 - pad_px)
    x1 = min(img.width, x1 + pad_px)
    y1 = min(img.height, y1 + pad_px)
    return img.crop((x0, y0, x1, y1))


def rotate_img(img, direction):
    """旋转 90°: cw=顺时针, ccw=逆时针"""
    return img.rotate(-90, expand=True) if direction == "cw" else img.rotate(90, expand=True)


def _aspect(img):
    lo, hi = min(img.width, img.height), max(img.width, img.height)
    return hi / lo if lo else 1.0


def compose_label(page_img, cfg):
    """把单页图像排成目标画布。
    - exact: 输入已近似为横版标签页面(宽高比>=3)则整页旋转
    - crop : 先裁剪内容再旋转
    - fit  : 缩放铺满(尽量保留原始比例)
    - auto : 宽高比>=3 走 exact, 否则走 crop
    返回 (canvas_img, info_dict)
    """
    pl = cfg["pipeline"]
    dpi = int(pl["render_dpi"])
    cw_mm, ch_mm = pl["canvas_mm"]
    cw_px = int(round(cw_mm / 25.4 * dpi))
    ch_px = int(round(ch_mm / 25.4 * dpi))
    mode = pl.get("mode", "auto")
    img = page_img
    cropped = False
    if mode == "crop":
        cropped = True
    elif mode == "auto":
        cropped = _aspect(page_img) < 3.0
    if cropped:
        pad_px = int(round(pl.get("crop_pad_mm", 0.5) / 25.4 * dpi))
        img = crop_to_content(img, pad_px, pl.get("crop_white", 250))
    img = rotate_img(img, pl.get("rotate_dir", "cw"))
    if mode == "fit":
        s = min(cw_px / img.width, ch_px / img.height)
        img = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.LANCZOS)
    canvas = Image.new("RGB", (cw_px, ch_px), "white")
    if img.width > cw_px or img.height > ch_px:
        # 不应发生(1:1 映射下会自动截掉超出的白边)
        pass
    ox = (cw_px - img.width) // 2
    oy = (ch_px - img.height) // 2
    align = pl.get("align", "center")
    if align == "top":
        oy = 0
    elif align == "bottom":
        oy = ch_px - img.height
    elif align == "left":
        ox = 0
    elif align == "right":
        ox = cw_px - img.width
    off_mm = pl.get("offset_mm", [0, 0])
    ox += int(round(off_mm[0] / 25.4 * dpi))
    oy += int(round(off_mm[1] / 25.4 * dpi))
    # 白色底 + 直接粘贴(允许负坐标, PIL 自动裁剪边界)
    canvas.paste(img, (ox, oy))
    info = {"cropped": cropped, "size": [img.width, img.height], "offset": [ox, oy]}
    return canvas, info
