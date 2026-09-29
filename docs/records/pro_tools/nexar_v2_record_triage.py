"""Record triage decisions as agent rows (append-only) and build the detail queue.

Rules (pro360 role, decision 8): collision frame defaults to nexar_event; a triage row never sets it.
If the triage contact tile differs from nexar_event by > 10 frames, or cut_in in (yes, cross, uncertain),
the video goes to the detail queue (frame-labeler) and is recorded with lane_entry_suitable=uncertain.
"""
import csv, json, subprocess, sys
from pathlib import Path
meta = {r['video_id']: r for r in csv.DictReader(open('work/nexar_v2/meta.csv', encoding='utf-8'))}
done = set()
lab = Path('data/derived/labels/agent/stage2_agent_labels.csv')
for r in csv.DictReader(open(lab, encoding='utf-8')):
    if 'nexar_v2_triage' in r['guideline_version']:
        done.add(r['video_id'])
rows = []
for f in sorted(Path('work/nexar_v2/triage_results').glob('group_*.json')):
    rows += json.load(open(f, encoding='utf-8'))
queue, log = [], []
for d in rows:
    vid = d['video_id']
    if vid not in meta: raise SystemExit(f'unknown {vid}')
    ev = int(meta[vid]['nexar_event_frame'])
    c = d['contact'] if d['contact'] in ('yes', 'no', 'uncertain') else 'uncertain'
    cut = d.get('cut_in') or 'uncertain'
    approx = d.get('contact_frame_approx')
    off = (approx - ev) if (c == 'yes' and isinstance(approx, int)) else None
    detail = cut in ('yes', 'cross', 'uncertain') or (off is not None and abs(off) > 10) or c == 'uncertain'
    les = 'no' if (cut == 'no' and not detail) else 'uncertain'
    if detail: queue.append(dict(video_id=vid, event=ev, contact=c, approx=approx, cut_in=cut, side=d.get('side'), note=d.get('note', '')))
    if vid in done: continue
    note = f"triage sheet event-116..+29 step5: contact_tile={approx} (nexar {ev}, off {off}); cut_in={cut}; side={d.get('side')}; {d.get('note','')}"
    if detail: note += ' | detail labeling pending'
    cmd = [sys.executable, 'scripts/stage2_agent_label.py', 'add', '--video-id', vid, '--actual-contact', c,
           '--lane-entry-suitable', les, '--confidence', str(min(1.0, max(0.0, float(d.get('confidence', 0.5))))),
           '--evidence', f'work/nexar_v2/triage/{vid}.jpg', '--notes', note,
           '--guideline', 'DATA_PREPARATION_SPEC.md#5@2026-09-25;nexar_v2_triage', '--meta', 'work/nexar_v2/meta.csv']
    p = subprocess.run(cmd, capture_output=True, text=True)
    log.append((vid, p.returncode, (p.stderr or '')[-200:]))
json.dump(queue, open('work/nexar_v2/detail_queue.json', 'w', encoding='utf-8'), indent=1)
print('triaged', len(rows), 'recorded_now', sum(1 for x in log if x[1] == 0), 'fail', [x for x in log if x[1]])
print('detail_queue', len(queue))
