import sys, io, re
sys.path.insert(0,'scripts')
from common import fetch
h=fetch('https://www.ebrun.com/retail/')
out=io.open('output/ebrun.txt','w',encoding='utf-8')
i=h.find('2026-11-22')
out.write(h[max(0,i-700):i+300].replace("\n"," ")+"\n\n")
for m in list(re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>\s*([^<]{10,60})\s*</a>', h))[:10]:
    out.write(f"{m.group(2).strip()[:44]} -> {m.group(1)[:90]}\n")
out.close(); print('ok')
