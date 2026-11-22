import sys
from pathlib import Path
sys.path.insert(0,'scripts')
import score as S
from common import read_json, load_profile, load_lexicon
prof=load_profile(); lex=load_lexicon()
d=read_json(Path('output/candidates/2026-11-22.json'))
for it in d['items']:
    if it['source'].startswith('联商') and ('永辉' in it['title'] or '山姆' in it['title'] or '盒马' in it['title']):
        s=S.score_item(it,prof,lex)
        print(f"{s['score']:>5} {s['section']:<8} off={s['signals']['offline']} | {it['title'][:40]}")
