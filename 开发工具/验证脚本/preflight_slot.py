# -*- coding: utf-8 -*-
"""启动前检查: 捕获文件与处理状态的关系, 避免重复打印或漏处理。"""
import glob
import hashlib
import json
import os
import time

ROOT = r'E:\软件开发\水洗唛打印助手'
cap = os.path.join(ROOT, 'spool', 'capture.pdf')
st_path = os.path.join(ROOT, 'out', 'slot_state.json')
res = {}
if not os.path.exists(cap):
    res['capture'] = 'missing'
else:
    data = open(cap, 'rb').read()
    h = hashlib.sha1(data).hexdigest()
    res['hash8'] = h[:8]
    res['size'] = len(data)
    last = ''
    try:
        last = json.load(open(st_path, encoding='utf-8')).get('last_hash', '')
    except Exception:
        pass
    same = (h == last)
    archived = glob.glob(os.path.join(ROOT, 'out', 'archive', '*%s*.pdf' % h[:8]))
    res['state_match'] = same
    res['archived_copies'] = len(archived)
    if not same and archived:
        json.dump({'last_hash': h, 'updated': time.strftime('%Y-%m-%d %H:%M:%S')},
                  open(st_path, 'w', encoding='utf-8'), ensure_ascii=False)
        res['action'] = 'marked_processed (已处理过, 防重复)'
    elif not same:
        res['action'] = 'left_for_processing (待处理)'
    else:
        res['action'] = 'noop'
print(json.dumps(res, ensure_ascii=False))
