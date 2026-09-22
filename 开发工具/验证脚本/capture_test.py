# -*- coding: utf-8 -*-
"""捕获速度压测：预热监视器 + 瞬间连发 3 个打印任务 x 3 轮，统计捕获到几个不同版本。"""
import os
import sys
import time
import hashlib
import threading
import subprocess

SRC = r'E:\软件开发\水洗唛打印助手\spool\vptest.pdf'
SNAP = r'E:\软件开发\水洗唛打印助手\spool\snap3'
os.makedirs(SNAP, exist_ok=True)
for f in os.listdir(SNAP):
    os.remove(os.path.join(SNAP, f))

captured = []
seen = set()
stop = False
lock = threading.Lock()


def watcher():
    while not stop:
        try:
            with open(SRC, 'rb') as fp:
                data = fp.read()
        except Exception:
            time.sleep(0.04)
            continue
        if data and data[:4] == b'%PDF' and b'%%EOF' in data[-4096:]:
            h = hashlib.sha256(data).hexdigest()[:12]
            with lock:
                if h not in seen:
                    seen.add(h)
                    p = os.path.join(SNAP, 'v_%02d_%s.pdf' % (len(captured) + 1, h))
                    with open(p, 'wb') as w:
                        w.write(data)
                    captured.append(p)
        time.sleep(0.04)


th = threading.Thread(target=watcher, daemon=True)
th.start()
time.sleep(0.6)  # 预热

for trial in range(1, 4):
    n0 = len(captured)
    cmd = (
        "& { 'JOB t%d A aaa111aaa111' | Out-Printer -Name 'VP-Test'; "
        "'JOB t%d B bbb222bbb222' | Out-Printer -Name 'VP-Test'; "
        "'JOB t%d C ccc333ccc333' | Out-Printer -Name 'VP-Test' }" % (trial, trial, trial)
    )
    subprocess.run(['powershell', '-NoProfile', '-Command', cmd], capture_output=True)
    deadline = time.time() + 15
    while time.time() < deadline:
        with lock:
            if len(captured) - n0 >= 3:
                break
        time.sleep(0.1)
    time.sleep(2.5)
    print('trial %d captured: %d / 3' % (trial, len(captured) - n0))

stop = True
time.sleep(0.3)
print('TOTAL captured: %d / 9' % len(captured))
print('files:')
for p in captured:
    print('  ', os.path.basename(p), os.path.getsize(p))
