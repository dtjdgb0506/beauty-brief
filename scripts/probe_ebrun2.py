import sys, io, re
sys.path.insert(0,'scripts')
from common import fetch
h=fetch('https://www.ebrun.com/retail/')
out=io.open('output/ebrun2.txt','w',encoding='utf-8')
idx=[m.start() for m in re.finditer(r'2026-11-\d\d', h)]
out.write(f"日期出现次数={len(idx)} 位置={idx[:6]}\n")
if len(idx)>=4:
    i=idx[3]
    out.write(h[max(0,i-900):i+200].replace("\n"," ")+"\n\n")
out.write("--- 链接样本 ---\n")
for m in list(re.finditer(r'href="([^"]*ebrun\.com[^"]*|/[^"]*)"[^>]*>([^<]{8,60})</a>', h))[:12]:
    out.write(f"{m.group(2).strip()[:44]} -> {m.group(1)[:80]}\n")
out.close(); print('ok')
