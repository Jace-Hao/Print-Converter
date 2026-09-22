# -*- coding: utf-8 -*-
"""水洗唛打印助手 - 虚拟打印机"文件槽"捕获器

原理: 自建虚拟打印机(水洗唛打印助手)会把每次打印任务写成固定文件
      (spool/capture.pdf, 由文件端口实现)。文件名固定会导致连打时被快速覆盖,
      因此这里以高频轮询 + 完整性校验(%PDF 头 + %%EOF 尾) 第一时间把每个
      完整版本复制到 spool/jobs/, 再交给处理线程逐张转换/打印。
"""
import hashlib
import json
import os
import queue
import threading
import time


class SlotWatcher:
    def __init__(self, cfg, log, on_file):
        self.cfg = cfg
        self.log = log
        self.on_file = on_file
        c = cfg.get("capture") or {}
        self.enabled = bool(c.get("enabled", True))
        slot = c.get("slot_file", "spool\\capture.pdf")
        self.slot = slot if os.path.isabs(slot) else os.path.join(cfg.root, slot)
        self.poll = float(c.get("poll_seconds", 0.06))
        self.jobs_dir = os.path.join(cfg.root, "spool", "jobs")
        self.state_path = os.path.join(cfg.root, "out", "slot_state.json")
        self._last_hash = self._load_state()
        self._stop = False
        self._q = queue.Queue()
        self._captured = 0

    # ---------- 状态 ----------
    def _load_state(self):
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                return json.load(f).get("last_hash", "")
        except Exception:
            return ""

    def _save_state(self):
        try:
            os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump({"last_hash": self._last_hash,
                           "updated": time.strftime("%Y-%m-%d %H:%M:%S")},
                          f, ensure_ascii=False)
        except Exception as e:
            self.log.warning("捕获状态保存失败: %s", e)

    # ---------- 读取与捕获 ----------
    def _read(self):
        """返回完整 PDF 的 bytes; 文件缺失/未写完/被锁定 时返回 None"""
        try:
            with open(self.slot, "rb") as f:
                data = f.read()
        except Exception:
            return None
        if len(data) < 64 or not data.startswith(b"%PDF-"):
            return None
        if b"%%EOF" not in data[-4096:]:
            return None
        return data

    def _capture_once(self):
        data = self._read()
        if data is None:
            return False
        h = hashlib.sha1(data).hexdigest()
        if h == self._last_hash:
            return False
        os.makedirs(self.jobs_dir, exist_ok=True)
        name = time.strftime("capture_%Y%m%d-%H%M%S_") + h[:8] + ".pdf"
        dst = os.path.join(self.jobs_dir, name)
        try:
            with open(dst, "wb") as f:
                f.write(data)
        except Exception as e:
            self.log.warning("捕获文件写入失败: %s", e)
            return False
        self._last_hash = h
        self._save_state()
        self._captured += 1
        self.log.info("捕获到新的打印任务: %s (%d bytes)", name, len(data))
        self._q.put(dst)
        return True

    # ---------- 线程 ----------
    def _capture_loop(self):
        self.log.info("文件槽捕获启动: %s (poll=%.0fms)", self.slot, self.poll * 1000)
        while not self._stop:
            try:
                self._capture_once()
            except Exception as e:
                self.log.exception("捕获异常: %s", e)
            time.sleep(self.poll)

    def _process_loop(self):
        while not self._stop:
            try:
                item = self._q.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self.on_file(item)
            except Exception as e:
                self.log.exception("处理捕获任务失败: %s (%s)", item, e)

    def start(self):
        if not self.enabled:
            self.log.info("文件槽捕获未启用(capture.enabled=false)")
            return False
        threading.Thread(target=self._capture_loop, name="slot-capture", daemon=True).start()
        threading.Thread(target=self._process_loop, name="slot-process", daemon=True).start()
        return True

    def stop(self):
        self._stop = True

    @property
    def captured_count(self):
        return self._captured
