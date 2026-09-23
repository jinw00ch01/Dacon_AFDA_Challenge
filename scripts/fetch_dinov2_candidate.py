"""Fetch official Apache-2.0 DINOv2 ViT-S/14 candidate; no remote code execution."""
from pathlib import Path
from urllib.request import urlopen
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
REVISION='7764ea0f912e53c92e82eb78a2a1631e92725fc8'
WEIGHT_URL='https://dl.fbaipublicfiles.com/dinov2/dinov2_vits14/dinov2_vits14_pretrain.pth'


def download(url,path):
    path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists():
        temporary=path.with_suffix(path.suffix+'.part')
        with urlopen(url,timeout=90) as response, temporary.open('wb') as handle:
            while block:=response.read(1024*1024):
                handle.write(block)
        temporary.replace(path)
    return {'url':url,'local_path':path.relative_to(ROOT).as_posix(),'bytes':path.stat().st_size,
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    directory=ROOT/'artifacts/pretrained/dinov2_vits14'
    files=[download(f'https://raw.githubusercontent.com/facebookresearch/dinov2/{REVISION}/{name}',directory/name)
           for name in ('README.md','LICENSE','MODEL_CARD.md')]
    weight=directory/'dinov2_vits14_pretrain.pth'
    files.append(download(WEIGHT_URL,weight))
    import torch
    state=torch.load(weight,map_location='cpu',weights_only=True)
    if not isinstance(state,dict) or not state or not all(isinstance(v,torch.Tensor) for v in state.values()):
        raise ValueError('Expected a tensor-only state dict')
    report={'model':'dinov2_vits14','revision':REVISION,'license':'Apache-2.0',
            'state_tensors':len(state),'parameters':sum(t.numel() for t in state.values()),
            'files':files,'verification':'HTTPS download, recorded SHA256, weights_only deserialization; not author-signed weight checksum',
            'status':'candidate_acquired_not_integrated_or_finetuned',
            'note':'Offline architecture packaging and real-video inference remain. Do not use torch.hub remote loads in submission.'}
    (directory/'manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
