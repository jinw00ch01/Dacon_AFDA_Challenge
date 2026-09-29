"""S3 speed proxy v2 (Pro, decision 1a07c3d2 request "speed proxy improvement"): ground-plane zoom search.

Why: 160px Farneback speed proxies saturate above ~20 m/s (per-source Spearman with speed turns negative, e.g.
SRC022 -0.5). Instead of estimating flow, search the one-parameter ground-plane motion directly.
For forward translation d over a flat road seen by a camera at height h with focal f and horizon row y_h,
a road pixel at (x - x0, r = y - y_h) in frame t+1 came from (x - x0, r) / (1 + kappa * r) in frame t,
kappa = d / (f h). The inverse map always lands inside frame t, so large motions do not alias.
Per 10 Hz step (consecutive aux rows = what a 10 Hz test clip gives) minimise a trimmed mean abs difference
of band-mean-normalised gray in the road band over kappa, with small horizontal (yaw) and vertical (pitch)
shifts refined by coordinate descent. kappa is proportional to speed * dt; one global scale is fitted on
train later (no per-source information).
Output: <out>/ground_speed.csv (source_id, sample_index, split, kappa, cost, curv, dx, dy, speed_mps, accel proxy)
usage: s3_ground_speed.py --out <dir> [--workers 4] [--sources SRC001 ...]
"""
from __future__ import annotations

import argparse
import glob
from multiprocessing import Pool
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
AUX = ROOT / "data/derived/comma_subset_v1/s3_auxiliary_10hz.csv"
SEGMENTS = ROOT / "data/external/comma2k19_subset_v1/segments"
W, H = 320, 240
YH = 0.47 * H
X0 = W / 2
Y_LO, Y_HI = YH + 6, 0.70 * H          # road band rows (below horizon, above dashboard edge)
X_HALF = 0.40 * W
KAPPAS = np.concatenate([[0.0], np.geomspace(2e-4, 0.08, 47)])
DXS = np.arange(-8, 9, 2, dtype=np.float32)
DYS = np.arange(-4, 5, 1, dtype=np.float32)

_ys = np.arange(int(np.ceil(Y_LO)), int(Y_HI), dtype=np.float32)
_xs = np.arange(int(X0 - X_HALF), int(X0 + X_HALF), dtype=np.float32)
GX, GY = np.meshgrid(_xs, _ys)
R = GY - YH
XR = GX - X0


def norm(g):
    g = g.astype(np.float32)
    band = g[int(Y_LO) - 8:int(Y_HI) + 2]
    return (g - band.mean()) / (band.std() + 1e-3)


def cost(prev, cur_band, kappa, dx, dy):
    s = 1.0 / (1.0 + kappa * R)
    mx = (X0 + XR * s + dx).astype(np.float32)
    my = (YH + R * s + dy).astype(np.float32)
    w = cv2.remap(prev, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    e = np.abs(w - cur_band).ravel()
    k = int(0.97 * e.size)
    return float(np.partition(e, k)[:k].mean())


def estimate(prev, cur):
    cur_band = cur[GY.astype(int), GX.astype(int)]
    dx = dy = 0.0
    ki = 0
    for _ in range(2):
        cs = np.array([cost(prev, cur_band, k, dx, dy) for k in KAPPAS])
        ki = int(np.argmin(cs))
        dx = float(DXS[int(np.argmin([cost(prev, cur_band, KAPPAS[ki], x, dy) for x in DXS]))])
        dy = float(DYS[int(np.argmin([cost(prev, cur_band, KAPPAS[ki], dx, y) for y in DYS]))])
    cs = np.array([cost(prev, cur_band, k, dx, dy) for k in KAPPAS])
    ki = int(np.argmin(cs))
    lk = np.log(KAPPAS[1:])
    if 1 <= ki - 1 and ki + 1 < len(KAPPAS):   # parabolic refine in log-kappa
        a, b, c = cs[ki - 1], cs[ki], cs[ki + 1]
        den = a - 2 * b + c
        off = 0.5 * (a - c) / den if den > 1e-9 else 0.0
        step = lk[1] - lk[0]
        kap = float(np.exp(lk[ki - 1] + np.clip(off, -0.5, 0.5) * step))
        curv = float(den)
    else:
        kap, curv = float(KAPPAS[ki]), float("nan")
    return {"kappa": kap, "cost": float(cs[ki]), "cost0": float(cs[0]), "curv": curv, "dx": dx, "dy": dy}


def gray_frames(hevc, idx):
    want = set(int(i) for i in idx)
    out, i = {}, 0
    cap = cv2.VideoCapture(str(hevc))
    last = max(want)
    while i <= last:
        ok, bgr = cap.read()
        if not ok:
            break
        if i in want:
            out[i] = norm(cv2.resize(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), (W, H), interpolation=cv2.INTER_AREA))
        i += 1
    cap.release()
    return out


def run_source(args):
    sid, g = args
    cv2.setNumThreads(1)
    g = g.sort_values("sample_index")
    origin = g["origin_group"].iloc[0]
    hv = glob.glob(str(SEGMENTS / origin.replace("|", "_") / "*" / "video.hevc"))
    if len(hv) != 1:
        return sid, None
    idx = g["source_frame_index"].to_numpy().astype(int)
    fr = gray_frames(hv[0], idx)
    keys = ["kappa", "cost", "cost0", "curv", "dx", "dy"]
    rows = []
    for k in range(len(idx)):
        a, b = (fr.get(int(idx[k - 1])) if k else None), fr.get(int(idx[k]))
        rows.append(estimate(a, b) if a is not None and b is not None else {f: np.nan for f in keys})
    df = pd.DataFrame(rows)
    if len(df) > 1:
        df.iloc[0] = df.iloc[1]
    for c in ["source_id", "sample_index", "split", "speed_mps", "steering_angle_deg", "acceleration_mps2_proxy"]:
        df[c] = g[c].to_numpy()
    df["frame_gap"] = np.r_[np.nan, np.diff(idx)]
    return sid, df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--sources", nargs="*")
    ap.add_argument("--max_rows", type=int, default=0)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    aux = pd.read_csv(AUX, encoding="utf-8-sig")
    aux = aux[aux["source_id"] != "SRC014"]
    if a.sources:
        aux = aux[aux["source_id"].isin(a.sources)]
    if a.max_rows:
        aux = aux.groupby("source_id").head(a.max_rows)
    parts = []
    with Pool(a.workers) as p:
        for sid, df in p.imap_unordered(run_source, list(aux.groupby("source_id"))):
            print(sid, None if df is None else len(df), flush=True)
            if df is not None:
                parts.append(df)
    pd.concat(parts).sort_values(["source_id", "sample_index"]).to_csv(a.out / "ground_speed.csv", index=False)


if __name__ == "__main__":
    main()
