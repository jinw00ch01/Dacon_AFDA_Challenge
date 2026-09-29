"""Inventory of Nexar clips available on Pro for the S1 official-format pairs (decision 13)."""
import csv
import glob
import json
import os
from collections import Counter

m = list(csv.DictReader(open('work/nexar_v2/meta.csv', encoding='utf-8')))
ids = {r['video_id'] for r in m}
print(Counter(r['source_label'] for r in m), Counter(r['out_res'] for r in m), Counter(r['parity_ok'] for r in m))
print('missing', sum(not os.path.exists(r['source_path']) for r in m))
v1 = [os.path.basename(p)[:-4] for p in glob.glob('data/external/nexar_subset_v1/train/*/*.mp4')]
print('v1', len(v1), 'overlap', len(set(v1) & ids))
man = json.load(open('data/external/nexar_subset_v1/manifest.json', encoding='utf-8'))
print(type(man), list(man)[:10] if isinstance(man, dict) else man[:1])
