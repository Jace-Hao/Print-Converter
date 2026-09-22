# -*- coding: utf-8 -*-
"""水洗唛打印助手 - 配置加载与保存"""
import copy
import json
import os

DEFAULTS = {
    "watch": {
        "dirs": [
            r"C:\Users\haoyuwei\Documents\PDF files\自动保存",
            r"D:\水洗唛输出",
            r"E:\软件开发\水洗唛打印助手\inbox"
        ],
        "pattern": "*.pdf",
        "ignore_names": ["spool.pdf"],
        "stable_seconds": 8,          # 文件大小/时间连续不变该秒数才认为写完(pdfFactory 合并需宽限)
        "poll_seconds": 1.5,
    },
    "validate": {                     # 防止误打印非标签内容
        "enabled": True,
        "aspect_range": [3.2, 4.6],   # 近似横版标签的比例范围
        "size_tol_mm": 3.0,
    },
    "pipeline": {
        "mode": "auto",               # auto | exact | crop | fit
        "rotate_dir": "cw",           # cw(顺时针90°) | ccw(逆时针90°)
        "canvas_mm": [30.0, 120.0],   # 目标标签纸尺寸(宽 x 长)
        "render_dpi": 300,            # 渲染与打印分辨率(与驱动一致)
        "offset_mm": [0.0, 0.0],      # 微调偏移(校准用)
        "crop_pad_mm": 0.5,           # 裁剪内容时的留边
        "crop_white": 250,            # 判定“白”的灰度阈值
        "align": "center",            # center | top | bottom | left | right
    },
    "print": {
        "printer": "水洗唛",           # 目标打印机(GP-9134T)
        "copies": 1,
        "dither": True,               # 灰度 -> 1bit 抖动
        "threshold": 160,             # 抖动/阈值参数
    },
    "automation": {
        "enabled": True,
        "mode": "auto",               # auto | dry_run（dry_run 只预览不打印）
        "close_pdffactory_window": True,   # 打印后自动关掉 pdfFactory 弹出窗口
    },
    "paths": {
        "archive": "out\\archive",
        "logs": "out\\logs",
        "previews": "out\\previews",
        "inbox": "inbox",
    },
}


def _merge(base, override):
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


class Config:
    def __init__(self, root):
        self.root = root
        self.path = os.path.join(root, "config.json")
        data = {}
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        self.data = _merge(DEFAULTS, data)

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def __getitem__(self, k):
        return self.data[k]

    def get(self, key, default=None):
        return self.data.get(key, default)

    def path_of(self, key):
        p = self.data["paths"][key]
        return p if os.path.isabs(p) else os.path.join(self.root, p)
