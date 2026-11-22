import sys, io, re
sys.path.insert(0,'scripts')
from common import fetch
out=io.open('output/offline_probe2.txt','w',encoding='utf-8')
# 1) 联商三个频道是否重复
def titles(u):
    h=fetch(u)
    return set(re.findall(r'<h2>\s*<a href="(https?://www\.linkshop\.com/news/\d+\.shtml|/news/\d+\.shtml)"', h))
a=titles('http://www.linkshop.com/news/pp/'); b=titles('http://www.linkshop.com/news/gwzx/'); c=titles('http://www.linkshop.com/news/bh/')
out.write(f"联商 pp={len(a)} gwzx={len(b)} bh={len(c)}  交集pp&gwzx={len(a&b)} pp&bh={len(a&c)}\n")
# 2) 中国药店 结构
h=fetch('http://www.ydzz.com/')
hrefs=re.findall(r'href="([^"]*(?:/\d{4,}|/news|/info|/content)[^"]*)"', h)
out.write(f"中国药店 href样本: {hrefs[:8]}\n")
# 3) 亿邦动力 零售/品牌频道
for u in ['https://www.ebrun.com/','https://www.ebrun.com/retail/','https://www.ebrun.com/brand/']:
    try:
        h=fetch(u); d=re.findall(r'20\d{2}[-/]\d{1,2}[-/]\d{1,2}', h)
        out.write(f"ebrun {u} len={len(h)} dates={len(d)} latest={max(d) if d else '-'}\n")
    except Exception as e:
        out.write(f"ebrun {u} ERR {str(e)[:60]}\n")
out.close(); print('ok')
