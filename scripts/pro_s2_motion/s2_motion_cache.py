"""Decision 12-A: cache low-res grayscale frames around the labelled collision for the S2 motion rule.

For every collision_valid video in the merged Nexar v2 label CSV, decode sequentially and keep the source
frames in [col - PRE s, col + POST s] as 160x90 uint8 grayscale (all source frames, so 10 Hz windows with any
phase can be rebuilt later). Output: <out>/<vid>.npz (frames, first_idx, fps, col) and <out>/index.csv.

Usage: s2_motion_cache.py <merged.csv> <out_dir> [workers]
"""
import csv
import sys
from multiprocessing import Pool
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PRE, POST, W, H = 6.0, 6.0, 160, 90


def work(args):
    vid, path, fps, col, out = args
    dst = Path(out) / f"{vid}.npz"
    if dst.exists():
        return vid, "cached", None
    lo, hi = max(0, int(col - PRE * fps)), int(col + POST * fps)
    cap = cv2.VideoCapture(str(ROOT / path))
    frames, i = [], 0
    while i <= hi:
        ok, f = cap.read()
        if not ok:
            break
        if i >= lo:
            g = cv2.cvtColor(cv2.resize(f, (W, H), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
            frames.append(g)
        i += 1
    cap.release()
    if not frames:
        return vid, "empty", None
    np.savez_compressed(dst, frames=np.stack(frames), first_idx=lo, fps=fps, col=col)
    return vid, "ok", len(frames)


def main():
    merged, out = sys.argv[1], Path(sys.argv[2])
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    out.mkdir(parents=True, exist_ok=True)
    jobs = []
    for r in csv.DictReader(open(merged, encoding="utf-8-sig")):
        if r["collision_valid"] != "1" or not r["collision_frame"]:
            continue
        jobs.append((r["video_id"], r["source_path"], float(r["fps"]), int(float(r["collision_frame"])), str(out)))
    with Pool(workers) as p, open(out / "index.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["video_id", "status", "n_frames"])
        for vid, st, n in p.imap_unordered(work, jobs):
            w.writerow([vid, st, n])
            print(vid, st, n, flush=True)


if __name__ == "__main__":
    main()
