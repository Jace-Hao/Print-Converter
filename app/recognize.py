# -*- coding: utf-8 -*-
"""水洗唛打印助手 - 打印数据识别

从捕获的标签 PDF 中提取字段（单号、客户、衣物名称、颜色、件数、品牌等）。
识别结果用于「标签内容编辑器」的预填；识别不完美的字段可直接在编辑器中修改。
"""
import re

import pymupdf

FIELD_ORDER = ["衣物名称", "颜色", "工艺", "电话", "客户", "单号", "件数",
               "下单日期", "品牌", "损坏说明", "服务项目", "门店名", "条码号"]

_START_TOKENS = ("电：", "电:", "电话：", "电话:", "单：", "单:", "件：", "件:",
                 "下单", "品牌", "损：", "损:", "服务")


def extract_text(pdf_path, page_index=0):
    doc = pymupdf.open(pdf_path)
    try:
        if len(doc) == 0:
            return ""
        return doc[page_index].get_text("text")
    finally:
        doc.close()


def recognize_fields(pdf_path, page_index=0):
    return parse_fields(extract_text(pdf_path, page_index))


def parse_fields(text):
    """从标签文本中解析字段；找不到的返回空字符串。"""
    fields = {k: "" for k in FIELD_ORDER}
    if not text:
        return fields
    flat = re.sub(r"[ \t]+", " ", text)

    # 电话 / 客户：电：<电话> <客户> 单：
    m = re.search(r"电[话]?[：:][ \t]*(\S+?)[ \t]+([^\s：:]+?)[ \t]+单[：:]", flat)
    if m:
        fields["电话"], fields["客户"] = m.group(1), m.group(2)
    else:
        m = re.search(r"电[话]?[：:][ \t]*(\S+)", flat)
        if m:
            fields["电话"] = m.group(1)

    # 单号 / 件数 / 下单日期 / 品牌（[ \t] 限定同一行内取值，避免跨行误配）
    m = re.search(r"单[：:][ \t]*([0-9A-Za-z\-]+)", flat)
    if m:
        fields["单号"] = m.group(1)
    m = re.search(r"件[：:][ \t]*(\S+)", flat)
    if m:
        fields["件数"] = m.group(1)
    m = re.search(r"下单[：:][ \t]*(\S+)", flat)
    if m:
        fields["下单日期"] = m.group(1)
    m = re.search(r"品牌[：:][ \t]*([^\s\n]*)", flat)
    if m:
        fields["品牌"] = m.group(1).strip()

    # 损坏说明 / 服务项目
    m = re.search(r"损[：:][ \t]*([^\n]*?)(?=[ \t]*服务[：:]|$)", flat)
    if m:
        fields["损坏说明"] = m.group(1).strip()
    m = re.search(r"服务[：:][ \t]*([^\n]*)", flat)
    if m:
        fields["服务项目"] = m.group(1).strip()

    # 条码号：10-14 位数字（先剔除电话号码与单号，避免误判）
    bc_text = flat
    for v in (fields.get("电话"), fields.get("单号")):
        if v:
            bc_text = bc_text.replace(v, " ")
    candidates = re.findall(r"(?<!\d)(\d{10,14})(?!\d)", bc_text)
    if candidates:
        fields["条码号"] = candidates[0]

    # 衣物行 + 门店名（按文本行顺序推断）
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    item_line = ""
    others = []
    for ln in lines:
        if ln.startswith(_START_TOKENS) or re.fullmatch(r"[0-9\s\-\.]+", ln):
            continue
        if not item_line:
            item_line = ln
        else:
            others.append(ln)

    if item_line:
        toks = item_line.split()
        if len(toks) >= 3:
            fields["衣物名称"] = " ".join(toks[:-2])
            fields["颜色"] = toks[-2]
            fields["工艺"] = toks[-1]
        elif len(toks) == 2:
            fields["衣物名称"] = toks[0]
            fields["工艺"] = toks[1]
        elif len(toks) == 1:
            fields["衣物名称"] = toks[0]

    # 门店名：剩余行中最像店名的一行（含"洗衣/店/馆/中心"优先）
    if others:
        pick = ""
        for ln in others:
            if 3 <= len(ln) <= 20 and not re.fullmatch(r"[0-9A-Za-z\-]+", ln):
                pick = ln
                if re.search(r"洗衣|店|馆|中心|干洗", ln):
                    break
        fields["门店名"] = pick

    return fields
