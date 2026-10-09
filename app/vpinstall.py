# -*- coding: utf-8 -*-
"""虚拟打印机管理: 创建/修复/移除 工具自建虚拟打印机(默认名: 水洗唛打印助手)。

实现: Microsoft Print To PDF 驱动 + 指向 spool\\capture.pdf 的"本地端口"(文件端口)。
打印任务会被静默写成 PDF 文件, 由工具的捕获器(app.capture)监视处理。
创建端口/打印机需要管理员权限。
"""
import ctypes
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.config import Config  # noqa: E402


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


CREATE_NO_WINDOW = 0x08000000  # 不弹出控制台窗口（Windows）


PS_TIMEOUT = 15  # PowerShell 单次调用最长等待秒数：打印后台处理程序/PowerShell 卡住时不拖死页面轮询


def _ps(cmd, check=True, timeout=PS_TIMEOUT):
    # stdin 显式置为 DEVNULL：pythonw 无控制台场景下子进程不会卡在等待输入
    try:
        p = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
             "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " + cmd],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            creationflags=CREATE_NO_WINDOW, stdin=subprocess.DEVNULL, timeout=timeout)
    except subprocess.TimeoutExpired:
        # 超时按失败处理：安装类调用抛错提示用户，状态检测类调用返回空串由调用方兜底
        if check:
            raise RuntimeError("PowerShell 命令超时（%d 秒未返回）: %s" % (timeout, cmd[:80]))
        return ""
    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()
    if check and p.returncode != 0:
        raise RuntimeError("PowerShell 命令失败(%d): %s" % (p.returncode, (err or out)))
    return out


def _q(s):
    return s.replace("'", "''")


def get_names():
    cfg = Config(ROOT)
    vp = cfg.get("vprinter") or {}
    cap = cfg.get("capture") or {}
    name = vp.get("name", "水洗唛打印助手")
    driver = vp.get("driver", "Microsoft Print To PDF")
    slot = cap.get("slot_file", "spool\\capture.pdf")
    if not os.path.isabs(slot):
        slot = os.path.join(ROOT, slot)
    return name, driver, os.path.normpath(slot)


def status():
    name, driver, port = get_names()
    cmd = ("[pscustomobject]@{"
           "port_ok=[bool](Get-PrinterPort -Name '%s' -ErrorAction SilentlyContinue); "
           "printer_ok=[bool](Get-Printer -Name '%s' -ErrorAction SilentlyContinue); "
           "driver_ok=[bool](Get-PrinterDriver -Name '%s' -ErrorAction SilentlyContinue)"
           " } | ConvertTo-Json -Compress") % (_q(port), _q(name), _q(driver))
    try:
        data = json.loads(_ps(cmd, check=False) or "{}")
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    if "port_ok" not in data:  # PowerShell 无返回 / 超时：标记出来，避免被当成"确实未安装"
        data["error"] = "虚拟打印机状态检测失败（PowerShell 无返回或超时 %d 秒）" % PS_TIMEOUT
    data.update({"name": name, "driver_name": driver, "port": port, "admin": is_admin()})
    return data


def install():
    name, driver, port = get_names()
    if not is_admin():
        print("[!] 需要管理员权限。请使用「安装虚拟打印机.cmd」(会自动请求提升)。")
        return 2
    os.makedirs(os.path.dirname(port), exist_ok=True)
    if _ps("(Get-PrinterDriver -Name '%s' -ErrorAction SilentlyContinue) -ne $null" % _q(driver)) != "True":
        print("[X] 未找到打印驱动: %s" % driver)
        return 3
    if _ps("(Get-PrinterPort -Name '%s' -ErrorAction SilentlyContinue) -ne $null" % _q(port)) != "True":
        _ps("Add-PrinterPort -Name '%s'" % _q(port))
        print("[+] 已创建文件端口: %s" % port)
    else:
        print("[=] 文件端口已存在: %s" % port)
    if _ps("(Get-Printer -Name '%s' -ErrorAction SilentlyContinue) -ne $null" % _q(name)) != "True":
        _ps("Add-Printer -Name '%s' -DriverName '%s' -PortName '%s'" % (_q(name), _q(driver), _q(port)))
        print("[+] 已创建虚拟打印机: %s" % name)
    else:
        cur = _ps("(Get-Printer -Name '%s').PortName" % _q(name), check=False)
        if cur != port:
            _ps("Set-Printer -Name '%s' -PortName '%s'" % (_q(name), _q(port)))
            print("[~] 已修正打印机端口: %s -> %s" % (cur, port))
        else:
            print("[=] 虚拟打印机已存在: %s" % name)
    st = status()
    print("[OK] 虚拟打印机就绪。打印时请选择：「%s」" % name)
    print("     端口文件: %s" % port)
    print("     状态: %s" % json.dumps(st, ensure_ascii=False))
    return 0


def uninstall():
    name, driver, port = get_names()
    if not is_admin():
        print("[!] 需要管理员权限。请使用「卸载虚拟打印机.cmd」(会自动请求提升)。")
        return 2
    if _ps("(Get-Printer -Name '%s' -ErrorAction SilentlyContinue) -ne $null" % _q(name)) == "True":
        _ps("Remove-Printer -Name '%s'" % _q(name))
        print("[-] 已删除虚拟打印机: %s" % name)
    else:
        print("[=] 虚拟打印机不存在: %s" % name)
    if _ps("(Get-PrinterPort -Name '%s' -ErrorAction SilentlyContinue) -ne $null" % _q(port)) == "True":
        _ps("Remove-PrinterPort -Name '%s'" % _q(port))
        print("[-] 已删除文件端口: %s" % port)
    else:
        print("[=] 文件端口不存在: %s" % port)
    return 0


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    cmd = argv[0] if argv else "status"
    if cmd == "install":
        return install()
    if cmd == "uninstall":
        return uninstall()
    if cmd == "status":
        print(json.dumps(status(), ensure_ascii=False, indent=2))
        return 0
    print("用法: python -m app.vpinstall [install|uninstall|status]")
    return 1


if __name__ == "__main__":
    sys.exit(main())
