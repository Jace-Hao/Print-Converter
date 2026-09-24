# -*- coding: utf-8 -*-
"""旋转方向语义自检:
- cw  (顺时针): 原左上角内容转到右上角;
- ccw (逆时针): 原左上角内容转到左下角;
- compose_label 在两种方向下都输出 30x120mm 画布且方向按配置生效。
运行: python -X utf8 test_rotate_dir.py
"""
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from PIL import Image

from app.render import compose_label, rotate_img

RED = (255, 0, 0)
BLUE = (0, 0, 255)


def has_px(img, xy, color):
    try:
        return img.getpixel(xy) == color
    except Exception:
        return False


def make_strip():
    """40x10 横条, 四周红色描边(保证裁剪保留全图), 左上角蓝色标记用于判向"""
    img = Image.new("RGB", (40, 10), "white")
    for x in range(40):
        img.putpixel((x, 0), RED)
        img.putpixel((x, 9), RED)
    for y in range(10):
        img.putpixel((0, y), RED)
        img.putpixel((39, y), RED)
    img.putpixel((0, 0), BLUE)
    return img


def main():
    fails = []
    base = make_strip()

    cw = rotate_img(base, "cw")
    ccw = rotate_img(base, "ccw")
    if cw.size != (10, 40):
        fails.append("cw 尺寸错误: %s" % (cw.size,))
    if ccw.size != (10, 40):
        fails.append("ccw 尺寸错误: %s" % (ccw.size,))
    if not has_px(cw, (9, 0), BLUE):
        fails.append("cw 未把左上角内容转到右上角")
    if not has_px(ccw, (0, 39), BLUE):
        fails.append("ccw 未把左上角内容转到左下角")

    cfg = {"pipeline": {"mode": "crop", "rotate_dir": "cw", "canvas_mm": [30.0, 120.0],
                        "render_dpi": 300, "offset_mm": [0.0, 0.0], "crop_pad_mm": 0.5,
                        "crop_white": 250, "align": "center"}}
    cfg_ccw = copy.deepcopy(cfg)
    cfg_ccw["pipeline"]["rotate_dir"] = "ccw"

    c1, i1 = compose_label(base, cfg)
    c2, i2 = compose_label(base, cfg_ccw)
    if c1.size != (354, 1417):
        fails.append("画布尺寸错误: %s" % (c1.size,))
    if tuple(i1["size"]) != (10, 40) or tuple(i2["size"]) != (10, 40):
        fails.append("排版后内容尺寸错误: %s / %s" % (i1["size"], i2["size"]))
    # 居中粘贴原点: ox=(354-10)//2=172, oy=(1417-40)//2=688
    ox, oy = 172, 688
    if not has_px(c1, (ox + 9, oy), BLUE):
        fails.append("compose_label(cw) 标记不在右上位置")
    if not has_px(c2, (ox, oy + 39), BLUE):
        fails.append("compose_label(ccw) 标记不在左下位置")

    if fails:
        print("RESULT: FAIL")
        for f in fails:
            print(" -", f)
        return 1
    print("RESULT: PASS  (cw/ccw 旋转语义与 compose_label 行为均正确)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
