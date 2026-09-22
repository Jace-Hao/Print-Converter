# -*- coding: utf-8 -*-
"""阶段3联调: 安装虚拟打印机后的实况捕获测试 + 物理打印烟测。"""
import os
import shutil
import subprocess
import sys
import time

ROOT = r'E:\软件开发\水洗唛打印助手'
LAB = r'E:\软件开发\.cluster\wash-label\lab'
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from PIL import Image, ImageChops

from app.capture import SlotWatcher
from app.config import Config
from app.logutil import get_logger
from app.pipeline import process_pdf
from app.watcher import Watcher

cfg = Config(ROOT)
log = get_logger(ROOT)
w = Watcher(cfg, log)

captured = []
processed = []


def on_file(path):
    ok, why = w._validate(path)
    print('  [slot] %s validate=%s (%s)' % (os.path.basename(path), ok, why))
    captured.append(path)
    if ok:
        res = process_pdf(cfg, log, path, dry_run=True)
        processed.append((path, res))
        print('  [slot] preview:', res['labels'][0]['preview'])


print('== start slot watcher ==')
sw = SlotWatcher(cfg, log, on_file)
sw.start()
time.sleep(1.0)

print('== rapid triple print to 水洗唛打印助手 ==')
cmd = ("& { 'LIVE-T1 aaa111' | Out-Printer -Name '水洗唛打印助手'; "
       "'LIVE-T2 bbb222' | Out-Printer -Name '水洗唛打印助手'; "
       "'LIVE-T3 ccc333' | Out-Printer -Name '水洗唛打印助手' }")
subprocess.run(['powershell', '-NoProfile', '-Command', cmd], capture_output=True)
time.sleep(10)
print('  captured so far:', len(captured), ' processed:', len(processed))

print('== simulate realistic capture: copy mimic_a4.pdf onto slot ==')
slot = os.path.join(ROOT, 'spool', 'capture.pdf')
shutil.copyfile(os.path.join(LAB, 'mimic_a4.pdf'), slot)
time.sleep(8)
print('  captured total:', len(captured), ' processed total:', len(processed))

sw.stop()
time.sleep(0.5)

print('== results ==')
for p in captured:
    print('  captured:', os.path.basename(p))
for p, res in processed:
    lab = res['labels'][0]
    print('  processed: %s | captured=%s preview=%s' % (
        os.path.basename(p), lab.get('captured'), lab.get('preview')))

print('== physical print smoke (real capture copy -> GP-9134T) ==')
phys_src = os.path.join(LAB, 'phys_test_1.pdf')
shutil.copyfile(r'D:\水洗唛输出\spool.pdf', phys_src)
res_phys = process_pdf(cfg, log, phys_src, dry_run=False)
prev = res_phys['labels'][0]['preview']
print('  physical label done, preview:', prev)
g = Image.open(prev).convert('L')
bb = ImageChops.difference(g, Image.new('L', g.size, 255)).getbbox()
mm = lambda v: round(v / 300 * 25.4, 2)
print('  canvas ink bbox mm:', [mm(v) for v in bb] if bb else None)

print('LIVE TEST DONE')
