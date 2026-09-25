#!/usr/bin/env python
"""Freeze a set of files into an immutable release directory with a SHA-256 manifest.

Usage (role venv python only):
  python scripts/freeze_release.py \
      --release-id s2-labels-v4-20260925 \
      --kind label \
      --created-utc 2026-09-25T03:01:55Z \
      --source-packet 64d637fff8ca4133a04acf26bffc7709 \
      --note "Nexar S2 agent labels v4 (agent-only, human reviewed=0)" \
      --meta label_source_human=0 --meta label_source_agent=75 \
      --file <abs-or-rel-path> [--file ...]

Writes data/derived/releases/<release-id>/ with the copied payload files, a
manifest.json (sorted list of {path, bytes, sha256}; excludes itself and
COMMITTED.json) and COMMITTED.json (release_id + manifest sha256). Refuses to
overwrite an existing release directory so frozen releases stay immutable.

Hashes are the SHA-256 of the bytes on disk. This does not re-serialize inputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def sha256_file(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    n = 0
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
            n += len(chunk)
    return h.hexdigest(), n


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--release-id", required=True)
    ap.add_argument("--kind", required=True, help="label|dataset|split|metric|model")
    ap.add_argument("--created-utc", required=True, help="RFC3339 UTC, e.g. 2026-09-25T03:01:55Z")
    ap.add_argument("--source-packet", default=None)
    ap.add_argument("--note", default="")
    ap.add_argument("--meta", action="append", default=[], help="key=value metadata, repeatable")
    ap.add_argument("--file", action="append", dest="files", required=True, help="payload file, repeatable")
    args = ap.parse_args(argv)

    rel_dir = ROOT / "data" / "derived" / "releases" / args.release_id
    if rel_dir.exists():
        print(f"ERROR: release dir already exists (immutable): {rel_dir}", file=sys.stderr)
        return 2

    srcs = []
    for f in args.files:
        p = Path(f)
        if not p.is_absolute():
            p = (ROOT / p).resolve()
        if not p.is_file():
            print(f"ERROR: not a file: {p}", file=sys.stderr)
            return 2
        srcs.append(p)

    names = [p.name for p in srcs]
    if len(set(names)) != len(names):
        print("ERROR: duplicate payload file names", file=sys.stderr)
        return 2

    meta = {}
    for kv in args.meta:
        if "=" not in kv:
            print(f"ERROR: bad --meta (need key=value): {kv}", file=sys.stderr)
            return 2
        k, v = kv.split("=", 1)
        meta[k] = v

    rel_dir.mkdir(parents=True)
    entries = []
    for p in srcs:
        dst = rel_dir / p.name
        shutil.copy2(p, dst)
        digest, size = sha256_file(dst)
        entries.append({"path": p.name, "bytes": size, "sha256": digest})
    entries.sort(key=lambda e: e["path"])

    manifest = {
        "release_id": args.release_id,
        "kind": args.kind,
        "created_utc": args.created_utc,
        "source_packet": args.source_packet,
        "note": args.note,
        "meta": meta,
        "files": entries,
    }
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    (rel_dir / "manifest.json").write_bytes(manifest_bytes)
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()

    committed = {"release_id": args.release_id, "manifest_sha256": manifest_sha, "created_utc": args.created_utc}
    (rel_dir / "COMMITTED.json").write_bytes(
        json.dumps(committed, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    )

    print(json.dumps({"release_dir": str(rel_dir), "manifest_sha256": manifest_sha, "n_files": len(entries)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
