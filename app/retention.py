# -*- coding: utf-8 -*-
"""水洗唛打印助手 - 每日清理: 删除过期的归档 / 预览文件

策略(config.json 可调):
  cleanup.enabled  是否启用自动清理(默认 true)
  cleanup.days     保留最近天数(默认 7; 设为 0 等价于每次清理时清空)
"""
import os
import time


def cleanup(cfg, log, force=False):
    """执行一次清理, 返回删除的文件数"""
    c = cfg.get("cleanup") or {}
    if not c.get("enabled", True) and not force:
        return 0
    try:
        days = float(c.get("days", 7))
    except Exception:
        days = 7.0
    cutoff = time.time() - days * 86400.0
    removed = 0
    kept = 0
    for label, key in (("归档", "archive"), ("预览", "previews")):
        d = cfg.path_of(key)
        if not os.path.isdir(d):
            continue
        try:
            names = os.listdir(d)
        except OSError as e:
            log.warning("每日清理: 无法读取 %s (%s)", d, e)
            continue
        for name in names:
            p = os.path.join(d, name)
            try:
                if not os.path.isfile(p):
                    continue
                if os.path.getmtime(p) < cutoff:
                    os.remove(p)
                    removed += 1
                else:
                    kept += 1
            except Exception as e:
                log.warning("每日清理: 跳过 %s (%s)", p, e)
    log.info("每日清理完成: 删除 %d 个过期文件, 保留 %d 个 (保留最近 %s 天)",
             removed, kept, ("%g" % days))
    return removed
