import pymupdf, os
doc = pymupdf.open()
page = doc.new_page(width=210/25.4*72, height=297/25.4*72)
page.insert_text((25, 45), "DUP-TEST-B (discard)", fontsize=16)
page.insert_text((25, 72), "post-fix double write -> expect 2", fontsize=11)
out = r"E:\软件开发\.openclaw\tmp\dup_test_b.pdf"
doc.save(out); doc.close()
print("made", out, os.path.getsize(out))
