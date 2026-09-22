import os, time, sys
proj = r"E:\软件开发\水洗唛打印助手"
sys.path.insert(0, proj)
os.chdir(proj)
from app.config import Config
from app.logutil import get_logger
from app import retention
cfg = Config(proj); log = get_logger(proj)
arch = cfg.path_of("archive"); prev = cfg.path_of("previews")
old_t = time.time() - 8*86400
made = []
for i, d in enumerate((arch, prev)):
    p1 = os.path.join(d, "zz_cleanup_test_old_%d.bin" % i); open(p1,"w").write("x"); os.utime(p1,(old_t,old_t)); made.append(p1)
    p2 = os.path.join(d, "zz_cleanup_test_new_%d.bin" % i); open(p2,"w").write("x"); made.append(p2)
print("created 4 test files (2 old / 2 new)")
n = retention.cleanup(cfg, log)
print("removed:", n)
for p in made:
    print("  ", os.path.basename(p), "exists:", os.path.exists(p))
for p in made:
    if os.path.exists(p):
        os.remove(p)
print("test leftovers cleaned")
