# -*- coding: utf-8 -*-
"""水洗唛打印助手 - 命令行入口

用法:
  python -m app.cli console                   启动后台服务 + 操作页面(软件主进程)
  python -m app.cli watch                     常驻监视(捕获->旋转->打印)
  python -m app.cli once <pdf> [--dry-run] [--force]    处理单个文件
  python -m app.cli printers                  打印机信息与分辨率
  python -m app.cli vp [install|uninstall|status]  虚拟打印机(水洗唛打印助手)
  python -m app.cli info <pdf>                PDF 页面几何信息
  python -m app.cli calibrate                打印旋转方向校准标签(两版)
  python -m app.cli cleanup                  立即清理归档/预览中的过期文件
"""
import argparse
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _setup():
    from app.config import Config
    from app.logutil import get_logger

    cfg = Config(PROJECT_ROOT)
    log = get_logger(PROJECT_ROOT)
    return cfg, log


def cmd_watch(args, cfg, log):
    from app.console import instance_running

    if instance_running() and not args.force:
        print("后台服务已在运行（操作页面模式）。如需命令行监视，请先停止软件，或添加 --force 参数。")
        return
    from app.watcher import Watcher

    Watcher(cfg, log).run(once=args.once)


def cmd_console(args, cfg, log):
    from app.console import run as console_run

    rc = console_run()
    if rc:
        log.warning("console 返回码 %d", rc)


def cmd_once(args, cfg, log):
    from app.pipeline import process_pdf

    if not args.force:
        from app.watcher import Watcher

        ok, why = Watcher(cfg, log)._validate(args.pdf)
        if not ok:
            print(json.dumps({"ok": False, "reason": why}, ensure_ascii=False))
            log.warning("未通过标签校验: %s (%s)", args.pdf, why)
            return
    res = process_pdf(cfg, log, args.pdf, dry_run=args.dry_run)
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))


def cmd_printers(args, cfg, log):
    import win32print

    from app.printutil import printer_info

    out = {"printers": [], "default": win32print.GetDefaultPrinter()}
    for p in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS):
        out["printers"].append({"name": p[2], "driver": p[3], "port": p[4] if len(p) > 4 else ""})
    try:
        out["target"] = printer_info(cfg["print"]["printer"])
    except Exception as e:
        out["target_error"] = str(e)
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))


def cmd_vp(args, cfg, log):
    from app import vpinstall

    rc = vpinstall.main([args.action])
    if rc:
        log.warning("vpinstall 返回码 %d", rc)


def cmd_info(args, cfg, log):
    import pymupdf

    doc = pymupdf.open(args.pdf)
    info = {"file": args.pdf, "pages": len(doc), "items": []}
    for i, page in enumerate(doc):
        info["items"].append({
            "page": i,
            "mm": [round(page.rect.width / 72 * 25.4, 2), round(page.rect.height / 72 * 25.4, 2)],
            "rotation": page.rotation,
        })
    doc.close()
    print(json.dumps(info, ensure_ascii=False, indent=2))


def _mock_label_page(dpi):
    """合成一个 120x30mm 的横版标签(测试内容, 不含真实客户数据)"""
    from PIL import Image, ImageDraw, ImageFont

    w = int(round(120 / 25.4 * dpi))
    h = int(round(30 / 25.4 * dpi))
    im = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(im)
    try:
        f = ImageFont.truetype("msyh.ttc", int(3.4 / 25.4 * dpi))
        f2 = ImageFont.truetype("msyh.ttc", int(3.0 / 25.4 * dpi))
    except Exception:
        f = f2 = ImageFont.load_default()
    x = int(4 / 25.4 * dpi)
    y = int(1.5 / 25.4 * dpi)
    for ln in ["短袖衬衫（普通） 蓝色 干洗", "电：13800000000 测试顾客 单：1100000001 件：1-2", "下单：09-22 品牌：测试", "损： 服务："]:
        d.text((x, y), ln, fill="black", font=f)
        y += int(5.2 / 25.4 * dpi)
    d.text((int(92 / 25.4 * dpi), int(2 / 25.4 * dpi)), "星测洗衣", fill="black", font=f2)
    d.text((int(92 / 25.4 * dpi), int(10 / 25.4 * dpi)), "1234567890123", fill="black", font=f2)
    return im


def cmd_calibrate(args, cfg, log):
    """打印两版旋转方向的校准标签: 第1版顺时针, 第2版逆时针"""
    from PIL import ImageDraw, ImageFont

    from app.printutil import print_image, to_mono
    from app.render import compose_label

    page = _mock_label_page(int(cfg["pipeline"]["render_dpi"]))
    old = cfg["pipeline"]["rotate_dir"]
    try:
        for idx, dirv in (("1", "cw"), ("2", "ccw")):
            cfg["pipeline"]["rotate_dir"] = dirv
            canvas, _ = compose_label(page, cfg)
            d = ImageDraw.Draw(canvas)
            d.rectangle([0, 0, canvas.width - 1, canvas.height - 1], outline="black", width=3)
            try:
                fm = ImageFont.truetype("msyh.ttc", 46)
            except Exception:
                fm = ImageFont.load_default()
            d.text((14, 10), "第%s版 %s" % (idx, "顺时针" if dirv == "cw" else "逆时针"), fill="black", font=fm)
            mono = to_mono(canvas, True)
            print_image(cfg["print"]["printer"], mono, doc_name="水洗唛校准-" + idx)
            log.info("已打印校准标签 第%s版 (%s)", idx, dirv)
    finally:
        cfg["pipeline"]["rotate_dir"] = old


def cmd_cleanup(args, cfg, log):
    from app import retention

    n = retention.cleanup(cfg, log, force=True)
    print(json.dumps({"ok": True, "removed": n,
                      "days": (cfg.get("cleanup") or {}).get("days", 7)},
                     ensure_ascii=False))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="水洗唛打印助手")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("console", help="启动后台服务 + 操作页面")
    p.set_defaults(func=cmd_console)

    p = sub.add_parser("watch", help="常驻监视")
    p.add_argument("--once", action="store_true")
    p.add_argument("--force", action="store_true", help="忽略已运行的后台服务")
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("once", help="处理单个 PDF")
    p.add_argument("pdf")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true", help="跳过标签尺寸校验")
    p.set_defaults(func=cmd_once)

    p = sub.add_parser("printers", help="打印机信息")
    p.set_defaults(func=cmd_printers)

    p = sub.add_parser("vp", help="虚拟打印机 install|uninstall|status")
    p.add_argument("action", nargs="?", default="status", choices=["install", "uninstall", "status"])
    p.set_defaults(func=cmd_vp)

    p = sub.add_parser("info", help="PDF 信息")
    p.add_argument("pdf")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("calibrate", help="打印旋转方向校准标签")
    p.set_defaults(func=cmd_calibrate)

    p = sub.add_parser("cleanup", help="立即清理归档/预览中的过期文件")
    p.set_defaults(func=cmd_cleanup)

    args = ap.parse_args(argv)
    cfg, log = _setup()
    args.func(args, cfg, log)


if __name__ == "__main__":
    main()
