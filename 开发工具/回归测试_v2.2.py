# -*- coding: utf-8 -*-
"""水洗唛打印助手 v2.2 独立回归测试（QA：严过关）

运行方式（唯一可用解释器）：
    C:\\Users\\haoyuwei\\AppData\\Local\\Python\\bin\\python.exe -X utf8 开发工具\\回归测试_v2.2.py

覆盖：
    A. 本机打印机状态检测（app.printerstatus）：实测 + 故障注入 + 位掩码映射
    B. 配置零容错（app.config）：坏 JSON / 空文件 / 顶层非对象 / 正常
    C. 关键词排除打印（app.console do_action）：增删开关、边界、持久化、失败回滚
    D. 端到端打印判定（app.pipeline process_pdf dry_run）：新增关键词后真的生效
    E. HTTP 端到端（8891~8899 临时实例）：/api/status、printer_check、skip_*、set_rotate、
       vp_check、异常降级不 500
    F. 前端（web/操作页面.html）：JS 语法检查、轮询不打断输入、XSS 转义

安全约定（脚本内强制）：
    * 绝不触发真实打印（不调 calibrate、不调 print_image，pipeline 一律 dry_run=True）
    * 全部用例落在 tempfile 临时目录，用户真实的 config.json 只读不写
      （脚本开头/结尾各取一次 sha256 并在结束时断言一致）
    * 测试用 HTTP 实例只在 8891~8899，且不启动 watcher / 不做每日清理；结束即 terminate
      并断言端口已释放
    * 不执行任何 git 写操作
"""
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PY = sys.executable
USER_CFG = os.path.join(ROOT, "config.json")
PAGE = os.path.join(ROOT, "web", "操作页面.html")

# ---------------------------------------------------------------- 结果收集
RESULTS = []


def rec(case, ok, detail="", level="FAIL"):
    """level:
        FAIL  = 阻断性失败（计入 RESULT: FAIL，需工程师修复）
        MINOR = 与约定不符但不影响功能/数据的偏差（单列，需工程师或主理人裁定）
        WARN  = 观察项/风险提示（不阻断）
    """
    RESULTS.append({"case": case, "ok": bool(ok), "detail": detail, "level": level})
    tag = "PASS" if ok else level
    print("[%s] %-58s %s" % (tag, case, detail if detail else ""))
    return bool(ok)


def expect(case, cond, detail=""):
    return rec(case, cond, detail)


def eq(case, got, want):
    return rec(case, got == want, "got=%r want=%r" % (got, want))


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def close_logger(log):
    """关掉 logger 的文件句柄，否则 Windows 下临时目录删不掉（文件被占用）。"""
    try:
        for h in list(log.handlers):
            try:
                h.close()
            except Exception:
                pass
        log.handlers[:] = []
    except Exception:
        pass


def mktmp_root(name, cfg_over=None):
    """建一个临时"项目根"，里面放一份 config.json（默认拷贝用户当前配置）。"""
    d = tempfile.mkdtemp(prefix="washtest_%s_" % name)
    if cfg_over is None:
        shutil.copy2(USER_CFG, os.path.join(d, "config.json"))
    else:
        write_json(os.path.join(d, "config.json"), cfg_over)
    return d


