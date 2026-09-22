# -*- coding: utf-8 -*-
"""水洗唛打印助手 - 控制面板 (tkinter)

轻量操作面板: 启动/停止监视、打印校准唛、手动处理 PDF、查看日志与目录。
处理逻辑全部复用 app.cli / app.watcher; 本界面只做入口与状态显示。
"""
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

CREATE_NO_WINDOW = 0x08000000


def python_exe():
    exe = sys.executable
    d = os.path.dirname(exe)
    if os.path.basename(exe).lower().startswith('pythonw'):
        pw, py = exe, os.path.join(d, 'python.exe')
    else:
        py, pw = exe, os.path.join(d, 'pythonw.exe')
    if not os.path.exists(py):
        py = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Python', 'bin', 'python.exe')
    if not os.path.exists(pw):
        pw = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Python', 'bin', 'pythonw.exe')
    return py, pw


PY, PYW = python_exe()


def app_path(*parts):
    return os.path.join(ROOT, *parts)


def run_ps(cmd):
    try:
        r = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', cmd],
                           capture_output=True, text=True, timeout=20, creationflags=CREATE_NO_WINDOW)
        return r.stdout.strip()
    except Exception:
        return ''


def watcher_pids():
    out = run_ps("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'app\\.cli watch' } | Select-Object -ExpandProperty ProcessId")
    pids = []
    for x in out.split():
        x = x.strip()
        if x.isdigit():
            pids.append(int(x))
    return pids


