import sys, io, re
sys.path.insert(0,'scripts')
from common import fetch
out=io.open('output/offline_probe.txt','w',encoding='utf-8')
urls = [
 ('联商-购物中心','http://www.linkshop.com/news/gwzx/'),
 ('联商-百货','http://www.linkshop.com/news/bh/'),
 ('联商-超市','http://www.linkshop.com/news/sm/'),
 ('赢商-选址','http://news.winshang.com/list-7008.html'),
 ('赢商-开关店','http://news.winshang.com/list-7001.html'),
 ('品观-渠道','https://www.pinguan.com/channel/'),
 ('聚美丽-零售','https://www.jumeili.cn/sale/1.html'),
 ('中国药店','http://www.ydzz.com/'),
 ('医美行业观察','https://www.sohu.com/'),
]
for name,u in urls:
    try:
        h=fetch(u, timeout=12)
        dates=re.findall(r'20\d{2}[-/]\d{1,2}[-/]\d{1,2}', h)
        out.write(f"{name} | len={len(h)} | dates={len(dates)} | latest={max(dates) if dates else '-'} | {u}\n")
        # 渠道关键词命中
        hits=[w for w in ['开店','关店','撤柜','进驻','招商','加盟','代理','经销商','门店','专柜','集合店','百货','购物中心','药房','药店','免税','坪效','客流'] if w in h]
        out.write(f"    渠道词命中: {', '.join(hits[:12])}\n")
    except Exception as e:
        out.write(f"{name} | ERR {type(e).__name__} {str(e)[:60]} | {u}\n")
out.close(); print('ok')
