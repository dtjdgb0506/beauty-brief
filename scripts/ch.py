import sys, io
from pathlib import Path
sys.path.insert(0,'scripts')
import score as S
from common import read_json, load_profile, load_lexicon
prof=load_profile(); lex=load_lexicon()
d=read_json(Path('output/candidates/2026-11-22.json'))
rows=[]
for it in d['items']:
    blob=f"{it['title']} {it.get('summary','')}"
    if S.is_noise(it,prof,lex,blob): continue
    s=S.score_item(it,prof,lex)
    if s['section']=='channel': rows.append(s)
rows.sort(key=lambda x:-x['score'])
out=io.open('output/ch.txt','w',encoding='utf-8')
for r in rows[:14]:
    out.write(f"{r['score']:>5} [{r['source']}] off={r['signals']['offline']} | {r['title'][:52]}\n")
out.close(); print(len(rows))