# ================================================================ A. 打印机状态
def section_a():
    print("\n" + "=" * 78)
    print("A. 本机(物理)打印机状态检测 —— app/printerstatus.py")
    print("=" * 78)
    from app import printerstatus as PS

    # A1 命令行实测
    try:
        p = subprocess.run([PY, "-X", "utf8", "-m", "app.printerstatus"],
                           cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
        out = p.stdout.strip()
        data = json.loads(out[out.index("{"):])
        print("---- python -X utf8 -m app.printerstatus ----")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        print("---------------------------------------------")
        rec("A1-1 CLI 退出码 0", p.returncode == 0, "rc=%s" % p.returncode)
        rec("A1-2 installed=True", data.get("installed") is True)
        eq("A1-3 name", data.get("name"), "水洗唛")
        eq("A1-4 status", data.get("status"), 0)
        eq("A1-5 status_text(status=0)", data.get("status_text"), "就绪")
        eq("A1-6 level", data.get("level"), "ok")
        eq("A1-7 ok", data.get("ok"), True)
        eq("A1-8 port", data.get("port"), "USB001")
        rec("A1-9 driver 含 GP-9134T", "GP-9134T" in (data.get("driver") or ""),
            data.get("driver"))
        rec("A1-10 jobs 为 int >=0", isinstance(data.get("jobs"), int) and data["jobs"] >= 0,
            "jobs=%s" % data.get("jobs"))
        rec("A1-11 printers 列表非空", bool(data.get("printers")),
            "%d 台" % len(data.get("printers") or []))
        rec("A1-12 checked_at 非空", bool(data.get("checked_at")))
    except Exception as e:
        rec("A1 CLI 实测", False, "异常: %r" % e)

    # A2 故障注入（全部要求"不抛异常 + 返回 dict"）
    real_wp = PS.win32print
    tmp = mktmp_root("prt")
    from app.config import Config
    cfg = Config(tmp)

    def _call(label, fn):
        try:
            r = fn()
            ok = isinstance(r, dict)
            rec("A2-%s 返回 dict 不抛异常" % label, ok, type(r).__name__)
            if ok:
                rec("A2-%s 含 error 或 installed=False" % label,
                    bool(r.get("error")) or r.get("installed") is False,
                    "error=%s" % (r.get("error") or ""))
                eq("A2-%s ok=False" % label, r.get("ok"), False)
            return r
        except Exception as e:
            rec("A2-%s 返回 dict 不抛异常" % label, False, "抛出异常: %r" % e)
            return {}

    # a) OpenPrinter 抛异常
    try:
        orig_open = real_wp.OpenPrinter
        real_wp.OpenPrinter = lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("模拟 OpenPrinter 失败"))
        r = _call("OpenPrinter抛异常", lambda: PS.status(cfg))
        rec("A2-OpenPrinter level=error", r.get("level") == "error", "level=%s" % r.get("level"))
    finally:
        real_wp.OpenPrinter = orig_open

    # b) win32print 导入失败（模块级置 None）
    try:
        PS.win32print = None
        r = _call("win32print缺失", lambda: PS.status(cfg))
        rec("A2-pywin32缺失 error 文案正确",
            "pywin32" in (r.get("error") or ""), r.get("error"))
    finally:
        PS.win32print = real_wp

    # c) 目标打印机名不存在
    cfg.data["print"]["printer"] = "QA-不存在的打印机-ZZZ"
    r = _call("目标打印机不存在", lambda: PS.status(cfg))
    eq("A2-不存在 installed", r.get("installed"), False)
    eq("A2-不存在 level", r.get("level"), "bad")
    rec("A2-不存在 status_text 提示未安装",
        "未安装" in (r.get("status_text") or ""), r.get("status_text"))

    # d) EnumPrinters 抛异常
    try:
        orig_enum = real_wp.EnumPrinters
        real_wp.EnumPrinters = lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("模拟枚举失败"))
        r = _call("EnumPrinters抛异常", lambda: PS.status(cfg))
        # 期望：status() 第 165-170 行的 try/except 会写入 "枚举本机打印机失败"
        # 实际：_enum_names() 内部已吞掉异常返回 []，该分支永远不可达，
        #       用户只会看到"未安装"而不是"枚举失败"。不抛异常这一点仍满足。
        rec("A2-枚举失败 error 文案正确",
            "枚举" in (r.get("error") or ""),
            "error=%r；实际降级为 %r（_enum_names 吞异常，status() 的枚举失败分支不可达）"
            % (r.get("error"), r.get("status_text")), level="MINOR")
    finally:
        real_wp.EnumPrinters = orig_enum

    # e) cfg=None / 参数异常也不许抛
    for label, fn in (("cfg=None", lambda: PS.status(None)),
                      ("name=空串", lambda: PS.status(cfg, "")),
                      ("name=None", lambda: PS.status(cfg, None)),
                      ("cfg=坏对象", lambda: PS.status(object()))):
        try:
            r = fn()
            rec("A2-%s 不抛异常" % label, isinstance(r, dict), type(r).__name__)
        except Exception as e:
            rec("A2-%s 不抛异常" % label, False, "抛出异常: %r" % e)
    shutil.rmtree(tmp, ignore_errors=True)

    # A3 位掩码映射（参数化）
    print("\n-- A3 位掩码 -> 状态文本 / 等级 --")
    F = {n: PS._flag("PRINTER_STATUS_" + n, 0) for n in (
        "PAUSED", "ERROR", "PAPER_JAM", "PAPER_OUT", "OFFLINE", "PRINTING",
        "BUSY", "DOOR_OPEN", "TONER_LOW", "OUTPUT_BIN_FULL", "USER_INTERVENTION")}
    CASES = [
        ("0x00000000 空闲", 0, "就绪", "ok", True),
        ("PAUSED 0x1", F["PAUSED"], "已暂停", "bad", False),
        ("PAPER_JAM 0x8", F["PAPER_JAM"], "卡纸", "bad", False),
        ("PAPER_OUT 0x10", F["PAPER_OUT"], "缺纸", "bad", False),
        ("OFFLINE 0x80", F["OFFLINE"], "离线", "bad", False),
        ("PRINTING 0x400", F["PRINTING"], "正在打印", "warn", True),
        ("BUSY 0x200", F["BUSY"], "忙", "warn", True),
        ("TONER_LOW 0x20000", F["TONER_LOW"], "墨量不足", "warn", True),
        ("OFFLINE+OUT_OF_PAPER", F["OFFLINE"] | F["PAPER_OUT"], "缺纸、离线", "bad", False),
        ("PAUSED+PAPER_JAM+OFFLINE",
         F["PAUSED"] | F["PAPER_JAM"] | F["OFFLINE"], "已暂停、卡纸、离线", "bad", False),
        ("PRINTING+DOOR_OPEN", F["PRINTING"] | F["DOOR_OPEN"], "正在打印、机盖打开", "bad", False),
        ("PRINTING+BUSY", F["PRINTING"] | F["BUSY"], "忙、正在打印", "warn", True),
        ("OUTPUT_BIN_FULL 0x800", F["OUTPUT_BIN_FULL"], "出纸盒已满", "bad", False),
        ("USER_INTERVENTION", F["USER_INTERVENTION"], "需人工干预", "bad", False),
        ("ERROR 0x2", F["ERROR"], "错误", "bad", False),
    ]
    for label, code, want_txt, want_lv, want_ok in CASES:
        txt = PS._decode_status(code)
        lv = PS._level(code, True)
        ok = (txt == want_txt) and (lv == want_lv) and ((lv != "bad") == want_ok)
        rec("A3 %s" % label, ok,
            "text=%r(want %r) level=%r(want %r) ok=%s(want %s)"
            % (txt, want_txt, lv, want_lv, lv != "bad", want_ok))
    # 未安装 -> bad
    eq("A3 未安装时 level", PS._level(0, False), "bad")
    # 未知位
    rec("A3 未知位兜底", "未知状态" in PS._decode_status(0x80000000),
        PS._decode_status(0x80000000))
    # 未安装时 ok 必须为 False
    rec("A3 installed=False => ok=False", PS._level(0, False) == "bad")

    # A4 只认完全同名（曾被子串回退把虚拟打印机「水洗唛打印助手」当成物理机报"就绪"）
    try:
        r = PS.status(name="水洗唛打")
        rec("A4 只认完全同名，不再子串误匹配",
            r.get("installed") is False and r.get("name") == "水洗唛打",
            "installed=%s name=%s" % (r.get("installed"), r.get("name")))
        rec("A4 similar 列出名字相近设备",
            "水洗唛打印助手" in (r.get("similar") or []), str(r.get("similar")))
        r2 = PS.status(name="水洗唛转换")   # 另一台确有其名的设备，应精确命中
        rec("A4 另一台同名设备精确命中",
            r2.get("installed") is True and r2.get("name") == "水洗唛转换",
            "installed=%s name=%s" % (r2.get("installed"), r2.get("name")))
        r3 = PS.status(name="水洗唛")
        eq("A4 目标机 similar 为相近名列表", sorted(r3.get("similar") or []),
           sorted(["水洗唛转换", "水洗唛打印助手"]))
    except Exception as e:
        rec("A4 完全同名匹配", False, "抛异常: %r" % e)

    # A5 超时护栏（新增行为）
    print("\n-- A5 超时护栏（驱动/假脱机卡住时降级） --")
    eq("A5 默认超时常量", PS.PRINTER_CHECK_TIMEOUT, 5.0)
    tmp2 = mktmp_root("prt_timeout")
    try:
        from app.config import Config as _Cfg
        cfg2 = _Cfg(tmp2)
        orig_open = real_wp.OpenPrinter
        base_threads = threading.active_count()

        def _hang(*a, **k):
            time.sleep(2.0)                      # 模拟驱动/假脱机无响应
            return orig_open(*a, **k)

        real_wp.OpenPrinter = _hang
        try:
            t0 = time.time()
            r = PS.status(cfg2, timeout=1.0)
            el = time.time() - t0
            rec("A5 卡住时 1 秒内返回（未拖死轮询）", el < 2.0, "耗时 %.2fs" % el)
            rec("A5 超时返回 error 中文提示", "检测超时" in (r.get("error") or ""), r.get("error"))
            eq("A5 超时 level", r.get("level"), "error")
            eq("A5 超时 ok", r.get("ok"), False)
            eq("A5 超时 status_text", r.get("status_text"), "检测失败")
            eq("A5 超时 installed", r.get("installed"), False)
            for k in ("name", "port", "driver", "jobs", "printers", "similar", "checked_at"):
                rec("A5 超时结果含字段 %s" % k, k in r)
        finally:
            real_wp.OpenPrinter = orig_open
        # 卡住的线程结束后应自然回收（daemon 线程，不阻塞退出）
        time.sleep(1.6)
        rec("A5 卡住线程已回收（无永久泄漏）",
            threading.active_count() <= base_threads + 1,
            "before=%d after=%d" % (base_threads, threading.active_count()))
        # 故障恢复后正常检测不受影响
        r4 = PS.status(cfg2)
        rec("A5 恢复后正常检测仍正确",
            r4.get("installed") is True and r4.get("status_text") == "就绪",
            json.dumps(r4, ensure_ascii=False)[:160])
        # timeout<=0 走同步不限时分支
        r5 = PS.status(cfg2, timeout=0)
        rec("A5 timeout=0 走同步分支", r5.get("installed") is True, str(r5.get("status_text")))
    finally:
        shutil.rmtree(tmp2, ignore_errors=True)


