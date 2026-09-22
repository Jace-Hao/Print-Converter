# -*- coding: utf-8 -*-
"""水洗唛打印助手 - 布局设计器 (tkinter)

自由设计 120x30mm 水洗唛布局：文本（支持 {字段} 占位）/ 条码 / 线条，拖动排版；
数据可识别最近打印或手工填写；横版设计与竖版打印效果预览；直接打印到标签机。
用法：python app/designer.py [--selftest]
"""
import argparse
import copy
import os
import sys
import threading
import traceback
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PIL import Image, ImageTk  # noqa: E402

from app.config import Config  # noqa: E402
from app.layout import (default_template, delete_template, ensure_default,  # noqa: E402
                        list_templates, load_template, print_layout,
                        render_template, resolve_text, save_template)
from app.logutil import get_logger  # noqa: E402
from app.recognize import FIELD_ORDER, recognize_fields  # noqa: E402

SAMPLE_DATA = {
    "衣物名称": "羽绒服", "颜色": "深蓝色", "工艺": "干洗",
    "电话": "13800000000", "客户": "张小伟", "单号": "1100099999", "件数": "1-1",
    "下单日期": "09-22", "品牌": "", "损坏说明": "", "服务项目": "清洁保养",
    "门店名": "星测洗衣", "条码号": "110000099999",
}

ZOOMS = [0.4, 0.5, 0.62, 0.78]


