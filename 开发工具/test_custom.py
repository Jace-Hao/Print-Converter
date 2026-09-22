# -*- coding: utf-8 -*-
"""自定义标签链路自测：模拟打印 PDF -> 字段识别 -> 版面渲染 -> 干跑打印（不实际出纸）。

用法（仓库根目录运行）：
    python 开发工具\\test_custom.py

可选：设置环境变量 WASH_LABEL_SAMPLE 指向一张真实水洗唛 PDF，额外验证真实样例识别。
"""
import os
import sys
import tempfile

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJ)

import pymupdf
from PIL import Image

from app.config import Config
from app.labelgen import print_custom_label, render_label
from app.logutil import get_logger
from app.recognize import recognize_fields

LAB = os.path.join(tempfile.gettempdir(), "wash-label-lab")
os.makedirs(LAB, exist_ok=True)
BC = "1100000" + "9" * 5

doc = pymupdf.open()
page = doc.new_page(width=120 / 25.4 * 72, height=30 / 25.4 * 72)
html = (
    "<div style=\"font-family:Microsoft YaHei;font-size:8pt;line-height:1.6\">"
    "POLO衫 白色 水洗<br>"
    "电：13800000000 张伟 单：1100099999 件：1-2<br>"
    "下单：09-22 品牌：POLO<br>"
    "损：轻微 服务：换拉链<br>"
    "星测洗衣<br>"
    + BC +
    "</div>"
)
rc = page.insert_htmlbox(pymupdf.Rect(6, 3, 334, 82), html)
print("htmlbox rc:", rc)
mimic = os.path.join(LAB, "mimic1.pdf")
doc.save(mimic)
doc.close()
print("mimic saved:", mimic)
print("mimic text:", repr(pymupdf.open(mimic)[0].get_text("text")))

f1 = recognize_fields(mimic)
print("mimic fields:", f1)
assert f1["单号"] == "1100099999", f1
assert f1["客户"] == "张伟", f1
assert f1["衣物名称"] == "POLO衫", f1
assert f1["颜色"] == "白色", f1
assert f1["工艺"] == "水洗", f1
assert f1["件数"] == "1-2", f1
assert f1["下单日期"] == "09-22", f1
assert f1["品牌"] == "POLO", f1
assert f1["损坏说明"] == "轻微", f1
assert f1["服务项目"] == "换拉链", f1
assert f1["门店名"] == "星测洗衣", f1
assert f1["条码号"] == BC, f1

real = os.environ.get("WASH_LABEL_SAMPLE", "")
if real and os.path.exists(real):
    f2 = recognize_fields(real)
    print("real fields:", f2)
    for k in ("衣物名称", "单号", "客户", "门店名", "条码号"):
        assert f2[k], (k, f2)
else:
    print("(跳过真实样例测试；可设置环境变量 WASH_LABEL_SAMPLE 指定一张真实水洗唛 PDF)")

cfg = Config(PROJ)
log = get_logger(PROJ)
img = render_label(f1, dpi=300)
out = os.path.join(LAB, "render1.png")
img.save(out)
print("render size:", img.size)
assert img.size == (1417, 354), img.size

g = Image.open(out).convert("L")
def dark(box):
    return sum(1 for p in g.crop(box).getdata() if p < 128)
left_dark = dark((20, 10, 900, 300))
bc_dark = dark((980, 140, 1400, 260))
mid_dark = dark((980, 55, 1400, 135))
print("left text dark px:", left_dark, "| barcode dark px:", bc_dark, "| mid strip:", mid_dark)
assert left_dark > 500, left_dark
assert bc_dark > 500, bc_dark

prev = print_custom_label(cfg, log, f1, dry_run=True)
print("dry-run preview:", prev)
assert os.path.exists(prev)

print("ALL OK")
