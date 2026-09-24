"""Validate acquired drives, align auxiliary sensors, and make S1 playback clips."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess

import cv2
import numpy as np
from prepare_public_pilot import align_sensor

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'data/external/comma2k19_subset_v1'
OUTPUT = ROOT / 'data/derived/comma_subset_v1'


def coalesce_sensor(times, values):
    times=np.asarray(times)
    values=np.asarray(values).reshape(-1)
    if len(times)!=len(values) or not np.isfinite(times).all() or not np.isfinite(values).all() or (np.diff(times)<0).any():
        raise ValueError('Invalid or decreasing sensor timestamps')
    unique,first,counts=np.unique(times,return_index=True,return_counts=True)
    means=np.add.reduceat(values,first)/counts
    spread=max((float(np.ptp(values[i:i+n])) for i,n in zip(first,counts) if n>1),default=0.0)
    return unique,means,{'duplicate_rows_collapsed':int(len(times)-len(unique)),'largest_same_time_value_spread':spread,'method':'mean at identical timestamps; raw files unchanged'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ffmpeg', required=True)
    parser.add_argument('--resume-incomplete',action='store_true',help='Resume an incomplete report, preserving verified playback files')
    args = parser.parse_args()
    if not Path(args.ffmpeg).is_file():
        raise FileNotFoundError(args.ffmpeg)
    manifest = json.loads((SOURCE / 'manifest.json').read_text())
    plan = json.loads((SOURCE / 'selection.json').read_text())
    previous={}
    if OUTPUT.exists():
        report_path=OUTPUT/'report.json'
        if not args.resume_incomplete or not report_path.exists():
            raise FileExistsError('Derived version already exists; preserve previous outputs')
        old=json.loads(report_path.read_text())
        if old.get('complete'):
            raise FileExistsError('Completed review version cannot be overwritten')
        previous={r['source_id']:r for r in old['sources']}
    if len(manifest['files']) != 6 * plan['count']:
        raise ValueError('Acquisition incomplete')
    for record in manifest['files']:
        path = SOURCE / record['path']
        if hashlib.sha256(path.read_bytes()).hexdigest() != record['sha256']:
            raise ValueError(f'Changed source: {path}')
    OUTPUT.mkdir(parents=True,exist_ok=True)
    (OUTPUT / 's1_playback').mkdir(exist_ok=True)
    report, aligned_rows = [], []
    for item in sorted(plan['selected'], key=lambda x:x['source_id']):
        segment = SOURCE / 'segments' / item['origin_group'].replace('|','_') / Path(item['prefix']).name
        ft = np.load(segment / 'global_pose/frame_times', allow_pickle=False)
        if not np.isfinite(ft).all() or not (np.diff(ft) > 0).all():
            raise ValueError('Invalid frame timestamps')
        sensor,duplicate_report = {},{}
        for name in ['speed','steering_angle']:
            folder = segment / 'processed_log/CAN' / name
            times,values,duplicates=coalesce_sensor(np.load(folder/'t',allow_pickle=False),np.load(folder/'value',allow_pickle=False))
            sensor[name] = (times,values)
            duplicate_report[name]=duplicates
        first = max(ft[0],*(pair[0][0] for pair in sensor.values()))
        last = min(ft[-1],*(pair[0][-1] for pair in sensor.values()))
        grid = np.arange(int(np.ceil((first-ft[0])*10)),int(np.floor((last-ft[0])*10))+1)
        query = ft[0] + grid/10
        right = np.searchsorted(ft,query).clip(1,len(ft)-1)
        nearest = np.where(abs(ft[right]-query)<abs(ft[right-1]-query),right,right-1)
        offset = ft[nearest]-query
        s3_error=None
        try:
            if abs(offset).max() > .03:
                raise ValueError('Frame offset > 30ms; exclude entire source from S3 auxiliary targets')
            targets = {name:align_sensor(t,v,query) for name,(t,v) in sensor.items()}
            acceleration = np.gradient(targets['speed'],query)
        except ValueError as error:
            s3_error=str(error)
        cap = cv2.VideoCapture(str(segment/'video.hevc'))
        container_fps = cap.get(cv2.CAP_PROP_FPS)
        decoded = 0
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                decoded += 1
        finally:
            cap.release()
        if decoded != len(ft):
            raise ValueError('Decoded frame count and timestamp count disagree')
        video = OUTPUT / 's1_playback' / (item['source_id'] + '_ORIGINAL.mp4')
        start = int(np.searchsorted(ft,ft[0]+10))
        finish = int(np.searchsorted(ft,ft[0]+20))
        input_rate = (finish-start)/(ft[finish]-ft[start])
        command = [args.ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-n','-r',str(input_rate),
                   '-i',str(segment/'video.hevc'),'-an','-vf',f'trim=start_frame={start}:end_frame={finish},setpts=PTS-STARTPTS,fps=20,scale=1280:-2','-r','20',
                   '-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(video)]
        if video.exists():
            old=previous.get(item['source_id'])
            if old is None or hashlib.sha256(video.read_bytes()).hexdigest()!=old['playback_sha256']:
                raise ValueError('Existing playback is not a verified previous output')
        else:
            subprocess.run(command,check=True,timeout=90,capture_output=True)
        check = cv2.VideoCapture(str(video))
        playback_count = 0
        playback_fps = check.get(cv2.CAP_PROP_FPS)
        try:
            while check.read()[0]:
                playback_count += 1
        finally:
            check.release()
        if abs(playback_fps-20) > .001 or abs(playback_count/20-(ft[finish]-ft[start])) > .1:
            raise ValueError('Unexpected playback encoding')
        for i,index in enumerate(nearest if s3_error is None else []):
            aligned_rows.append({'source_id':item['source_id'],'origin_group':item['origin_group'],'recording_date':item['recording_date'],
                'split':item['split'],'sample_index':i,'source_frame_index':int(index),'elapsed_seconds':float(query[i]-ft[0]),
                'frame_offset_seconds':float(offset[i]),'speed_mps':float(targets['speed'][i]),
                'steering_angle_deg':float(targets['steering_angle'][i]),'acceleration_mps2_proxy':float(acceleration[i]),
                'label_kind':'continuous_auxiliary_not_official_gt'})
        row = {**{k:item[k] for k in ['source_id','origin_group','recording_date','split']},'decoded_frames':decoded,
               'duration_seconds':float(ft[-1]-ft[0]),'container_fps_ignored':container_fps,
               'aligned_rows':len(query) if s3_error is None else 0,'s3_exclusion_reason':s3_error,'max_frame_offset_seconds':float(abs(offset).max()),
               'playback_path':video.relative_to(ROOT).as_posix(),'playback_sha256':hashlib.sha256(video.read_bytes()).hexdigest(),
               'clip_start_frame':start,'clip_end_frame_exclusive':finish,'playback_fps':playback_fps,'playback_frames':playback_count,'playback_transform':'source clip trimmed, mean source rate, CFR20, scaled to width1280, H264 CRF18; not a phone recapture',
               'source_clip_start_seconds':float(ft[start]-ft[0]),'source_clip_end_seconds':float(ft[finish]-ft[0]),'sensor_duplicate_handling':duplicate_report}
        report.append(row)
        (OUTPUT/'report.json').write_text(json.dumps({'complete':False,'sources':report},indent=2),encoding='utf-8')
        print(json.dumps({'prepared':item['source_id'],'frames':decoded,'aligned_rows':row['aligned_rows'],'s3_exclusion_reason':s3_error}),flush=True)
    with (OUTPUT/'s3_auxiliary_10hz.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f,fieldnames=list(aligned_rows[0]))
        writer.writeheader(); writer.writerows(aligned_rows)
    with (ROOT/'docs/templates/s23_capture_plan.csv').open(encoding='utf-8-sig',newline='') as f:
        reader = csv.DictReader(f); fields=reader.fieldnames; capture=list(reader)
    by_id={r['source_id']:r for r in report}
    for row in capture:
        item=by_id[row['planned_source_id']]
        row.update(origin_group=item['origin_group'],source_path=item['playback_path'],
                   source_url=f'https://huggingface.co/datasets/commaai/comma2k19/tree/{plan["revision"]}',
                   license_status='MIT_dataset_card_and_license_saved',confirmed_split=item['split'],
                   source_start_seconds='0',source_end_seconds='10',
                   notes='Use the supplied 10-second playback clip. Original full-minute source is preserved. SHA column is for the future phone recording.')
    with (OUTPUT/'s23_capture_ready.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(capture)
    summary={'complete':True,'sources':report,'source_count':len(report),'distinct_recording_dates':len({r['recording_date'] for r in report}),
             'total_source_seconds':sum(r['duration_seconds'] for r in report),'s3_aligned_rows':len(aligned_rows),
             's1_playback_files':len(report),'s3_eligible_sources':sum(r['s3_exclusion_reason'] is None for r in report),
             's3_excluded_source_ids':[r['source_id'] for r in report if r['s3_exclusion_reason'] is not None],
             's1_real_phone_captures':0,'official_stage3_class_labels_created':False}
    (OUTPUT/'report.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k!='sources'}),flush=True)


if __name__=='__main__':
    main()
