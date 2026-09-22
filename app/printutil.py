# -*- coding: utf-8 -*-
"""水洗唛打印助手 - Windows GDI 打印: 位图 -> 打印机"""
import win32con
import win32ui
from PIL import Image, ImageWin


def printer_info(printer_name):
    """查询打印机的分辨率与可打印区域(设备像素)"""
    hdc = win32ui.CreateDC()
    hdc.CreatePrinterDC(printer_name)
    info = {
        "dpi_x": hdc.GetDeviceCaps(win32con.LOGPIXELSX),
        "dpi_y": hdc.GetDeviceCaps(win32con.LOGPIXELSY),
        "width": hdc.GetDeviceCaps(win32con.HORZRES),
        "height": hdc.GetDeviceCaps(win32con.VERTRES),
        "phys_w": hdc.GetDeviceCaps(win32con.PHYSICALWIDTH),
        "phys_h": hdc.GetDeviceCaps(win32con.PHYSICALHEIGHT),
        "off_x": hdc.GetDeviceCaps(win32con.PHYSICALOFFSETX),
        "off_y": hdc.GetDeviceCaps(win32con.PHYSICALOFFSETY),
    }
    hdc.DeleteDC()
    return info


def to_mono(img, dither=True, threshold=160):
    """转 1bit 单色: 抖动(照片型) 或 阈值(文字型)"""
    g = img.convert("L")
    if dither:
        return g.convert("1", dither=Image.FLOYDSTEINBERG)
    return g.point(lambda v: 255 if v >= threshold else 0).convert("1")


def print_image(printer_name, img, doc_name="水洗唛标签", copies=1):
    """把 PIL 图像按 1:1 像素(同 dpi)打印到指定打印机"""
    hdc = win32ui.CreateDC()
    hdc.CreatePrinterDC(printer_name)
    hdc.StartDoc(doc_name)
    try:
        for _ in range(max(1, int(copies))):
            hdc.StartPage()
            dib = ImageWin.Dib(img)
            dib.draw(hdc.GetHandleOutput(), (0, 0, img.width, img.height))
            hdc.EndPage()
    finally:
        try:
            hdc.EndDoc()
        except Exception:
            pass
        hdc.DeleteDC()
