"""Record frame-labeler JSON decisions (work/nexar_v2/detail_results/<id>.json) as agent rows.

Skips videos whose latest agent row already carries the nexar_v2_detail guideline tag.
"""
import csv, json, subprocess, sys
from pathlib import Path

lab = Path('data/derived/labels/agent/stage2_agent_labels.csv')
done = {r['video_id'] for r in csv.DictReader(open(lab, encoding='utf-8')) if 'nexar_v2_detail' in r['guideline_version']}
ok, fail = [], []
for f in sorted(Path('work/nexar_v2/detail_results').glob('*.json')):
    d = json.load(open(f, encoding='utf-8'))
    vid = d['video_id']
    if vid in done:
        continue
    cmd = [sys.executable, 'scripts/stage2_agent_label.py', 'add', '--video-id', vid,
           '--actual-contact', d['actual_contact'], '--lane-entry-suitable', d['lane_entry_suitable'],
           '--confidence', str(d['confidence']), '--notes', 'frame-labeler detail: ' + d.get('notes', ''),
           '--guideline', 'DATA_PREPARATION_SPEC.md#5@2026-09-25;nexar_v2_detail', '--meta', 'work/nexar_v2/meta.csv']
    for key, flag in (('collision_frame', '--collision-frame'), ('entry_frame', '--entry-frame'),
                      ('evasion_space', '--evasion-space'), ('entry_side', '--entry-side')):
        if d.get(key) is not None:
            cmd += [flag, str(d[key])]
    ev = [Path(e).as_posix().split('Dacon_AFDA_Challenge_git/')[-1] for e in d.get('evidence', [])]
    if ev:
        cmd += ['--evidence', *ev]
    p = subprocess.run(cmd, capture_output=True, text=True)
    (ok if p.returncode == 0 else fail).append((vid, (p.stderr or p.stdout)[-300:]))
print('recorded', [v for v, _ in ok], 'fail', fail)
