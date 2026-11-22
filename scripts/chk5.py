import json, io
b=json.load(io.open('config/brief.json',encoding='utf-8'))
out=io.open('output/check5.txt','w',encoding='utf-8')
out.write(f"channel_pool={len(b.get('channel_pool',[]))}\n")
for p in b.get('channel_pool',[]): out.write(f"  · [{p.get('tag')}] {p['title'][:50]}\n")
out.write("\n线下渠道条目:\n")
for it in b['items']:
    if it['section']=='channel':
        a=it['analysis']
        out.write(f"- {it['title'][:40]} | move={a.get('channel_move')}\n  判断: {it['so_what']}\n  影响渠道: {a['impact']['channel']}\n  建议: {a['action'][:1]}\n")
out.close(); print('ok')
