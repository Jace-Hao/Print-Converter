# -*- coding: utf-8 -*-
"""水洗唛打印助手 - 标签内容编辑器 (tkinter)

功能：识别打印数据（或手工填写）→ 逐项编辑字段 → 实时预览 → 打印自定义水洗唛。
用法：python app/editor.py [--pdf <文件>] [--selftest]
"""
import argparse
import os
import sys
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PIL import Image, ImageTk  # noqa: E402

from app.config import Config  # noqa: E402
from app.labelgen import print_custom_label, render_label  # noqa: E402
from app.logutil import get_logger  # noqa: E402
from app.recognize import FIELD_ORDER, recognize_fields  # noqa: E402


class Editor:
    def __init__(self, initial_pdf=None):
        self.cfg = Config(ROOT)
        self.log = get_logger(ROOT)
        self._preview_job = None
        self.vars = {}
        self.preview_img = None
        self.root = tk.Tk()
        self.root.title('水洗唛打印助手 - 标签内容编辑器')
        self.root.geometry('1020x660')
        self.root.minsize(940, 600)
        self._build()
        self.root.after(400, self.refresh_preview)
        if initial_pdf:
            self.root.after(600, lambda: self.load_pdf(initial_pdf))

    # ---------- UI ----------
    def _build(self):
        top = tk.Frame(self.root)
        top.pack(fill='x', padx=10, pady=(10, 6))
        self._btn(top, '打开 PDF 并识别...', self.choose_pdf)
        self._btn(top, '识别最近打印', self.load_latest)
        self._btn(top, '清空', self.clear_fields)
        self._btn(top, '刷新预览', self.refresh_preview)
        self._btn(top, '另存预览图...', self.save_preview)
        self._btn(top, '打印到标签机', self.do_print)

        body = tk.Frame(self.root)
        body.pack(fill='both', expand=True, padx=10)

        left = tk.Frame(body)
        left.pack(side='left', fill='y')
        for i, key in enumerate(FIELD_ORDER):
            r, c = i % 7, (i // 7) * 2
            tk.Label(left, text=key, anchor='e', width=7,
                     font=('Microsoft YaHei', 10)).grid(row=r, column=c, sticky='e', padx=(0, 4), pady=3)
            var = tk.StringVar()
            ent = tk.Entry(left, textvariable=var, width=26, font=('Microsoft YaHei', 10))
            ent.grid(row=r, column=c + 1, sticky='w', padx=(0, 14), pady=3)
            var.trace_add('write', lambda *a: self._schedule_preview())
            self.vars[key] = var

        right = tk.Frame(body)
        right.pack(side='left', fill='both', expand=True, padx=(12, 0))
        self.canvas = tk.Canvas(right, background='#3a3a3a', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)

        self.status = tk.StringVar(value='就绪：可「打开 PDF 并识别」或直接填写字段；右侧为实时预览（打印时自动旋转 90°输出）。')
        tk.Label(self.root, textvariable=self.status, anchor='w').pack(fill='x', padx=10, pady=(6, 8))

    def _btn(self, parent, text, cmd):
        b = tk.Button(parent, text=text, command=self._wrap(cmd), width=15, font=('Microsoft YaHei', 10))
        b.pack(side='left', padx=3)
        return b

    def _wrap(self, fn):
        def inner():
            try:
                fn()
            except Exception as e:
                self.log.exception('editor: %s', e)
                messagebox.showerror('错误', str(e))
        return inner

    def _schedule_preview(self):
        if self._preview_job:
            try:
                self.root.after_cancel(self._preview_job)
            except Exception:
                pass
        self._preview_job = self.root.after(500, self.refresh_preview)

    # ---------- data ----------
    def fields(self):
        return {k: v.get().strip() for k, v in self.vars.items()}

    def set_fields(self, data):
        for k in FIELD_ORDER:
            self.vars[k].set(str((data or {}).get(k) or "").strip())

    # ---------- actions ----------
    def choose_pdf(self):
        f = filedialog.askopenfilename(title='选择要识别的标签 PDF', filetypes=[('PDF 文件', '*.pdf')])
        if f:
            self.load_pdf(f)

    def load_pdf(self, path):
        data = recognize_fields(path)
        self.set_fields(data)
        self.status.set('已识别：%s（识别结果可直接手工修正）' % os.path.basename(path))
        self.refresh_preview()

    def load_latest(self):
        latest, mt = None, -1
        for d in self.cfg['watch']['dirs']:
            if not os.path.isdir(d):
                continue
            for name in os.listdir(d):
                if name.lower().endswith('.pdf'):
                    p = os.path.join(d, name)
                    try:
                        t = os.path.getmtime(p)
                    except OSError:
                        continue
                    if t > mt:
                        latest, mt = p, t
        if latest:
            self.load_pdf(latest)
        else:
            messagebox.showinfo('提示', '监视目录中暂未找到 PDF 文件')

    def clear_fields(self):
        self.set_fields({})
        self.status.set('已清空，可重新填写。')
        self.refresh_preview()

    # ---------- preview ----------
    def refresh_preview(self):
        self._preview_job = None
        img = render_label(self.fields(), dpi=int(self.cfg['pipeline']['render_dpi']))
        self.root.update_idletasks()
        cw = max(self.canvas.winfo_width(), 480)
        ch = max(self.canvas.winfo_height(), 240)
        scale = min(cw / img.width, ch / img.height) * 0.92
        disp = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.LANCZOS)
        self.preview_img = ImageTk.PhotoImage(disp)
        self.canvas.delete('all')
        self.canvas.create_image(cw // 2, ch // 2, image=self.preview_img)

    def save_preview(self):
        img = render_label(self.fields(), dpi=int(self.cfg['pipeline']['render_dpi']))
        f = filedialog.asksaveasfilename(defaultextension='.png', filetypes=[('PNG 图片', '*.png')],
                                         initialfile='自定义水洗唛.png')
        if f:
            img.save(f)
            self.status.set('预览图已保存：%s' % f)

    # ---------- print ----------
    def do_print(self):
        data = self.fields()
        if not any(data.values()):
            messagebox.showinfo('提示', '请先填写或识别标签内容。')
            return
        if not messagebox.askyesno('确认', '将打印 1 张自定义水洗唛（30×120mm），继续？'):
            return

        def work():
            try:
                prev = print_custom_label(self.cfg, self.log, data, dry_run=False)
                self.root.after(0, lambda: self.status.set('已打印。存档预览：%s' % prev))
                self.root.after(0, lambda: messagebox.showinfo('完成', '已送到标签机打印。'))
            except Exception as e:
                self.log.exception('editor print failed')
                self.root.after(0, lambda: messagebox.showerror('打印失败', str(e)))

        threading.Thread(target=work, daemon=True).start()

    def run(self):
        self.root.mainloop()


def main(argv=None):
    ap = argparse.ArgumentParser(prog='标签内容编辑器')
    ap.add_argument('--pdf', help='启动时预加载并识别的 PDF')
    ap.add_argument('--selftest', action='store_true', help='自检模式（自动填字段、渲染并退出）')
    args = ap.parse_args(argv)
    try:
        if args.selftest:
            ed = Editor()
            ed.set_fields({
                "衣物名称": "测试衬衫", "颜色": "蓝色", "工艺": "干洗",
                "电话": "13800000000", "客户": "测试顾客", "单号": "1100000001",
                "件数": "1-1", "下单日期": "09-22", "品牌": "测试",
                "损坏说明": "", "服务项目": "换拉链", "门店名": "星测洗衣",
                "条码号": "110000000123",
            })
            ed.root.update()
            ed.refresh_preview()
            ed.root.update()
            assert ed.preview_img is not None, 'preview failed'
            out = os.path.join(ROOT, 'out', 'previews', 'selftest-label.png')
            os.makedirs(os.path.dirname(out), exist_ok=True)
            render_label(ed.fields(), dpi=int(ed.cfg['pipeline']['render_dpi'])).save(out)
            print('SELFTEST OK ->', out)
            ed.root.destroy()
            return
        Editor(initial_pdf=args.pdf).run()
    except Exception:
        try:
            with open(os.path.join(ROOT, 'out', 'logs', 'editor_error.log'), 'a', encoding='utf-8') as f:
                f.write('\n' + traceback.format_exc())
        except Exception:
            pass
        raise


if __name__ == '__main__':
    main()
