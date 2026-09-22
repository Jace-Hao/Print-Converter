# -*- coding: utf-8 -*-
"""水洗唛打印助手 - 日志"""
import datetime
import logging
import os
import sys


def get_logger(root, name="labelhelper"):
    logdir = os.path.join(root, "out", "logs")
    os.makedirs(logdir, exist_ok=True)
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.FileHandler(
        os.path.join(logdir, datetime.date.today().strftime("%Y-%m-%d") + ".log"),
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    try:
        sh = logging.StreamHandler(sys.stdout)
        sh.setLevel(logging.INFO)
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    except Exception:
        pass
    return logger
