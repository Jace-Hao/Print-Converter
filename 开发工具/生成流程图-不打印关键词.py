# -*- coding: utf-8 -*-
"""生成「不打印关键词」判定流程图（供使用说明与交付物使用）。"""
import math, os
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "不打印关键词判定流程.png")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

W, H = 1600, 680
img = Image.new("RGB", (W, H), "#F8FAFC")
d = ImageDraw.Draw(img)

def F(size, bold=False):
    p = r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc"
    return ImageFont.truetype(p, size)

def ctext(box, lines, f, fill):
    x0, y0, x1, y1 = box
    lh = f.size * 1.45
    total = lh * len(lines)
    cy = (y0 + y1) / 2 - total / 2 + lh / 2
    for i, t in enumerate(lines):
        d.text(((x0 + x1) / 2, cy + i * lh), t, font=f, fill=fill, anchor="mm")

def box(x, y, w, h, fill, outline, lw=3, r=18):
    d.rounded_rectangle([x, y, x + w, y + h], radius=r, fill=fill, outline=outline, width=lw)
    return (x, y, x + w, y + h)

def arrow(x1, y1, x2, y2, color="#64748B", w=3, head=15):
    d.line([x1, y1, x2, y2], fill=color, width=w)
    ang = math.atan2(y2 - y1, x2 - x1)
    for da in (math.radians(150), math.radians(-150)):
        d.line([x2, y2, x2 + head * math.cos(ang + da), y2 + head * math.sin(ang + da)], fill=color, width=w)

d.text((60, 38), "不打印关键词 · 处理流程", font=F(46, True), fill="#0F172A")
d.text((60, 104), "命中「布草 / 洗涤服务 / 窗帘 / 窗纱」的标签自动跳过打印，其余照常打印", font=F(24), fill="#475569")

f24 = F(25)
b1 = box(60, 280, 240, 110, "#FFFFFF", "#CBD5E1");  ctext(b1, ["洗衣管家", "打印水洗唛"], f24, "#0F172A")
b2 = box(360, 280, 240, 110, "#FFFFFF", "#CBD5E1"); ctext(b2, ["虚拟打印机", "自动捕获"], f24, "#0F172A")
b3 = box(660, 280, 240, 110, "#FFFFFF", "#CBD5E1"); ctext(b3, ["识别标签文字"], f24, "#0F172A")
b4 = box(960, 280, 260, 110, "#FFF7ED", "#FDBA74"); ctext(b4, ["命中关键词？"], f24, "#9A3412")
arrow(300, 335, 355, 335)
arrow(600, 335, 655, 335)
arrow(900, 335, 955, 335)

d.line([1220, 335, 1250, 335], fill="#64748B", width=3)
d.line([1250, 195, 1250, 415], fill="#64748B", width=3)
arrow(1250, 195, 1288, 195)
arrow(1250, 415, 1288, 415)
f22 = F(23)
bu = box(1290, 140, 290, 110, "#FFFBEB", "#F59E0B"); ctext(bu, ["命中 → 跳过打印", "（仍保留归档与预览）"], f22, "#92400E")
bl = box(1290, 360, 290, 110, "#F0FDF4", "#4ADE80"); ctext(bl, ["未命中 → 正常打印", "（佳博 30×120mm）"], f22, "#166534")
d.text((1270, 168), "命中", font=F(21), fill="#B45309", anchor="mm")
d.text((1270, 442), "未命中", font=F(21), fill="#15803D", anchor="mm")

f24b = F(24)
d.text((60, 508), "• 命中：跳过打印、不出纸；归档与预览照常保留，日志注明「命中不打印关键词」", font=f24b, fill="#475569")
d.text((60, 554), "• 关键词可在 config.json → skip_print 调整（默认：布草 / 洗涤服务 / 窗帘 / 窗纱）", font=f24b, fill="#475569")
d.text((60, 600), "• 按「张」判断：同一批里命中的张跳过，其余照常打印", font=f24b, fill="#475569")

img.save(OUT)
print("saved:", OUT, os.path.getsize(OUT), "bytes")
