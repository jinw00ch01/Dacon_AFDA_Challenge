"""Opt-in real Syncthing round trip on loopback, not physical Pro validation.

Uses the installed Ultra transport binary, temporary Git clones and isolated
Syncthing identities/ports. Does not change the production device pairing.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from exchange_bridge import __main__ as bridge
from exchange_bridge.transport import api,configure


def wait_for(check,description,seconds=60):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        try:
            result=check()
            if result:
                return result
        except (OSError,ValueError,KeyError):
            pass
        time.sleep(.5)
    raise RuntimeError('Timed out: '+description)


def main():
    local=bridge.load_config(ROOT/'configs/local-exchange.json')
    work=ROOT/'work';work.mkdir(exist_ok=True)
    base=Path(tempfile.mkdtemp(prefix='exchange-e2e-',dir=work))
    configs={};processes=[];handles=[]
    try:
        for index,role in enumerate(('ultra5060','pro360')):
            state=base/role;home=state/'syncthing';project=state/'project'
            state.mkdir()
            result=bridge.command(['git','clone','--no-hardlinks',str(ROOT),str(project)],ROOT)
            if result.returncode:
                raise RuntimeError(result.stderr)
            cfg=dict(local,role=role,project_root=str(project),state_root=str(state),
                     exchange_root=str(state/'exchange'),syncthing_home=str(home),
                     auto_git=False,review_debounce_seconds=0,peer_device_id='')
            configs[role]=cfg
            result=bridge.command([local['syncthing_exe'],'generate','--home',str(home),'--no-port-probing'],ROOT)
            if result.returncode:
                raise RuntimeError(result.stderr)
            xml=ET.parse(home/'config.xml');top=xml.getroot()
            top.find('gui/address').text=f'127.0.0.1:{18385+index}'
            options=top.find('options')
            for name in ('globalAnnounceEnabled','localAnnounceEnabled','relaysEnabled','natEnabled','startBrowser'):
                options.find(name).text='false'
            for child in list(options.findall('listenAddress')):
                options.remove(child)
            ET.SubElement(options,'listenAddress').text=f'tcp://127.0.0.1:{22101+index}'
            for folder in list(top.findall('folder')):
                top.remove(folder)
            xml.write(home/'config.xml',encoding='utf-8',xml_declaration=True)
            handle=(state/'transport.log').open('wb');handles.append(handle)
            processes.append(subprocess.Popen([local['syncthing_exe'],'serve','--home',str(home),'--no-browser','--no-console','--no-upgrade','--no-restart'],
                              stdout=handle,stderr=handle,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0))
            cfg['device_id']=wait_for(lambda:api(home,'system/status'),'transport startup')['myID']
            bridge.atomic_json(state/'config.json',cfg)
        for index,(role,cfg) in enumerate(configs.items()):
            other=configs['pro360' if role=='ultra5060' else 'ultra5060']
            configure(cfg['syncthing_home'],role,cfg['exchange_root'],other['device_id'])
            settings=api(cfg['syncthing_home'],'config')
            for device in settings['devices']:
                if device['deviceID']==other['device_id']:
                    device['addresses']=[f'tcp://127.0.0.1:{22102-index}']
            api(cfg['syncthing_home'],'config',settings,'PUT')
        ultra=configs['ultra5060'];pro=configs['pro360']
        wait_for(lambda:api(ultra['syncthing_home'],'system/connections')['connections'].get(pro['device_id'],{}).get('connected'),'mutual TLS connection')
        print('Connected two isolated loopback Syncthing devices',flush=True)
        import cv2
        import numpy as np
        video=Path(ultra['project_root'])/'data/derived/exchange_test/clip.mp4'
        video.parent.mkdir(parents=True)
        writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'mp4v'),10,(64,48))
        for value in range(10):
            writer.write(np.full((48,64,3),value*20,dtype=np.uint8))
        writer.release()
        review=Path(ultra['project_root'])/bridge.WATCH[0]
        review.parent.mkdir(parents=True);review.write_text('id,label\nfixture,unreviewed\n',encoding='utf-8')
        job=bridge.publish(ultra,'prepare_review',['data/derived/exchange_test',bridge.WATCH[0]])
        def process_pro():
            bridge.run_worker(pro,Path(pro['state_root'])/'config.json')
            path=bridge.dirs(pro)[0]/'results'/job['id']/'result.json'
            return json.loads(path.read_text()) if path.exists() else None
        result=wait_for(process_pro,'transfer and supervised CPU preview',90)
        if result['status']!='completed':
            raise RuntimeError(result)
        print('Transferred, hashed, imported and generated CPU preview',flush=True)
        preview_index=bridge.dirs(pro)[0]/'results'/job['id']/'previews/index.json'
        assert len(json.loads(preview_index.read_text()))==1
        returned_review=Path(pro['project_root'])/bridge.WATCH[0]
        returned_review.write_text('id,label\nfixture,reviewed\n',encoding='utf-8')
        bridge.run_worker(pro,Path(pro['state_root'])/'config.json')
        bridge.run_worker(pro,Path(pro['state_root'])/'config.json')
        def process_ultra():
            bridge.run_worker(ultra,Path(ultra['state_root'])/'config.json')
            path=Path(ultra['project_root'])/'data/derived/peer_reviews/latest.json'
            return json.loads(path.read_text()) if path.exists() else None
        latest=wait_for(process_ultra,'automatic reviewed CSV return')
        returned=Path(ultra['project_root'])/latest['directory']/bridge.WATCH[0]
        assert 'reviewed' in returned.read_text() and 'unreviewed' in review.read_text()
        remote_result=bridge.dirs(ultra)[1]/'results'/job['id']/'result.json'
        wait_for(lambda:remote_result.exists(),'CPU result back to Ultra')
        report=dict(status='passed',physical_pro_test=False,checks=['mutual TLS','data SHA-256','CPU harness preview','automatic label return','original label preserved','CPU result synchronization'])
        bridge.atomic_json(base/'report.json',report)
        print(json.dumps(dict(report,report_path=str(base/'report.json')),indent=2),flush=True)
    finally:
        for cfg in configs.values():
            try:
                api(cfg['syncthing_home'],'system/shutdown',{},'POST')
            except Exception:
                pass
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.terminate();process.wait(timeout=10)
        for handle in handles:
            handle.close()


if __name__=='__main__':
    main()
