"""Plan/download official Nexar training videos after user-controlled HF access.

No gate bypass, no test-set downloads, no guessed collision/entry labels.
Run with .venv-data-tools; HF authentication uses its standard local login.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import hashlib
import json
from pathlib import Path
import random
import shutil

from huggingface_hub import HfApi, hf_hub_download

ROOT = Path(__file__).resolve().parents[1]
REPO = 'nexar-ai/nexar_collision_prediction'
REVISION = '260710de7e076bc3f5259071421a77dd76d36ac3'
OUT = ROOT / 'data/external/nexar_subset_v1'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan-only', action='store_true')
    parser.add_argument('--positive', type=int, default=80)
    parser.add_argument('--negative', type=int, default=24)
    args = parser.parse_args()
    if not 1 <= args.positive <= 100 or not 0 <= args.negative <= 50:
        parser.error('Use 1..100 positive and 0..50 negative videos')
    api = HfApi(token=False if args.plan_only else None)
    info = api.dataset_info(REPO,revision=REVISION,files_metadata=True)
    rng=random.Random(20260924)
    selected=[]
    for label,count in [('positive',args.positive),('negative',args.negative)]:
        pool=sorted([x for x in info.siblings if x.rfilename.startswith(f'train/{label}/') and x.rfilename.endswith('.mp4')],key=lambda x:x.rfilename)
        rng.shuffle(pool)
        if len(pool)<count:
            raise ValueError('Insufficient source candidates')
        selected.extend(pool[:count])
    total=sum(x.size or 0 for x in selected)
    if any(x.size is None for x in selected) or total>3*1024**3:
        raise ValueError('Unknown size or 3 GiB budget exceeded; reduce counts')
    if shutil.disk_usage(ROOT).free<40*1024**3:
        raise RuntimeError('Keep 40 GiB free on Ultra')
    OUT.mkdir(parents=True,exist_ok=True)
    queue=OUT/'stage2_candidates.csv'
    if queue.exists():
        with queue.open(encoding='utf-8-sig',newline='') as f:
            previous={r['source_path'] for r in csv.DictReader(f)}
        expected={str((OUT/x.rfilename).relative_to(ROOT)).replace('\\','/') for x in selected}
        if previous!=expected:
            raise ValueError('Existing review session has a different selection; preserve it and use a new version')
    plan={'repository':REPO,'revision':REVISION,'positive_candidates':args.positive,'negative_candidates':args.negative,
          'video_bytes':total,'note':'Positive combines collision and near-miss. This is not DACON ground truth.',
          'files':[{'path':x.rfilename,'bytes':x.size,'publisher_sha256':x.lfs.sha256 if x.lfs else None} for x in selected]}
    (OUT/'selection.json').write_text(json.dumps(plan,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in plan.items() if k!='files'}),flush=True)
    if args.plan_only:
        return
    downloads=['LICENSE','README.md','train/positive/metadata.csv','train/negative/metadata.csv']+[x.rfilename for x in selected]
    def fetch_one(filename):
        # The HF client sends credentials through its supported authentication path.
        # Never print credentials or put them in command-line arguments/manifests.
        path=Path(hf_hub_download(repo_id=REPO,repo_type='dataset',filename=filename,revision=REVISION,local_dir=OUT))
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        source=next((x for x in selected if x.rfilename==filename),None)
        if source and source.lfs and digest!=source.lfs.sha256:
            raise ValueError('Publisher SHA-256 mismatch: '+filename)
        return {'path':filename,'bytes':path.stat().st_size,'sha256':digest,'source_url':f'https://huggingface.co/datasets/{REPO}/resolve/{REVISION}/{filename}'}
    records=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(fetch_one,filename) for filename in downloads]):
            record=future.result()
            records.append(record)
            temporary=OUT/'manifest.json.part'
            temporary.write_text(json.dumps({'complete':False,'files':records},indent=2),encoding='utf-8')
            temporary.replace(OUT/'manifest.json')
            print(json.dumps({'acquired':record['path'],'files':len(records)}),flush=True)
    fields=['video_id','source_path','source_label','actual_contact','lane_entry_suitable','collision_frame','entry_frame','evasion_space','entry_side','origin_group_confirmed','split','review_status','notes']
    if not queue.exists():
        with queue.open('x',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
            for item in selected:
                writer.writerow({'video_id':Path(item.rfilename).stem,'source_path':str((OUT/item.rfilename).relative_to(ROOT)).replace('\\','/'),
                    'source_label':Path(item.rfilename).parent.name,'review_status':'unreviewed'})
    (OUT/'manifest.json').write_text(json.dumps({'complete':True,'files':records},indent=2),encoding='utf-8')
    print(json.dumps({'complete':True,'video_count':len(selected),'dacon_labels_created':0}),flush=True)


if __name__=='__main__':
    main()
