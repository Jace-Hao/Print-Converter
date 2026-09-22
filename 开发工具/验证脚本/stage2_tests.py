# -*- coding: utf-8 -*-
"""阶段2回归测试: 捕获页截取与版面对齐、校验逻辑、多页处理。"""
import os
import sys

ROOT = r'E:\软件开发\水洗唛打印助手'
SAMP = r'E:\软件开发\.cluster\wash-label\samples'
LAB = r'E:\软件开发\.cluster\wash-label\lab'
sys.path.insert(0, ROOT)

import pymupdf
from PIL import Image, ImageChops

from app.config import Config
from app.logutil import get_logger
from app.pipeline import process_pdf
from app.watcher import Watcher

cfg = Config(ROOT)
log = get_logger(ROOT)
w = Watcher(cfg, log)

print('== config ==')
print(' vprinter:', cfg.get('vprinter'))
print(' capture :', cfg.get('capture'))

# 1) 生成"虚拟打印机捕获页"（A4，内容按捕获特性左移 2.03mm）
src = os.path.join(SAMP, 'pf_20260922_single.pdf')
mimic_png = os.path.join(LAB, 'mimic_a4_canvas.png')
mimic_pdf = os.path.join(LAB, 'mimic_a4.pdf')
DPI = 300
pg = pymupdf.open(src)[0]
pix = pg.get_pixmap(dpi=DPI)
img = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
canvas = Image.new('RGB', (int(round(210 / 25.4 * DPI)), int(round(297 / 25.4 * DPI))), 'white')
canvas.paste(img, (-int(round(2.03 / 25.4 * DPI)), 0))
canvas.save(mimic_png)
doc2 = pymupdf.open()
p2 = doc2.new_page(width=210 / 25.4 * 72, height=297 / 25.4 * 72)
p2.insert_image(p2.rect, filename=mimic_png)
doc2.save(mimic_pdf)
doc2.close()
print('== mimic built ==', mimic_pdf, os.path.getsize(mimic_pdf))

# 2) 负样例: 内容超出版面的 A4(应被校验拦截)
neg_pdf = os.path.join(LAB, 'neg_page.pdf')
d3 = pymupdf.open()
p3 = d3.new_page(width=210 / 25.4 * 72, height=297 / 25.4 * 72)
p3.draw_rect(pymupdf.Rect(20, 20, 560, 800), width=3)
d3.save(neg_pdf)
d3.close()

print('== validate ==')
checks = [
    ('mimic_a4(捕获)', mimic_pdf, True),
    ('Dspool(真实捕获)', r'D:\水洗唛输出\spool.pdf', True),
    ('neg_page(干扰)', neg_pdf, False),
    ('pf_single(旧格式)', src, True),
    ('batch7(旧格式7页)', os.path.join(SAMP, 'pf_20260922_batch7.pdf'), True),
]
all_ok = True
for tag, path, want in checks:
    ok, why = w._validate(path)
    hit = (ok == want)
    all_ok = all_ok and hit
    print('  [%s] %s -> %s (%s)' % ('OK' if hit else 'FAIL', tag, ok, why))

# 3) 处理对比: 捕获页 vs 旧格式 => 预览应几乎一致
print('== process compare ==')
res_m = process_pdf(cfg, log, mimic_pdf, dry_run=True)
res_o = process_pdf(cfg, log, src, dry_run=True)
pm = res_m['labels'][0]['preview']
po = res_o['labels'][0]['preview']
print('  captured flag:', res_m['labels'][0].get('captured'))
a = Image.open(pm).convert('L')
b = Image.open(po).convert('L')
print('  preview sizes:', a.size, b.size)


def ink_px(im):
    bb = ImageChops.difference(im, Image.new('L', im.size, 255)).getbbox()
    return bb


if a.size == b.size:
    diff = ImageChops.difference(a, b)
    nz = sum(diff.histogram()[1:])
    total = a.size[0] * a.size[1]
    print('  diff pixels: %d / %d (%.3f%%) bbox=%s' % (nz, total, nz * 100.0 / total, diff.getbbox()))
    am, bm = ink_px(a), ink_px(b)
    print('  ink bbox mimic:', am, ' old:', bm)
    if am and bm:
        dev = max(abs(am[i] - bm[i]) for i in range(4))
        print('  ink bbox max deviation(px):', dev)
        all_ok = all_ok and dev <= 8
    all_ok = all_ok and (nz * 100.0 / total < 2.0)
    print('  mimic preview :', pm)
    print('  old   preview :', po)
else:
    all_ok = False

# 4) 真实捕获样例处理(仅信息)
print('== real capture dry-run ==')
res_d = process_pdf(cfg, log, r'D:\水洗唛输出\spool.pdf', dry_run=True)
pd_ = res_d['labels'][0]['preview']
print('  labels:', len(res_d['labels']), ' preview:', pd_, ' captured:', res_d['labels'][0].get('captured'))

# 5) 七页批量
print('== batch7 ==')
res_b = process_pdf(cfg, log, os.path.join(SAMP, 'pf_20260922_batch7.pdf'), dry_run=True)
print('  labels:', len(res_b['labels']))
all_ok = all_ok and len(res_b['labels']) == 7

print('== RESULT:', 'ALL OK' if all_ok else 'HAS FAILURES', '==')
