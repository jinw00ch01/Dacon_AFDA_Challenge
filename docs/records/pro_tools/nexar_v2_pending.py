"""List detail-queue videos without a detail result, in priority order.

priority: yes+cross, yes+yes, uncertain+yes, uncertain+cross, yes+uncertain, other.
usage: nexar_v2_pending.py [N]  -> prints counts and the first N ids (default 10)
"""
import json, sys
from collections import Counter
from pathlib import Path

q = json.load(open('work/nexar_v2/detail_queue.json', encoding='utf-8'))
done = {p.stem for p in Path('work/nexar_v2/detail_results').glob('*.json')}
order = [('yes', 'cross'), ('yes', 'yes'), ('uncertain', 'yes'), ('uncertain', 'cross'), ('yes', 'uncertain')]
rank = lambda d: order.index((d['contact'], d['cut_in'])) if (d['contact'], d['cut_in']) in order else len(order)
pend = sorted([d for d in q if d['video_id'] not in done], key=lambda d: (rank(d), d['video_id']))
print('done', len(done), 'pending', len(pend))
print(dict(Counter(f"{d['contact']}+{d['cut_in']}" for d in pend)))
n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
for d in pend[:n]:
    print(json.dumps(d, ensure_ascii=False))
