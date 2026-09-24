"""Configure only the dedicated AFDA Syncthing instance via its loopback API."""
import argparse
import copy
import json
from pathlib import Path
import re
import urllib.request
import xml.etree.ElementTree as ET

FOLDERS={'ultra5060':'ultra_to_pro','pro360':'pro_to_ultra'}


def api(home,endpoint,body=None,method=None):
    xml=ET.parse(Path(home)/'config.xml').getroot()
    address=xml.findtext('gui/address')
    if not re.fullmatch(r'127\.0\.0\.1:\d+',address or ''):
        raise ValueError('AFDA administration must stay on IPv4 loopback')
    key=xml.findtext('gui/apikey')
    request=urllib.request.Request('http://'+address+'/rest/'+endpoint,
        data=None if body is None else json.dumps(body).encode(),
        headers={'X-API-Key':key,'Content-Type':'application/json'},method=method)
    with urllib.request.urlopen(request,timeout=15) as response:
        data=response.read()
    return json.loads(data) if data else None


def configure(home,role,exchange_root,peer_id=None):
    if peer_id and not re.fullmatch(r'[A-Z2-7]{7}(?:-[A-Z2-7]{7}){7}',peer_id):
        raise ValueError('Invalid Syncthing device ID')
    cfg=api(home,'config')
    my_id=api(home,'system/status')['myID']
    if peer_id==my_id:
        raise ValueError('Peer cannot be this device')
    if peer_id and not any(d['deviceID']==peer_id for d in cfg['devices']):
        device=copy.deepcopy(cfg['defaults']['device'])
        device.update(deviceID=peer_id,name='AFDA-'+('Pro360' if role=='ultra5060' else 'Ultra'),autoAcceptFolders=False)
        cfg['devices'].append(device)
    for device in cfg['devices']:
        if device['deviceID']==my_id:
            device['name']='AFDA-'+role
    for owner,name in FOLDERS.items():
        folder_id='afda-'+name.replace('_','-')+'-v1'
        folder=next((copy.deepcopy(f) for f in cfg['folders'] if f['id']==folder_id),copy.deepcopy(cfg['defaults']['folder']))
        path=Path(exchange_root)/name
        path.mkdir(parents=True,exist_ok=True)
        members={d['deviceID'] for d in folder.get('devices',[])}|{my_id}
        if peer_id:
            members.add(peer_id)
        # Syncthing v2 preserves an encryptionPassword field when it is omitted
        # from an existing folder device entry.  The AFDA exchange is plain data
        # on both folders, so explicitly clear the field for every peer.  Leaving
        # whitespace from the generated defaults makes one side expect encrypted
        # data and prevents the folder from syncing after TLS connects.
        folder.update(id=folder_id,label='AFDA '+name,path=str(path.resolve()),
                      type='sendonly' if owner==role else 'receiveonly',
                      devices=[{'deviceID':d,'encryptionPassword':''} for d in sorted(members)],
                      rescanIntervalS=60,fsWatcherEnabled=True)
        if owner!=role:
            folder['versioning']={**folder.get('versioning',{}),'type':'simple','params':{'keep':'5'}}
        cfg['folders']=[f for f in cfg['folders'] if f['id']!=folder_id]+[folder]
        ignore=path/'.stignore'
        if not ignore.exists():
            ignore.write_text('*.partial\n.staging-*\n',encoding='utf-8')
    cfg['options'].update(startBrowser=False,natEnabled=False,urAccepted=-1,autoUpgradeIntervalH=0)
    api(home,'config',cfg,'PUT')
    return {'device_id':my_id,'role':role,'peer_id':peer_id,'restart_required':api(home,'config/restart-required')['requiresRestart']}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['configure','status','pair'])
    parser.add_argument('--config',required=True)
    parser.add_argument('--peer-id')
    args=parser.parse_args()
    path=Path(args.config)
    cfg=json.loads(path.read_text(encoding='utf-8-sig'))
    if args.action in ['configure','pair']:
        peer=args.peer_id or cfg.get('peer_device_id')
        if args.action=='pair' and not peer:
            parser.error('--peer-id required')
        result=configure(cfg['syncthing_home'],cfg['role'],cfg['exchange_root'],peer)
        cfg['device_id']=result['device_id'];cfg['peer_device_id']=peer
        path.write_text(json.dumps(cfg,indent=2),encoding='utf-8')
        print(json.dumps(result))
    else:
        status=api(cfg['syncthing_home'],'system/status')
        connections=api(cfg['syncthing_home'],'system/connections')['connections']
        peer=cfg.get('peer_device_id')
        print(json.dumps({'role':cfg['role'],'device_id':status['myID'],'peer_device_id':peer,
                          'peer_connected':bool(connections.get(peer,{}).get('connected')),
                          'pending_devices':api(cfg['syncthing_home'],'cluster/pending/devices')}))


if __name__=='__main__':
    main()
