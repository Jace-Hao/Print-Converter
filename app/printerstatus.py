# -*- coding: utf-8 -*-
"""水洗唛打印助手 - 本机(物理)目标打印机状态检测

用途：让操作台能看到真正出纸的那台打印机（配置 print.printer，默认「水洗唛」/GP-9134T）
是否安装、是否就绪、走哪个端口、队里压了几个任务。

实现（仅用 pywin32 的 win32print，无新增第三方依赖）：
  1. EnumPrinters(LOCAL|CONNECTIONS) 判断本机是否安装了目标打印机；
  2. OpenPrinter + GetPrinter(level=2) 读取 pPortName / pDriverName / Status / cJobs；
  3. Status 按 win32print.PRINTER_STATUS_* 位掩码映射为中文可读状态。

容错：所有异常都在模块内消化，status() 永不抛出（失败返回带 error 字段的字典），
     保证 /api/status 不会因为打印机检测失败而 500。
"""
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DEFAULT_PRINTER = "水洗唛"   # 配置缺失时的兜底打印机名
PRINTER_CHECK_TIMEOUT = 5.0  # 单次检测最长等待秒数：驱动 / 假脱机卡住时降级，不拖死页面轮询

try:
    import win32print
except Exception:  # pywin32 缺失时降级：仅返回错误，不影响其它功能
    win32print = None


def _flag(attr, value):
    """取 win32print 状态常量；pywin32 不可用时用标准值兜底。"""
    if win32print is not None:
        return getattr(win32print, attr, value)
    return value


# 状态位掩码 -> 中文说明（按位掩码从小到大排列，与 Windows 定义一致）
STATUS_MAP = [
    (_flag("PRINTER_STATUS_PAUSED", 0x00000001), "已暂停"),
    (_flag("PRINTER_STATUS_ERROR", 0x00000002), "错误"),
    (_flag("PRINTER_STATUS_PENDING_DELETION", 0x00000004), "正在删除"),
    (_flag("PRINTER_STATUS_PAPER_JAM", 0x00000008), "卡纸"),
    (_flag("PRINTER_STATUS_PAPER_OUT", 0x00000010), "缺纸"),
    (_flag("PRINTER_STATUS_MANUAL_FEED", 0x00000020), "需手动进纸"),
    (_flag("PRINTER_STATUS_PAPER_PROBLEM", 0x00000040), "纸张问题"),
    (_flag("PRINTER_STATUS_OFFLINE", 0x00000080), "离线"),
    (_flag("PRINTER_STATUS_IO_ACTIVE", 0x00000100), "正在传输数据"),
    (_flag("PRINTER_STATUS_BUSY", 0x00000200), "忙"),
    (_flag("PRINTER_STATUS_PRINTING", 0x00000400), "正在打印"),
    (_flag("PRINTER_STATUS_OUTPUT_BIN_FULL", 0x00000800), "出纸盒已满"),
    (_flag("PRINTER_STATUS_NOT_AVAILABLE", 0x00001000), "不可用"),
    (_flag("PRINTER_STATUS_WAITING", 0x00002000), "等待中"),
    (_flag("PRINTER_STATUS_PROCESSING", 0x00004000), "正在处理"),
    (_flag("PRINTER_STATUS_INITIALIZING", 0x00008000), "正在初始化"),
    (_flag("PRINTER_STATUS_WARMING_UP", 0x00010000), "正在预热"),
    (_flag("PRINTER_STATUS_TONER_LOW", 0x00020000), "墨量不足"),
    (_flag("PRINTER_STATUS_NO_TONER", 0x00040000), "缺墨"),
    (_flag("PRINTER_STATUS_PAGE_PUNT", 0x00080000), "该页无法打印"),
    (_flag("PRINTER_STATUS_USER_INTERVENTION", 0x00100000), "需人工干预"),
    (_flag("PRINTER_STATUS_OUT_OF_MEMORY", 0x00200000), "内存不足"),
    (_flag("PRINTER_STATUS_DOOR_OPEN", 0x00400000), "机盖打开"),
    (_flag("PRINTER_STATUS_SERVER_UNKNOWN", 0x00800000), "服务器状态未知"),
    (_flag("PRINTER_STATUS_POWER_SAVE", 0x01000000), "省电模式"),
]

