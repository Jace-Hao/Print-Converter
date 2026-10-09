# -*- coding: utf-8 -*-
"""水洗唛打印助手 - 后台服务 + 操作页面（本地，单进程）

一个进程同时提供：
  1. 后台监视（watcher）：虚拟打印机捕获 → 转换 → 送印 → 归档；
  2. 本地操作页面：http://127.0.0.1:8787/（仅本机可访问，零外部依赖）；
  3. 每日清理：归档 / 预览超过保留天数(默认 7 天)的文件自动删除。

状态检测：虚拟打印机（app.vpinstall）+ 本机目标打印机（app.printerstatus，佳博 GP-9134T）。

启动：pythonw -X utf8 -m app.console run   （后台静默运行，经「打开操作页面.cmd」拉起）
停止：结束该进程（见「停止软件.cmd」）
其它：python -m app.console status | url | open
  - status: 输出运行状态 JSON
  - url   : 确保已运行并输出访问地址（不打开浏览器）
  - open  : 确保已运行并打开浏览器访问操作页面
"""
import argparse
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import webbrowser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

BASE_PORT = 8787
PORT_TRIES = 10
CREATE_NO_WINDOW = 0x08000000
APP_TITLE = "水洗唛打印助手"
VERSION = "v2.2"

VP_CACHE_TTL = 30        # 虚拟打印机状态缓存秒数
PRINTER_CACHE_TTL = 15   # 本机打印机状态缓存秒数（出纸状态变化快，缓存短一些）
SKIP_KW_MAX_LEN = 30     # 单个不打印关键词最大字符数
SKIP_KW_MAX_COUNT = 50   # 不打印关键词最多条数

STATE = {}


def _setup():
    from app.config import Config
    from app.logutil import get_logger
    return Config(ROOT), get_logger(ROOT)


def _pythonw():
    # 安装版优先用随附运行时；否则用当前解释器同目录 / 本机 Python
    root_pw = os.path.join(ROOT, "runtime", "pythonw.exe")
    if os.path.exists(root_pw):
        return root_pw
    exe = sys.executable or ""
    pw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if not os.path.exists(pw):
        pw = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Python", "bin", "pythonw.exe")
    return pw


