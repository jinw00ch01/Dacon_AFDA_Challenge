"""QA for an S1 synthetic recapture folder: count, duplicates, SHA-256, decode, size, split consistency.

Usage: s1_qa.py <out_dir> <report.json> [--variants 4]
"""
import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "data/derived/comma_subset_v1/s23_capture_ready.csv"
MAX_BYTES = 512 * 1024 * 1024


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("report", type=Path)
    ap.add_argument("--variants", type=int, default=4)
    args = ap.parse_args()
    out_dir = args.out_dir if args.out_dir.is_absolute() else ROOT / args.out_dir
    with PLAN.open(encoding="utf-8-sig", newline="") as f:
        plan = {}
        for r in csv.DictReader(f):
            plan.setdefault(r["planned_source_id"], r)
    with (out_dir / "manifest.csv").open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    problems = []
    dup = [k for k, n in Counter(r["file"] for r in rows).items() if n > 1]
    if dup:
        problems.append(f"duplicate manifest rows: {dup}")
    listed = {r["file"] for r in rows}
    on_disk = {p.name for p in out_dir.glob("*.mp4")}
    if on_disk - listed:
        problems.append(f"mp4 not in manifest: {sorted(on_disk - listed)}")
    if listed - on_disk:
        problems.append(f"manifest file missing on disk: {sorted(listed - on_disk)}")

    per_source = defaultdict(list)
    decoded = {}
    for r in rows:
        per_source[r["source_id"]].append(r)
        path = out_dir / r["file"]
        if not path.exists():
            continue
        size = path.stat().st_size
        if size > MAX_BYTES:
            problems.append(f"{r['file']} exceeds 512MiB ({size})")
        if str(size) != r["bytes"]:
            problems.append(f"{r['file']} size {size} != manifest {r['bytes']}")
        if sha256(path) != r["sha256"]:
            problems.append(f"{r['file']} sha256 mismatch")
        cap = cv2.VideoCapture(str(path))
        n = 0
        while cap.grab():
            n += 1
        w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        decoded[r["file"]] = n
        if n != int(r["frames"]) or (w, h) != (int(r["width"]), int(r["height"])):
            problems.append(f"{r['file']} decoded {n} frames {w}x{h}, manifest {r['frames']} {r['width']}x{r['height']}")

    expected = set(plan)
    missing_sources = sorted(expected - set(per_source))
    if missing_sources:
        problems.append(f"sources without output: {missing_sources}")
    for src, rs in per_source.items():
        variants = sorted(r["variant"] for r in rs)
        want = sorted(["ORIG"] + [f"SYN{k}" for k in range(args.variants)])
        if variants != want:
            problems.append(f"{src} variants {variants} != {want}")
        splits = {r["split"] for r in rs}
        groups = {r["origin_group"] for r in rs}
        if len(splits) != 1 or len(groups) != 1:
            problems.append(f"{src} mixed split/group {splits} {groups}")
        if src in plan and splits != {plan[src]["confirmed_split"]}:
            problems.append(f"{src} split {splits} != plan {plan[src]['confirmed_split']}")
    group_splits = defaultdict(set)
    for r in rows:
        group_splits[r["origin_group"]].add(r["split"])
    for g, s in group_splits.items():
        if len(s) > 1:
            problems.append(f"origin_group {g} spans splits {sorted(s)}")

    split_counts = Counter(r["split"] for r in rows)
    source_split = Counter(plan[s]["confirmed_split"] for s in per_source if s in plan)
    report = {
        "out_dir": str(out_dir.relative_to(ROOT)) if out_dir.is_relative_to(ROOT) else str(out_dir),
        "files": len(rows), "sources": len(per_source), "expected_sources": len(expected),
        "files_per_split": dict(split_counts), "sources_per_split": dict(source_split),
        "total_bytes": sum(int(r["bytes"]) for r in rows),
        "max_bytes": max((int(r["bytes"]) for r in rows), default=0),
        "decoded_frames": sorted(set(decoded.values())),
        "synthetic_all": all(r["synthetic"] == "1" for r in rows),
        "pass": not problems, "problems": problems,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "problems"} | {"n_problems": len(problems)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
