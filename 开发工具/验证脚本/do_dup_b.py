import time, hashlib, os
src = r"E:\软件开发\.openclaw\tmp\dup_test_b.pdf"
slot = r"E:\软件开发\水洗唛打印助手\spool\capture.pdf"
data = open(src, "rb").read()
print("bytes=%d sha1=%s" % (len(data), hashlib.sha1(data).hexdigest()[:8]))
open(slot, "wb").write(data)
print("write1 done at", time.strftime("%H:%M:%S.")+("%03d" % (time.time()%1*1000)))
time.sleep(0.4)
open(slot, "wb").write(data)
print("write2 done at", time.strftime("%H:%M:%S.")+("%03d" % (time.time()%1*1000)), "(same bytes)")
time.sleep(5)
print("settle wait done")