# ================================================================ B. 配置容错
def section_b():
    print("\n" + "=" * 78)
    print("B. 配置零容错 —— app/config.py")
    print("=" * 78)
    from app.config import Config, DEFAULTS

    BAD_JSON = '{\n  "watch": {\n    "dirs": ["D:\\\\x"]\n  "pattern": "*.pdf"\n}\n'  # 漏逗号
    CASES = [
        ("B1 坏JSON(漏逗号)", BAD_JSON, True),
        ("B2 空文件", "", True),
        ("B3 顶层是list", "[1, 2, 3]", True),
        ("B4 正常JSON", json.dumps({"print": {"printer": "水洗唛"}}, ensure_ascii=False), False),
    ]
    for label, content, should_err in CASES:
        d = tempfile.mkdtemp(prefix="washtest_cfg_")
        p = os.path.join(d, "config.json")
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        try:
            err = None
            cfg = None
            try:
                cfg = Config(d)          # 关键：不得抛异常
            except Exception as e:
                err = e
            rec("%s 构造不抛异常" % label, err is None, "异常: %r" % err)
            if cfg is None:
                continue
            rec("%s 返回可用配置(有 DEFAULTS 兜底)" % label,
                bool(cfg.data) and "watch" in cfg.data and "print" in cfg.data,
                "keys=%d" % len(cfg.data))
            rec("%s load_error %s" % (label, "非空" if should_err else "为空"),
                bool(cfg.load_error) == should_err, "load_error=%r" % cfg.load_error[:120])
            baks = [f for f in os.listdir(d) if ".corrupt-" in f and f.endswith(".bak")]
            if should_err:
                rec("%s 生成 .corrupt-*.bak" % label, len(baks) == 1, str(baks))
                if baks:
                    bak = os.path.join(d, baks[0])
                    with open(bak, "r", encoding="utf-8") as f:
                        got = f.read()
                    eq("%s bak 内容 == 原始损坏内容" % label, got, content)
                    rec("%s load_error 说明备份位置" % label,
                        (os.path.basename(cfg.backup_path) in cfg.load_error) or (not content),
                        cfg.load_error[:140])
                    rec("%s 备份路径记入 backup_path" % label,
                        os.path.abspath(cfg.backup_path) == os.path.abspath(bak),
                        cfg.backup_path)
                    # 原件仍在（copy2 保留原件）
                    rec("%s 损坏原件未被删除" % label, os.path.exists(p))
                # 回退后仍然能取到默认打印机名
                eq("%s DEFAULTS 兜底 printer" % label,
                   cfg.data["print"]["printer"], DEFAULTS["print"]["printer"])
            else:
                rec("%s 不产生 .bak" % label, len(baks) == 0, str(baks))
                eq("%s 自定义值生效" % label, cfg.data["print"]["printer"], "水洗唛")
                eq("%s backup_path 为空" % label, cfg.backup_path, "")
            # save() 之后应能重新解析
            cfg.data["print"]["printer"] = "水洗唛"
            cfg.save()
            try:
                with open(p, "r", encoding="utf-8") as f:
                    again = json.load(f)
                rec("%s save() 后可重新解析" % label, isinstance(again, dict))
            except Exception as e:
                rec("%s save() 后可重新解析" % label, False, "%r" % e)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    # B5 文件不存在
    d = tempfile.mkdtemp(prefix="washtest_cfg_")
    try:
        cfg = Config(d)
        rec("B5 无 config.json 不抛异常", bool(cfg.data))
        eq("B5 无 config.json load_error 为空", cfg.load_error, "")
    finally:
        shutil.rmtree(d, ignore_errors=True)

    # B6 顶层是字符串
    d = tempfile.mkdtemp(prefix="washtest_cfg_")
    try:
        with open(os.path.join(d, "config.json"), "w", encoding="utf-8") as f:
            f.write('"只是一个字符串"')
        cfg = Config(d)
        rec("B6 顶层是字符串不抛异常", bool(cfg.data))
        rec("B6 顶层是字符串 load_error 非空", bool(cfg.load_error), cfg.load_error[:80])
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ================================================================ C. 关键词逻辑
def section_c():
    print("\n" + "=" * 78)
    print("C. 关键词排除打印 —— app/console.py do_action（临时目录配置，不碰用户 config.json）")
    print("=" * 78)
    from app.config import Config
    from app.logutil import get_logger
    from app import console as C

    tmp = mktmp_root("kw", {"skip_print": {"enabled": True, "keywords": ["布草", "窗帘"]},
                            "print": {"printer": "水洗唛"}})
    try:
        cfg = Config(tmp)
        log = get_logger(tmp, name="qa_action")
        p = cfg.path

        def act(name, arg=None):
            return C.do_action(cfg, log, name, arg)

        def persisted():
            return read_json(p)["skip_print"]

        # C1 正常添加 + 落盘
        r = act("skip_add", "婚纱")
        rec("C1 skip_add ok", r.get("ok") is True, json.dumps(r, ensure_ascii=False))
        eq("C1 落盘 keywords", persisted()["keywords"], ["布草", "窗帘", "婚纱"])
        # C2 重复
        r = act("skip_add", "婚纱")
        eq("C2 重复添加 ok", r.get("ok"), False)
        rec("C2 重复添加 提示已在列表", "已在列表中" in (r.get("msg") or ""), r.get("msg"))
        # C3 纯空格 / 空串 / None
        for label, arg in (("C3 纯空格", "   "), ("C3 空串", ""), ("C3 None", None),
                           ("C3 全空白符", "\t\n 　")):
            r = act("skip_add", arg)
            eq("%s 被拒(ok=False)" % label, r.get("ok"), False)
        eq("C3 非法输入未污染 keywords", persisted()["keywords"], ["布草", "窗帘", "婚纱"])
        # C4 长度边界：30 字通过 / 31 字拒绝
        r = act("skip_add", "x" * 30)
        eq("C4 30字 通过", r.get("ok"), True)
        r = act("skip_add", "y" * 31)
        eq("C4 31字 拒绝", r.get("ok"), False)
        rec("C4 31字 提示超长", "过长" in (r.get("msg") or ""), r.get("msg"))
        rec("C4 31字 提示含字符数", "30" in (r.get("msg") or "") and "31" in (r.get("msg") or ""),
            r.get("msg"))
        # C5 去空白 + 去重（"布 草" -> "布草" 已存在）
        r = act("skip_add", "布 草")
        eq("C5 内部空白归一后判重", r.get("ok"), False)
        rec("C5 归一为「布草」", "布草" in (r.get("msg") or ""), r.get("msg"))
        r = act("skip_add", "  床单  ")
        eq("C5 首尾空白裁剪后通过", r.get("ok"), True)
        rec("C5 落盘为「床单」", "床单" in persisted()["keywords"], str(persisted()["keywords"]))
        # C6 特殊字符（引号 / 斜杠 / 尖括号 / &）
        evil = '"q"/s<l>&\'a'
        r = act("skip_add", evil)
        eq("C6 特殊字符可添加", r.get("ok"), True)
        eq("C6 特殊字符原样落盘", evil in persisted()["keywords"], True)
        # C7 删除
        r = act("skip_del", evil)
        eq("C7 skip_del ok", r.get("ok"), True)
        rec("C7 特殊字符已移除", evil not in persisted()["keywords"])
        r = act("skip_del", "根本不存在的词")
        eq("C7 删除不存在的词 ok", r.get("ok"), False)
        rec("C7 删除不存在 提示未找到", "未找到" in (r.get("msg") or ""), r.get("msg"))
        eq("C7 删除空词 ok", act("skip_del", "").get("ok"), False)
        # C8 开关
        before = persisted()["enabled"]
        r = act("skip_toggle")
        eq("C8 skip_toggle ok", r.get("ok"), True)
        eq("C8 enabled 翻转并落盘", persisted()["enabled"], (not before))
        act("skip_toggle")
        eq("C8 再切回原值", persisted()["enabled"], before)
        # C9 条数上限 50
        cfg.data["skip_print"]["keywords"] = ["k%02d" % i for i in range(50)]
        cfg.save()
        r = act("skip_add", "第51个")
        eq("C9 超过50条 拒绝", r.get("ok"), False)
        rec("C9 提示条数上限", "50" in (r.get("msg") or ""), r.get("msg"))
        eq("C9 拒绝后条数仍为50", len(read_json(p)["skip_print"]["keywords"]), 50)
        # C10 保存失败 -> 回滚内存 + 返回 ok=False
        cfg.data["skip_print"]["keywords"] = ["布草"]
        cfg.save()

        def _boom():
            raise IOError("模拟 config.json 写入失败")

        cfg.save = _boom
        try:
            r = act("skip_add", "会失败吗")
            eq("C10 save失败 ok", r.get("ok"), False)
            rec("C10 save失败 中文提示", ("撤销" in (r.get("msg") or "")) or
                ("保存配置失败" in (r.get("msg") or "")), r.get("msg"))
            eq("C10 save失败 内存回滚", cfg.data["skip_print"]["keywords"], ["布草"])
            # 删除路径同样回滚
            r = act("skip_del", "布草")
            eq("C10 del失败 ok", r.get("ok"), False)
            eq("C10 del失败 内存回滚", cfg.data["skip_print"]["keywords"], ["布草"])
        finally:
            del cfg.save
        # C11 _norm_keyword 归一化
        eq("C11 _norm_keyword 去所有空白", C._norm_keyword(" a　b\tc \n"), "abc")
        eq("C11 _norm_keyword None", C._norm_keyword(None), "")
        # C12 常量
        eq("C12 SKIP_KW_MAX_LEN", C.SKIP_KW_MAX_LEN, 30)
        eq("C12 SKIP_KW_MAX_COUNT", C.SKIP_KW_MAX_COUNT, 50)
        eq("C12 VERSION", C.VERSION, "v2.2")
        # C13 未知动作
        eq("C13 未知动作 ok", act("no_such_action").get("ok"), False)
    finally:
        try:
            close_logger(log)
        except Exception:
            pass
        shutil.rmtree(tmp, ignore_errors=True)


