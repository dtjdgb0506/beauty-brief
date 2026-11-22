import json, io
b=json.load(io.open('config/brief.json',encoding='utf-8'))
out=io.open('output/check4.txt','w',encoding='utf-8')
out.write(f"channel_pool={len(b.get('channel_pool',[]))}\n")
for p in b.get('channel_pool',[]): out.write(f"  · [{p.get('tag')}] {p['title'][:50]}\n")
out.write("\nitems:\n")
for it in b['items']: out.write(f"  [{it['section_label']}] {it['title'][:40]} | move={it['analysis'].get('channel_move','')}\n")
out.close(); print('ok')
