"""S3 accel from body pitch (Pro probe). Braking dips the nose, accelerating lifts it; the camera is fixed to the body,
so the far scene shifts vertically by an amount roughly proportional to longitudinal acceleration.
Per 10 Hz step: Farneback at 160x120 gray (same as s3_motion_features), median vertical flow in a horizon-centred
band (forward expansion cancels above/below the horizon) and in the upper far band; also the horizon-band vertical
shift found by 1-D row-profile cross-correlation (sub-pixel), which does not depend on texture tracking.
Output: <out>/pitch.csv (source_id, sample_index, split, pitch_v_hb, pitch_v_far, prof_shift, labels inputs)
usage: s3_pitch_probe.py --out <dir> [--workers 4] [--sources ...] [--max_rows N]
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
W, H = 160, 120
YH = 0.47 * H
_yy, _xx = np.mgrid[0:H, 0:W].astype(np.float32)
HB = (np.abs(_yy - YH) <= 0.08 * H) & (np.abs(_xx - W / 2) <= 0.45 * W)
FARU = (_yy >= 0.15 * H) & (_yy < 0.40 * H)
P_LO, P_HI = int(0.20 * H), int(0.62 * H)
SH = np.arange(-6, 6.01, 0.25)


def prof(g):
    return g[:, int(0.1 * W):int(0.9 * W)].astype(np.float32).mean(axis=1)


def prof_shift(pa, pb):
    """vertical shift s (px, +down) minimising |pb(y) - pa(y - s)| on the horizon rows."""
    ys = np.arange(P_LO, P_HI, dtype=np.float32)
    base = np.arange(H, dtype=np.float32)
    ga = np.gradient(pa)
    gb = np.gradient(pb)
    c = [np.mean(np.abs(np.interp(ys, ys * 0 + ys, gb[P_LO:P_HI]) - np.interp(ys - s, base, ga))) for s in SH]
    return float(SH[int(np.argmin(c))])


def step(a, b):
    f = cv2.calcOpticalFlowFarneback(a, b, None, 0.5, 4, 15, 3, 5, 1.1, 0)
    v = f[..., 1]
    return {"pitch_v_hb": float(np.median(v[HB])), "pitch_v_far": float(np.median(v[FARU])),
            "prof_shift": prof_shift(prof(a), prof(b))}


def run_source(args):
    sid, g = args
    cv2.setNumThreads(1)
    g = g.sort_values("sample_index")
    hv = glob.glob(str(SEGMENTS / g["origin_group"].iloc[0].replace("|", "_") / "*" / "video.hevc"))
    if len(hv) != 1:
        return sid, None
    idx = g["source_frame_index"].to_numpy().astype(int)
    want, fr, i = set(idx.tolist()), {}, 0
    cap = cv2.VideoCapture(hv[0])
    while i <= idx.max():
        ok, bgr = cap.read()
        if not ok:
            break
        if i in want:
            fr[i] = cv2.resize(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), (W, H), interpolation=cv2.INTER_AREA)
        i += 1
    cap.release()
    keys = ["pitch_v_hb", "pitch_v_far", "prof_shift"]
    rows = []
    for k in range(len(idx)):
        a, b = (fr.get(int(idx[k - 1])) if k else None), fr.get(int(idx[k]))
        rows.append(step(a, b) if a is not None and b is not None else {x: 0.0 for x in keys})
    df = pd.DataFrame(rows)
    for c in ["source_id", "sample_index", "split", "speed_mps", "steering_angle_deg", "acceleration_mps2_proxy"]:
        df[c] = g[c].to_numpy()
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
    pd.concat(parts).sort_values(["source_id", "sample_index"]).to_csv(a.out / "pitch.csv", index=False)


if __name__ == "__main__":
    main()
