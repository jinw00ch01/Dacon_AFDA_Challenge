"""Decision 12-C step 1: pooled optical-flow grids for the official-format windows of rule A (windows_pair.csv).

For every window (same 50 source frames that rule A and e001 see), compute Farneback flow between consecutive
160x90 gray frames and pool u, v, |frame diff| to a 16x9 grid. Output npz key <vid>_<win> -> (49, 3, 9, 16) float16.

Usage: s2_scene_flow.py <windows_pair.csv> <cache_dir> <out.npz> [workers]
"""
import sys
from multiprocessing import Pool
from pathlib import Path

import cv2
import numpy as np
import pandas as pd


def pool(x, g=10):
    h, w = x.shape
    return x.reshape(h // g, g, w // g, g).mean((1, 3))


def work(args):
    vid, win, idx, cache = args
    z = np.load(Path(cache) / f"{vid}.npz")
    fr, first = z["frames"], int(z["first_idx"])
    f = fr[[i - first for i in idx]]
    out = np.zeros((len(idx) - 1, 3, 9, 16), np.float16)
    for k in range(1, len(idx)):
        a, b = f[k - 1], f[k]
        fl = cv2.calcOpticalFlowFarneback(a, b, None, 0.5, 3, 13, 3, 5, 1.1, 0)
        out[k - 1, 0] = pool(fl[..., 0])
        out[k - 1, 1] = pool(fl[..., 1])
        out[k - 1, 2] = pool(np.abs(a.astype(np.float32) - b.astype(np.float32)))
    return f"{vid}_{win}", out


def main():
    wp, cache, dst = sys.argv[1], sys.argv[2], sys.argv[3]
    workers = int(sys.argv[4]) if len(sys.argv) > 4 else 4
    w = pd.read_csv(wp, dtype={"video_id": str})
    jobs = [(r.video_id, int(r.win), [int(i) for i in r.source_frame_indices.split()], cache) for r in w.itertuples()]
    res = {}
    with Pool(workers) as p:
        for i, (k, a) in enumerate(p.imap_unordered(work, jobs, chunksize=4)):
            res[k] = a
            if i % 50 == 0:
                print(i, k, flush=True)
    np.savez_compressed(dst, **res)
    print("done", len(res))


if __name__ == "__main__":
    main()
