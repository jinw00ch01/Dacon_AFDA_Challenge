"""Create a fresh human-review session; never invent labels or overwrite reviews."""
import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_rows(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames, list(reader)


def write_rows(path, fields, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def export_frames(output, samples):
    import cv2

    segment = next((ROOT / 'data/external/comma2k19/Example_1').glob('*/*'))
    wanted = {int(row['source_frame_index']) for row in samples}
    folder = output / 'stage3_frames'
    folder.mkdir()
    cap = cv2.VideoCapture(str(segment / 'video.hevc'))
    saved = set()
    try:
        for index in range(max(wanted) + 1):
            ok, frame = cap.read()
            if not ok:
                raise ValueError(f'Video ended before requested frame {index}')
            if index in wanted:
                if not cv2.imwrite(str(folder / f'source_{index:06d}.jpg'), frame):
                    raise OSError(f'Could not write review frame {index}')
                saved.add(index)
    finally:
        cap.release()
    if saved != wanted:
        raise ValueError('Missing review frames')
    return len(saved)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--session', required=True, help='New simple directory name')
    parser.add_argument('--with-frames', action='store_true', help='Decode 20 source frames for Stage 3 visual review (requires OpenCV)')
    args = parser.parse_args()
    if not args.session or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in args.session):
        parser.error('Use letters, numbers, underscore or hyphen only')
    output = ROOT / 'data/derived/review_sessions' / args.session
    if output.exists():
        raise FileExistsError('Session already exists; choose a new name to preserve human edits')
    fields, rows = read_rows(ROOT / 'data/derived/pilot/stage2_review_queue.csv')
    buckets = defaultdict(list)
    for row in rows:
        if row['origin_group']:
            buckets[row['source_anomaly_type']].append(row)
    rng = random.Random(20260924)
    for key in sorted(buckets):
        rng.shuffle(buckets[key])
    selected, groups = [], set()
    while len(selected) < 50 and any(buckets.values()):
        for key in sorted(buckets):
            while buckets[key]:
                row = buckets[key].pop()
                if row['origin_group'] not in groups:
                    groups.add(row['origin_group'])
                    selected.append(dict(row, label_status='pending_video_and_license', reviewed_by='', uncertainty_reason='', second_review='', notes=''))
                    break
            if len(selected) == 50:
                break
    if len(selected) != 50:
        raise ValueError('Not enough distinct source groups for the 50-candidate plan')
    s3fields, s3rows = read_rows(ROOT / 'data/derived/pilot/comma_10hz_continuous.csv')
    if len(s3rows) < 20:
        raise ValueError('Expected at least 20 aligned rows')
    samples = [dict(s3rows[round(i*(len(s3rows)-1)/19)], alignment_ok='', reviewed_by='', notes='') for i in range(20)]
    capture_fields, capture_rows = read_rows(ROOT / 'docs/templates/s23_capture_plan.csv')
    output.mkdir(parents=True)
    write_rows(output/'stage2_candidates_50.csv', fields+['label_status','reviewed_by','uncertainty_reason','second_review','notes'], selected)
    write_rows(output/'stage3_alignment_20.csv', s3fields+['alignment_ok','reviewed_by','notes'], samples)
    write_rows(output/'s23_capture_plan.csv', capture_fields, capture_rows)
    exported_frames = export_frames(output, samples) if args.with_frames else 0
    summary = {'stage2_candidates':50, 'stage2_source_groups':len(groups), 'stage2_labelled':0,
               'stage2_note':'Stratified source-anomaly candidates only; lane-entry suitability, video rights and video availability need review.',
               'stage3_review_rows':20, 'stage3_exported_frames':exported_frames, 'stage1_planned_recordings':len(capture_rows),
               'stage1_sources_acquired_by_this_script':0, 'seed':20260924}
    (output/'session.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps({'output':str(output), **summary}, indent=2))


if __name__ == '__main__':
    main()