# 会导致"不能正常出纸"的状态位（命中即判定不可用）
BLOCKING_FLAGS = (
    _flag("PRINTER_STATUS_PAUSED", 0x00000001),
    _flag("PRINTER_STATUS_ERROR", 0x00000002),
    _flag("PRINTER_STATUS_PENDING_DELETION", 0x00000004),
    _flag("PRINTER_STATUS_PAPER_JAM", 0x00000008),
    _flag("PRINTER_STATUS_PAPER_OUT", 0x00000010),
    _flag("PRINTER_STATUS_MANUAL_FEED", 0x00000020),
    _flag("PRINTER_STATUS_PAPER_PROBLEM", 0x00000040),
    _flag("PRINTER_STATUS_OFFLINE", 0x00000080),
    _flag("PRINTER_STATUS_OUTPUT_BIN_FULL", 0x00000800),
    _flag("PRINTER_STATUS_NOT_AVAILABLE", 0x00001000),
    _flag("PRINTER_STATUS_NO_TONER", 0x00040000),
    _flag("PRINTER_STATUS_PAGE_PUNT", 0x00080000),
    _flag("PRINTER_STATUS_USER_INTERVENTION", 0x00100000),
    _flag("PRINTER_STATUS_OUT_OF_MEMORY", 0x00200000),
    _flag("PRINTER_STATUS_DOOR_OPEN", 0x00400000),
    _flag("PRINTER_STATUS_SERVER_UNKNOWN", 0x00800000),
)


def _decode_status(code):
    """把 win32print 原始状态码翻译为人类可读文本。"""
    code = int(code or 0)
    if code == 0:
        return "就绪"
    texts = [t for mask, t in STATUS_MAP if code & mask]
    return "、".join(texts) if texts else "未知状态(%d)" % code


def _level(code, installed):
    """综合判定等级：ok=可用 / warn=工作中 / bad=不可用 / error=检测失败。"""
    if not installed:
        return "bad"
    code = int(code or 0)
    if code == 0:
        return "ok"
    if any(code & flag for flag in BLOCKING_FLAGS):
        return "bad"
    return "warn"


def _enum_names():
    """返回本机可见的打印机名列表（本地 + 连接）。

    异常不在此吞掉：交给 status() 的 error 分支，让"打印服务异常/枚举失败"
    能与"这台打印机没装"区分开，避免排查方向被带偏。
    """
    if win32print is None:
        raise RuntimeError("未安装 pywin32(win32print)")
    names = []
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    for item in win32print.EnumPrinters(flags):
        nm = item[2]
        if nm:
            names.append(nm)
    return names


def target_name(cfg=None):
    """目标打印机名：优先取配置的 print.printer，缺省用内置默认值。"""
    name = ""
    try:
        pr = (cfg.get("print") if cfg is not None else None) or {}
        name = str(pr.get("printer") or "").strip()
    except Exception:
        name = ""
    return name or DEFAULT_PRINTER


def status(cfg=None, name=None, timeout=PRINTER_CHECK_TIMEOUT):
    """检测本机目标打印机状态（对外入口，带超时保护，永不抛异常）。

    真正的检测跑在守护线程里：OpenPrinter / GetPrinter 在驱动或打印后台
    处理程序无响应时可能长时间不返回，这里最多等 timeout 秒即降级为 error，
    避免操作台每 3 秒一次的轮询把线程越堆越多。

    :param cfg: app.config.Config 实例（用于取 print.printer）；可为 None
    :param name: 显式指定打印机名；为空则用配置值
    :param timeout: 最长等待秒数（<=0 表示不限时）
    :return: dict，含 installed / is_default / port / driver / status /
             status_text / jobs / ok / level；检测失败时含 error 字段。
    """
    box = {}

    def work():
        try:
            box["data"] = _status_inner(cfg, name)
        except Exception as e:  # 双保险：_status_inner 本身已不抛异常
            box["data"] = _failed(target_name(cfg), "检测异常: %s" % e)

    if timeout and timeout > 0:
        th = threading.Thread(target=work, name="printer-status", daemon=True)
        th.start()
        th.join(timeout)
        if "data" not in box:
            return _failed((str(name).strip() if name else "") or target_name(cfg),
                           "检测超时：%.0f 秒内打印机未响应（驱动或打印后台处理程序可能卡住）" % timeout)
        return box["data"]
    work()
    return box.get("data") or _failed(target_name(cfg), "检测未产出结果")


