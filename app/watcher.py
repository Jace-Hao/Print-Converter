# -*- coding: utf-8 -*-
"""水洗唛打印助手 - 目录监视: 捕获自动保存/落入目录的标签 PDF 并处理"""
import fnmatch
import json
import os
import time

from .pipeline import process_pdf


class Watcher:
    def __init__(self, cfg, log):
        self.cfg = cfg
        self.log = log
        self.state_path = os.path.join(cfg.root, "out", "state.json")
        self.pending = {}
        self.processed = {}
        self._load()

    # ---------- 状态 ----------
    def _load(self):
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                self.processed = json.load(f).get("processed", {})
        except Exception:
            self.processed = {}

    def _save(self):
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        try:
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump({"processed": self.processed}, f, ensure_ascii=False, indent=1)
        except Exception as e:
            self.log.warning("状态保存失败: %s", e)

    # ---------- 扫描 ----------
    def _signature(self, path):
        try:
            st = os.stat(path)
            return "%s:%s" % (st.st_size, int(st.st_mtime))
        except OSError:
            return None

    def _iter_candidates(self):
        w = self.cfg["watch"]
        ignores = [x.lower() for x in w.get("ignore_names", [])]
        for d in w["dirs"]:
            if not os.path.isdir(d):
                continue
            try:
                names = os.listdir(d)
            except OSError:
                continue
            for name in names:
                low = name.lower()
                if not fnmatch.fnmatch(low, w["pattern"].lower()):
                    continue
                if low in ignores:
                    continue
                yield os.path.join(d, name)

    def _stable(self, path):
        need = float(self.cfg["watch"].get("stable_seconds", 8))
        try:
            st = os.stat(path)
            if st.st_size <= 0:
                return False
            with open(path, "rb") as f:
                f.read(8)
        except Exception:
            return False
        key = (st.st_size, int(st.st_mtime))
        rec = self.pending.get(path)
        now = time.time()
        if not rec or rec["key"] != key:
            self.pending[path] = {"key": key, "since": now}
            return False
        return (now - rec["since"]) >= need

    # ---------- 校验(防止误打印非标签内容) ----------
    def _validate(self, path):
        v = self.cfg.get("validate") or {}
        if not v.get("enabled", True):
            return True, "validate off"
        try:
            import pymupdf
            doc = pymupdf.open(path)
            n = len(doc)
            if n < 1:
                doc.close()
                return False, "无页面"
            r = doc[0].rect
            w_mm = r.width / 72.0 * 25.4
            h_mm = r.height / 72.0 * 25.4
            doc.close()
        except Exception as e:
            return False, "无法解析: %s" % e
        lo, hi = min(w_mm, h_mm), max(w_mm, h_mm)
        ar = (hi / lo) if lo else 0
        ar_lo, ar_hi = v.get("aspect_range", [3.2, 4.6])
        tol = float(v.get("size_tol_mm", 3.0))
        cw, ch = self.cfg["pipeline"]["canvas_mm"]
        tw, th = min(cw, ch), max(cw, ch)
        ok = (ar_lo <= ar <= ar_hi) and (abs(lo - tw) <= tol) and (abs(hi - th) <= tol * 2.0)
        return ok, "%.1fx%.1fmm ar=%.2f" % (w_mm, h_mm, ar)

    # ---------- 处理 ----------
    def _hold(self, path, why):
        hold_dir = os.path.join(self.cfg.root, "out", "hold")
        os.makedirs(hold_dir, exist_ok=True)
        base = os.path.basename(path)
        dst = os.path.join(hold_dir, time.strftime("%Y%m%d-%H%M%S_") + base)
        try:
            os.rename(path, dst)
            self.log.warning("文件未通过标签校验(%s), 已移入待处理区: %s", why, dst)
        except Exception as e:
            self.log.warning("移入待处理区失败(%s): %s", why, e)

    def _maybe_close_windows(self):
        if not self.cfg["automation"].get("close_pdffactory_window", True):
            return
        try:
            import win32con
            import win32gui

            def cb(h, _):
                if win32gui.IsWindowVisible(h):
                    t = win32gui.GetWindowText(h)
                    if t and "pdfFactory" in t:
                        win32gui.PostMessage(h, win32con.WM_CLOSE, 0, 0)
                        self.log.info("已关闭 pdfFactory 窗口: %s", t)
                return True

            win32gui.EnumWindows(cb, None)
        except Exception as e:
            self.log.debug("窗口关闭跳过: %s", e)

    def scan_once(self):
        acted = 0
        for path in list(self._iter_candidates()):
            sig = self._signature(path)
            if sig and self.processed.get(path) == sig:
                continue
            if not self._stable(path):
                continue
            ok, why = self._validate(path)
            if not ok:
                self.pending.pop(path, None)
                self._hold(path, why)
                continue
            dry = self.cfg["automation"].get("mode") == "dry_run"
            try:
                res = process_pdf(self.cfg, self.log, path, dry_run=dry)
                self.processed[path] = sig or "done"
                self.pending.pop(path, None)
                acted += 1
                self._maybe_close_windows()
                self.log.info("完成: %s -> %s 个标签", os.path.basename(path), len(res.get("labels", [])))
            except Exception as e:
                self.log.exception("处理失败 %s: %s", path, e)
        if acted:
            self._save()
        return acted

    def run(self, once=False):
        self.log.info("监视启动: %s", " , ".join(self.cfg["watch"]["dirs"]))
        while True:
            try:
                self.scan_once()
            except Exception as e:
                self.log.exception("扫描异常: %s", e)
            if once:
                return
            time.sleep(float(self.cfg["watch"].get("poll_seconds", 1.5)))
