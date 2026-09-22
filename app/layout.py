# -*- coding: utf-8 -*-
"""水洗唛打印助手 - 布局模板渲染引擎

模板 JSON 结构 (templates/<名称>.json):
{
  "name": "默认",
  "canvas_mm": [120, 30],
  "elements": [
    {"type": "text", "x_mm": 7.6, "y_mm": 1.2, "size_mm": 3.9, "bold": false,
     "align": "left", "text": "{衣物名称}  {颜色}  {工艺}"},
    {"type": "barcode", "x_mm": 91.0, "y_mm": 5.2, "width_mm": 28.0, "height_mm": 7.2,
     "align": "center", "show_digits": false, "source": "条码号"},
    {"type": "line", "x1_mm": 2, "y1_mm": 20, "x2_mm": 118, "y2_mm": 20, "width_mm": 0.2}
  ]
}

- 文本内容支持 {字段} 占位（识别字段名），如 {客户}；另有 {今日}。
- 元素在 120x30mm 横版设计空间内布局；打印走既有旋转管线，与自动链路一致。
"""
import json
import os
import re
import time

from PIL import Image, ImageDraw, ImageFont

FONT_PATH = "msyh.ttc"
FONT_BOLD = "msyhbd.ttc"
_FIELD_RE = re.compile(r"\{([^{}]+)\}")

TEMPLATES_DIRNAME = "templates"


def _mm(v, dpi):
    return v / 25.4 * dpi


def _font(size_mm, dpi, bold=False):
    px = max(1, int(round(_mm(size_mm, dpi))))
    for path in ([FONT_BOLD, FONT_PATH] if bold else [FONT_PATH]):
        try:
            return ImageFont.truetype(path, px)
        except Exception:
            continue
    return ImageFont.load_default()


def resolve_text(text, fields):
    def sub(m):
        key = m.group(1).strip()
        if key in ("今日", "今天"):
            return time.strftime("%m-%d")
        return str((fields or {}).get(key, "") or "")
    return _FIELD_RE.sub(sub, text or "")


def default_template():
    """默认模板: 尽量贴近原版水洗唛样式(实测坐标: 左侧信息栏 + 右侧门店名/条码)。"""
    return {
        "name": "默认",
        "canvas_mm": [120, 30],
        "elements": [
            {"type": "text", "x_mm": 7.6, "y_mm": 1.2, "size_mm": 4.0,
             "text": "{衣物名称}  {颜色}  {工艺}"},
            {"type": "text", "x_mm": 7.6, "y_mm": 7.7, "size_mm": 3.4,
             "text": "电：{电话}  {客户}  单：{单号}  件：{件数}"},
            {"type": "text", "x_mm": 7.6, "y_mm": 13.1, "size_mm": 3.4,
             "text": "下单：{下单日期}  品牌：{品牌}"},
            {"type": "text", "x_mm": 7.6, "y_mm": 18.4, "size_mm": 3.4,
             "text": "损：{损坏说明}"},
            {"type": "text", "x_mm": 7.6, "y_mm": 23.8, "size_mm": 3.4,
             "text": "服务：{服务项目}"},
            {"type": "text", "x_mm": 102.7, "y_mm": 1.3, "size_mm": 4.3, "align": "right",
             "text": "{门店名}"},
            {"type": "barcode", "x_mm": 91.0, "y_mm": 5.0, "width_mm": 28.0, "height_mm": 7.4,
             "align": "center", "show_digits": False},
            {"type": "text", "x_mm": 91.0, "y_mm": 12.8, "size_mm": 3.3, "align": "center",
             "text": "{条码号}"},
        ],
    }


def templates_dir(cfg):
    return os.path.join(cfg.root, TEMPLATES_DIRNAME)


def ensure_default(cfg):
    d = templates_dir(cfg)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "默认.json")
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default_template(), f, ensure_ascii=False, indent=2)
    return path


def list_templates(cfg):
    d = templates_dir(cfg)
    os.makedirs(d, exist_ok=True)
    out = []
    for name in sorted(os.listdir(d)):
        if name.lower().endswith(".json"):
            out.append(name[:-5])
    if "默认" not in out:
        out.insert(0, "默认")
    return out


def _safe_name(name):
    name = (name or "").strip()
    for ch in '\\/:*?"<>|':
        name = name.replace(ch, "")
    return name


def load_template(cfg, name=None):
    """按名称加载模板; name 为空时用默认模板。"""
    name = _safe_name(name) or "默认"
    ensure_default(cfg)
    path = os.path.join(templates_dir(cfg), name + ".json")
    if not os.path.exists(path):
        if name == "默认":
            return default_template()
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            tpl = json.load(f)
        tpl.setdefault("canvas_mm", [120, 30])
        tpl.setdefault("elements", [])
        return tpl
    except Exception:
        return None


