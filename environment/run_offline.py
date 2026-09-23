"""Invoke all three submission entry points and validate explicitly supplied manifests."""
from pathlib import Path
import argparse
import importlib.util
import json
import platform
import time
import sys
from harness.contracts import validate


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--submission',type=Path,default=Path('/submission'))
    parser.add_argument('--data',type=Path,default=Path('/data'))
    parser.add_argument('--expected',type=Path,default=Path('/expected'))
    parser.add_argument('--output',type=Path,default=Path('/output'))
    parser.add_argument('--require-cuda',action='store_true')
    args=parser.parse_args()
    if platform.system()!='Linux':
        raise RuntimeError('Run this gate inside Linux')
    import torch
    import pandas as pd
    if args.require_cuda and not torch.cuda.is_available():
        raise RuntimeError('CUDA gate requested but GPU unavailable')
    args.output.mkdir(parents=True,exist_ok=True)
    # Resolve sibling modules in the submission while preserving the mounted input.
    sys.path.insert(0,str(args.submission.resolve()))
    spec=importlib.util.spec_from_file_location('afda_submission',args.submission/'inference.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report={'platform':platform.platform(),'python':sys.version,'torch':torch.__version__,
            'cuda_available':torch.cuda.is_available(),'stages':{},
            'scope':'local evaluation-like run; not official scoring or L40S equivalence'}
    started=time.monotonic()
    for stage in ('stage1','stage2','stage3'):
        expected=json.loads((args.expected/(stage+'.json')).read_text(encoding='utf-8'))
        t=time.monotonic()
        frame=getattr(module,'predict_'+stage)(str(args.data/stage),str(args.submission/'model'/stage))
        if not isinstance(frame,pd.DataFrame):
            raise TypeError(f'{stage} must return pandas.DataFrame')
        validate(stage,list(frame.columns),frame.to_dict(orient='records'),expected)
        frame.to_csv(args.output/(stage+'.csv'),index=False,encoding='utf-8')
        report['stages'][stage]={'rows':len(frame),'seconds':time.monotonic()-t}
    report['seconds']=time.monotonic()-started
    (args.output/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