def _ping_port(port, timeout=0.25):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as s:
            s.sendall(b"GET /api/ping HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
            data = s.recv(256)
            return b" 200 " in data or b'"ok": true' in data
    except Exception:
        return False


def find_instance():
    """返回正在运行实例的端口号；未运行返回 None"""
    for p in range(BASE_PORT, BASE_PORT + PORT_TRIES):
        if _ping_port(p):
            return p
    return None


def instance_running():
    return find_instance() is not None


# ---------------- 状态与操作 ----------------
def _vp_status_cached():
    now = time.time()
    cache = STATE.get("vp_cache")
    if cache and now - cache[0] < VP_CACHE_TTL:
        return cache[1]
    from app import vpinstall
    try:
        st = vpinstall.status()
    except Exception as e:
        st = {"error": str(e)}
    STATE["vp_cache"] = (now, st)
    return st


def _printer_status_cached(cfg):
    """本机目标打印机状态（短 TTL 缓存；手动检测时清空缓存强制刷新）"""
    now = time.time()
    cache = STATE.get("printer_cache")
    if cache and now - cache[0] < PRINTER_CACHE_TTL:
        return cache[1]
    from app import printerstatus
    try:
        st = printerstatus.status(cfg)
    except Exception as e:
        st = {"error": str(e), "level": "error", "ok": False,
              "name": printerstatus.target_name(cfg), "installed": False,
              "status_text": "检测失败", "jobs": 0, "port": "", "driver": "",
              "checked_at": time.strftime("%H:%M:%S")}
    STATE["printer_cache"] = (now, st)
    return st


def collect_status(cfg):
    st = {
        "ok": True, "app": APP_TITLE, "version": VERSION,
        "now": time.strftime("%Y-%m-%d %H:%M:%S"),
        "started": STATE.get("started", ""),
        "port": STATE.get("port"),
        "pid": os.getpid(),
        "watcher": {
            "alive": bool(STATE.get("watcher") is not None),
            "dirs": list(cfg["watch"]["dirs"]),
        },
        "vprinter": {}, "printer": {}, "capture": {}, "recent": [], "log_tail": [],
        "config_error": getattr(cfg, "load_error", "") or "",
        "skip_print": {"enabled": True, "keywords": []},
    }
    try:
        sp = cfg.get("skip_print") or {}
        kws = [str(k) for k in (sp.get("keywords") or []) if str(k)]
        st["skip_print"] = {"enabled": bool(sp.get("enabled", True)), "keywords": kws}
    except Exception:
        pass
    st["rotate_dir"] = (cfg.get("pipeline") or {}).get("rotate_dir", "cw")
    st["vprinter"] = _vp_status_cached()
    try:
        st["printer"] = _printer_status_cached(cfg)
    except Exception as e:
        st["printer"] = {"error": str(e), "level": "error", "ok": False,
                         "name": "", "installed": False, "status_text": "检测失败"}
    try:
        slot = (cfg.get("capture") or {}).get("slot_file", "spool\\capture.pdf")
        slotp = slot if os.path.isabs(slot) else os.path.join(cfg.root, slot)
        if os.path.exists(slotp):
            m = os.path.getmtime(slotp)
            st["capture"] = {
                "exists": True, "size": os.path.getsize(slotp),
                "mtime": time.strftime("%m-%d %H:%M:%S", time.localtime(m)),
                "age_s": int(time.time() - m),
            }
        else:
            st["capture"] = {"exists": False}
    except Exception as e:
        st["capture"] = {"error": str(e)}
    try:
        arch = cfg.path_of("archive")
        if os.path.isdir(arch):
            files = [os.path.join(arch, f) for f in os.listdir(arch) if f.lower().endswith(".pdf")]
            files.sort(key=os.path.getmtime, reverse=True)
            st["recent"] = [{
                "name": os.path.basename(f),
                "time": time.strftime("%m-%d %H:%M:%S", time.localtime(os.path.getmtime(f))),
            } for f in files[:8]]
    except Exception:
        pass
    try:
        logf = os.path.join(cfg.path_of("logs"), time.strftime("%Y-%m-%d") + ".log")
        if os.path.exists(logf):
            with open(logf, "r", encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()
            st["log_tail"] = [ln.rstrip("\r\n") for ln in lines[-12:]]
    except Exception:
        pass
    return st


def _skip_section(cfg):
    """取 cfg 中的 skip_print 段（就地保证结构完整，使内存配置即时生效）。"""
    sp = cfg.data.get("skip_print")
    if not isinstance(sp, dict):
        sp = {}
        cfg.data["skip_print"] = sp
    kws = sp.get("keywords")
    if not isinstance(kws, list):
        kws = []
        sp["keywords"] = kws
    sp["enabled"] = bool(sp.get("enabled", True))
    return sp, kws


def _skip_snapshot(cfg):
    sp, kws = _skip_section(cfg)
    return {"enabled": bool(sp.get("enabled", True)),
            "keywords": [str(k) for k in kws]}


def _norm_keyword(raw):
    """规范化关键词：去首尾空白、去内部所有空白字符。"""
    return re.sub(r"\s+", "", str(raw if raw is not None else ""))


def _skip_save(cfg, sp, backup):
    """写回 config.json；失败时把内存值回滚为 backup。返回 (ok, err)。"""
    try:
        cfg.save()
        return True, ""
    except Exception as e:
        sp["enabled"] = backup["enabled"]
        sp["keywords"] = list(backup["keywords"])
        return False, str(e)


def do_action(cfg, log, name, arg=None):
    from app import vpinstall
    if name == "calibrate":
        subprocess.Popen([_pythonw(), "-X", "utf8", "-m", "app.cli", "calibrate"],
                         cwd=ROOT, creationflags=CREATE_NO_WINDOW,
                         stdin=subprocess.DEVNULL)
        return {"ok": True, "msg": "已发送校准唛打印（两版，约 5 秒内出纸）"}
    if name == "open_dir":
        targets = {
            "root": ROOT,
            "archive": cfg.path_of("archive"),
            "previews": cfg.path_of("previews"),
            "logs": cfg.path_of("logs"),
            "spool": os.path.join(ROOT, "spool"),
            "inbox": cfg.path_of("inbox"),
        }
        p = targets.get(str(arg or ""))
        if not p:
            return {"ok": False, "msg": "未知目录: %s" % arg}
        os.makedirs(p, exist_ok=True)
        os.startfile(p)
        return {"ok": True, "msg": "已打开目录"}
    if name == "set_rotate":
        d = str(arg or "").strip().lower()
        if d not in ("cw", "ccw"):
            return {"ok": False, "msg": "无效方向: %s（仅支持 cw / ccw）" % arg}
        pl = cfg["pipeline"]
        old = pl.get("rotate_dir", "cw")
        pl["rotate_dir"] = d
        try:
            cfg.save()
        except Exception as e:
            pl["rotate_dir"] = old
            return {"ok": False, "msg": "保存配置失败，已保持原方向: %s" % e}
        log.info("打印方向已切换: %s -> %s（即时生效）",
                 "顺时针" if old == "cw" else "逆时针",
                 "顺时针" if d == "cw" else "逆时针")
        return {"ok": True, "rotate_dir": d,
                "msg": "已切换为%s，立即生效（下一条标签按新方向打印）" % ("顺时针" if d == "cw" else "逆时针")}
    if name == "vp_check":
        STATE["vp_cache"] = None
        return {"ok": True, "data": _vp_status_cached()}
    if name == "printer_check":
        STATE["printer_cache"] = None
        data = _printer_status_cached(cfg)
        return {"ok": True, "data": data,
                "msg": "本机打印机「%s」：%s" % (data.get("name") or "?",
                                          data.get("status_text") or "未知状态")}
    if name == "skip_toggle":
        sp, _kws = _skip_section(cfg)
        backup = {"enabled": bool(sp.get("enabled", True)),
                  "keywords": list(sp.get("keywords") or [])}
        sp["enabled"] = not backup["enabled"]
        ok, err = _skip_save(cfg, sp, backup)
        if not ok:
            return {"ok": False, "msg": "保存配置失败，已保持原状态: %s" % err}
        log.info("关键词排除打印已%s（即时生效）", "启用" if sp["enabled"] else "停用")
        return {"ok": True, "data": _skip_snapshot(cfg),
                "msg": "关键词排除打印已%s，立即生效" % ("启用" if sp["enabled"] else "停用")}
    if name == "skip_add":
        kw = _norm_keyword(arg)
        if not kw:
            return {"ok": False, "msg": "请输入关键词（不能为空或全是空格）"}
        if len(kw) > SKIP_KW_MAX_LEN:
            return {"ok": False, "msg": "关键词过长：最多 %d 个字符（当前 %d 个）"
                                        % (SKIP_KW_MAX_LEN, len(kw))}
        sp, kws = _skip_section(cfg)
        backup = {"enabled": bool(sp.get("enabled", True)), "keywords": list(kws)}
        if any(str(k) == kw for k in kws):
            return {"ok": False, "msg": "关键词「%s」已在列表中" % kw}
        if len(kws) >= SKIP_KW_MAX_COUNT:
            return {"ok": False, "msg": "关键词最多 %d 条，请先删除不再需要的条目"
                                        % SKIP_KW_MAX_COUNT}
        kws.append(kw)
        ok, err = _skip_save(cfg, sp, backup)
        if not ok:
            return {"ok": False, "msg": "保存配置失败，已撤销添加: %s" % err}
        log.info("新增不打印关键词「%s」（即时生效，共 %d 条）", kw, len(kws))
        return {"ok": True, "data": _skip_snapshot(cfg),
                "msg": "已添加「%s」，立即生效" % kw}
    if name == "skip_del":
        kw = _norm_keyword(arg)
        if not kw:
            return {"ok": False, "msg": "要删除的关键词为空"}
        sp, kws = _skip_section(cfg)
        backup = {"enabled": bool(sp.get("enabled", True)), "keywords": list(kws)}
        hit = next((k for k in kws if str(k) == kw), None)
        if hit is None:
            return {"ok": False, "msg": "未找到关键词「%s」" % kw}
        kws.remove(hit)
        ok, err = _skip_save(cfg, sp, backup)
        if not ok:
            return {"ok": False, "msg": "保存配置失败，已撤销删除: %s" % err}
        log.info("移除不打印关键词「%s」（即时生效，剩余 %d 条）", kw, len(kws))
        return {"ok": True, "data": _skip_snapshot(cfg),
                "msg": "已删除「%s」，立即生效" % kw}
    if name == "vp_install":
        cmd = os.path.join(ROOT, "安装虚拟打印机.cmd")
        if not os.path.exists(cmd):
            return {"ok": False, "msg": "未找到安装脚本"}
        os.startfile(cmd)
        return {"ok": True, "msg": "已请求安装/修复（请在弹出窗口确认管理员权限）"}
    return {"ok": False, "msg": "未知操作: %s" % name}


# ---------------- HTTP 服务 ----------------
def safe_status():
    """/api/status 的总兜底：任一段取状态失败都只降级，绝不返回 500。"""
    try:
        return collect_status(STATE["cfg"])
    except Exception as e:
        return {
            "ok": False, "app": APP_TITLE, "version": VERSION,
            "now": time.strftime("%Y-%m-%d %H:%M:%S"),
            "started": STATE.get("started", ""), "port": STATE.get("port"),
            "pid": os.getpid(),
            "watcher": {"alive": bool(STATE.get("watcher") is not None), "dirs": []},
            "vprinter": {}, "printer": {"error": str(e), "level": "error", "ok": False,
                                        "name": "", "installed": False, "status_text": "检测失败"},
            "capture": {}, "recent": [], "log_tail": [],
            "config_error": "读取运行状态失败: %s" % e,
            "skip_print": {"enabled": True, "keywords": []},
            "error": str(e),
        }


def _page_path():
    return os.path.join(ROOT, "web", "操作页面.html")


def _make_handler():
    from http.server import BaseHTTPRequestHandler

    class Handler(BaseHTTPRequestHandler):
        server_version = "WashLabelConsole/2.2"

        def log_message(self, *a):
            pass

        def _send(self, code, payload, ctype="application/json; charset=utf-8"):
            if isinstance(payload, (dict, list)):
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            elif isinstance(payload, str):
                body = payload.encode("utf-8")
            else:
                body = payload
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(body)
            except Exception:
                pass

        def do_GET(self):
            try:
                if self.path in ("/", "/index.html"):
                    p = _page_path()
                    if os.path.exists(p):
                        with open(p, "rb") as fh:
                            self._send(200, fh.read(), "text/html; charset=utf-8")
                    else:
                        self._send(500, "操作页面文件缺失: " + p, "text/plain; charset=utf-8")
                elif self.path == "/api/ping":
                    self._send(200, {"ok": True})
                elif self.path == "/api/status":
                    self._send(200, safe_status())
                else:
                    self._send(404, {"ok": False, "msg": "not found"})
            except Exception as e:
                self._send(200, {"ok": False, "app": APP_TITLE, "version": VERSION,
                                 "error": str(e), "recent": [], "log_tail": []})

        def do_POST(self):
            try:
                if self.path != "/api/action":
                    self._send(404, {"ok": False, "msg": "not found"})
                    return
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n) if n else b"{}"
                try:
                    data = json.loads(raw.decode("utf-8") or "{}")
                except Exception:
                    data = {}
                res = do_action(STATE["cfg"], STATE["log"], str(data.get("name")), data.get("arg"))
                self._send(200, res)
            except Exception as e:
                # 操作失败也要回 200 + 中文提示，页面才能正常弹 toast
                self._send(200, {"ok": False, "msg": "操作失败: %s" % e})

    return Handler


# ---------------- 运行 ----------------
def _daily_cleanup_loop(cfg, log):
    """每日清理线程: 启动时先执行一次, 之后每天(日期变化)执行一次"""
    last = None
    while True:
        today = time.strftime("%Y-%m-%d")
        if today != last:
            try:
                from app import retention
                retention.cleanup(cfg, log)
            except Exception as e:
                log.warning("每日清理异常: %s", e)
            last = today
        time.sleep(600)


def run(argv=None):
    cfg, log = _setup()
    if getattr(cfg, "load_error", ""):
        # 配置损坏也不能阻止启动：仅告警，服务与状态检测照常
        log.warning("配置回退: %s", cfg.load_error)
    existing = find_instance()
    if existing:
        log.info("软件已在运行（端口 %s），本次启动被忽略。", existing)
        return 0
    from http.server import ThreadingHTTPServer
    server = None
    port = None
    for p in range(BASE_PORT, BASE_PORT + PORT_TRIES):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", p), _make_handler())
            port = p
            break
        except OSError:
            continue
    if server is None:
        log.error("无法绑定本地端口（%d-%d 均被占用）", BASE_PORT, BASE_PORT + PORT_TRIES - 1)
        return 3
    from app.watcher import Watcher
    watcher = Watcher(cfg, log)
    STATE.update({"cfg": cfg, "log": log, "port": port, "watcher": watcher,
                  "started": time.strftime("%Y-%m-%d %H:%M:%S")})
    threading.Thread(target=watcher.run, name="watcher", daemon=True).start()
    threading.Thread(target=_daily_cleanup_loop, args=(cfg, log), name="daily-cleanup", daemon=True).start()
    log.info("软件已启动（后台运行）。操作页面: http://127.0.0.1:%d/", port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        watcher.stop()
        server.server_close()
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="水洗唛打印助手(后台服务)")
    ap.add_argument("cmd", nargs="?", default="status",
                    choices=["run", "status", "url", "open"])
    args = ap.parse_args(argv)
    if args.cmd == "run":
        return run()
    p = find_instance()
    if args.cmd == "status":
        if p:
            print(json.dumps({"running": True, "port": p, "url": "http://127.0.0.1:%d/" % p},
                             ensure_ascii=False))
            return 0
        print(json.dumps({"running": False}, ensure_ascii=False))
        return 1
    # url / open：确保后台服务在运行
    if not p:
        subprocess.Popen([_pythonw(), "-X", "utf8", "-m", "app.console", "run"],
                         cwd=ROOT, creationflags=CREATE_NO_WINDOW,
                         stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):
            time.sleep(0.4)
            p = find_instance()
            if p:
                break
    if not p:
        print("启动失败：请检查是否被安全软件拦截。")
        return 2
    url = "http://127.0.0.1:%d/" % p
    if args.cmd == "open":
        webbrowser.open(url)
    print(url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