def save_template(cfg, name, template):
    name = _safe_name(name)
    if not name:
        raise ValueError("模板名不能为空")
    ensure_default(cfg)
    template = dict(template or {})
    template["name"] = name
    template.setdefault("canvas_mm", [120, 30])
    template.setdefault("elements", [])
    path = os.path.join(templates_dir(cfg), name + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(template, f, ensure_ascii=False, indent=2)
    return path


def delete_template(cfg, name):
    name = _safe_name(name)
    if name == "默认":
        raise ValueError("默认模板不可删除")
    path = os.path.join(templates_dir(cfg), name + ".json")
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def render_template(template, fields, dpi=300):
    """将模板 + 字段渲染为 120x30mm 横版设计稿(PIL 图)。"""
    cw_mm, ch_mm = (template or {}).get("canvas_mm", [120, 30])
    W = int(round(_mm(cw_mm, dpi)))
    H = int(round(_mm(ch_mm, dpi)))
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    for el in (template or {}).get("elements", []):
        try:
            _draw_element(img, d, el, fields, dpi)
        except Exception:
            continue
    return img


def _anchor_x(el, dpi, width_px):
    x = _mm(el.get("x_mm", 0), dpi)
    align = el.get("align", "left")
    if align == "center":
        x -= width_px / 2.0
    elif align == "right":
        x -= width_px
    return x


def _draw_element(img, d, el, fields, dpi):
    et = el.get("type")
    y = _mm(el.get("y_mm", 0), dpi)
    if et == "text":
        txt = resolve_text(el.get("text", ""), fields).strip()
        if not txt:
            return
        f = _font(el.get("size_mm", 3.5), dpi, bool(el.get("bold")))
        w = d.textlength(txt, font=f)
        x = _anchor_x(el, dpi, w)
        d.text((x, y), txt, fill="black", font=f)
    elif et == "barcode":
        val = str((fields or {}).get(el.get("source", "条码号")) or "").strip()
        if not val:
            return
        from .labelgen import _barcode_image
        w_box = int(round(_mm(el.get("width_mm", 28.0), dpi)))
        h_box = int(round(_mm(el.get("height_mm", 7.0), dpi)))
        bc = _barcode_image(val, dpi, w_box, h_box)
        if bc is None:
            return
        x = _anchor_x(el, dpi, bc.width)
        img.paste(bc, (int(round(x)), int(round(y))))
        if el.get("show_digits"):
            fd = _font(el.get("digits_size_mm", 3.0), dpi)
            tw = d.textlength(val, font=fd)
            xd = _anchor_x(el, dpi, tw)
            d.text((xd, y + bc.height + _mm(0.4, dpi)), val, fill="black", font=fd)
    elif et == "line":
        x1 = _mm(el.get("x1_mm", 0), dpi)
        y1 = _mm(el.get("y1_mm", 0), dpi)
        x2 = _mm(el.get("x2_mm", 0), dpi)
        y2 = _mm(el.get("y2_mm", 0), dpi)
        w = max(1, int(round(_mm(el.get("width_mm", 0.25), dpi))))
        d.line([(x1, y1), (x2, y2)], fill="black", width=w)


def print_layout(cfg, log, template, fields, dry_run=False):
    """渲染模板 -> 旋转排版(与自动链路一致) -> 打印；返回预览存档路径。"""
    import datetime

    from app.printutil import print_image, to_mono
    from app.render import compose_label

    dpi = int(cfg["pipeline"]["render_dpi"])
    page = render_template(template, fields, dpi=dpi)
    canvas, _info = compose_label(page, cfg)
    mono = to_mono(canvas, bool(cfg["print"]["dither"]), int(cfg["print"]["threshold"]))

    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    prev_dir = cfg.path_of("previews")
    os.makedirs(prev_dir, exist_ok=True)
    prev = os.path.join(prev_dir, "layout-%s.png" % ts)
    mono.save(prev)
    try:
        with open(os.path.join(prev_dir, "layout-%s.json" % ts), "w", encoding="utf-8") as f:
            json.dump({"template": (template or {}).get("name"), "fields": fields},
                      f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    if dry_run:
        log.info("dry_run 布局标签预览: %s", prev)
    else:
        print_image(cfg["print"]["printer"], mono, doc_name="布局水洗唛-" + ts,
                    copies=int(cfg["print"]["copies"]))
        log.info("布局标签已打印: %s", prev)
    return prev
