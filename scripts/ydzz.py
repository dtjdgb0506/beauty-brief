import sys, io, re
sys.path.insert(0,'scripts')
from common import fetch
out=io.open('output/ydzz.txt','w',encoding='utf-8')
for u in ['http://www.ydzz.com/news.php?col=66','http://www.ydzz.com/news.php?col=67']:
    try:
        h=fetch(u, timeout=12)
        d=re.findall(r'20\d{2}-\d{2}-\d{2}', h)
        out.write(f"{u} len={len(h)} dates={len(d)} latest={max(d) if d else '-'}\n")
        for m in list(re.finditer(r'href="([^"]+)"[^>]*>([^<]{10,50})</a>', h))[:8]:
            out.write(f"   {m.group(2).strip()[:40]} -> {m.group(1)[:70]}\n")
    except Exception as e:
        out.write(f"{u} ERR {str(e)[:60]}\n")
out.close(); print('ok')
