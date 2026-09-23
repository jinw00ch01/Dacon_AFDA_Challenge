"""Fetch small author-hosted pilots, keeping source URLs, Git object hashes and SHA256."""
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import quote
import concurrent.futures
import hashlib
import json
import time

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "comma2k19": ("commaai/comma2k19", "4c7f1a6e1957745beadc1def0e7225f559b09a2a"),
    "dota": ("MoonBlvd/Detection-of-Traffic-Anomaly", "f8f603b8c06a946bc314752947ed480a4f33f82a"),
    "ccd": ("Cogito2012/CarCrashDataset", "bf2faa84a38898516992d4307ecf91653b7e7831"),
}


def request(url):
    return urlopen(Request(url, headers={"User-Agent": "AFDA-public-data-pilot"}), timeout=60)


def fetch(task):
    name, repo, revision, entry = task
    original = entry["path"]
    url = f"https://raw.githubusercontent.com/{repo}/{revision}/{quote(original, safe='/')}"
    relative = original.replace("|", "_")
    path = ROOT / "data/external" / name / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        temporary = path.with_name(path.name + ".part")
        for attempt in range(3):
            try:
                with request(url) as response, temporary.open("wb") as handle:
                    while block := response.read(1024 * 1024):
                        handle.write(block)
                temporary.replace(path)
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2)
    data = path.read_bytes()
    git_sha = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
    if git_sha != entry["sha"] or len(data) != entry["size"]:
        raise ValueError(f"Author Git object mismatch: {path}")
    return {"dataset": name, "source_url": url, "repository_revision": revision,
            "source_path": original, "local_path": path.relative_to(ROOT).as_posix(),
            "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "git_blob_sha1": git_sha}


def main():
    tasks = []
    for name, (repo, revision) in SOURCES.items():
        with request(f"https://api.github.com/repos/{repo}/git/trees/{revision}?recursive=1") as response:
            tree = json.load(response)
        for entry in tree["tree"]:
            path = entry["path"]
            include = path in {"README.md", "LICENSE"}
            include |= name == "comma2k19" and path.startswith("Example_1/")
            include |= name == "dota" and path in {"dataset/DoTA_annotations.zip", "dataset/metadata_train.json", "dataset/metadata_val.json"}
            if include and entry["type"] == "blob":
                tasks.append((name, repo, revision, entry))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(fetch, tasks))
    output = ROOT / "data/external/pilot_manifest.json"
    output.write_text(json.dumps({"files": records, "notes": {
        "comma2k19": "One 1-minute video+sensor pilot, MIT dataset card; not a full training set.",
        "dota": "Annotations only. Video access and dataset-specific use terms still need review.",
        "ccd": "Documentation/license only. Repository MIT does not alone settle third-party video rights."}}, indent=2), encoding="utf-8")
    print(json.dumps({"files": len(records), "bytes": sum(r["bytes"] for r in records), "manifest": str(output)}, indent=2))


if __name__ == "__main__":
    main()
