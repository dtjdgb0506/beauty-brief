import urllib.request, urllib.parse, json, io
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36'
def post(page):
    req=urllib.request.Request('https://www.iqingyan.cn/handlers/Handler1.ashx',
        data=urllib.parse.urlencode({'PageNum':str(page)}).encode(),
        headers={'User-Agent':UA,'Content-Type':'application/x-www-form-urlencoded'})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode('utf-8','replace'))
out=io.open('output/qy.txt','w',encoding='utf-8')
lo,hi=1,25
# 找最后一个非空页
for p in range(1,26):
    try:
        d=post(p)
        n=len(d) if isinstance(d,list) else 0
        if n and str(d[0].get('Num',''))!='-1':
            out.write(f"page {p}: {n} 条 | 首条 {str(d[0].get('Title'))[:30]} | time={d[0].get('CreatedTime')}\n")
        else:
            out.write(f"page {p}: EMPTY\n"); break
    except Exception as e:
        out.write(f"page {p}: ERR {type(e).__name__}\n"); break
out.close(); print('ok')