class Panel:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('水洗唛打印助手 - 控制面板')
        self.root.geometry('920x620')
        self.root.minsize(820, 520)

        top = tk.Frame(self.root)
        top.pack(fill='x', padx=10, pady=(10, 4))
        self.status_var = tk.StringVar(value='状态: 检查中...')
        tk.Label(top, textvariable=self.status_var, font=('Microsoft YaHei', 12, 'bold')).pack(side='left')

        btns = tk.Frame(self.root)
        btns.pack(fill='x', padx=10, pady=4)
        row1 = tk.Frame(btns); row1.pack(fill='x', pady=2)
        self._btn(row1, '启动监视', self.on_start)
        self._btn(row1, '停止监视', self.on_stop)
        self._btn(row1, '打印校准唛(两版)', self.on_calibrate)
        self._btn(row1, '处理 PDF 文件...', self.on_pick_pdf)
        self._btn(row1, '布局设计器', self.open_editor)
        row2 = tk.Frame(btns); row2.pack(fill='x', pady=2)
        self._btn(row2, '监视目录', lambda: self.open_dir(self.watch_dir()))
        self._btn(row2, '归档目录', lambda: self.open_dir(app_path('out', 'archive')))
        self._btn(row2, '预览目录', lambda: self.open_dir(app_path('out', 'previews')))
        self._btn(row2, '日志目录', lambda: self.open_dir(app_path('out', 'logs')))
        self._btn(row2, '使用说明', self.open_manual)
        self._btn(row2, '虚拟打印机', self.on_vprinter)

        tk.Label(self.root, text='运行日志（最近 300 行）:', anchor='w').pack(fill='x', padx=10, pady=(8, 0))
        self.logbox = scrolledtext.ScrolledText(self.root, height=18, font=('Consolas', 9), wrap='none')
        self.logbox.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        self.logbox.configure(state='disabled')

        self.busy = False
        self.refresh_status()
        self.refresh_log()
        self.root.after(3000, self._tick_log)
        self.root.after(1200, self._tick_status)

    # ---------- helpers ----------
    def _btn(self, parent, text, cmd):
        b = tk.Button(parent, text=text, command=self._wrap(cmd), width=17, font=('Microsoft YaHei', 10))
        b.pack(side='left', padx=3, pady=1)
        return b

    def _wrap(self, fn):
        def inner():
            try:
                fn()
            except Exception as e:
                messagebox.showerror('错误', str(e))
        return inner

    def watch_dir(self):
        try:
            from app.config import Config
            dirs = Config(ROOT)['watch']['dirs']
            return dirs[0] if dirs else ROOT
        except Exception:
            return ROOT

    def open_dir(self, path):
        os.makedirs(path, exist_ok=True)
        os.startfile(path)

    def open_manual(self):
        for name in ('使用说明.html', '使用说明与交付报告.html'):
            p = app_path(name)
            if os.path.exists(p):
                os.startfile(p)
                return
        messagebox.showinfo('提示', '未找到使用说明文件（使用说明.html）')

    def open_editor(self):
        import subprocess
        subprocess.Popen([PYW, '-X', 'utf8', app_path('app', 'designer.py')],
                         cwd=ROOT, creationflags=CREATE_NO_WINDOW)

    def on_vprinter(self):
        try:
            from app import vpinstall
            st = vpinstall.status()
        except Exception as e:
            messagebox.showerror('错误', str(e))
            return
        ok = bool(st.get('port_ok')) and bool(st.get('printer_ok')) and bool(st.get('driver_ok'))
        txt = '虚拟打印机「%s」\n端口文件: %s\n\n状态: %s' % (
            st.get('name'), st.get('port'), '已就绪' if ok else '未就绪')
        if ok:
            messagebox.showinfo('虚拟打印机', txt)
        elif messagebox.askyesno('虚拟打印机', txt + '\n\n是否现在安装/修复？（会弹出管理员确认窗口）'):
            os.startfile(app_path('安装虚拟打印机.cmd'))

    # ---------- actions ----------
    def on_start(self):
        if watcher_pids():
            messagebox.showinfo('提示', '监视已在运行中')
            return
        subprocess.Popen([PYW, '-X', 'utf8', '-m', 'app.cli', 'watch'], cwd=ROOT, creationflags=CREATE_NO_WINDOW)
        self.root.after(2000, self.refresh_status)

    def on_stop(self):
        if not watcher_pids():
            messagebox.showinfo('提示', '监视当前未运行')
            return
        run_ps("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'app\\.cli watch' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
        self.root.after(1200, self.refresh_status)

    def _run_cli_async(self, args, done_msg):
        if self.busy:
            messagebox.showinfo('提示', '上一个操作还在执行，请稍候...')
            return
        self.busy = True

        def work():
            try:
                r = subprocess.run([PY, '-X', 'utf8', '-m', 'app.cli'] + args, cwd=ROOT,
                                   capture_output=True, text=True, timeout=900, creationflags=CREATE_NO_WINDOW)
                out = ((r.stdout or '') + (r.stderr or '')).strip()
                tail = '\n'.join(out.splitlines()[-8:])
                self.root.after(0, lambda: messagebox.showinfo('完成', done_msg + ('\n\n' + tail if tail else '')))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror('失败', str(e)))
            finally:
                self.busy = False
                self.root.after(0, self.refresh_log)

        threading.Thread(target=work, daemon=True).start()

    def on_calibrate(self):
        if not messagebox.askyesno('确认', '将向标签机打印 2 张校准唛（第1版/第2版），继续？'):
            return
        self._run_cli_async(['calibrate'], '校准唛打印完成')

    def on_pick_pdf(self):
        f = filedialog.askopenfilename(title='选择要处理的 PDF', filetypes=[('PDF 文件', '*.pdf')])
        if not f:
            return
        self._run_cli_async(['once', '--force', f], '处理完成')

    # ---------- refresh ----------
    def refresh_status(self):
        def work():
            pids = watcher_pids()
            text = ('状态: 监视中 (PID %s)' % ','.join(map(str, pids))) if pids else '状态: 未运行'
            self.root.after(0, lambda: self.status_var.set(text))
        threading.Thread(target=work, daemon=True).start()

    def refresh_log(self):
        try:
            import datetime
            log = app_path('out', 'logs', datetime.date.today().strftime('%Y-%m-%d') + '.log')
            lines = []
            if os.path.exists(log):
                with open(log, 'r', encoding='utf-8', errors='replace') as f:
                    lines = f.readlines()[-300:]
            self.logbox.configure(state='normal')
            self.logbox.delete('1.0', 'end')
            self.logbox.insert('end', ''.join(lines))
            self.logbox.see('end')
            self.logbox.configure(state='disabled')
        except Exception:
            pass

    def _tick_log(self):
        self.refresh_log()
        self.root.after(3000, self._tick_log)

    def _tick_status(self):
        self.refresh_status()
        self.root.after(12000, self._tick_status)

    def run(self):
        self.root.mainloop()


def main():
    try:
        Panel().run()
    except Exception:
        import datetime
        import traceback
        try:
            os.makedirs(app_path('out', 'logs'), exist_ok=True)
            with open(app_path('out', 'logs', 'ui_error.log'), 'a', encoding='utf-8') as f:
                f.write('\n[%s]\n%s\n' % (datetime.datetime.now(), traceback.format_exc()))
        except Exception:
            pass
        raise


if __name__ == '__main__':
    main()
