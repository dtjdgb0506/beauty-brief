import json, io
b=json.load(io.open('config/brief.json',encoding='utf-8'))
print("channel_pool:", [p['title'][:36] for p in b.get('channel_pool',[])])
print("sections:", [(it['section_label'], it['title'][:26]) for it in b['items']][:5])
