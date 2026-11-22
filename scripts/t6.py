import sys, datetime
from pathlib import Path
sys.path.insert(0,'scripts')
import score as S
from common import read_json, load_profile, load_lexicon
prof=load_profile(); lex=load_lexicon()
d=read_json(Path('output/candidates/2026-11-22.json'))
cd=datetime.date(2026,11,22)
items=[it for it in d['items'] if 0 <= (cd-datetime.date.fromisoformat(it['published'])).days <= 4]
print("window items:", len(items))
noise=0; below=0; ok=0
for it in items:
    blob=f"{it['title']} {it.get('summary','')}"
    if S.is_noise(it,prof,lex,blob): noise+=1; continue
    s=S.score_item(it,prof,lex,ref_day='2026-11-22')
    if s['score']<16: below+=1
    else: ok+=1
print("noise:",noise,"below_threshold:",below,"ok:",ok)
from collections import Counter
c=Counter(it['source'] for it in items)
print(c.most_common(8))
print([ (it['title'][:26], it['published']) for it in items[:6] ])
