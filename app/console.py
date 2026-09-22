# -*- coding: utf-8 -*-
"""水洗唛打印助手 - 后台服务 + 操作页面（本地，单进程）

一个进程同时提供：
  1. 后台监视（watcher）：虚拟打印机捕获 → 转换 → 送印 → 归档；
  2. 本地操作页面：http://127.0.0.1:8787/（仅本机可访问，零外部依赖）；
  3. 每日清理：归档 / 预览超过保留天数(默认 7 天)的文件自动删除。

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
VERSION = "v2.1"

STATE = {}


def _setup():
    from app.config import Config
    from app.logutil import get_logger
    return Config(ROOT), get_logger(ROOT)


def _pythonw():
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
    if cache and now - cache[0] < 30:
        return cache[1]
    from app import vpinstall
    try:
        st = vpinstall.status()
    except Exception as e:
        st = {"error": str(e)}
    STATE["vp_cache"] = (now, st)
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
        "vprinter": {}, "capture": {}, "recent": [], "log_tail": [],
    }
    st["vprinter"] = _vp_status_cached()
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


def do_action(cfg, log, name, arg=None):
    from app import vpinstall
    if name == "calibrate":
        subprocess.Popen([_pythonw(), "-X", "utf8", "-m", "app.cli", "calibrate"],
                         cwd=ROOT, creationflags=CREATE_NO_WINDOW)
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
    if name == "vp_check":
        STATE["vp_cache"] = None
        return {"ok": True, "data": _vp_status_cached()}
    if name == "vp_install":
        cmd = os.path.join(ROOT, "安装虚拟打印机.cmd")
        if not os.path.exists(cmd):
            return {"ok": False, "msg": "未找到安装脚本"}
        os.startfile(cmd)
        return {"ok": True, "msg": "已请求安装/修复（请在弹出窗口确认管理员权限）"}
    return {"ok": False, "msg": "未知操作: %s" % name}


# ---------------- HTTP 服务 ----------------
def _page_path():
    return os.path.join(ROOT, "web", "操作页面.html")


def _make_handler():
    from http.server import BaseHTTPRequestHandler

    class Handler(BaseHTTPRequestHandler):
        server_version = "WashLabelConsole/2.1"

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
                    self._send(200, collect_status(STATE["cfg"]))
                else:
                    self._send(404, {"ok": False, "msg": "not found"})
            except Exception as e:
                self._send(500, {"ok": False, "msg": str(e)})

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
                self._send(500, {"ok": False, "msg": str(e)})

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
                         cwd=ROOT, creationflags=CREATE_NO_WINDOW)
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
