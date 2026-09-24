"""File-based job queue over mutually authenticated Syncthing folders.

No shell commands are accepted from peers. Project data is imported without
overwriting edits. Only explicit CPU actions exist in protocol version 1.
"""
import argparse
import csv
from contextlib import contextmanager
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import re
import shutil
import subprocess
import tempfile
import time
import uuid

from .transport import FOLDERS,api

ACTIONS={'ping','verify_bundle','import_bundle','prepare_review','run_contract_tests','return_reviews'}
ID=re.compile(r'[a-f0-9]{32}')
HASH=re.compile(r'[a-f0-9]{64}')
ORIGIN='https://github.com/jinw00ch01/Dacon_AFDA_Challenge.git'
WATCH=('data/derived/nexar_subset_v1/stage2_review_with_metadata.csv',
       'data/derived/comma_subset_v1/s23_capture_ready.csv')


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.partial')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    temp.replace(path)


def load_config(path):
    cfg=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if cfg.get('version')!=1 or cfg.get('role') not in FOLDERS:
        raise ValueError('Invalid local exchange configuration')
    for key in ['project_root','exchange_root','state_root','python']:
        if not Path(cfg[key]).is_absolute():
            raise ValueError('Local configuration paths must be absolute')
    return cfg


def dirs(cfg):
    other=next(r for r in FOLDERS if r!=cfg['role'])
    base=Path(cfg['exchange_root'])
    return base/FOLDERS[cfg['role']],base/FOLDERS[other],other


