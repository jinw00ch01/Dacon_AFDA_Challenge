"""Decision 12-D: 10 Hz motion features for S3 from low-res optical flow (comma2k19 subset).

For each source the aux 10 Hz rows' source_frame_index frames are decoded (same full sequential decode as the
cache), resized to 160x120 gray, and Farneback flow is computed between consecutive 10 Hz rows (what a 10 Hz
test clip gives). Per step:
  rad_road   median radial flow (from the FOE, assumed at (0.5W, 0.47H)) in the road band y in [0.52H, 0.74H]
  spd_road   median of radial flow / ((y - y_h) * r) in the road band  (ground-plane normalised speed proxy)
  mag_all    median |flow| above the hood (y < 0.74H)
  div_all    mean radial expansion (u*rx + v*ry)/(rx^2+ry^2+1) above the hood
  div_far/mid mean radial expansion x W in y [0.30H,0.50H) / [0.50H,0.62H) (probe: far band tracks speed best)
  yaw_far    median horizontal flow in the far band y in [0.25H, 0.47H]
  yaw_all    median horizontal flow above the hood
  diff_road  mean abs frame difference in the road band
Output: <out>/features.csv (source_id, sample_index, split, features..., speed_mps, steering_angle_deg, accel proxy).

usage: s3_motion_features.py --out <dir> [--workers 4] [--sources SRC001 ...]
"""
from __future__ import annotations

import argparse
import glob
import sys
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
_rx, _ry = _xx - W / 2, _yy - YH
_rn = np.sqrt(_rx ** 2 + _ry ** 2) + 1e-6
_ux, _uy = _rx / _rn, _ry / _rn
ROAD = (_yy >= 0.52 * H) & (_yy <= 0.74 * H) & (np.abs(_rx) > 6)
ABOVE_HOOD = _yy < 0.74 * H
FAR = (_yy >= 0.25 * H) & (_yy < 0.47 * H)
_gnorm = np.where(ROAD, (_yy - YH) * _rn, 1.0)
_r2 = _rx ** 2 + _ry ** 2 + 1.0
FEATS = ["rad_road", "spd_road", "mag_all", "div_all", "div_far", "div_mid", "yaw_far", "yaw_all", "diff_road"]
FARB = (_yy >= 0.30 * H) & (_yy < 0.50 * H)
MIDB = (_yy >= 0.50 * H) & (_yy < 0.62 * H)


def step_features(a, b):
    f = cv2.calcOpticalFlowFarneback(a, b, None, 0.5, 4, 15, 3, 5, 1.1, 0)
    u, v = f[..., 0], f[..., 1]
    rad = u * _ux + v * _uy
    return {
        "rad_road": float(np.median(rad[ROAD])),
        "spd_road": float(np.median((rad / _gnorm)[ROAD]) * 1000),
        "mag_all": float(np.median(np.hypot(u, v)[ABOVE_HOOD])),
        "div_all": float(np.mean(((u * _rx + v * _ry) / _r2)[ABOVE_HOOD]) * 100),
        "div_far": float(np.mean(((u * _rx + v * _ry) / _r2)[FARB]) * W),
        "div_mid": float(np.mean(((u * _rx + v * _ry) / _r2)[MIDB]) * W),
        "yaw_far": float(np.median(u[FAR])),
        "yaw_all": float(np.median(u[ABOVE_HOOD])),
        "diff_road": float(np.mean(np.abs(a.astype(np.int16) - b.astype(np.int16))[ROAD])),
    }


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
            out[i] = cv2.resize(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), (W, H), interpolation=cv2.INTER_AREA)
        i += 1
    cap.release()
    return out


def run_source(args):
    sid, g = args
    g = g.sort_values("sample_index")
    origin = g["origin_group"].iloc[0]
    hv = glob.glob(str(SEGMENTS / origin.replace("|", "_") / "*" / "video.hevc"))
    if len(hv) != 1:
        return sid, None
    idx = g["source_frame_index"].to_numpy().astype(int)
    fr = gray_frames(hv[0], idx)
    rows = []
    for k in range(len(idx)):
        a, b = fr.get(int(idx[k - 1])) if k else None, fr.get(int(idx[k]))
        rows.append(step_features(a, b) if a is not None and b is not None else {f: np.nan for f in FEATS})
    df = pd.DataFrame(rows)
    if len(df) > 1:
        df.iloc[0] = df.iloc[1]
    for c in ["source_id", "sample_index", "split", "speed_mps", "steering_angle_deg", "acceleration_mps2_proxy"]:
        df[c] = g[c].to_numpy()
    return sid, df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--sources", nargs="*")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    aux = pd.read_csv(AUX, encoding="utf-8-sig")
    aux = aux[aux["source_id"] != "SRC014"]
    if a.sources:
        aux = aux[aux["source_id"].isin(a.sources)]
    parts = []
    with Pool(a.workers) as p:
        for sid, df in p.imap_unordered(run_source, list(aux.groupby("source_id"))):
            print(sid, None if df is None else len(df), flush=True)
            if df is not None:
                parts.append(df)
    pd.concat(parts).sort_values(["source_id", "sample_index"]).to_csv(a.out / "features.csv", index=False)


if __name__ == "__main__":
    main()
