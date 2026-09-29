"""Render one triage sheet per new Nexar v2 video: event-116 .. event+29, step 5 (30 tiles, 213px)."""
import csv, subprocess, sys, json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
existing = {r['video_id'] for r in csv.DictReader(open('data/derived/labels/agent/stage2_agent_labels.csv', encoding='utf-8'))}
rows = [r for r in csv.DictReader(open('work/nexar_v2/meta.csv', encoding='utf-8')) if r['video_id'] not in existing]
out = Path('work/nexar_v2/triage'); out.mkdir(parents=True, exist_ok=True)
def one(r):
    ev, n = int(r['nexar_event_frame']), int(r['decoded_frames'])
    start = max(0, ev - 116); end = min(n, start + 150)
    o = out/f"{r['video_id']}.jpg"
    if o.exists(): return r['video_id'], 'skip'
    p = subprocess.run([sys.executable, 'scripts/frame_sheet.py', '--video', r['source_path'], '--start', str(start), '--end', str(end),
                        '--step', '5', '--cols', '6', '--width', '213', '--out', str(o)], capture_output=True, text=True)
    return r['video_id'], 'ok' if p.returncode == 0 else p.stderr[-300:]
with ThreadPoolExecutor(4) as ex:
    res = list(ex.map(one, rows))
bad = [x for x in res if x[1] not in ('ok', 'skip')]
print(len(rows), 'videos; failures', bad)
Path('work/nexar_v2/new_ids.txt').write_text('\n'.join(r['video_id'] for r in rows) + '\n')
