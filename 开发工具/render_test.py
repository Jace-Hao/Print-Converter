#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""水洗唛版面实验室: PDF -> 分析/裁剪/旋转 -> 合成 30x120mm@300dpi 预览
用法: python 开发工具\\render_test.py <input.pdf> [outdir]
产物: info.json + pN_crop.png + pN_rot_cw/ccw.png + pN_compose_cw/ccw.png + pN_full_rot_cw/ccw.png
"""
import sys, os, json
import pymupdf as fitz
from PIL import Image, ImageChops

TARGET_W_MM, TARGET_H_MM, DPI = 30.0, 120.0, 300
CANVAS_W = int(round(TARGET_W_MM / 25.4 * DPI))   # 354
CANVAS_H = int(round(TARGET_H_MM / 25.4 * DPI))   # 1417


def contain_fit(img, cw, ch):
    """缩放到完整放入 cw x ch 并居中, 返回 (canvas, scale, offsets)"""
    s = min(cw / img.width, ch / img.height)
    nw, nh = max(1, int(round(img.width * s))), max(1, int(round(img.height * s)))
    im2 = img.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGB", (cw, ch), "white")
    ox, oy = (cw - nw) // 2, (ch - nh) // 2
    canvas.paste(im2, (ox, oy))
    return canvas, s, (ox, oy)


def ink_bbox(img):
    g = img.convert("L")
    bg = Image.new("L", g.size, 255)
    return ImageChops.difference(g, bg).getbbox()


def analyze(pdf_path, outdir):
    os.makedirs(outdir, exist_ok=True)
    doc = fitz.open(pdf_path)
    res = {"file": pdf_path, "pages": len(doc), "target_mm": [TARGET_W_MM, TARGET_H_MM],
           "canvas_px": [CANVAS_W, CANVAS_H], "items": []}
    for i, page in enumerate(doc):
        item = {"page": i, "rect_pt": [round(float(x), 2) for x in page.rect],
                "rect_mm": [round(float(page.rect.width) / 72 * 25.4, 2),
                            round(float(page.rect.height) / 72 * 25.4, 2)],
                "rotation": page.rotation}
        pix = page.get_pixmap(dpi=200)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        item["render200"] = [img.width, img.height]
        # 全页旋转变体
        for rot, tag in [(-90, "cw"), (90, "ccw")]:
            img.rotate(rot, expand=True).save(os.path.join(outdir, f"p{i}_full_rot_{tag}.png"))
        bb = ink_bbox(img)
        item["ink_bbox_px200"] = list(bb) if bb else None
        if bb:
            mm = lambda px: round(px / 200 * 25.4, 2)
            item["ink_mm"] = [mm(bb[2] - bb[0]), mm(bb[3] - bb[1])]
            crop = img.crop(bb)
            crop.save(os.path.join(outdir, f"p{i}_crop.png"))
            for rot, tag in [(-90, "cw"), (90, "ccw")]:
                r = crop.rotate(rot, expand=True)
                r.save(os.path.join(outdir, f"p{i}_rot_{tag}.png"))
                canvas, s, off = contain_fit(r, CANVAS_W, CANVAS_H)
                canvas.save(os.path.join(outdir, f"p{i}_compose_{tag}.png"))
                item[f"compose_{tag}"] = {"scale": round(s, 4), "offset_px": list(off)}
        res["items"].append(item)
    with open(os.path.join(outdir, "info.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    pdf = sys.argv[1]
    outdir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(pdf), "lab_out")
    analyze(pdf, outdir)
