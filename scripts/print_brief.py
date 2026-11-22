import json, io, sys
b=json.load(io.open('config/brief.json',encoding='utf-8'))
out=io.open('output/brief_check.txt','w',encoding='utf-8')
out.write("日期: "+b['date']+"\n今日3件事:\n")
for t in b['today3']: out.write(f"  · {t['headline']} —— {t['why']}\n")
out.write("\n")
for it in b['items']:
    out.write(f"[{it['section_label']}] {it['title']}\n   so-what: {it['so_what']}\n   meta: brand={it['brand']} price={it['price']} channel={it['channel']} | {it['source']} {it['published']}\n")
out.write("\n小结: "+str(b.get('close'))+"\n")
out.close(); print('ok')
