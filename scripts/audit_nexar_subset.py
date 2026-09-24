"""Decode every acquired video and attach source metadata to a blank review table."""
import csv
import hashlib
import json
from pathlib import Path
import cv2

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'data/external/nexar_subset_v1'
OUT=ROOT/'data/derived/nexar_subset_v1'


def main():
    manifest=json.loads((SOURCE/'manifest.json').read_text())
    if not manifest.get('complete'):
        raise ValueError('Download incomplete')
    if OUT.exists():
        raise FileExistsError('Preserve existing review files; choose a new derived version')
    metadata={}
    for label in ['positive','negative']:
        with (SOURCE/f'train/{label}/metadata.csv').open(encoding='utf-8-sig',newline='') as f:
            for row in csv.DictReader(f):
                metadata[f'train/{label}/{row["file_name"]}']=row
    OUT.mkdir(parents=True)
    rows=[]
    for record in manifest['files']:
        path=SOURCE/record['path']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=record['sha256']:
            raise ValueError('Changed file '+record['path'])
        if path.suffix!='.mp4':
            continue
        source=metadata[record['path']]
        cap=cv2.VideoCapture(str(path))
        fps=cap.get(cv2.CAP_PROP_FPS)
        expected=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH));height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        decoded=0
        try:
            while True:
                ok,frame=cap.read()
                if not ok:
                    break
                decoded+=1
        finally:
            cap.release()
        if decoded==0 or decoded!=expected or fps<=0:
            raise ValueError('Incomplete video decode '+record['path'])
        rows.append({'video_id':path.stem,'source_path':path.relative_to(ROOT).as_posix(),'source_label':path.parent.name,
                     'source_time_of_event_seconds':source['time_of_event'],'source_time_of_alert_seconds':source['time_of_alert'],
                     'light_conditions':source['light_conditions'],'weather':source['weather'],'scene':source['scene'],
                     'fps':fps,'decoded_frames':decoded,'width':width,'height':height,'duration_seconds':decoded/fps,
                     'sha256':record['sha256'],'actual_contact':'','lane_entry_suitable':'','collision_frame':'','entry_frame':'',
                     'evasion_space':'','entry_side':'','origin_group_confirmed':'','split':'','review_status':'unreviewed','notes':''})
        print(json.dumps({'decoded':record['path'],'frames':decoded}),flush=True)
    rows.sort(key=lambda x:(x['source_label'],x['video_id']))
    with (OUT/'stage2_review_with_metadata.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    report={'complete':True,'videos':len(rows),'positive_collision_or_near_miss':sum(r['source_label']=='positive' for r in rows),
            'negative':sum(r['source_label']=='negative' for r in rows),'decoded_frames':sum(r['decoded_frames'] for r in rows),
            'duration_seconds':sum(r['duration_seconds'] for r in rows),'dacon_ground_truth_labels_created':0,
            'source_event_is_not_dacon_collision_or_entry_ground_truth':True}
    (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__=='__main__':
    main()