# ================================================================ D. 端到端打印判定
def make_label_pdf(path, lines, w_mm=120.0, h_mm=30.0):
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page(width=w_mm / 25.4 * 72, height=h_mm / 25.4 * 72)
    y = 16
    for ln in lines:
        page.insert_text((14, y), ln, fontsize=11, fontname="china-s")
        y += 15
    doc.save(path)
    doc.close()


def section_d():
    print("\n" + "=" * 78)
    print("D. 端到端打印判定 —— app/pipeline.py process_pdf(dry_run=True)（不出纸）")
    print("=" * 78)
    from app.config import Config
    from app.logutil import get_logger
    from app.pipeline import process_pdf

    tmp = mktmp_root("pipe", {"skip_print": {"enabled": True, "keywords": ["布草"]},
                              "print": {"printer": "水洗唛"},
                              "paths": {"archive": "out\\archive", "logs": "out\\logs",
                                        "previews": "out\\previews", "inbox": "inbox"}})
    try:
        cfg = Config(tmp)
        # get_logger 会往 out/logs 写；全部在临时目录
        log = get_logger(tmp, name="qa_dryrun")
        src = os.path.join(tmp, "qa_布草标签.pdf")
        make_label_pdf(src, ["布草（酒店） 可丢弃", "QA-DRYRUN 测试页 不出纸"])
        arch = cfg.path_of("archive")
        prev = cfg.path_of("previews")

        # D1 命中关键词 -> skipped=True
        res = process_pdf(cfg, log, src, dry_run=True)
        lab = (res.get("labels") or [{}])[0]
        print("    labels[0] = %s" % json.dumps(lab, ensure_ascii=False, default=str))
        eq("D1 skipped=True", lab.get("skipped"), True)
        eq("D1 skip_keyword", lab.get("skip_keyword"), "布草")
        rec("D1 未归档(dry_run)", "archived" not in res, str(res.get("archived")))
        eq("D1 归档目录为空(不产生垃圾)", len(os.listdir(arch)) if os.path.isdir(arch) else 0, 0)
        rec("D1 源文件仍在(未被移走)", os.path.exists(src))
        rec("D1 生成了预览PNG", bool(lab.get("preview")) and os.path.exists(lab["preview"]),
            lab.get("preview"))

        # D2 删除关键词 -> 同一份 PDF 不再跳过
        cfg.data["skip_print"]["keywords"] = []
        cfg.save()
        res2 = process_pdf(cfg, log, src, dry_run=True)
        lab2 = (res2.get("labels") or [{}])[0]
        print("    labels[0] = %s" % json.dumps(lab2, ensure_ascii=False, default=str))
        rec("D2 skipped 不为 True", lab2.get("skipped") is not True,
            "skipped=%r" % lab2.get("skipped"))
        rec("D2 无 skip_keyword", "skip_keyword" not in lab2)
        eq("D2 归档目录仍为空", len(os.listdir(arch)) if os.path.isdir(arch) else 0, 0)
        rec("D2 源文件仍在", os.path.exists(src))

        # D3 新增一个全新关键词后立刻生效（模拟"用户在页面加词"）
        cfg.data["skip_print"]["keywords"] = ["QA-DRYRUN"]
        cfg.save()
        cfg2 = Config(tmp)           # 重新加载，模拟服务读到新配置
        res3 = process_pdf(cfg2, log, src, dry_run=True)
        lab3 = (res3.get("labels") or [{}])[0]
        eq("D3 新关键词立即生效 skipped", lab3.get("skipped"), True)
        eq("D3 skip_keyword", lab3.get("skip_keyword"), "QA-DRYRUN")

        # D4 enabled=False 时不跳过
        cfg.data["skip_print"] = {"enabled": False, "keywords": ["布草"]}
        cfg.save()
        res4 = process_pdf(Config(tmp), log, src, dry_run=True)
        rec("D4 功能停用时不跳过", (res4["labels"][0].get("skipped") is not True))

        # D5 PDF 文本里带空格也要命中（空白归一）
        cfg.data["skip_print"] = {"enabled": True, "keywords": ["酒店布草"]}
        cfg.save()
        src2 = os.path.join(tmp, "qa_空格.pdf")
        make_label_pdf(src2, ["酒店 布草 可丢弃", "QA-DRYRUN"])
        res5 = process_pdf(Config(tmp), log, src2, dry_run=True)
        eq("D5 文本含空格仍命中", res5["labels"][0].get("skip_keyword"), "酒店布草")

        # D6 清理：确认预览目录里只有本次产物（脚本结束会整目录删除）
        n_prev = len(os.listdir(prev)) if os.path.isdir(prev) else 0
        rec("D6 预览产物数量>0 且在临时目录", n_prev > 0 and prev.startswith(tmp),
            "%d 个 preview" % n_prev)
    finally:
        close_logger(log)
        shutil.rmtree(tmp, ignore_errors=True)