class Designer:
    def __init__(self):
        self.cfg = Config(ROOT)
        self.log = get_logger(ROOT)
        ensure_default(self.cfg)
        self.template = load_template(self.cfg, self.cfg["pipeline"].get("layout_template") or "默认") \
            or default_template()
        self.data = dict(SAMPLE_DATA)
        self.sel = -1
        self.zoom_i = 1
        self._drag = None
        self._pt = None
        self._prev_refs = []
        self._prop_vars = {}
        self._syncing = False
        self._items = []
        self._bboxes = []
        self.root = tk.Tk()
        self.root.title('水洗唛打印助手 - 布局设计器')
        self.root.geometry('1320x800')
        self.root.minsize(1100, 640)
        self._build()
        self._refresh_tpl_list()
        self.refresh_all()

    # ---------- 辅助 ----------
    def _btn(self, parent, text, cmd, width=7):
        b = tk.Button(parent, text=text, command=self._wrap(cmd), width=width,
                      font=('Microsoft YaHei', 9))
        b.pack(side='left', padx=2)
        return b

    def _wrap(self, fn):
        def inner():
            try:
                fn()
            except Exception as e:
                self.log.exception('designer: %s', e)
                messagebox.showerror('错误', str(e))
        return inner

    @property
    def zf(self):
        return ZOOMS[self.zoom_i]

    def ppm(self):
        return 1417.0 / 120.0 * self.zf

    # ---------- UI ----------
    def _build(self):
        bar = tk.Frame(self.root)
        bar.pack(fill='x', padx=10, pady=(8, 4))
        tk.Label(bar, text='模板:', font=('Microsoft YaHei', 10)).pack(side='left')
        self.tpl_box = ttk.Combobox(bar, width=14, state='readonly')
        self.tpl_box.pack(side='left', padx=(2, 6))
        self._btn(bar, '打开', self.on_open_tpl)
        self._btn(bar, '保存', self.on_save)
        self._btn(bar, '另存为', self.on_save_as, width=8)
        self._btn(bar, '删除', self.on_delete_tpl)
        tk.Label(bar, text='　数据:', font=('Microsoft YaHei', 10)).pack(side='left', padx=(14, 0))
        self._btn(bar, '示例数据', lambda: self.set_data(dict(SAMPLE_DATA), '示例数据'), width=9)
        self._btn(bar, '识别最近打印', self.on_recognize, width=11)
        self._btn(bar, '编辑数据...', self.on_edit_data, width=9)

        bar2 = tk.Frame(self.root)
        bar2.pack(fill='x', padx=10, pady=(0, 6))
        self._btn(bar2, '渲染预览', self.on_preview, width=9)
        self._btn(bar2, '打印测试...', self.on_print, width=9)
        self.auto_var = tk.BooleanVar(value=False)
        tk.Checkbutton(bar2, text='用于自动打印（打印时按此布局重排）', variable=self.auto_var,
                       font=('Microsoft YaHei', 10), command=self.on_auto_toggle).pack(side='left', padx=12)
        tk.Label(bar2, text='缩放:', font=('Microsoft YaHei', 10)).pack(side='left', padx=(16, 2))
        self._btn(bar2, '－', lambda: self.on_zoom(-1), width=3)
        self._btn(bar2, '＋', lambda: self.on_zoom(1), width=3)
        tk.Label(bar2, text='提示：拖动元素移动；方向键微调(Shift=精细)；Delete 删除',
                 font=('Microsoft YaHei', 9), fg='#666').pack(side='left', padx=16)

        body = tk.Frame(self.root)
        body.pack(fill='both', expand=True, padx=10)

        left = tk.Frame(body)
        left.pack(side='left', fill='y')
        tk.Label(left, text='元素列表', font=('Microsoft YaHei', 10, 'bold')).pack(anchor='w')
        self.elem_list = tk.Listbox(left, width=32, font=('Microsoft YaHei', 9), exportselection=False)
        self.elem_list.pack(fill='y', expand=True, pady=2)
        self.elem_list.bind('<<ListboxSelect>>', self.on_list_select)
        lb = tk.Frame(left)
        lb.pack(fill='x')
        self._btn(lb, '添加文本', self.add_text, width=8)
        self._btn(lb, '添加条码', self.add_barcode, width=8)
        self._btn(lb, '添加线条', self.add_line, width=8)
        lb2 = tk.Frame(left)
        lb2.pack(fill='x', pady=2)
        self._btn(lb2, '上移', lambda: self.move_elem(-1), width=8)
        self._btn(lb2, '下移', lambda: self.move_elem(1), width=8)
        self._btn(lb2, '复制', self.dup_elem, width=8)
        self._btn(lb2, '删除', self.del_elem, width=8)

        center = tk.Frame(body)
        center.pack(side='left', fill='both', expand=True, padx=8)
        self.canvas = tk.Canvas(center, background='#F6F3EE', highlightthickness=1,
                                highlightbackground='#999')
        self.canvas.pack(pady=6)
        self.canvas.bind('<Button-1>', self.on_click)
        self.canvas.bind('<B1-Motion>', self.on_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_release)
        self.canvas.bind('<Left>', lambda e: self.nudge(-0.5, 0))
        self.canvas.bind('<Right>', lambda e: self.nudge(0.5, 0))
        self.canvas.bind('<Up>', lambda e: self.nudge(0, -0.5))
        self.canvas.bind('<Down>', lambda e: self.nudge(0, 0.5))
        self.canvas.bind('<Shift-Left>', lambda e: self.nudge(-0.1, 0))
        self.canvas.bind('<Shift-Right>', lambda e: self.nudge(0.1, 0))
        self.canvas.bind('<Shift-Up>', lambda e: self.nudge(0, -0.1))
        self.canvas.bind('<Shift-Down>', lambda e: self.nudge(0, 0.1))
        self.canvas.bind('<Delete>', lambda e: self.del_elem())
        self.snap = tk.BooleanVar(value=True)
        tk.Checkbutton(center, text='拖动吸附(0.5mm)', variable=self.snap,
                       font=('Microsoft YaHei', 9)).pack()

        right = tk.Frame(body)
        right.pack(side='left', fill='y')
        tk.Label(right, text='属性', font=('Microsoft YaHei', 10, 'bold')).pack(anchor='w')
        self.props = tk.Frame(right, width=300)
        self.props.pack(fill='y', expand=True, pady=2)
        self.props.pack_propagate(False)

        self.status = tk.StringVar(
            value='就绪：拖动排版 → 渲染预览 → 打印测试；勾选「用于自动打印」后，以后每张标签都会按此布局重排。')
        tk.Label(self.root, textvariable=self.status, anchor='w',
                 font=('Microsoft YaHei', 9)).pack(fill='x', padx=10, pady=(4, 8))

    # ---------- 画布 ----------
    def refresh_all(self):
        self.redraw()
        self.refresh_list()
        self.build_props()
        self._update_auto_flag()

    def redraw(self):
        c = self.canvas
        c.delete('all')
        ppm = self.ppm()
        W, H = int(120 * ppm), int(30 * ppm)
        c.config(width=W + 2, height=H + 2)
        for mm in range(0, 121, 5):
            c.create_line(mm * ppm, 0, mm * ppm, H, fill='#E6E0D8')
        for mm in range(0, 31, 5):
            c.create_line(0, mm * ppm, W, mm * ppm, fill='#E6E0D8')
        for mm in range(0, 121, 10):
            c.create_line(mm * ppm, 0, mm * ppm, H, fill='#D9D2C6')
        c.create_rectangle(0, 0, W, H, outline='#888')
        self._items = []
        self._bboxes = []
        for el in self.template.get('elements', []):
            ids = self._draw_elem(c, el, ppm)
            self._items.append(ids)
            bb = None
            for it in ids:
                b = c.bbox(it)
                if b:
                    bb = b if bb is None else (min(bb[0], b[0]), min(bb[1], b[1]),
                                               max(bb[2], b[2]), max(bb[3], b[3]))
            self._bboxes.append(bb)
        if 0 <= self.sel < len(self._bboxes) and self._bboxes[self.sel]:
            x0, y0, x1, y1 = self._bboxes[self.sel]
            c.create_rectangle(x0 - 3, y0 - 3, x1 + 3, y1 + 3, outline='#D2691E',
                               dash=(4, 2), width=2)

    def _draw_elem(self, c, el, ppm):
        t = el.get('type')
        try:
            if t == 'text':
                txt = resolve_text(el.get('text', ''), self.data).strip()
                fill = 'black'
                if not txt:
                    txt = (el.get('text', '') or '(空)')
                    fill = '#AAAAAA'
                size = max(7, int(round(float(el.get('size_mm', 3.5)) * ppm)))
                anchor = {'left': 'nw', 'center': 'n', 'right': 'ne'}.get(el.get('align', 'left'), 'nw')
                style = 'bold' if el.get('bold') else 'normal'
                return [c.create_text(float(el.get('x_mm', 0)) * ppm, float(el.get('y_mm', 0)) * ppm,
                                      text=txt, anchor=anchor, fill=fill,
                                      font=('Microsoft YaHei', size, style))]
            if t == 'barcode':
                x = float(el.get('x_mm', 91))
                y = float(el.get('y_mm', 5))
                w = float(el.get('width_mm', 28))
                h = float(el.get('height_mm', 7.4))
                align = el.get('align', 'center')
                x0 = x - w / 2 if align == 'center' else (x - w if align == 'right' else x)
                ids = [c.create_rectangle(x0 * ppm, y * ppm, (x0 + w) * ppm, (y + h) * ppm,
                                          outline='#8FA6B5', fill='#E9EFF3')]
                ids.append(c.create_text((x0 + w / 2) * ppm, (y + h / 2) * ppm, text='▮▯ 条码',
                                         fill='#5B7385',
                                         font=('Microsoft YaHei', max(7, int(h * ppm * 0.35)))))
                return ids
            if t == 'line':
                return [c.create_line(float(el.get('x1_mm', 0)) * ppm, float(el.get('y1_mm', 0)) * ppm,
                                      float(el.get('x2_mm', 0)) * ppm, float(el.get('y2_mm', 0)) * ppm,
                                      fill='black',
                                      width=max(1, int(round(float(el.get('width_mm', 0.25)) * ppm))))]
        except Exception:
            return []
        return []

    def hit(self, x, y):
        for i in range(len(self._items) - 1, -1, -1):
            b = self._bboxes[i]
            if b and b[0] - 3 <= x <= b[2] + 3 and b[1] - 3 <= y <= b[3] + 3:
                return i
        return -1

    def on_click(self, ev):
        self.canvas.focus_set()
        idx = self.hit(ev.x, ev.y)
        self.sel = idx
        self.refresh_list()
        self.redraw()
        self.build_props()
        if idx >= 0:
            el = self.template['elements'][idx]
            d = {'i': idx, 'mx': ev.x, 'my': ev.y}
            if el.get('type') == 'line':
                d.update({'k': ['x1_mm', 'y1_mm', 'x2_mm', 'y2_mm']})
                for k in d['k']:
                    d[k] = float(el.get(k, 0))
            else:
                d.update({'k': ['x_mm', 'y_mm'],
                          'x_mm': float(el.get('x_mm', 0)), 'y_mm': float(el.get('y_mm', 0))})
            self._drag = d

    def on_drag(self, ev):
        if not self._drag:
            return
        d = self._drag
        el = self.template['elements'][d['i']]
        ppm = self.ppm()
        dx = (ev.x - d['mx']) / ppm
        dy = (ev.y - d['my']) / ppm
        for k in d['k']:
            v = d[k] + (dx if k.startswith('x') else dy)
            if self.snap.get():
                v = round(v * 2) / 2
            el[k] = round(v, 2)
        self.redraw()
        self._sync_props()

    def on_release(self, ev):
        self._drag = None
        self.refresh_list()

    def nudge(self, dx, dy):
        if not (0 <= self.sel < len(self.template.get('elements', []))):
            return
        el = self.template['elements'][self.sel]
        keys = ['x1_mm', 'y1_mm', 'x2_mm', 'y2_mm'] if el.get('type') == 'line' else ['x_mm', 'y_mm']
        for k in keys:
            v = float(el.get(k, 0)) + (dx if k.startswith('x') else dy)
            el[k] = round(v, 2)
        self.redraw()
        self._sync_props()
        self.refresh_list()

    # ---------- 元素操作 ----------
    def add_text(self):
        self.template['elements'].append(
            {"type": "text", "x_mm": 7.0, "y_mm": 4.0, "size_mm": 3.5, "text": "新文本",
             "align": "left"})
        self.sel = len(self.template['elements']) - 1
        self.refresh_all()

    def add_barcode(self):
        self.template['elements'].append(
            {"type": "barcode", "x_mm": 91.0, "y_mm": 5.0, "width_mm": 28.0, "height_mm": 7.4,
             "align": "center", "source": "条码号"})
        self.sel = len(self.template['elements']) - 1
        self.refresh_all()

    def add_line(self):
        self.template['elements'].append(
            {"type": "line", "x1_mm": 5.0, "y1_mm": 15.0, "x2_mm": 115.0, "y2_mm": 15.0,
             "width_mm": 0.25})
        self.sel = len(self.template['elements']) - 1
        self.refresh_all()

    def del_elem(self):
        if not (0 <= self.sel < len(self.template.get('elements', []))):
            return
        self.template['elements'].pop(self.sel)
        self.sel = min(self.sel, len(self.template['elements']) - 1)
        self.refresh_all()

    def dup_elem(self):
        if not (0 <= self.sel < len(self.template.get('elements', []))):
            return
        el = copy.deepcopy(self.template['elements'][self.sel])
        if el.get('type') == 'line':
            el['y1_mm'] = round(float(el.get('y1_mm', 0)) + 2, 2)
            el['y2_mm'] = round(float(el.get('y2_mm', 0)) + 2, 2)
        else:
            el['y_mm'] = round(float(el.get('y_mm', 0)) + 2, 2)
        self.template['elements'].insert(self.sel + 1, el)
        self.sel += 1
        self.refresh_all()

    def move_elem(self, d):
        i = self.sel
        n = len(self.template.get('elements', []))
        if not (0 <= i < n) or not (0 <= i + d < n):
            return
        els = self.template['elements']
        els[i], els[i + d] = els[i + d], els[i]
        self.sel = i + d
        self.refresh_all()

    def on_list_select(self, ev=None):
        sel = self.elem_list.curselection()
        if sel:
            self.sel = int(sel[0])
            self.redraw()
            self.build_props()

    # ---------- 属性 ----------
    def build_props(self):
        for w in self.props.winfo_children():
            w.destroy()
        self._prop_vars = {}
        if not (0 <= self.sel < len(self.template.get('elements', []))):
            tk.Label(self.props, text='（未选中元素）', fg='#888',
                     font=('Microsoft YaHei', 9)).pack(anchor='w', pady=6)
            return
        el = self.template['elements'][self.sel]
        t = el.get('type')
        self._syncing = True

        def prow(label, key, width=10):
            f = tk.Frame(self.props)
            f.pack(fill='x', pady=2)
            tk.Label(f, text=label, width=8, anchor='e', font=('Microsoft YaHei', 9)).pack(side='left')
            var = tk.StringVar(value=str(el.get(key, '')))
            ent = tk.Entry(f, textvariable=var, width=width, font=('Microsoft YaHei', 9))
            ent.pack(side='left')
            self._prop_vars[key] = var
            return var, ent

        def num(label, key):
            var, ent = prow(label, key)

            def apply(_=None):
                if self._syncing:
                    return
                try:
                    el[key] = round(float(var.get()), 2)
                except Exception:
                    return
                self.redraw()
                self.refresh_list()
            ent.bind('<Return>', apply)
            ent.bind('<FocusOut>', apply)

        def align_row():
            f = tk.Frame(self.props)
            f.pack(fill='x', pady=2)
            tk.Label(f, text='对齐', width=8, anchor='e', font=('Microsoft YaHei', 9)).pack(side='left')
            var = tk.StringVar(value=el.get('align', 'left'))
            self._prop_vars['align'] = var
            om = ttk.Combobox(f, textvariable=var, values=['left', 'center', 'right'],
                              width=8, state='readonly')
            om.pack(side='left')

            def apply(_=None):
                if self._syncing:
                    return
                el['align'] = var.get()
                self.redraw()
            om.bind('<<ComboboxSelected>>', apply)

        if t == 'text':
            f = tk.Frame(self.props)
            f.pack(fill='x', pady=2)
            tk.Label(f, text='内容', width=8, anchor='e', font=('Microsoft YaHei', 9)).pack(side='left')
            var = tk.StringVar(value=el.get('text', ''))
            self._prop_vars['text'] = var
            ent = tk.Entry(f, textvariable=var, width=26, font=('Microsoft YaHei', 9))
            ent.pack(side='left')

            def tapply(*a):
                if self._syncing:
                    return
                el['text'] = var.get()
                self.redraw()
                self.refresh_list()
            var.trace_add('write', tapply)
            num('X(mm)', 'x_mm')
            num('Y(mm)', 'y_mm')
            num('字号(mm)', 'size_mm')
            bf = tk.Frame(self.props)
            bf.pack(fill='x', pady=2)
            bold = tk.BooleanVar(value=bool(el.get('bold')))
            self._prop_vars['bold'] = bold

            def bapply():
                if self._syncing:
                    return
                el['bold'] = bool(bold.get())
                self.redraw()
            tk.Checkbutton(bf, text='加粗', variable=bold, command=bapply,
                           font=('Microsoft YaHei', 9)).pack(side='left')
            align_row()
        elif t == 'barcode':
            num('X(mm)', 'x_mm')
            num('Y(mm)', 'y_mm')
            num('宽(mm)', 'width_mm')
            num('高(mm)', 'height_mm')
            f = tk.Frame(self.props)
            f.pack(fill='x', pady=2)
            tk.Label(f, text='来源', width=8, anchor='e', font=('Microsoft YaHei', 9)).pack(side='left')
            var = tk.StringVar(value=el.get('source', '条码号'))
            self._prop_vars['source'] = var
            ent = tk.Entry(f, textvariable=var, width=10, font=('Microsoft YaHei', 9))
            ent.pack(side='left')

            def sapply(_=None):
                if self._syncing:
                    return
                el['source'] = var.get().strip() or '条码号'
                self.redraw()
            ent.bind('<Return>', sapply)
            ent.bind('<FocusOut>', sapply)
            sd = tk.BooleanVar(value=bool(el.get('show_digits')))
            self._prop_vars['show_digits'] = sd

            def dapply():
                if self._syncing:
                    return
                el['show_digits'] = bool(sd.get())
                self.redraw()
            tk.Checkbutton(self.props, text='数字跟随条码下方', variable=sd, command=dapply,
                           font=('Microsoft YaHei', 9)).pack(anchor='w', pady=2)
            align_row()
        elif t == 'line':
            num('X1(mm)', 'x1_mm')
            num('Y1(mm)', 'y1_mm')
            num('X2(mm)', 'x2_mm')
            num('Y2(mm)', 'y2_mm')
            num('粗细(mm)', 'width_mm')
        self._syncing = False

    def _sync_props(self):
        if not (0 <= self.sel < len(self.template.get('elements', []))):
            return
        el = self.template['elements'][self.sel]
        self._syncing = True
        try:
            for k in ('x_mm', 'y_mm', 'x1_mm', 'y1_mm', 'x2_mm', 'y2_mm'):
                if k in self._prop_vars:
                    self._prop_vars[k].set(str(el.get(k, '')))
        finally:
            self._syncing = False

    def refresh_list(self):
        self.elem_list.delete(0, 'end')
        for i, el in enumerate(self.template.get('elements', [])):
            t = el.get('type')
            if t == 'text':
                s = '文本: %s' % (str(el.get('text', ''))[:18])
            elif t == 'barcode':
                s = '条码: %s' % el.get('source', '条码号')
            elif t == 'line':
                s = '线条 (%s,%s)-(%s,%s)' % (el.get('x1_mm'), el.get('y1_mm'),
                                              el.get('x2_mm'), el.get('y2_mm'))
            else:
                s = str(t)
            self.elem_list.insert('end', '%d. %s' % (i + 1, s))
        if self.elem_list.size() == 0:
            return
        i = min(max(self.sel, 0), self.elem_list.size() - 1)
        self.elem_list.selection_clear(0, 'end')
        self.elem_list.selection_set(i)
        self.elem_list.see(i)

    # ---------- 模板 ----------
    def _refresh_tpl_list(self):
        names = list_templates(self.cfg)
        self.tpl_box['values'] = names
        self.tpl_box.set(self.template.get('name') or '默认')

    def on_open_tpl(self):
        name = self.tpl_box.get().strip()
        tpl = load_template(self.cfg, name)
        if tpl is None:
            messagebox.showerror('错误', '模板不存在: %s' % name)
            return
        self.template = tpl
        self.sel = -1
        self.refresh_all()
        self._refresh_tpl_list()
        self.status.set('已打开模板「%s」。' % name)

    def on_save(self):
        name = self.template.get('name') or '默认'
        save_template(self.cfg, name, self.template)
        self._refresh_tpl_list()
        self._update_auto_flag()
        self.status.set('模板已保存: %s' % name)

    def on_save_as(self):
        name = simpledialog.askstring('另存为', '模板名称:',
                                      initialvalue=(self.template.get('name', '') + '-副本'),
                                      parent=self.root)
        if not name:
            return
        save_template(self.cfg, name, self.template)
        self.template = load_template(self.cfg, name) or self.template
        self._refresh_tpl_list()
        self.refresh_all()
        self.status.set('已另存为模板「%s」。' % name)

    def on_delete_tpl(self):
        name = self.tpl_box.get().strip()
        if not name:
            return
        if not messagebox.askyesno('确认', '删除模板「%s」？' % name):
            return
        try:
            delete_template(self.cfg, name)
        except Exception as e:
            messagebox.showerror('错误', str(e))
            return
        self._refresh_tpl_list()
        self.status.set('已删除模板: %s' % name)

    # ---------- 数据 ----------
    def set_data(self, data, src=''):
        self.data = {k: str((data or {}).get(k) or '').strip() for k in FIELD_ORDER}
        self.redraw()
        self.status.set('数据已载入（%s）。' % (src or '手工'))

    def latest_pdf(self):
        cands = []
        p = os.path.join(ROOT, 'spool', 'capture.pdf')
        if os.path.exists(p):
            cands.append(p)
        dirs = [os.path.join(ROOT, 'spool', 'jobs'), os.path.join(ROOT, 'out', 'archive')]
        dirs += list(self.cfg['watch']['dirs'])
        for d in dirs:
            if not os.path.isdir(d):
                continue
            for n in os.listdir(d):
                if n.lower().endswith('.pdf'):
                    cands.append(os.path.join(d, n))
        if not cands:
            return None
        return max(cands, key=lambda x: os.path.getmtime(x))

    def on_recognize(self):
        p = self.latest_pdf()
        if not p:
            messagebox.showinfo('提示', '未找到可识别的 PDF（最近捕获 / 归档 / 监视目录均为空）。')
            return
        try:
            data = recognize_fields(p)
        except Exception as e:
            messagebox.showerror('识别失败', str(e))
            return
        if not any(data.values()):
            messagebox.showinfo('提示', '未能从该文件识别出字段：%s' % os.path.basename(p))
            return
        self.set_data(data, '识别自 ' + os.path.basename(p))

    def on_edit_data(self):
        win = tk.Toplevel(self.root)
        win.title('编辑数据（预览/打印用）')
        win.transient(self.root)
        win.grab_set()
        vars_ = {}
        for i, key in enumerate(FIELD_ORDER):
            r, c = i % 7, (i // 7) * 2
            tk.Label(win, text=key, anchor='e', width=7,
                     font=('Microsoft YaHei', 10)).grid(row=r, column=c, sticky='e', padx=(10, 4), pady=3)
            v = tk.StringVar(value=self.data.get(key, ''))
            tk.Entry(win, textvariable=v, width=26,
                     font=('Microsoft YaHei', 10)).grid(row=r, column=c + 1, sticky='w', pady=3)
            vars_[key] = v

        def ok():
            self.set_data({k: v.get() for k, v in vars_.items()}, '手工编辑')
            win.destroy()
        btns = tk.Frame(win)
        btns.grid(row=8, column=0, columnspan=4, pady=8)
        tk.Button(btns, text='确定', width=10, command=ok).pack(side='left', padx=6)
        tk.Button(btns, text='取消', width=10, command=win.destroy).pack(side='left', padx=6)

    # ---------- 预览 / 打印 ----------
    def on_preview(self):
        img = render_template(self.template, self.data, dpi=int(self.cfg['pipeline']['render_dpi']))
        from app.render import compose_label
        canvas, _ = compose_label(img, self.cfg)
        if self._pt and self._pt.winfo_exists():
            self._pt.destroy()
        win = tk.Toplevel(self.root)
        win.title('预览（左：横版设计　右：竖版打印效果）')
        self._pt = win
        self._prev_refs = []
        c1 = tk.Canvas(win, width=580, height=220, background='#666')
        c1.pack(side='left', padx=8, pady=8)
        s1 = min(560.0 / img.width, 200.0 / img.height)
        d1 = img.resize((max(1, int(img.width * s1)), max(1, int(img.height * s1))), Image.LANCZOS)
        r1 = ImageTk.PhotoImage(d1)
        self._prev_refs.append(r1)
        c1.create_image(290, 110, image=r1)
        c2 = tk.Canvas(win, width=220, height=560, background='#666')
        c2.pack(side='left', padx=8, pady=8)
        s2 = min(180.0 / canvas.width, 540.0 / canvas.height)
        d2 = canvas.resize((max(1, int(canvas.width * s2)), max(1, int(canvas.height * s2))),
                           Image.LANCZOS)
        r2 = ImageTk.PhotoImage(d2)
        self._prev_refs.append(r2)
        c2.create_image(110, 280, image=r2)

    def on_print(self):
        if not messagebox.askyesno('确认', '将按当前布局打印 1 张水洗唛（30×120mm），继续？'):
            return

        def work():
            try:
                prev = print_layout(self.cfg, self.log, copy.deepcopy(self.template),
                                    dict(self.data), dry_run=False)
                self.root.after(0, lambda: self.status.set('已打印。预览存于: %s' % prev))
            except Exception as e:
                self.log.exception('designer print failed')
                self.root.after(0, lambda: messagebox.showerror('打印失败', str(e)))

        threading.Thread(target=work, daemon=True).start()

    # ---------- 自动打印开关 ----------
    def _update_auto_flag(self):
        name = self.template.get('name') or '默认'
        on = (str(self.cfg['pipeline'].get('render_mode', 'rotate')) == 'layout'
              and self.cfg['pipeline'].get('layout_template') == name)
        self.auto_var.set(bool(on))

    def on_auto_toggle(self):
        on = bool(self.auto_var.get())
        name = self.template.get('name') or '默认'
        try:
            if on:
                save_template(self.cfg, name, self.template)
                self.cfg['pipeline']['render_mode'] = 'layout'
                self.cfg['pipeline']['layout_template'] = name
            else:
                self.cfg['pipeline']['render_mode'] = 'rotate'
            self.cfg.save()
        except Exception as e:
            messagebox.showerror('错误', str(e))
            return
        self._refresh_tpl_list()
        if on:
            self.status.set('已启用：自动打印将按模板「%s」重排（识别失败时自动回退为原样旋转）。' % name)
        else:
            self.status.set('已关闭布局重排：自动打印为原样旋转。')

    # ---------- 其它 ----------
    def on_zoom(self, d):
        self.zoom_i = max(0, min(len(ZOOMS) - 1, self.zoom_i + d))
        self.refresh_all()

    def run(self):
        self.root.mainloop()


def main(argv=None):
    ap = argparse.ArgumentParser(prog='布局设计器')
    ap.add_argument('--selftest', action='store_true', help='自检模式（渲染并退出）')
    args = ap.parse_args(argv)
    try:
        if args.selftest:
            d = Designer()
            d.data = dict(SAMPLE_DATA)
            d.refresh_all()
            d.root.update()
            out1 = os.path.join(ROOT, 'out', 'previews', 'designer-selftest.png')
            os.makedirs(os.path.dirname(out1), exist_ok=True)
            img = render_template(d.template, d.data, dpi=int(d.cfg['pipeline']['render_dpi']))
            img.save(out1)
            from app.render import compose_label
            c, _ = compose_label(img, d.cfg)
            out2 = os.path.join(ROOT, 'out', 'previews', 'designer-selftest-print.png')
            c.save(out2)
            print('DESIGNER SELFTEST OK ->', out1, '|', out2)
            d.root.destroy()
            return
        Designer().run()
    except Exception:
        try:
            os.makedirs(os.path.join(ROOT, 'out', 'logs'), exist_ok=True)
            with open(os.path.join(ROOT, 'out', 'logs', 'designer_error.log'), 'a',
                      encoding='utf-8') as f:
                f.write('\n[%s]\n%s\n' % (traceback.format_exc(), ''))
        except Exception:
            pass
        raise


if __name__ == '__main__':
    main()
