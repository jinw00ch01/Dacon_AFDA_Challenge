"""Align the acquired comma pilot; create an unlabelled DoTA review queue.

No official DACON class labels are inferred here. Sensor values are auxiliary
training targets only; submission inference must consume video alone.
"""
from pathlib import Path
import csv
import json
import zipfile
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def align_sensor(times, values, query):
    times, values = np.asarray(times), np.asarray(values).reshape(-1)
    if len(times) != len(values) or not np.isfinite(times).all() or not np.isfinite(values).all():
        raise ValueError('Invalid sensor arrays')
    if not (np.diff(times) > 0).all():
        raise ValueError('Sensor times must strictly increase')
    if query[0] < times[0] or query[-1] > times[-1]:
        raise ValueError('Extrapolation is forbidden')
    positions = np.searchsorted(times, query).clip(1, len(times) - 1)
    if np.max(times[positions] - times[positions - 1]) > 0.1:
        raise ValueError('Sensor gap exceeds 100ms')
    return np.interp(query, times, values)


def main():
    out = ROOT / 'data/derived/pilot'
    out.mkdir(parents=True, exist_ok=True)
    segment = next((ROOT / 'data/external/comma2k19/Example_1').glob('*/*'))
    ft = np.load(segment / 'global_pose/frame_times', allow_pickle=False)
    sensors = {}
    for name in ('speed', 'steering_angle'):
        base = segment / 'processed_log/CAN' / name
        sensors[name] = (np.load(base/'t', allow_pickle=False), np.load(base/'value', allow_pickle=False))
    if not (np.diff(ft) > 0).all():
        raise ValueError('Non-monotonic video timestamps')
    first = max(ft[0], *(v[0][0] for v in sensors.values()))
    last = min(ft[-1], *(v[0][-1] for v in sensors.values()))
    grid_index = np.arange(int(np.ceil((first-ft[0])*10)), int(np.floor((last-ft[0])*10))+1)
    target_times = ft[0] + grid_index/10
    right = np.searchsorted(ft, target_times).clip(1, len(ft)-1)
    frame_index = np.where(abs(ft[right]-target_times) < abs(ft[right-1]-target_times), right, right-1)
    if max(abs(ft[frame_index]-target_times)) > 0.03:
        raise ValueError('Nearest frame exceeds 30ms tolerance')
    aligned = {name: align_sensor(t, v, target_times) for name, (t, v) in sensors.items()}
    acceleration = np.gradient(aligned['speed'], target_times)
    cap = cv2.VideoCapture(str(segment / 'video.hevc'))
    container_fps = cap.get(cv2.CAP_PROP_FPS)
    decoded = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        decoded += 1
    cap.release()
    if decoded != len(ft):
        raise ValueError(f'Decoded frames {decoded} != timestamp count {len(ft)}')
    with (out/'comma_10hz_continuous.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(['origin_group','sample_index','source_frame_index','elapsed_seconds','frame_offset_seconds','speed_mps','steering_angle_deg','acceleration_mps2_proxy','split','label_kind'])
        for i, idx in enumerate(frame_index):
            writer.writerow([segment.parent.name, i, int(idx), float(target_times[i]-ft[0]), float(ft[idx]-target_times[i]), float(aligned['speed'][i]), float(aligned['steering_angle'][i]), float(acceleration[i]), 'pilot_only', 'continuous_auxiliary_not_official_gt'])
    queue = []
    with zipfile.ZipFile(ROOT/'data/external/dota/dataset/DoTA_annotations.zip') as archive:
        for name in sorted(archive.namelist()):
            if not name.endswith('.json'):
                continue
            item = json.loads(archive.read(name))
            if item.get('ego_involve') and not item.get('ignore'):
                queue.append([item['video_name'], item['video_name'].rsplit('_',1)[0], item.get('accident_name'), item['num_frames'], item['anomaly_start'], item['anomaly_end'], '', '', '', '', 'unreviewed', 'video_not_acquired'])
    with (out/'stage2_review_queue.csv').open('w',newline='',encoding='utf-8') as handle:
        writer=csv.writer(handle)
        writer.writerow(['video_id','origin_group','source_anomaly_type','source_frame_count','source_anomaly_start','source_anomaly_end','collision_frame','entry_frame','evasion_space','entry_side','review_status','video_status'])
        writer.writerows(queue)
    report = {'comma': {'decoded_frames': decoded, 'sensor_timebase_fps': float(1/np.median(np.diff(ft))), 'container_fps_ignored': container_fps, 'duration_seconds': float(ft[-1]-ft[0]), 'aligned_10hz_rows': len(target_times), 'max_frame_offset_seconds': float(max(abs(ft[frame_index]-target_times))), 'source_frame_zero_based': True, 'speed_range_mps': [float(min(aligned['speed'])), float(max(aligned['speed']))], 'steering_range_deg': [float(min(aligned['steering_angle'])), float(max(aligned['steering_angle']))], 'independent_drive_groups': 1, 'use': 'pipeline pilot only; not validation or competition class ground truth'}, 'dota_review_candidates': len(queue), 'dota_note': 'Anomaly onset is NOT collision or lane-entry ground truth. Videos not acquired.'}
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