def _failed(name, err):
    """构造一个"检测失败"结果，字段与正常结果保持一致，页面无需特殊分支。"""
    return {
        "name": name or DEFAULT_PRINTER, "installed": False, "is_default": False,
        "port": "", "driver": "", "status": None, "status_text": "检测失败",
        "level": "error", "jobs": 0, "ok": False, "printers": [], "similar": [],
        "error": err, "checked_at": time.strftime("%H:%M:%S"),
    }


def _status_inner(cfg=None, name=None):
    """检测本机目标打印机状态（内部实现，所有异常都在此消化）。

    :param cfg: app.config.Config 实例（用于取 print.printer）；可为 None
    :param name: 显式指定打印机名；为空则用配置值
    :return: dict，含 installed / is_default / port / driver / status /
             status_text / jobs / ok / level；检测失败时含 error 字段。
             本函数不抛异常。
    """
    want = (str(name).strip() if name else "") or target_name(cfg)
    out = {
        "name": want,
        "installed": False,
        "is_default": False,
        "port": "",
        "driver": "",
        "status": None,
        "status_text": "未检测",
        "level": "error",
        "jobs": 0,
        "ok": False,
        "printers": [],
        "similar": [],
        "checked_at": time.strftime("%H:%M:%S"),
    }
    if win32print is None:
        out["error"] = "未安装 pywin32(win32print)，无法检测打印机状态"
        return out
    try:
        names = _enum_names()
    except Exception as e:
        names = []
        out["printers"] = names
        out["error"] = "枚举本机打印机失败: %s" % e
        out["status_text"] = "检测失败"
        return out
    out["printers"] = names
    low = want.lower()
    # 只认完全同名（忽略大小写）：包含匹配会把「水洗唛打印助手」这类另一台设备
    # 当成目标机报"就绪"，造成假可用，因此只做提示不做定位。
    real = next((n for n in names if n.lower() == low), None)
    out["similar"] = [n for n in names if n.lower() != low and low in n.lower()]
    if real is None:
        out["status_text"] = "未安装（本机找不到这台打印机）"
        out["level"] = "bad"
        out["ok"] = False
        return out
    out["name"] = real
    out["installed"] = True
    try:
        out["is_default"] = (win32print.GetDefaultPrinter() or "").lower() == real.lower()
    except Exception:
        out["is_default"] = False
    handle = None
    try:
        handle = win32print.OpenPrinter(real)
        info = win32print.GetPrinter(handle, 2)
        out["port"] = str(info.get("pPortName") or "")
        out["driver"] = str(info.get("pDriverName") or "")
        code = int(info.get("Status") or 0)
        jobs = int(info.get("cJobs") or 0)
        out["status"] = code
        out["jobs"] = jobs
        out["status_text"] = _decode_status(code)
        out["level"] = _level(code, True)
        out["ok"] = out["level"] != "bad"
        return out
    except Exception as e:
        out["error"] = "读取打印机「%s」状态失败: %s" % (real, e)
        out["level"] = "error"
        out["ok"] = False
        return out
    finally:
        if handle is not None:
            try:
                win32print.ClosePrinter(handle)
            except Exception:
                pass


def main(argv=None):
    """命令行自检: python -m app.printerstatus [打印机名]"""
    import json as _json
    nm = (argv[0] if argv else None) if argv is not None else (sys.argv[1] if len(sys.argv) > 1 else None)
    print(_json.dumps(status(name=nm), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
