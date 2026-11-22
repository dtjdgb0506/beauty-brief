import json, io
b=json.load(io.open('config/brief.json',encoding='utf-8'))
out=io.open('output/check2.txt','w',encoding='utf-8')
out.write("TOP3:\n")
for t in b['today3']: out.write(f"  · {t['headline']} —— {t['why']}\n")
out.write("\nclose: "+b['close']+"\n\n")
it=b['items'][0]
out.write(f"ITEM0: {it['title']}\n")
out.write(f"  so_what: {it['so_what']}\n")
a=it['analysis']
out.write(f"  what: {a['what']}\n")
for v in a['views']: out.write(f"  view[{v['who']}]: {v['text']}\n")
for k,v in a['impact'].items(): out.write(f"  impact[{k}]: {v}\n")
out.write(f"  risk: {a['risk']}\n")
out.write(f"  watch: {a['watch']}\n")
out.write(f"  action: {a['action']}\n")
out.write(f"  question: {a['question']}\n")
out.write(f"  depth: {a['depth']}\n")
out.close(); print('ok')
