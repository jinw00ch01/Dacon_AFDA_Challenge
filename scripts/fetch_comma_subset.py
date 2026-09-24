"""Fetch a bounded, reproducible comma2k19 subset from official public ZIPs.

HTTP Range reads avoid downloading all 95 GB. ZIP CRC and local SHA-256 are
checked; the whole archive's publisher SHA is recorded, NOT claimed verified.
"""
import argparse
from collections import OrderedDict, defaultdict
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import random
import re
import shutil
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REPO = 'commaai/comma2k19'
REVISION = '4bff77c7254c654c28d4c2726186b4e825adccee'
GITHUB_REVISION = '4c7f1a6e1957745beadc1def0e7225f559b09a2a'
OUT = ROOT / 'data/external/comma2k19_subset_v1'
SUFFIXES = ('video.hevc', 'global_pose/frame_times', 'processed_log/CAN/speed/t',
            'processed_log/CAN/speed/value', 'processed_log/CAN/steering_angle/t',
            'processed_log/CAN/steering_angle/value')


def request(url, headers=None):
    return urllib.request.urlopen(urllib.request.Request(url, headers={
        'User-Agent': 'AFDA-public-subset/1', **(headers or {})}), timeout=60)


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + '.part')
    temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
    temporary.replace(path)


