from pathlib import Path
from urllib.request import urlopen
from concurrent.futures import ThreadPoolExecutor
import hashlib, json

root = Path(__file__).resolve().parents[1] / 'work/linux'
root.mkdir(parents=True, exist_ok=True)
urls = {
 '7zr.exe': 'https://github.com/ip7z/7zip/releases/download/26.03/7zr.exe',
 '7z2603-x64.exe': 'https://github.com/ip7z/7zip/releases/download/26.03/7z2603-x64.exe',
 'qemu.exe': 'https://qemu.weilnetz.de/w64/qemu-w64-setup-20260811.exe',
 'qemu.sha512': 'https://qemu.weilnetz.de/w64/qemu-w64-setup-20260811.sha512',
 'ubuntu.img': 'https://cloud-images.ubuntu.com/minimal/releases/noble/release-20260905/ubuntu-24.04-minimal-cloudimg-amd64.img',
 'ubuntu.SHA256SUMS': 'https://cloud-images.ubuntu.com/minimal/releases/noble/release-20260905/SHA256SUMS',
}
def fetch(item):
 name, url = item
 p = root / name
 if not p.exists():
  tmp = p.with_suffix(p.suffix + '.part')
  with urlopen(url, timeout=60) as r, tmp.open('wb') as f:
   while block := r.read(1024*1024): f.write(block)
  tmp.replace(p)
 result = {'file': name, 'url':url, 'bytes':p.stat().st_size, 'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
 print(json.dumps(result), flush=True)
 return result
with ThreadPoolExecutor(max_workers=4) as pool:
 records = list(pool.map(fetch, urls.items()))
assert hashlib.sha512((root/'qemu.exe').read_bytes()).hexdigest() == (root/'qemu.sha512').read_text().split()[0]
line = next(x for x in (root/'ubuntu.SHA256SUMS').read_text().splitlines() if x.endswith('ubuntu-24.04-minimal-cloudimg-amd64.img'))
assert hashlib.sha256((root/'ubuntu.img').read_bytes()).hexdigest() == line.split()[0]
(root/'download_manifest.json').write_text(json.dumps(records,indent=2))
print('Vendor checksums verified', flush=True)
for name, expected in {
 '7zr.exe': 'ad4c82fadcbdf93c03b4fc440f300509c7d60c5c2f4d183e35d9d70d6957037d',
 '7z2603-x64.exe': '0859c524b8a63551848f0c246abddcb1d0b7b656b0fbfe879f8d85e61a9e6edd',
}.items():
 if hashlib.sha256((root/name).read_bytes()).hexdigest() != expected:
  raise ValueError('Pinned official download differs: '+name)
import subprocess
if not (root/'7zip/7z.exe').is_file():
 subprocess.run([str(root/'7zr.exe'),'x',str(root/'7z2603-x64.exe'),'-o'+str(root/'7zip'),'-y'],check=True)
if not (root/'qemu/qemu-system-x86_64.exe').is_file():
 subprocess.run([str(root/'7zip/7z.exe'),'x',str(root/'qemu.exe'),'-o'+str(root/'qemu'),'-y'],check=True)
subprocess.run([str(root/'qemu/qemu-system-x86_64.exe'),'--version'],check=True)
