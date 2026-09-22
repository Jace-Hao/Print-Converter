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
        self._last_hash, self._last_mtime_ns = self._load_state()
        self._stop = False
        self._q = queue.Queue()
        self._captured = 0

    # ---------- 状态 ----------
    def _load_state(self):
        """返回 (last_hash, last_mtime_ns)；旧版状态文件可能没有 mtime 字段"""
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                d = json.load(f)
            return d.get("last_hash", ""), d.get("last_mtime_ns")
        except Exception:
            return "", None

    def _save_state(self):
        try:
            os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump({"last_hash": self._last_hash,
                           "last_mtime_ns": self._last_mtime_ns,
                           "updated": time.strftime("%Y-%m-%d %H:%M:%S")},
                          f, ensure_ascii=False)
        except Exception as e:
            self.log.warning("捕获状态保存失败: %s", e)

    # ---------- 读取与捕获 ----------
    def _read(self):
        """返回 (完整 PDF bytes, 文件 mtime_ns); 文件缺失/未写完/读取期间被改写时返回 None"""
        try:
            st1 = os.stat(self.slot)
            with open(self.slot, "rb") as f:
                data = f.read()
            st2 = os.stat(self.slot)
        except Exception:
            return None
        if st1.st_mtime_ns != st2.st_mtime_ns or st1.st_size != st2.st_size:
            return None  # 读取期间文件在变化, 等下一轮
        if len(data) < 64 or not data.startswith(b"%PDF-"):
            return None
        if b"%%EOF" not in data[-4096:]:
            return None
        return data, st2.st_mtime_ns

    def _capture_once(self):
        got = self._read()
        if got is None:
            return False
        data, mtime_ns = got
        h = hashlib.sha1(data).hexdigest()
        repeat = (h == self._last_hash)
        if repeat:
            if self._last_mtime_ns is None:
                # 旧版状态文件只有 hash：记下当前写入时间, 本次按同一版本跳过
                self._last_mtime_ns = mtime_ns
                self._save_state()
                return False
            if mtime_ns == self._last_mtime_ns:
                return False  # 同一版文件被重复读取(未发生新写入), 跳过
            # 内容与上一张相同、但发生了新的写入 -> 是复打(如一双鞋的第二张), 正常捕获
        os.makedirs(self.jobs_dir, exist_ok=True)
        name = time.strftime("capture_%Y%m%d-%H%M%S_") + h[:8] + ".pdf"
        dst = os.path.join(self.jobs_dir, name)
        n = 1
        while os.path.exists(dst):
            # 极端情况: 同一秒内同内容的第二笔(修复后才可能出现) -> 加序号避免覆盖
            name = "%s_%s_%02d.pdf" % (time.strftime("capture_%Y%m%d-%H%M%S"), h[:8], n)
            dst = os.path.join(self.jobs_dir, name)
            n += 1
        try:
            with open(dst, "wb") as f:
                f.write(data)
        except Exception as e:
            self.log.warning("捕获文件写入失败: %s", e)
            return False
        self._last_hash = h
        self._last_mtime_ns = mtime_ns
        self._save_state()
        self._captured += 1
        self.log.info("捕获到新的打印任务: %s (%d bytes%s)", name, len(data),
                      "，与上一张内容相同(复打)" if repeat else "")
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
