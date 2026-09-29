"""Merge Stage 2 labels with the Nexar v2 meta and write a qa attachment folder + summary JSON."""
import csv, json, shutil, subprocess, sys, collections
from pathlib import Path

name = sys.argv[1]  # e.g. nexar_v2_labels_v1
out = Path('work/agent/outbox') / f'{name}_files'
out.mkdir(parents=True, exist_ok=True)
merged = out / 'stage2_merged_nexar_v2.csv'
p = subprocess.run([sys.executable, 'scripts/stage2_agent_label.py', 'merge', '--meta', 'work/nexar_v2/meta.csv', '--out', str(merged)],
                   capture_output=True, text=True, check=True)
merge_info = json.loads(p.stdout.strip().splitlines()[-1])
meta = {r['video_id']: r for r in csv.DictReader(open('work/nexar_v2/meta.csv', encoding='utf-8'))}
new_ids = Path('work/nexar_v2/new_ids.txt').read_text().split()
latest = {}
for r in csv.DictReader(open('data/derived/labels/agent/stage2_agent_labels.csv', encoding='utf-8')):
    latest[r['video_id']] = r
rows = []
for vid in new_ids:
    a = latest.get(vid)
    g = a['guideline_version'] if a else ''
    stage = 'detail' if 'nexar_v2_detail' in g else ('triage' if 'nexar_v2_triage' in g else 'pending')
    rows.append(dict(video_id=vid, packet_id=meta[vid]['packet_id'], stage=stage,
                     actual_contact=a['actual_contact'] if a else 'contact_unverified',
                     lane_entry_suitable=a['lane_entry_suitable'] if a else '',
                     collision_frame=a['collision_frame'] if a else '', nexar_event_frame=meta[vid]['nexar_event_frame'],
                     entry_frame=a['entry_frame'] if a else '', entry_side=a['entry_side'] if a else '',
                     evasion_space=a['evasion_space'] if a else '', confidence=a['confidence'] if a else '',
                     notes=(a['notes'] if a else '')[:400]))
with open(out / 'nexar_v2_new220_status.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
det = [r for r in rows if r['stage'] == 'detail']
summary = dict(
    merge=merge_info,
    new_videos=len(new_ids), overlap_with_v1_labeled=300 - len(new_ids),
    stage_counts=collections.Counter(r['stage'] for r in rows),
    contact_counts_triaged=collections.Counter(r['actual_contact'] for r in rows if r['stage'] != 'pending'),
    detail_n=len(det),
    detail_collision_minus_nexar=[int(r['collision_frame']) - int(r['nexar_event_frame']) for r in det if r['collision_frame']],
    detail_confidence=[float(r['confidence']) for r in det],
    detail_side=collections.Counter(r['entry_side'] for r in det),
    detail_evasion=collections.Counter(r['evasion_space'] for r in det),
)
json.dump(summary, open(out / 'summary.json', 'w', encoding='utf-8'), indent=1, default=dict)
shutil.copy('work/nexar_v2/triage_prompt.md', out / 'triage_prompt.md')
print(json.dumps(summary, default=dict))
