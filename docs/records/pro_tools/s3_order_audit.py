"""S3 e005 prob review + model-free frame/label order audit (result de511b18 requests).

Part 1 (probs): recompute ACC-vs-DEC AUROC (score = p_ACC - p_DEC) from the 3 attached CSVs against labels
  re-derived here from the aux CSV (stage3_labels v1b), with integrity checks (join, accel_true/speed equality,
  duplicates, split), overall / per-source / speed-stratified.
Part 2 (audit, model free): decode each source video.hevc (same cv2 path as cache_s3_clips), take the
  source_frame_index rows, compute Farneback flow magnitude between consecutive 10Hz frames (160x120 gray).
  Flow magnitude ~ ego speed, so per source:
    - order checks: sample_index contiguous, source_frame_index / elapsed strictly increasing, idx < decoded frames
    - corr(flow, speed) forward vs time-reversed speed, and best lag in +-30 samples
    - AUROC of smoothed d(flow)/dt for GT ACC vs DEC (video-derived accel agrees with labels?)
  If val sources show forward corr > reversed, lag ~0 and flow-accel AUROC > 0.5 like train sources,
  the val frames and labels are aligned and the inversion is the model's, not the data's.

usage: s3_order_audit.py --probs-dir <dir> --out <dir> [--sources SRC017 ...]
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s3_accdec_auroc import ACC, DEC, AUX, load_all, stratified_auroc  # noqa: E402
from s3_stopped_gate import ROOT, auroc  # noqa: E402

SEGMENTS = ROOT / "data/external/comma2k19_subset_v1/segments"


def probs_part(aux, pdir):
    out = {}
    for name in ["e005_train_stride10_probs", "e005_val_probs", "e005_val_reversed_probs"]:
        p = pd.read_csv(pdir / f"{name}.csv")
        dup = int(p.duplicated(["source_id", "sample_index"]).sum())
        m = p.merge(aux[["source_id", "sample_index", "split", "gt_accel", "speed_mps", "speed_bin"]],
                    on=["source_id", "sample_index"], how="left", suffixes=("", "_aux"), indicator=True)
        integ = {"rows": len(p), "dup": dup, "unjoined": int((m["_merge"] != "both").sum()),
                 "split_mismatch": int((m["split"] != m["split_aux"]).sum()),
                 "accel_true_mismatch": int((m["accel_true"] != m["gt_accel"]).sum()),
                 "speed_max_absdiff": float((m["speed_mps"] - m["speed_mps_aux"]).abs().max()),
                 "prob_sum_max_dev": float((m[["p_ACCELERATING", "p_DECELERATING", "p_CONSTANT", "p_STOPPED"]]
                                            .sum(1) - 1).abs().max()),
                 "reverse_window_values": sorted(map(str, m["reverse_window"].unique()))}
        sp = m["split_aux"].iloc[0]
        exp_rows = aux[aux["split"] == sp]
        if "stride10" in name:
            exp_rows = exp_rows[exp_rows["sample_index"] % 10 == 0]
        integ["expected_rows"] = len(exp_rows)
        integ["pass"] = (dup == 0 and integ["unjoined"] == 0 and integ["split_mismatch"] == 0
                         and integ["accel_true_mismatch"] == 0 and integ["speed_max_absdiff"] < 1e-6)
        d = m[m["gt_accel"].isin([ACC, DEC])]
        y = (d["gt_accel"] == ACC).to_numpy()
        s = (d["p_ACCELERATING"] - d["p_DECELERATING"]).to_numpy(float)
        pred = m[["p_ACCELERATING", "p_DECELERATING", "p_CONSTANT", "p_STOPPED"]].to_numpy().argmax(1)
        out[name] = {"integrity": integ, "n_acc": int(y.sum()), "n_dec": int((~y).sum()),
                     "auroc_overall": auroc(y, s),
                     "auroc_speed_stratified": stratified_auroc(y, s, d["speed_bin"].to_numpy()),
                     "auroc_per_source": {k: auroc((g["gt_accel"] == ACC).to_numpy(),
                                                   (g["p_ACCELERATING"] - g["p_DECELERATING"]).to_numpy(float))
                                          for k, g in d.groupby("source_id")},
                     "argmax_counts": {c: int((pred == i).sum()) for i, c in
                                       enumerate(["ACCELERATING", "DECELERATING", "CONSTANT", "STOPPED"])},
                     "gt_counts": m["gt_accel"].value_counts().to_dict()}
    return out


W, H = 320, 240
_yy, _xx = np.mgrid[0:H, 0:W].astype(np.float32)
_rx, _ry = _xx - W / 2, _yy - H / 2
_rn = np.sqrt(_rx ** 2 + _ry ** 2) + 1e-6
_ux, _uy = _rx / _rn, _ry / _rn
# road band below the horizon, above the hood, away from the centre (FOE): radial flow ~ speed there
ROAD = (_yy > H * 0.55) & (_yy < H * 0.82) & (_rn > 30)
# whole-frame ring away from centre: sign of mean radial flow = expansion (forward play) vs contraction (reversed)
RING = (_rn > 40) & (_yy > H * 0.15) & (_yy < H * 0.82)


def flow_series(hevc, idx):
    """Flow between frame idx-1 and idx (consecutive 20fps frames) -> road radial flow (speed proxy)
    and ring expansion sign (time direction)."""
    cap = cv2.VideoCapture(str(hevc))
    want = set(idx.tolist()) | set((idx - 1).tolist())
    grays, i = {}, 0
    while True:
        ok, bgr = cap.read()
        if not ok:
            break
        if i in want:
            grays[i] = cv2.resize(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), (W, H), interpolation=cv2.INTER_AREA)
        i += 1
    cap.release()
    road = np.full(len(idx), np.nan)
    expand = np.full(len(idx), np.nan)
    for k in range(len(idx)):
        a, b = grays.get(int(idx[k]) - 1), grays.get(int(idx[k]))
        if a is None or b is None:
            continue
        f = cv2.calcOpticalFlowFarneback(a, b, None, 0.5, 4, 21, 3, 5, 1.1, 0)
        rad = f[..., 0] * _ux + f[..., 1] * _uy
        road[k] = float(np.median(rad[ROAD]))
        expand[k] = float(np.median(rad[RING]))
    if np.isnan(road[0]) and len(road) > 1:
        road[0], expand[0] = road[1], expand[1]
    return road, expand, i


def corr(a, b):
    ok = ~(np.isnan(a) | np.isnan(b))
    return float(np.corrcoef(a[ok], b[ok])[0, 1]) if ok.sum() > 3 else None


def audit_source(g):
    g = g.sort_values("sample_index")
    idx = g["source_frame_index"].to_numpy().astype(np.int64)
    origin = g["origin_group"].iloc[0]
    hv = glob.glob(str(SEGMENTS / origin.replace("|", "_") / "*" / "video.hevc"))
    r = {"split": g["split"].iloc[0], "rows": len(g),
         "sample_index_contiguous": bool((np.diff(g["sample_index"]) == 1).all()),
         "frame_idx_increasing": bool((np.diff(idx) > 0).all()),
         "frame_idx_step_median": float(np.median(np.diff(idx))),
         "elapsed_increasing": bool((np.diff(g["elapsed_seconds"]) > 0).all())}
    if len(hv) != 1:
        r["error"] = f"video.hevc matches {len(hv)}"
        return r, None
    t0 = time.time()
    mag, expand, total = flow_series(Path(hv[0]), idx)
    r["decoded_frames"], r["idx_max"], r["decode_s"] = total, int(idx.max()), round(time.time() - t0, 1)
    sp = g["speed_mps"].to_numpy(float)
    mv = sp > 3.0
    r["moving_rows"] = int(mv.sum())
    r["expansion_positive_frac_moving"] = float(np.nanmean(expand[mv] > 0)) if mv.any() else None
    r["expansion_median_moving"] = float(np.nanmedian(expand[mv])) if mv.any() else None
    r["corr_flow_speed_forward"] = corr(mag, sp)
    r["corr_flow_speed_reversed"] = corr(mag, sp[::-1].copy())
    lags = {}
    for L in range(-30, 31):
        if L >= 0:
            lags[L] = corr(mag[L:], sp[:len(sp) - L])  # flow at t+L vs speed at t
        else:
            lags[L] = corr(mag[:L], sp[-L:])
    valid = {k: v for k, v in lags.items() if v is not None}
    r["best_lag_samples"] = max(valid, key=valid.get) if valid else None
    r["best_lag_corr"] = valid.get(r["best_lag_samples"])
    sm = pd.Series(mag).rolling(11, center=True, min_periods=3).median().rolling(11, center=True, min_periods=3).mean()
    dflow = np.gradient(sm.to_numpy())
    lab = g["gt_accel"].to_numpy()
    m = np.isin(lab, [ACC, DEC])
    y = lab[m] == ACC
    r["n_acc"], r["n_dec"] = int(y.sum()), int((~y).sum())
    r["auroc_flow_accel"] = auroc(y, dflow[m])
    r["auroc_flow_accel_reversed_time"] = auroc(y, -dflow[::-1][m]) if m.any() else None
    r["auroc_gt_proxy_accel"] = auroc(y, g["acceleration_mps2_proxy"].to_numpy(float)[m])
    ser = pd.DataFrame({"source_id": g["source_id"].to_numpy(), "sample_index": g["sample_index"].to_numpy(),
                        "flow_mag": mag, "expand": expand, "dflow": dflow, "speed_mps": sp, "gt_accel": lab})
    return r, ser


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probs-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--sources", nargs="*")
    ap.add_argument("--skip-audit", action="store_true")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    aux = load_all(AUX)
    rep = {"aux": str(AUX.relative_to(ROOT)), "probs": probs_part(aux, a.probs_dir)}
    if not a.skip_audit:
        srcs = a.sources or sorted(aux["source_id"].unique())
        rep["audit"], series = {}, []
        for s in srcs:
            r, ser = audit_source(aux[aux["source_id"] == s])
            rep["audit"][s] = r
            if ser is not None:
                series.append(ser)
            print(s, json.dumps(r, default=str), flush=True)
        if series:
            allser = pd.concat(series)
            allser.to_csv(a.out / "flow_series.csv", index=False)
            summ = {}
            for sp in ["train", "validation"]:
                rows = [v for v in rep["audit"].values() if v.get("split") == sp and "auroc_flow_accel" in v]
                summ[sp] = {k: [round(v[k], 3) if isinstance(v[k], float) else v[k] for v in rows]
                            for k in ["expansion_positive_frac_moving", "corr_flow_speed_forward", "corr_flow_speed_reversed", "best_lag_samples",
                                      "auroc_flow_accel"]}
                ids = [s for s, v in rep["audit"].items() if v.get("split") == sp]
                d = allser[allser["source_id"].isin(ids) & allser["gt_accel"].isin([ACC, DEC])]
                summ[sp]["pooled_auroc_flow_accel"] = auroc((d["gt_accel"] == ACC).to_numpy(), d["dflow"].to_numpy())
            rep["audit_summary"] = summ
    (a.out / "report.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in rep.items() if k != "audit"}, indent=1, ensure_ascii=False, default=str)[:7000])


if __name__ == "__main__":
    main()
