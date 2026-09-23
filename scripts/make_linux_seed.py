"""Create a cloud-init ISO that runs harness tests in an isolated Linux network.

Requires pycdlib in a tooling environment (not the submission environment).
No Windows directories are shared, and no incoming ports or passwords are set.
"""
from pathlib import Path
import base64
import io
import json
import tarfile
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'work/vm-tools'))
import pycdlib


def main():
    directory=ROOT/'work/linux'
    directory.mkdir(parents=True, exist_ok=True)
    archive=io.BytesIO()
    with tarfile.open(fileobj=archive,mode='w:gz') as handle:
        for folder in ('harness','tests'):
            for path in sorted((ROOT/folder).glob('*.py')):
                handle.add(path,arcname=path.relative_to(ROOT).as_posix())
    script='''#!/bin/bash
set -eu
mkdir -p /opt/afda/code
tar -xzf /opt/afda/contracts.tar.gz -C /opt/afda/code
cd /opt/afda/code
{
  uname -a
  cat /etc/os-release
  python3 --version
  python3 -c "import psutil; print('psutil', psutil.__version__)"
  unshare --net sh -c 'ip -brief address; python3 -m unittest discover -s tests -v'
} > /opt/afda/result.txt 2>&1 && status=0 || status=$?
echo AFDA_LINUX_RESULT_BEGIN > /dev/ttyS0
cat /opt/afda/result.txt > /dev/ttyS0
echo AFDA_LINUX_EXIT=$status > /dev/ttyS0
echo AFDA_LINUX_RESULT_END > /dev/ttyS0
sync
poweroff
'''
    data={'hostname':'afda-linux-cpu', 'manage_etc_hosts':True, 'ssh_pwauth':False,
          'package_update':True, 'packages':['python3','python3-psutil','util-linux','iproute2'],
          'write_files':[{'path':'/opt/afda/contracts.tar.gz','encoding':'b64','content':base64.b64encode(archive.getvalue()).decode()},
                         {'path':'/opt/afda/run-checks.sh','permissions':'0755','content':script}],
          'runcmd':[['bash','/opt/afda/run-checks.sh']]}
    iso=pycdlib.PyCdlib()
    iso.new(interchange_level=3,joliet=3,rock_ridge='1.09',vol_ident='cidata')
    for name, content in [('user-data','#cloud-config\n'+json.dumps(data)),('meta-data','instance-id: afda-contracts-v1\nlocal-hostname: afda-linux-cpu\n')]:
        raw=content.encode()
        iso.add_fp(io.BytesIO(raw),len(raw),iso_path='/'+name.upper().replace('-','_')+';1',rr_name=name,joliet_path='/'+name)
    iso.write(str(directory/'seed.iso'))
    iso.close()
    print(directory/'seed.iso')


if __name__=='__main__':
    main()
