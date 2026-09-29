"""Build expansion meta CSV (stage2_agent_label.py --meta format) for Nexar v2 640px handoff batches."""
import csv, sys
from pathlib import Path
root = Path('.')
inbox = root/'data/derived/experiment_packets/inbox'
pk = ['8361901dcdd542b1a13027005f22f872', '6badf0be61c743198b0ba72d70124aca']
existing = {r['video_id'] for r in csv.DictReader(open('data/derived/labels/agent/stage2_agent_labels.csv', encoding='utf-8'))}
rows = []
for p in pk:
    for r in csv.DictReader(open(inbox/p/'files/nexar_ext_meta.csv', encoding='utf-8')):
        rows.append(dict(video_id=r['video_id'], source_path=str((inbox/p/'files'/r['out_path']).as_posix()),
                         source_label='positive', decoded_frames=r['out_decoded_frames'], fps=r['fps'],
                         nexar_event_frame=r['collision_frame_nexar'], time_of_event_s=r['time_of_event_s'],
                         parity_ok=r['parity_ok'], out_sha256=r['out_sha256'], out_res=r['out_res'], packet_id=p))
ids = [r['video_id'] for r in rows]
print('rows', len(rows), 'unique', len(set(ids)), 'overlap_existing', sorted(set(ids) & existing))
print('parity_fail', [r['video_id'] for r in rows if r['parity_ok'] != '1'])
print('missing_files', [r['video_id'] for r in rows if not Path(r['source_path']).exists()])
out = Path('work/nexar_v2'); out.mkdir(parents=True, exist_ok=True)
with open(out/'meta.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
import collections
print('fps', collections.Counter(r['fps'] for r in rows), 'res', collections.Counter(r['out_res'] for r in rows))
fr=[int(r['decoded_frames']) for r in rows]; ev=[int(r['nexar_event_frame']) for r in rows]
print('frames min/max', min(fr), max(fr), 'event out of range', [r['video_id'] for r in rows if not 0 <= int(r['nexar_event_frame']) < int(r['decoded_frames'])])
