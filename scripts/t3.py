import sys
from pathlib import Path
sys.path.insert(0,'scripts')
from common import load_profile
p=load_profile()
w=p.get('watch',{})
print('keys:', list(w.keys()))
print('offline len:', len(w.get('offline',[])))
print('sample:', w.get('offline',[])[:6])
