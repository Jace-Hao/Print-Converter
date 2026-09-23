# -*- coding: utf-8 -*-
"""「不打印关键词」回归测试：命中关键词的标签跳过打印；普通标签正常打印。

用例：
  1. 窗帘（测试）        -> 跳过打印（不打印）
  2. 布草（酒店）        -> 跳过打印
  3. 窗纱（测试）        -> 跳过打印
  4. 洗涤服务（加急）    -> 跳过打印
  5. 测试衬衫（可丢弃）  -> 正常打印（会真实打印 1 张测试唛，可丢弃）
  6. 测试外套（服务：已洗）-> 不命中「洗涤服务」，不应跳过

注意：脚本内含开发机绝对路径；用例 5 会真实打印 1 张测试标签。
"""
import os
import sys

ROOT = r"E:\软件开发\水洗唛打印助手"
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import pymupdf  # noqa: E402

from app.config import Config  # noqa: E402
from app.logutil import get_logger  # noqa: E402
from app.pipeline import process_pdf  # noqa: E402

TMP = r"E:\软件开发\.openclaw\tmp\skip_test"


def make_pdf(path, title):
    doc = pymupdf.open()
    page = doc.new_page(width=210 / 25.4 * 72, height=297 / 25.4 * 72)
    page.insert_text((25, 45), title, fontsize=16, fontname="china-s")
    page.insert_text((25, 72), "SKIP-TEST (discard)", fontsize=11)
    doc.save(path)
    doc.close()


def main():
    os.makedirs(TMP, exist_ok=True)
    cfg = Config(ROOT)
    log = get_logger(ROOT)

    cases = [
        ("skip_curtain.pdf", "窗帘（测试）", True, True),
        ("skip_linen.pdf", "布草（酒店）", True, True),
        ("skip_sheer.pdf", "窗纱（测试）", True, True),
        ("skip_service.pdf", "洗涤服务（加急）", True, True),
        ("normal_shirt.pdf", "测试衬衫（可丢弃）", False, False),
        ("normal_other.pdf", "测试外套（服务：已洗）", False, True),
    ]
    ok_all = True
    for fname, title, expect_skip, dry in cases:
        p = os.path.join(TMP, fname)
        make_pdf(p, title)
        res = process_pdf(cfg, log, p, dry_run=dry)
        lab = (res.get("labels") or [{}])[0]
        got = bool(lab.get("skipped"))
        ok = (got == expect_skip)
        ok_all = ok_all and ok
        print("case %-18s expect_skip=%-5s got=%-5s keyword=%-6s dry=%-5s -> %s"
              % (fname, expect_skip, got, lab.get("skip_keyword"), dry, "OK" if ok else "FAIL"))
    print("RESULT:", "PASS" if ok_all else "FAIL")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