class RemoteZip(io.RawIOBase):
    transferred = 0
    max_transfer = 3 * 1024**3
    block_size = 4 * 1024**2

    def __init__(self, entry):
        self.size = entry['size']
        self.url = f'https://huggingface.co/datasets/{REPO}/resolve/{REVISION}/{entry["path"]}'
        self.position = 0
        self.cache = OrderedDict()

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        position = offset if whence == 0 else (self.position if whence == 1 else self.size) + offset
        if position < 0:
            raise ValueError('Negative seek')
        self.position = position
        return position

    def read(self, size=-1):
        end = self.size if size < 0 else min(self.size, self.position + size)
        chunks = []
        while self.position < end:
            start = (self.position // self.block_size) * self.block_size
            if start not in self.cache:
                last = min(self.size - 1, start + self.block_size - 1)
                length = last - start + 1
                if RemoteZip.transferred + length > self.max_transfer:
                    raise RuntimeError('3 GiB transfer budget reached; existing files preserved')
                for attempt in range(3):
                    try:
                        # Separate cache keys prevent proxies serving another Range response.
                        url = self.url + f'?download=true&afda_range={start}-{last}'
                        with request(url, {'Range': f'bytes={start}-{last}'}) as response:
                            expected = f'bytes {start}-{last}/{self.size}'
                            if response.status != 206 or response.headers.get('Content-Range') != expected:
                                raise ValueError('Server did not honor the exact requested range')
                            data = response.read(length + 1)
                        RemoteZip.transferred += len(data)
                        if len(data) != length:
                            raise ValueError('Truncated range')
                        self.cache[start] = data
                        break
                    except Exception:
                        if attempt == 2:
                            raise
                        time.sleep(2)
                while len(self.cache) > 8:
                    self.cache.popitem(last=False)
            self.cache.move_to_end(start)
            amount = min(end - self.position, len(self.cache[start]) - (self.position - start))
            chunks.append(self.cache[start][self.position-start:self.position-start+amount])
            self.position += amount
        return b''.join(chunks)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--count', type=int, default=24)
    parser.add_argument('--plan-only', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.count <= 24:
        parser.error('count must be between 1 and 24 for this bounded acquisition')
    if shutil.disk_usage(ROOT).free < 40 * 1024**3:
        raise RuntimeError('Keep at least 40 GiB free on Ultra')
    OUT.mkdir(parents=True, exist_ok=True)
    evidence = OUT / 'source_evidence'
    evidence.mkdir(exist_ok=True)
    sources = {
        'DATASET_CARD.md': f'https://huggingface.co/datasets/{REPO}/resolve/{REVISION}/README.md',
        'LICENSE': f'https://raw.githubusercontent.com/{REPO}/{GITHUB_REVISION}/LICENSE',
        'GITHUB_README.md': f'https://raw.githubusercontent.com/{REPO}/{GITHUB_REVISION}/README.md'}
    for filename, url in sources.items():
        with request(url) as response:
            data = response.read(1024**2)
        (evidence / filename).write_bytes(data)
    with request(f'https://huggingface.co/api/datasets/{REPO}/tree/{REVISION}/raw_data?expand=false') as response:
        entries = json.load(response)
    entries = sorted((e for e in entries if e['path'].endswith('.zip')), key=lambda e: int(re.search(r'Chunk_(\d+)', e['path'])[1]))
    catalog = []
    for entry in entries:
        index_path = evidence / (Path(entry['path']).stem + '_index.json')
        if index_path.exists():
            index = json.loads(index_path.read_text())
        else:
            with RemoteZip(entry) as remote, zipfile.ZipFile(remote) as archive:
                index = [{'name': z.filename, 'size': z.file_size, 'compressed_size': z.compress_size, 'crc32': f'{z.CRC:08x}'} for z in archive.infolist() if not z.is_dir()]
            atomic_json(index_path, index)
        names = {x['name'] for x in index}
        count = 0
        for item in index:
            if not item['name'].endswith('/video.hevc'):
                continue
            prefix = item['name'][:-len('video.hevc')]
            route = PurePosixPath(prefix).parts[-2]
            if not all(prefix + suffix in names for suffix in SUFFIXES):
                continue
            if route == 'b0c9d2329ad1606b|2018-08-02--08-34-47':
                continue  # Already acquired pilot route.
            date = route.split('|')[-1][:10]
            catalog.append({'archive': entry, 'prefix': prefix, 'origin_group': route, 'recording_date': date})
            count += 1
        print(json.dumps({'indexed':entry['path'], 'eligible_segments':count}), flush=True)
    rng = random.Random(20260924)
    rng.shuffle(catalog)
    by_date = defaultdict(list)
    for item in catalog:
        by_date[item['recording_date']].append(item)
    dates = sorted(by_date)
    rng.shuffle(dates)
    selected = [by_date[date][0] for date in dates[:args.count]]
    # Distinct recording days are a stronger grouping constraint than route IDs.
    if len(selected) != args.count:
        raise ValueError(f'Only {len(selected)} distinct dates; do not fake independent sources')
    for index, item in enumerate(selected):
        item['source_id'] = f'SRC{index+1:03d}'
        item['split'] = 'train' if index < 16 else ('validation' if index < 20 else 'test')
    plan = {'repository':REPO, 'revision':REVISION, 'seed':20260924, 'count':len(selected),
            'grouping':'one segment per recording date; same highway/vehicles may still correlate', 'selected':selected}
    atomic_json(OUT / 'selection.json', plan)
    if args.plan_only:
        print(json.dumps({'planned':len(selected), 'dates':sorted(x['recording_date'] for x in selected), 'network_bytes':RemoteZip.transferred}), flush=True)
        return
    manifest_path = OUT / 'manifest.json'
    previous = json.loads(manifest_path.read_text())['files'] if manifest_path.exists() else []
    records = {row['path']:row for row in previous}
    for item in sorted(selected, key=lambda x: (x['archive']['path'], x['prefix'])):
        with RemoteZip(item['archive']) as remote, zipfile.ZipFile(remote) as archive:
            for suffix in SUFFIXES:
                member = item['prefix'] + suffix
                relative = PurePosixPath('segments') / item['origin_group'].replace('|','_') / PurePosixPath(item['prefix']).name / suffix
                if '..' in relative.parts or relative.is_absolute():
                    raise ValueError('Unsafe archive path')
                destination = OUT.joinpath(*relative.parts)
                if not destination.resolve().is_relative_to(OUT.resolve()):
                    raise ValueError('Archive member escapes acquisition directory')
                relative_string = relative.as_posix()
                if destination.exists():
                    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
                    if relative_string not in records or records[relative_string]['sha256'] != digest:
                        raise ValueError(f'Untracked or changed existing file: {relative}')
                    continue
                info = archive.getinfo(member)
                if info.file_size > 100 * 1024**2:
                    raise ValueError('Member exceeds 100 MiB bound')
                data = archive.read(member)  # zipfile validates member CRC.
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary = destination.with_name(destination.name + '.part')
                temporary.write_bytes(data)
                temporary.replace(destination)
                records[relative_string] = {'path':relative_string, 'source_id':item['source_id'], 'origin_group':item['origin_group'],
                    'recording_date':item['recording_date'], 'split':item['split'], 'source_url':remote.url, 'archive_member':member,
                    'archive_publisher_sha256_not_fully_verified':item['archive']['lfs']['oid'],
                    'bytes':len(data), 'sha256':hashlib.sha256(data).hexdigest(), 'zip_crc32_verified':f'{info.CRC:08x}'}
                atomic_json(manifest_path, {'repository':REPO,'revision':REVISION,'files':list(records.values())})
        print(json.dumps({'acquired':item['source_id'],'date':item['recording_date'],'files':len(records),'network_bytes':RemoteZip.transferred}), flush=True)
    print(json.dumps({'complete':True,'sources':len(selected),'files':len(records),'bytes':sum(x['bytes'] for x in records.values()),'network_bytes':RemoteZip.transferred}), flush=True)


if __name__ == '__main__':
    main()
