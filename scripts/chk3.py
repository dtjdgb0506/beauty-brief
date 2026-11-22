import json, io
b=json.load(io.open('config/brief.json',encoding='utf-8'))
out=io.open('output/check3.txt','w',encoding='utf-8')
for it in b['items'][:4]:
    a=it['analysis']
    out.write(f"{it['title'][:30]}\n  risk: {a['risk'][:80]}\n  act0: {a['action'][0] if a['action'] else ''}\n  what: {a['what'][:70]}\n\n")
out.close(); print('ok')