def safe_path(root,name):
    if not isinstance(name,str) or not name or len(name)>500 or '\\' in name or ':' in name:
        raise ValueError('Unsafe path')
    p=PurePosixPath(name)
    if p.is_absolute() or p.as_posix()!=name or any(part in ['.','..'] or part.endswith((' ','.')) for part in p.parts):
        raise ValueError('Unsafe path components')
    reserved={'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}
    if any(part.split('.')[0].upper() in reserved for part in p.parts):
        raise ValueError('Reserved path')
    root=Path(root).resolve();target=root.joinpath(*p.parts)
    if not target.resolve().is_relative_to(root) or target.is_symlink():
        raise ValueError('Path escapes its root or is a symlink')
    return target


def allowed_data(name):
    p=PurePosixPath(name)
    return (name.startswith(('data/external/','data/derived/','data/captures/'))
            and not any(x.startswith('.') for x in p.parts)
            and p.suffix.lower() not in {'.py','.ps1','.bat','.cmd','.exe','.dll','.key','.pem','.pfx','.env','.sqlite','.db'})


def command(args,cwd,timeout=60):
    return subprocess.run(args,cwd=cwd,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout,
                          env={**os.environ,'GIT_TERMINAL_PROMPT':'0'},
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)


def commit(root):
    result=command(['git','rev-parse','HEAD'],root)
    value=result.stdout.strip()
    if result.returncode or not re.fullmatch(r'[a-f0-9]{40}',value):
        raise ValueError('Project must have a valid Git commit')
    return value


def validate_job(job,filename,role):
    keys={'version','id','sender','target','action','bundle','manifest_sha256','code_commit','created_utc'}
    if set(job)!=keys or job['version']!=1 or not ID.fullmatch(job['id']) or job['id']!=filename:
        raise ValueError('Invalid job schema/ID')
    if job['target']!=role or job['sender'] not in FOLDERS or job['sender']==role:
        raise ValueError('Wrong sender/target')
    if job['action'] not in ACTIONS:
        raise ValueError('Action not allowed')
    if not re.fullmatch(r'[a-f0-9]{40}',job['code_commit']):
        raise ValueError('Invalid code commit')
    if job['bundle'] is not None:
        if job['bundle']!=job['id'] or not HASH.fullmatch(job['manifest_sha256'] or ''):
            raise ValueError('Invalid bundle reference')
    elif job['action'] not in {'ping','run_contract_tests'} or job['manifest_sha256'] is not None:
        raise ValueError('Action requires a bundle')
    if job['action']=='return_reviews' and role!='ultra5060':
        raise ValueError('Review return is only accepted by Ultra')


def verify_bundle(inbox,job):
    folder=safe_path(inbox,'bundles/'+job['bundle'])
    manifest=folder/'manifest.json'
    if not manifest.exists():
        return None
    if manifest.stat().st_size>4*1024**2 or digest(manifest)!=job['manifest_sha256']:
        raise ValueError('Manifest integrity mismatch')
    data=json.loads(manifest.read_text(encoding='utf-8'))
    if set(data)!={'version','files'} or data['version']!=1 or not 1<=len(data['files'])<=5000:
        raise ValueError('Invalid manifest')
    total=0;seen=set()
    for row in data['files']:
        if set(row)!={'path','bytes','sha256'} or not allowed_data(row['path']):
            raise ValueError('Disallowed data path')
        source=safe_path(folder/'files',row['path'])
        key=row['path'].casefold()
        if key in seen or type(row['bytes']) is not int or not 0<=row['bytes']<=512*1024**2 or not HASH.fullmatch(row['sha256']):
            raise ValueError('Invalid or duplicate file record')
        seen.add(key);total+=row['bytes']
        if total>8*1024**3:
            raise ValueError('Bundle exceeds 8 GiB')
    # Check completeness before expensive hashing; Syncthing may deliver job first.
    if any(not safe_path(folder/'files',r['path']).is_file() or safe_path(folder/'files',r['path']).stat().st_size!=r['bytes'] for r in data['files']):
        return None
    for row in data['files']:
        if digest(safe_path(folder/'files',row['path']))!=row['sha256']:
            raise ValueError('Payload hash mismatch')
    return data['files']


def publish(cfg,action,paths=()):
    if action not in ACTIONS:
        raise ValueError('Unsupported action')
    outbox,_,other=dirs(cfg)
    job_id=uuid.uuid4().hex
    root=Path(cfg['project_root'])
    files={}
    for name in paths:
        p=safe_path(root,name)
        candidates=sorted(p.rglob('*')) if p.is_dir() else [p]
        for source in candidates:
            relative=source.relative_to(root).as_posix()
            if source.is_file() and not source.is_symlink() and allowed_data(relative):
                safe_path(root,relative)
                files[relative]=source
    bundle=None;manifest_sha=None
    if paths and not files:
        raise ValueError('No allowed data files selected')
    if files:
        bundle=job_id
        folder=outbox/'bundles'/bundle
        rows=[];total=0
        for name,source in sorted(files.items()):
            size=source.stat().st_size;total+=size
            if size>512*1024**2 or total>8*1024**3 or len(files)>5000:
                raise ValueError('Data snapshot exceeds limits')
            destination=safe_path(folder/'files',name)
            destination.parent.mkdir(parents=True,exist_ok=True)
            temporary=destination.with_name(destination.name+'.partial')
            before=(source.stat().st_size,source.stat().st_mtime_ns)
            shutil.copyfile(source,temporary)
            if before!=(source.stat().st_size,source.stat().st_mtime_ns):
                raise ValueError('Source changed during publication; no job was queued')
            temporary.replace(destination)
            rows.append({'path':name,'bytes':size,'sha256':digest(destination)})
        atomic_json(folder/'manifest.json',{'version':1,'files':rows})
        manifest_sha=digest(folder/'manifest.json')
    job={'version':1,'id':job_id,'sender':cfg['role'],'target':other,'action':action,'bundle':bundle,
         'manifest_sha256':manifest_sha,'code_commit':commit(root),'created_utc':datetime.now(timezone.utc).isoformat()}
    validate_job(job,job_id,other)
    atomic_json(outbox/'jobs'/(job_id+'.json'),job)
    return job


def import_files(cfg,inbox,job,rows):
    root=Path(cfg['project_root'])
    destination_root=root if job['action']!='return_reviews' else root/'data/derived/peer_reviews'/job['sender']/job['id']
    targets=[];required=0
    for row in rows:
        target=safe_path(destination_root,row['path'])
        if target.exists():
            if not target.is_file() or digest(target)!=row['sha256']:
                raise ValueError('Existing local edit preserved: '+row['path'])
        else:
            required+=row['bytes']
        targets.append((row,target))
    free=shutil.disk_usage(root).free
    reserve=(20 if cfg['role']=='pro360' else 40)*1024**3
    if free-required<reserve:
        raise ValueError('Not enough free space after import for role reserve')
    for row,target in targets:
        if target.exists():
            continue
        target.parent.mkdir(parents=True,exist_ok=True)
        # Link a verified same-volume temp file atomically: never replace a file
        # another process may have created after the conflict preflight.
        descriptor,temp=tempfile.mkstemp(prefix='.afda-import-',suffix='.partial',dir=target.parent)
        os.close(descriptor)
        try:
            shutil.copyfile(safe_path(inbox,'bundles/'+job['id']+'/files/'+row['path']),temp)
            if digest(temp)!=row['sha256']:
                raise ValueError('Source changed while importing')
            os.link(temp,target)
        finally:
            Path(temp).unlink(missing_ok=True)
    if job['action']=='return_reviews':
        atomic_json(root/'data/derived/peer_reviews/latest.json',{'job_id':job['id'],'directory':destination_root.relative_to(root).as_posix()})
    return {'imported_or_identical':len(rows),'bytes':sum(r['bytes'] for r in rows),'destination':str(destination_root)}


def sync_code(cfg,state):
    if not cfg.get('auto_git') or time.time()-state.get('last_git_check',0)<300:
        return
    state['last_git_check']=time.time()
    root=cfg['project_root']
    status=command(['git','status','--porcelain'],root)
    if status.returncode or status.stdout.strip():
        state['git_status']='local_changes_preserved';return
    if command(['git','remote','get-url','origin'],root).stdout.strip()!=ORIGIN or command(['git','branch','--show-current'],root).stdout.strip()!='main':
        state['git_status']='unexpected_origin_or_branch';return
    fetched=command(['git','-c','credential.interactive=never','fetch','origin','main'],root,45)
    if fetched.returncode:
        state['git_status']='fetch_failed';return
    merged=command(['git','merge','--ff-only','origin/main'],root,30)
    state['git_status']='current_or_fast_forwarded' if merged.returncode==0 else 'divergence_preserved'


def watch_reviews(cfg,state):
    if cfg['role']!='pro360':
        return
    root=Path(cfg['project_root']);watch=state.setdefault('watch',{})
    candidates=[root/p for p in WATCH]
    captures=root/'data/captures/s23'
    if captures.exists():
        candidates.extend(p for p in captures.rglob('*') if p.suffix.lower() in {'.mp4','.mov'})
    changed=[]
    for path in candidates:
        if not path.is_file():
            continue
        name=path.relative_to(root).as_posix();safe_path(root,name)
        stamp=[path.stat().st_size,path.stat().st_mtime_ns]
        entry=watch.setdefault(name,{})
        if entry.get('stamp')!=stamp:
            entry.update(stamp=stamp,stable_since=time.time());continue
        if time.time()-entry['stable_since']<cfg.get('review_debounce_seconds',30):
            continue
        value=digest(path)
        if value!=entry.get('sent_sha'):
            if path.suffix.lower()=='.csv':
                with path.open(encoding='utf-8-sig',newline='') as f:
                    reader=csv.DictReader(f)
                    if not reader.fieldnames or not any(True for _ in reader):
                        continue
            changed.append((name,value))
    if changed:
        job=publish(cfg,'return_reviews',[name for name,_ in changed])
        for name,value in changed:
            watch[name]['sent_sha']=value
        state['last_auto_return']=job['id']


def task_previews(cfg,job):
    import cv2
    outbox,inbox,_=dirs(cfg)
    rows=verify_bundle(inbox,job)
    if rows is None:
        raise ValueError('Incomplete preview inputs')
    folder=outbox/'results'/job['id']/'previews'
    folder.mkdir(parents=True,exist_ok=True)
    result=[]
    for row in rows:
        if PurePosixPath(row['path']).suffix.lower() not in {'.mp4','.hevc','.mov'}:
            continue
        path=safe_path(cfg['project_root'],row['path'])
        cap=cv2.VideoCapture(str(path))
        try:
            ok,frame=cap.read()
            if not ok:
                raise ValueError('Preview decode failed: '+row['path'])
            height,width=frame.shape[:2]
            small=cv2.resize(frame,(480,round(height*480/width)))
            name=row['sha256'][:20]+'.jpg'
            if not cv2.imwrite(str(folder/name),small):
                raise ValueError('Preview write failed')
            result.append({'source':row['path'],'preview':name,'source_width':width,'source_height':height})
        finally:
            cap.release()
    atomic_json(folder/'index.json',result)
    print(json.dumps({'previews':len(result)}))


@contextmanager
def worker_lock(state_root):
    path=Path(state_root)/'worker.lock'
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as handle:
        if path.stat().st_size==0:
            handle.write(b'0');handle.flush()
        handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as error:
            raise RuntimeError('Another exchange worker is active') from error
        try:
            yield
        finally:
            handle.seek(0)
            if os.name=='nt':
                msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:
                fcntl.flock(handle.fileno(),fcntl.LOCK_UN)


def run_worker(cfg,config_path):
    with worker_lock(cfg['state_root']):
        _run_worker(cfg,config_path)


def _run_worker(cfg,config_path):
    outbox,inbox,_=dirs(cfg)
    state_path=Path(cfg['state_root'])/'worker-state.json'
    state=json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {'jobs':{},'watch':{}}
    try:
        sync_code(cfg,state)
        for path in sorted((inbox/'jobs').glob('*.json')):
            if not ID.fullmatch(path.stem):
                continue
            job_id=path.stem
            if state['jobs'].get(job_id,{}).get('status') in {'completed','failed','rejected','interrupted'}:
                continue
            if path.stat().st_size>16384:
                state['jobs'][job_id]={'status':'rejected','reason':'Job too large'};continue
            job=None
            try:
                job=json.loads(path.read_text(encoding='utf-8'))
                validate_job(job,job_id,cfg['role'])
                job_sha=digest(path)
                previous=state['jobs'].get(job_id,{})
                if previous.get('job_sha') and previous['job_sha']!=job_sha:
                    raise ValueError('Job ID reused with different content')
                if previous.get('status')=='running':
                    raise ValueError('Previous worker interrupted; submit a new job ID after inspection')
                if job['action'] in {'prepare_review','run_contract_tests'}:
                    if job['code_commit']!=commit(cfg['project_root']) or command(['git','status','--porcelain'],cfg['project_root']).stdout.strip():
                        state['jobs'][job_id]={'status':'waiting_for_clean_matching_code','job_sha':job_sha};continue
                rows=verify_bundle(inbox,job) if job['bundle'] else []
                if rows is None:
                    state['jobs'][job_id]={'status':'waiting_for_files','job_sha':job_sha};continue
                state['jobs'][job_id]={'status':'running','job_sha':job_sha}
                atomic_json(state_path,state)
                details={'role':cfg['role'],'action':job['action'],'verified_files':len(rows)}
                if job['action'] in {'import_bundle','prepare_review','return_reviews'}:
                    details.update(import_files(cfg,inbox,job,rows))
                    if cfg['role']=='pro360':
                        for row in rows:
                            if row['path'] in WATCH:
                                p=Path(cfg['project_root'])/row['path']
                                state['watch'][row['path']]={'stamp':[p.stat().st_size,p.stat().st_mtime_ns],'stable_since':time.time(),'sent_sha':row['sha256']}
                if job['action'] in {'prepare_review','run_contract_tests'}:
                    child=[cfg['python'],'-m','unittest','discover','-s','tests','-v'] if job['action']=='run_contract_tests' else [cfg['python'],'-m','exchange_bridge','task-previews','--config',str(config_path),'--job',str(path)]
                    result=command([cfg['python'],'-m','harness','execute','--profile',cfg['role'],'--kind','cpu','--timeout','600','--',*child],cfg['project_root'],630)
                    details.update(returncode=result.returncode,stdout=result.stdout[-12000:],stderr=result.stderr[-4000:])
                    if result.returncode:
                        raise ValueError('CPU task failed; see local harness runs')
                result={'job_id':job_id,'job_sha':job_sha,'status':'completed','details':details,'finished_utc':datetime.now(timezone.utc).isoformat()}
                atomic_json(outbox/'results'/job_id/'result.json',result)
                state['jobs'][job_id]={'status':'completed','job_sha':job_sha}
            except Exception as error:
                reason=f'{type(error).__name__}: {error}'
                state['jobs'][job_id]={'status':'failed','reason':reason}
                atomic_json(outbox/'results'/job_id/'result.json',{'job_id':job_id,'status':'failed','reason':reason})
            atomic_json(state_path,state)
        watch_reviews(cfg,state)
    finally:
        atomic_json(state_path,state)
        atomic_json(outbox/'status'/f'{cfg["role"]}.json',{'role':cfg['role'],'updated_utc':datetime.now(timezone.utc).isoformat(),
                    'git_status':state.get('git_status'),'jobs':state['jobs'],'last_auto_return':state.get('last_auto_return')})


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['worker','publish','task-previews','stop-transport'])
    parser.add_argument('--config',required=True)
    parser.add_argument('--operation',choices=sorted(ACTIONS))
    parser.add_argument('--path',action='append',default=[])
    parser.add_argument('--job')
    args=parser.parse_args();cfg=load_config(args.config)
    if args.action=='worker':
        run_worker(cfg,args.config)
    elif args.action=='publish':
        if not args.operation:
            parser.error('--operation required')
        print(json.dumps(publish(cfg,args.operation,args.path),indent=2))
    elif args.action=='task-previews':
        job=json.loads(Path(args.job).read_text(encoding='utf-8'))
        validate_job(job,Path(args.job).stem,cfg['role'])
        task_previews(cfg,job)
    else:
        api(cfg['syncthing_home'],'system/shutdown',{},'POST')


if __name__=='__main__':
    main()