# ================================================================ E. HTTP 端到端
LAUNCHER = r'''# -*- coding: utf-8 -*-
"""QA 临时服务启动器：只用于回归测试，不启动 watcher、不做每日清理。"""
import os, sys
proj, port, tmproot, mode = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
sys.path.insert(0, proj)
import app.watcher, app.retention

class _NoWatcher(object):
    def __init__(self, cfg, log): pass
    def run(self): return None
    def stop(self): return None
app.watcher.Watcher = _NoWatcher
app.retention.cleanup = lambda *a, **k: 0

import app.console as C
from app.config import Config
from app.logutil import get_logger

def _setup():
    return Config(tmproot), get_logger(tmproot, name="qa_srv")
C._setup = _setup
C.BASE_PORT = port
C.PORT_TRIES = 1
if mode == "badprinter":
    import app.printerstatus as PS
    def _boom(*a, **k):
        raise RuntimeError("模拟打印机检测崩溃")
    PS.status = _boom
sys.exit(C.run())
'''


def pick_port():
    for p in range(8891, 8900):
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", p))
            return p
        except OSError:
            continue
        finally:
            s.close()
    return None


def http_json(url, data=None, timeout=15):
    import urllib.request
    import urllib.error
    if data is None:
        req = urllib.request.Request(url, headers={"Cache-Control": "no-store"})
    else:
        body = data if isinstance(data, bytes) else json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=body,
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


class Server(object):
    def __init__(self, tmproot, port, mode="ok"):
        self.tmproot, self.port, self.mode = tmproot, port, mode
        self.proc = None
        self.logf = None

    def __enter__(self):
        lp = os.path.join(self.tmproot, "_srv.py")
        with open(lp, "w", encoding="utf-8") as f:
            f.write(LAUNCHER)
        self.logf = open(os.path.join(self.tmproot, "_srv.log"), "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [PY, "-X", "utf8", lp, ROOT, str(self.port), self.tmproot, self.mode],
            cwd=ROOT, stdout=self.logf, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL)
        deadline = time.time() + 40
        while time.time() < deadline:
            if self.proc.poll() is not None:
                break
            try:
                code, _ = http_json("http://127.0.0.1:%d/api/ping" % self.port, timeout=1.5)
                if code == 200:
                    return self
            except Exception:
                pass
            time.sleep(0.4)
        raise RuntimeError("测试实例未能在端口 %d 启动" % self.port)
        return self

    def __exit__(self, *a):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except Exception:
                self.proc.kill()
                self.proc.wait(timeout=10)
        if self.logf:
            try:
                self.logf.close()
            except Exception:
                pass
        # 断言端口已释放
        free = False
        for _ in range(25):
            s = socket.socket()
            try:
                s.bind(("127.0.0.1", self.port))
                free = True
                break
            except OSError:
                time.sleep(0.3)
            finally:
                s.close()
        rec("E0 测试实例已退出、端口 %d 已释放" % self.port, free)


