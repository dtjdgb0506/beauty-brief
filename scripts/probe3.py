import sys, io, json, urllib.request, urllib.parse
sys.path.insert(0,'scripts')
out=io.open('output/probe3.txt','w',encoding='utf-8')
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36'
def post(url, data):
    req=urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(), headers={'User-Agent':UA,'Content-Type':'application/x-www-form-urlencoded'})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode('utf-8','replace')
# 1) 青眼接口
for page in ('1','20','40','50'):
    try:
        t=post('https://www.iqingyan.cn/handlers/Handler1.ashx',{'PageNum':page})
        out.write(f"qingyan page={page} len={len(t)} head={t[:160]}\n")
    except Exception as e:
        out.write(f"qingyan page={page} ERR {type(e).__name__} {str(e)[:60]}\n")
# 2) jina reader 看能不能拿到被墙站
for target in ('http://news.winshang.com/list-12.html','http://www.linkshop.com/news/pp/'):
    url='https://r.jina.ai/'+target
    try:
        req=urllib.request.Request(url, headers={'User-Agent':UA})
        with urllib.request.urlopen(req, timeout=25) as r:
            t=r.read().decode('utf-8','replace')
        out.write(f"jina {target} len={len(t)} head={t[:200].replace(chr(10),' ')}\n")
        out.write(f"   含标题链接数={t.count('](')}\n")
    except Exception as e:
        out.write(f"jina {target} ERR {type(e).__name__} {str(e)[:80]}\n")
out.close(); print('ok')