def section_e():
    print("\n" + "=" * 78)
    print("E. HTTP 端到端（8891~8899 临时实例；不启动 watcher / 不做清理 / 不出纸）")
    print("=" * 78)
    port1 = pick_port()
    if port1 is None:
        rec("E 端口选择", False, "8891~8899 无空闲端口")
        return
    tmp = mktmp_root("e2e", {"skip_print": {"enabled": True, "keywords": ["布草"]},
                             "print": {"printer": "水洗唛"},
                             "pipeline": {"rotate_dir": "ccw"},
                             "paths": {"archive": "out\\archive", "logs": "out\\logs",
                                       "previews": "out\\previews", "inbox": "inbox"}})
    try:
        cfgp = os.path.join(tmp, "config.json")
        with Server(tmp, port1, "ok") as srv:
            base = "http://127.0.0.1:%d" % srv.port
            # E1 /api/status
            code, st = http_json(base + "/api/status")
            rec("E1 GET /api/status -> 200", code == 200, "HTTP %s" % code)
            for k in ("printer", "config_error", "skip_print", "version"):
                rec("E1 status 含字段 %s" % k, k in st, "")
            eq("E1 version", st.get("version"), "v2.2")
            eq("E1 config_error 为空(配置正常)", st.get("config_error"), "")
            eq("E1 skip_print.keywords", (st.get("skip_print") or {}).get("keywords"), ["布草"])
            eq("E1 skip_print.enabled", (st.get("skip_print") or {}).get("enabled"), True)
            print("---- /api/status 的 printer 字段 ----")
            print(json.dumps(st.get("printer"), ensure_ascii=False, indent=2))
            print("------------------------------------")
            pr = st.get("printer") or {}
            for k in ("installed", "is_default", "port", "driver", "status",
                      "status_text", "jobs", "ok", "level", "printers", "similar"):
                rec("E1 printer 含字段 %s" % k, k in pr)
            rec("E1 printer.installed=True", pr.get("installed") is True)
            eq("E1 printer.name", pr.get("name"), "水洗唛")
            eq("E1 printer.status_text", pr.get("status_text"), "就绪")
            eq("E1 printer.ok", pr.get("ok"), True)
            rec("E1 printer.printers 非空", bool(pr.get("printers")))
            # E1b 其它既有字段未回归
            for k in ("watcher", "vprinter", "capture", "recent", "log_tail", "rotate_dir"):
                rec("E1b status 仍含 %s" % k, k in st)
            eq("E1b rotate_dir", st.get("rotate_dir"), "ccw")

            # E2 printer_check
            code, r = http_json(base + "/api/action", {"name": "printer_check"})
            rec("E2 POST printer_check -> 200", code == 200, "HTTP %s" % code)
            rec("E2 printer_check ok", r.get("ok") is True, json.dumps(r, ensure_ascii=False)[:200])
            rec("E2 printer_check 返回 data.status_text",
                bool(((r.get("data") or {}).get("status_text"))),
                (r.get("data") or {}).get("status_text"))

            # E3 skip_add / skip_del 经 HTTP
            code, r = http_json(base + "/api/action", {"name": "skip_add", "arg": "窗帘"})
            rec("E3 skip_add -> 200", code == 200, "HTTP %s" % code)
            rec("E3 skip_add ok", r.get("ok") is True, r.get("msg"))
            eq("E3 skip_add 后 config.json 落盘", read_json(cfgp)["skip_print"]["keywords"],
               ["布草", "窗帘"])
            code, r = http_json(base + "/api/action", {"name": "skip_add", "arg": "窗帘"})
            eq("E3 重复 skip_add 被拒", r.get("ok"), False)
            code, r = http_json(base + "/api/action", {"name": "skip_add", "arg": "  "})
            eq("E3 空格 skip_add 被拒", r.get("ok"), False)
            code, r = http_json(base + "/api/action", {"name": "skip_add", "arg": ""})
            eq("E3 空串 skip_add 被拒", r.get("ok"), False)
            code, r = http_json(base + "/api/action", {"name": "skip_add", "arg": "z" * 31})
            eq("E3 31字 skip_add 被拒", r.get("ok"), False)
            sp = '"/\\<>&\''
            code, r = http_json(base + "/api/action", {"name": "skip_add", "arg": sp})
            rec("E3 特殊字符 skip_add ok", r.get("ok") is True, r.get("msg"))
            rec("E3 特殊字符原样落盘", sp in read_json(cfgp)["skip_print"]["keywords"],
                str(read_json(cfgp)["skip_print"]["keywords"]))
            code, r = http_json(base + "/api/action", {"name": "skip_del", "arg": sp})
            eq("E3 特殊字符 skip_del ok", r.get("ok"), True)
            rec("E3 特殊字符已删除", sp not in read_json(cfgp)["skip_print"]["keywords"])
            code, r = http_json(base + "/api/action", {"name": "skip_del", "arg": "窗帘"})
            eq("E3 skip_del ok", r.get("ok"), True)
            eq("E3 skip_del 后落盘", read_json(cfgp)["skip_print"]["keywords"], ["布草"])
            code, r = http_json(base + "/api/action", {"name": "skip_del", "arg": "没有这个词"})
            eq("E3 删除不存在的词被拒", r.get("ok"), False)

            # E4 skip_toggle
            code, r = http_json(base + "/api/action", {"name": "skip_toggle"})
            eq("E4 skip_toggle ok", r.get("ok"), True)
            eq("E4 落盘 enabled=False", read_json(cfgp)["skip_print"]["enabled"], False)
            code, r2 = http_json(base + "/api/action", {"name": "skip_toggle"})
            eq("E4 再切回 enabled=True", read_json(cfgp)["skip_print"]["enabled"], True)
            code, st2 = http_json(base + "/api/status")
            eq("E4 /api/status 反映 enabled", (st2.get("skip_print") or {}).get("enabled"), True)

            # E5 set_rotate（既有功能回归）
            code, r = http_json(base + "/api/action", {"name": "set_rotate", "arg": "cw"})
            rec("E5 set_rotate cw ok", r.get("ok") is True, r.get("msg"))
            eq("E5 落盘 rotate_dir=cw", read_json(cfgp)["pipeline"]["rotate_dir"], "cw")
            code, st3 = http_json(base + "/api/status")
            eq("E5 /api/status rotate_dir=cw", st3.get("rotate_dir"), "cw")
            code, r = http_json(base + "/api/action", {"name": "set_rotate", "arg": "ccw"})
            eq("E5 还原 rotate_dir=ccw", read_json(cfgp)["pipeline"]["rotate_dir"], "ccw")
            code, r = http_json(base + "/api/action", {"name": "set_rotate", "arg": "up"})
            eq("E5 非法方向被拒", r.get("ok"), False)
            eq("E5 非法方向未写坏配置", read_json(cfgp)["pipeline"]["rotate_dir"], "ccw")

            # E6 vp_check（虚拟打印机）
            code, r = http_json(base + "/api/action", {"name": "vp_check"}, timeout=60)
            rec("E6 vp_check -> 200", code == 200, "HTTP %s" % code)
            rec("E6 vp_check ok", r.get("ok") is True)
            d = r.get("data") or {}
            print("---- vp_check data ----")
            print(json.dumps(d, ensure_ascii=False, indent=2))
            print("-----------------------")
            eq("E6 port_ok", d.get("port_ok"), True)
            eq("E6 printer_ok", d.get("printer_ok"), True)

            # E7 异常/非法请求不得 500
            code, r = http_json(base + "/api/action", b"{not json}")
            rec("E7 非法 JSON -> 200 不是 5xx", code == 200, "HTTP %s" % code)
            rec("E7 非法 JSON 返回中文 msg", isinstance(r, dict) and bool(r.get("msg")),
                json.dumps(r, ensure_ascii=False)[:160] if isinstance(r, dict) else str(r)[:160])
            code, r = http_json(base + "/api/action", {"name": "根本不存在的动作"})
            rec("E7 未知动作 -> 200", code == 200, "HTTP %s" % code)
            eq("E7 未知动作 ok=False", (r or {}).get("ok"), False)
            code, r = http_json(base + "/api/notexist")
            rec("E7 未知路径 -> 404(非500)", code == 404, "HTTP %s" % code)

        # E8 打印机检测崩溃 -> /api/status 仍 200
        port2 = pick_port()
        if port2 is None:
            rec("E8 端口选择", False, "无空闲端口")
        else:
            tmp2 = mktmp_root("e2e_bad", {"print": {"printer": "水洗唛"}})
            try:
                with Server(tmp2, port2, "badprinter") as srv2:
                    base2 = "http://127.0.0.1:%d" % srv2.port
                    code, st = http_json(base2 + "/api/status")
                    rec("E8 打印机检测崩溃 /api/status 仍 200", code == 200, "HTTP %s" % code)
                    prb = st.get("printer") or {}
                    rec("E8 printer 降级为 error 不 500", bool(prb) and prb.get("ok") is False,
                        json.dumps(prb, ensure_ascii=False)[:200])
                    rec("E8 printer.status_text 可读中文",
                        bool(prb.get("status_text")), prb.get("status_text"))
                    code, r = http_json(base2 + "/api/action", {"name": "printer_check"})
                    rec("E8 printer_check 崩溃仍 200", code == 200, "HTTP %s" % code)
                    rec("E8 printer_check 崩溃仍返回 dict", isinstance(r, dict) and "ok" in r,
                        json.dumps(r, ensure_ascii=False)[:200])
            finally:
                shutil.rmtree(tmp2, ignore_errors=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ================================================================ G. 超时护栏（虚拟打印机）
def section_g():
    print("\n" + "=" * 78)
    print("G. 超时护栏 —— app/vpinstall.py PowerShell 调用")
    print("=" * 78)
    from app import vpinstall as VP
    eq("G1 默认超时常量", VP.PS_TIMEOUT, 15)

    orig_run = VP.subprocess.run
    try:
        VP.subprocess.run = lambda *a, **k: (_ for _ in ()).throw(
            subprocess.TimeoutExpired("powershell", VP.PS_TIMEOUT))
        # check=False：状态检测降级为空串
        out = VP._ps("任意命令", check=False)
        eq("G2 超时(check=False) 返回空串", out, "")
        st = VP.status()
        rec("G3 超时后 status() 带 error 字段", bool(st.get("error")), st.get("error"))
        rec("G3 error 说明超时秒数", "15" in (st.get("error") or ""), st.get("error"))
        rec("G3 超时不会被误读成「确实未安装」", "port_ok" not in st, str(sorted(st.keys())))
        rec("G3 仍返回设备名/端口等静态信息",
            st.get("name") == "水洗唛打印助手" and bool(st.get("port")))
        # check=True：安装类操作抛错提示用户
        try:
            VP._ps("任意命令", check=True)
            rec("G4 超时(check=True) 抛 RuntimeError", False, "未抛异常")
        except RuntimeError as e:
            rec("G4 超时(check=True) 抛 RuntimeError", "超时" in str(e), str(e)[:120])
        except Exception as e:
            rec("G4 超时(check=True) 抛 RuntimeError", False, "抛了 %r" % e)
    finally:
        VP.subprocess.run = orig_run

    # 真实调用仍然正常（不 mock）
    st = VP.status()
    eq("G5 真实 vpinstall.status() port_ok", st.get("port_ok"), True)
    eq("G5 真实 vpinstall.status() printer_ok", st.get("printer_ok"), True)
    eq("G5 真实 vpinstall.status() driver_ok", st.get("driver_ok"), True)
    rec("G5 正常时无 error 字段", not st.get("error"), str(st.get("error")))


# ================================================================ F. 前端
HARNESS = r'''
const fs = require('fs');
const HTML = process.argv[2];
const OUT = process.argv[3];
const html = fs.readFileSync(HTML, 'utf8');
const m = html.match(/<script>([\s\S]*?)<\/script>/);
if (!m) { fs.writeFileSync(OUT, JSON.stringify([{name:'F0 抽取<script>', ok:false, detail:'页面内未找到 script'}])); process.exit(2); }
const code = m[1];

const els = {};
function mk(id){
  if (els[id]) return els[id];
  const el = {
    id: id, textContent: '', innerHTML: '', className: '', value: '',
    disabled: false, _focused: false, _cls: new Set(), _ev: {},
    classList: {
      add(c){ el._cls.add(c); }, remove(c){ el._cls.delete(c); },
      toggle(c, v){ if (v === undefined) { el._cls.has(c) ? el._cls.delete(c) : el._cls.add(c); } else { v ? el._cls.add(c) : el._cls.delete(c); } },
      contains(c){ return el._cls.has(c); }
    },
    addEventListener(t, f){ el._ev[t] = f; },
    focus(){ el._focused = true; },
    getAttribute(a){ return el['_attr_' + a]; },
    setAttribute(a, v){ el['_attr_' + a] = v; }
  };
  els[id] = el; return el;
}
const document = { getElementById: mk, querySelectorAll: function(){ return {forEach: function(){}}; } };
let SERVER = {};
const fetchStub = async function(u, o){ return { ok: true, json: async function(){ return SERVER; } }; };
const setIntervalStub = function(){ return 0; };
const setTimeoutStub = function(){ return 0; };
const clearTimeoutStub = function(){};
const confirmStub = function(){ return true; };

let api;
try {
  api = new Function('document','fetch','setInterval','setTimeout','clearTimeout','confirm',
    code + '\n;return {esc: esc, skipSig: skipSig, renderSkip: renderSkip, refresh: refresh};')(
    document, fetchStub, setIntervalStub, setTimeoutStub, clearTimeoutStub, confirmStub);
} catch (e) {
  fs.writeFileSync(OUT, JSON.stringify([{name:'F0 页面脚本可求值', ok:false, detail:String(e)}]));
  process.exit(2);
}

const res = [];
function chk(name, cond, detail){ res.push({name: name, ok: !!cond, detail: String(detail === undefined ? '' : detail)}); }

(async function(){
  const status = {
    ok:true, app:'水洗唛打印助手', version:'v2.2', now:'2026-01-01 00:00:00',
    started:'2026-01-01 00:00:00', port:8891, pid:1234,
    watcher:{alive:true, dirs:['D:\\水洗唛输出']},
    vprinter:{name:'水洗唛打印助手', printer_ok:true, port_ok:true, port:'spool\\capture.pdf'},
    printer:{name:'水洗唛', installed:true, port:'USB001', driver:'Gprinter GP-9134T',
             status:0, status_text:'就绪', level:'ok', jobs:0, ok:true, checked_at:'10:00:00'},
    capture:{exists:false}, recent:[], log_tail:['log1'],
    config_error:'', skip_print:{enabled:true, keywords:['布草','窗帘']}, rotate_dir:'ccw'
  };
  SERVER = status;

  // F1 页面脚本能跑完一次 refresh
  try { await api.refresh(); chk('F1 refresh() 可执行', true); }
  catch(e){ chk('F1 refresh() 可执行', false, String(e)); }
  chk('F1 版本号渲染', document.getElementById('ver').textContent === 'v2.2',
      document.getElementById('ver').textContent);
  chk('F1 打印机名渲染', document.getElementById('pt-name').innerHTML.indexOf('水洗唛') >= 0,
      document.getElementById('pt-name').innerHTML);
  chk('F1 打印机状态渲染', document.getElementById('pt-status').innerHTML.indexOf('就绪') >= 0,
      document.getElementById('pt-status').innerHTML);
  chk('F1 配置告警条默认隐藏', document.getElementById('cfgwarn')._cls.has('show') === false);

  // F2 轮询不打断输入
  const inp = document.getElementById('sk-input');
  inp.value = '正在输入的窗帘';
  inp.focus();
  const chips1 = document.getElementById('sk-chips').innerHTML;
  await api.refresh();
  await api.refresh();
  chk('F2 两次轮询后输入框 value 未被覆盖', inp.value === '正在输入的窗帘', inp.value);
  chk('F2 两次轮询后焦点状态未丢（未被 blur/重绘）', inp._focused === true);
  chk('F2 关键词未变时 chips 未重绘', document.getElementById('sk-chips').innerHTML === chips1);
  chk('F2 chips 内含已有关键词', chips1.indexOf('窗帘') >= 0, chips1.slice(0, 120));

  // F3 服务端关键词变化 -> 重绘
  status.skip_print = {enabled:true, keywords:['布草','窗帘','婚纱']};
  await api.refresh();
  const chips2 = document.getElementById('sk-chips').innerHTML;
  chk('F3 服务端关键词变化后 chips 重绘', chips2 !== chips1);
  chk('F3 chips 含新增关键词', chips2.indexOf('婚纱') >= 0, chips2.slice(0,160));
  chk('F3 输入框仍未受影响', inp.value === '正在输入的窗帘', inp.value);

  // F4 XSS 转义
  const bad = '"><img src=x onerror=alert(1)>';
  const e1 = api.esc(bad);
  chk('F4 esc() 转义双引号', e1.indexOf('"') === -1, e1);
  chk('F4 esc() 转义尖括号', e1.indexOf('<') === -1 && e1.indexOf('>') === -1, e1);
  status.skip_print = {enabled:true, keywords:[bad]};
  await api.refresh();
  const h = document.getElementById('sk-chips').innerHTML;
  chk('F4 恶意关键词不产生 <img> 标签', !/<img/i.test(h), h.slice(0, 200));
  chk('F4 data-kw 属性内引号已转义', h.indexOf('data-kw="' + bad + '"') === -1, h.slice(0,200));
  chk('F4 页面含 &quot;/&lt;/&gt; 实体', h.indexOf('&quot;') >= 0 && h.indexOf('&lt;') >= 0);
  chk('F4 删除按钮走 data-kw', h.indexOf("skipDel(this.getAttribute('data-kw'))") >= 0);

  // F5 告警条：config_error 非空时显示
  status.config_error = '配置文件已回退';
  await api.refresh();
  chk('F5 config_error 非空时告警条显示', document.getElementById('cfgwarn')._cls.has('show') === true);
  chk('F5 告警条文案正确', document.getElementById('cfgwarn').textContent === '配置文件已回退',
      document.getElementById('cfgwarn').textContent);

  // F6 观察项：skipSig 用空串 join，不同切分同签名
  const s1 = api.skipSig({enabled:true, keywords:['ab','c']});
  const s2 = api.skipSig({enabled:true, keywords:['a','bc']});
  res.push({name:'F6 skipSig 空串join存在签名碰撞(观察项)', ok:true, level:'WARN',
            detail:'["ab","c"] 与 ["a","bc"] 同签名=' + s1 + ' / ' + s2});
  const s3 = api.skipSig({enabled:false, keywords:['ab','c']});
  res.push({name:'F6b skipSig 区分启用状态', ok:(s1 !== s3), detail:s1 + ' vs ' + s3});

  // F7 未安装时的 similar 提示与转义
  status.printer = {name:'水洗唛打', installed:false, level:'bad', ok:false,
                    status_text:'未安装（本机找不到这台打印机）', jobs:0,
                    printers:['水洗唛','水洗唛打印助手'], similar:['水洗唛打印助手'],
                    checked_at:'10:00:00'};
  await api.refresh();
  const hint = document.getElementById('pt-hint').innerHTML;
  chk('F7 未安装时列出名字相近设备', hint.indexOf('水洗唛打印助手') >= 0, hint.slice(0,220));
  chk('F7 提示只认完全同名', hint.indexOf('只认完全同名') >= 0);
  chk('F7 打印名标记为未安装', document.getElementById('pt-name').innerHTML.indexOf('未安装') >= 0,
      document.getElementById('pt-name').innerHTML);
  status.printer.similar = ['"><img src=x onerror=alert(1)>'];
  await api.refresh();
  const hint2 = document.getElementById('pt-hint').innerHTML;
  chk('F7 similar 已转义，不产生 <img>', !/<img/i.test(hint2), hint2.slice(0,220));
  chk('F7 similar 实体转义', hint2.indexOf('&lt;img') >= 0);

  fs.writeFileSync(OUT, JSON.stringify(res, null, 1));
})().catch(function(e){
  fs.writeFileSync(OUT, JSON.stringify([{name:'F harness 异常', ok:false, detail:String(e && e.stack || e)}]));
  process.exit(3);
});
'''


def section_f():
    print("\n" + "=" * 78)
    print("F. 前端 —— web/操作页面.html（node --check + DOM 桩行为仿真）")
    print("=" * 78)
    d = tempfile.mkdtemp(prefix="washtest_fe_")
    try:
        with open(PAGE, "r", encoding="utf-8") as f:
            html = f.read()
        m = None
        import re
        m = re.search(r"<script>([\s\S]*?)</script>", html)
        rec("F0 页面含 <script>", m is not None)
        if not m:
            return
        js = os.path.join(d, "page.js")
        with open(js, "w", encoding="utf-8") as f:
            f.write(m.group(1))
        # F0-1 node --check
        try:
            p = subprocess.run(["node", "--check", js], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=60)
            rec("F0-1 node --check 语法通过", p.returncode == 0,
                (p.stderr or p.stdout or "").strip()[:200])
        except FileNotFoundError:
            rec("F0-1 node --check 语法通过", False, "未找到 node，跳过")
        # F0-2 源码静态检查
        rec("F0-2 refresh() 不写 #sk-input 的 value",
            "sk-input').value" not in m.group(1) and '$(\'sk-input\').value' not in m.group(1))
        rec("F0-2 renderSkip 有 skSig 短路", "if(sig === skSig) return;" in m.group(1))
        # F1+ 行为仿真
        hp = os.path.join(d, "harness.js")
        with open(hp, "w", encoding="utf-8") as f:
            f.write(HARNESS)
        op = os.path.join(d, "harness_out.json")
        try:
            p = subprocess.run(["node", hp, PAGE, op], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=120)
            if p.returncode != 0:
                rec("F harness 运行", False, (p.stderr or p.stdout or "")[:400])
                return
            out = read_json(op)
        except FileNotFoundError:
            rec("F harness 运行", False, "未找到 node")
            return
        for item in out:
            lvl = item.get("level") or "FAIL"
            rec(item["name"], item.get("ok"), item.get("detail", ""), level=lvl)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ================================================================ main
def main():
    print("=" * 78)
    print("水洗唛打印助手 v2.2 独立回归测试（QA）")
    print("解释器: %s" % PY)
    print("项目根: %s" % ROOT)
    print("=" * 78)

    cfg_before = sha256(USER_CFG)
    print("用户 config.json 初始 sha256 = %s" % cfg_before[:16])

    t0 = time.time()
    try:
        section_a()
        section_b()
        section_c()
        section_d()
        section_e()
        section_g()
        section_f()
    finally:
        cfg_after = sha256(USER_CFG)
        print("\n用户 config.json 结束 sha256 = %s" % cfg_after[:16])
        rec("Z0 用户 config.json 全程未被写入", cfg_before == cfg_after,
            "%s -> %s" % (cfg_before[:12], cfg_after[:12]))
        base = tempfile.gettempdir()
        left = []
        for nm in os.listdir(base):
            if nm.startswith("washtest_"):
                pth = os.path.join(base, nm)
                shutil.rmtree(pth, ignore_errors=True)
                if os.path.exists(pth):
                    left.append(pth)
        rec("Z1 临时目录(washtest_*)已全部清理", not left, str(left))

    failed = [r for r in RESULTS if not r["ok"] and r["level"] == "FAIL"]
    minor = [r for r in RESULTS if not r["ok"] and r["level"] == "MINOR"]
    warns = [r for r in RESULTS if not r["ok"] and r["level"] == "WARN"]
    passed = [r for r in RESULTS if r["ok"]]

    print("\n" + "=" * 78)
    print("汇总：共 %d 项 | PASS %d | FAIL(阻断) %d | MINOR(待裁定) %d | WARN(观察) %d | 耗时 %.1fs"
          % (len(RESULTS), len(passed), len(failed), len(minor), len(warns),
             time.time() - t0))
    if failed:
        print("\n---- 阻断性失败 ----")
        for r in failed:
            print("  FAIL   %s  |  %s" % (r["case"], r["detail"]))
    if minor:
        print("\n---- 偏差（不影响功能，待工程师/主理人裁定） ----")
        for r in minor:
            print("  MINOR  %s  |  %s" % (r["case"], r["detail"]))
    if warns:
        print("\n---- 观察项（不阻断） ----")
        for r in warns:
            print("  WARN   %s  |  %s" % (r["case"], r["detail"]))
    print("=" * 78)
    print("RESULT: %s" % ("PASS" if not failed else "FAIL"))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
