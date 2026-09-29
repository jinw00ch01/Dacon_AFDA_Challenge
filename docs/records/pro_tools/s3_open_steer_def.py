"""S3 steer definition probe on the official public examples (decision 13 gate back-validation).

The 47 non-STOPPED labelled rows of Baseline/data/stage3 are the only rows labelled by the OFFICIAL labeller.
Our comma val uses our own proxy labeller (stage3_labels v1b), whose yaw-rule gain (+0.40 steer F1) did not
transfer to the LB (+0.004). This script measures, on the official rows only:
  A. current graft rule (w=9, t_lo=-0.303, t_hi=0.198) -> steer Macro-F1
  B. leave-one-video-out (LOVO) fitted rules: fit (w, t_lo, t_hi) on 4 videos, predict the 5th; pooled Macro-F1.
     B1 symmetric (t_lo=-t_hi, w=9), B2 asymmetric (t_lo, t_hi, w free).
  C. the effect of each candidate on comma val/test rows (our labeller) to bound the downside.
yaw series: afda.s3_yaw_steer.yaw_series on the 10 Hz frames (frame_index = 2*sample_index), identical to the graft.
Usage: s3_open_steer_def.py <features.csv> <out_dir>
"""
import itertools
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "work" / "pro_tools"))
from afda import s3_yaw_steer as ys  # noqa: E402
from afda.stage3_labels import add_labels  # noqa: E402
from s3_yaw_steer_rule import mf1, predict  # noqa: E402

WS = [1, 5, 9, 15, 21, 31]


def open_series():
    lab = pd.read_csv(ROOT / "Baseline/data/stage3/labels.csv")
    ser = {}
    for vid, g in lab.groupby("ID"):
        cap = cv2.VideoCapture(str(ROOT / f"Baseline/data/stage3/videos/{vid}.mp4"))
        gray = []
        while True:
            ok, f = cap.read()
            if not ok:
                break
            gray.append(cv2.resize(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), (ys.W, ys.H), interpolation=cv2.INTER_AREA))
        cap.release()
        nz = g[g.sample_index > 0]
        step = int(round(float((nz.frame_index / nz.sample_index).median())))
        ser[vid] = ys.yaw_series(np.stack(gray[::step]))
    return lab, ser


def rows_for(lab, ser, w):
    out = []
    for r in lab.itertuples():
        s = ys.smooth(ser[r.ID], w)
        out.append(s[min(int(r.sample_index), len(s) - 1)])
    return np.array(out)


def fit(x, y, sym, w_fixed=None):
    vals = np.unique(np.round(np.abs(x), 3))
    cands = np.concatenate([[0.02], (vals[:-1] + vals[1:]) / 2 if len(vals) > 1 else vals, [1.0]])
    best = (-1, None)
    his = cands
    los = [-c for c in cands]
    for hi in his:
        for lo in ([-hi] if sym else los):
            f = mf1(y, predict(x, lo, hi))
            # tie-break toward thresholds closer to the train-fitted graft (conservative)
            key = (round(f, 6), -abs(hi - ys.T_HI) - abs(lo - ys.T_LO))
            if best[0] == -1 or key > best[0]:
                best = (key, (float(lo), float(hi)))
    return best[1], best[0][0]


def lovo(lab, ser, sym, ws):
    keep = (lab.accel_label != "STOPPED").values
    y = lab.steer_label.values
    xs = {w: rows_for(lab, ser, w) for w in ws}
    pred = np.array(["STRAIGHT"] * len(lab), dtype=object)
    chosen = {}
    for vid in sorted(lab.ID.unique()):
        tr = keep & (lab.ID != vid).values
        te = keep & (lab.ID == vid).values
        best = None
        for w in ws:
            (lo, hi), f = fit(xs[w][tr], y[tr], sym)
            if best is None or f > best[0]:
                best = (f, w, lo, hi)
        f, w, lo, hi = best
        chosen[vid] = {"w": w, "t_lo": round(lo, 4), "t_hi": round(hi, 4), "fit_f1": round(f, 4)}
        pred[te] = predict(xs[w][te], lo, hi)
    full = None
    for w in ws:
        (lo, hi), f = fit(xs[w][keep], y[keep], sym)
        if full is None or f > full["fit_f1"]:
            full = {"w": w, "t_lo": round(lo, 4), "t_hi": round(hi, 4), "fit_f1": round(f, 4)}
    return {"lovo_macro_f1": round(mf1(y[keep], pred[keep]), 4), "per_fold": chosen, "fit_all5": full,
            "pred_counts": pd.Series(pred[keep]).value_counts().to_dict(), "_pred": pred}


def video_boot(lab, keep, y, pa, pb, n=2000, seed=0):
    """paired bootstrap over the 5 videos of pooled Macro-F1(pa) - Macro-F1(pb)."""
    rng = np.random.default_rng(seed)
    vids = sorted(lab.ID.unique())
    idx = {v: np.where(keep & (lab.ID == v).values)[0] for v in vids}
    d = []
    for _ in range(n):
        ii = np.concatenate([idx[v] for v in rng.choice(vids, len(vids))])
        d.append(mf1(y[ii], pa[ii]) - mf1(y[ii], pb[ii]))
    d = np.array(d)
    return {"delta_ci95": [round(float(np.quantile(d, 0.025)), 4), round(float(np.quantile(d, 0.975)), 4)],
            "p_delta_le0": round(float(np.mean(d <= 0)), 4)}


def comma_eval(features_csv, rules):
    df = add_labels(pd.read_csv(features_csv))
    df = df[df.accel_label != "STOPPED"]
    out = {}
    for name, (w, lo, hi) in rules.items():
        x = df.groupby("source_id").yaw_far.transform(lambda s: pd.Series(ys.smooth(s.values, w), index=s.index))
        p = predict(x.values, lo, hi)
        out[name] = {sp: round(mf1(df.steer_label.values[m], p[m]), 4)
                     for sp in ("train", "validation", "test") for m in [(df.split == sp).values]}
    return out


def main():
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    lab, ser = open_series()
    keep = (lab.accel_label != "STOPPED").values
    y = lab.steer_label.values
    x9 = rows_for(lab, ser, ys.SMOOTH_W)
    cur = predict(x9, ys.T_LO, ys.T_HI)
    rep = {"n_rows": int(len(lab)), "n_scored": int(keep.sum()),
           "gt_counts": pd.Series(y[keep]).value_counts().to_dict(),
           "A_current_graft": {"macro_f1": round(mf1(y[keep], cur[keep]), 4),
                               "pred_counts": pd.Series(cur[keep]).value_counts().to_dict()},
           "B1_lovo_symmetric_w9": lovo(lab, ser, True, [9]),
           "B2_lovo_asym_wfree": lovo(lab, ser, False, WS)}
    # per-class yaw_s (w=9) on official rows
    rep["yaw9_by_class"] = {c: sorted(round(float(v), 3) for v in x9[keep & (y == c)]) for c in ("LEFT", "RIGHT")}
    st = np.abs(x9[keep & (y == "STRAIGHT")])
    rep["yaw9_straight_abs_q"] = {q: round(float(np.quantile(st, q)), 3) for q in (0.5, 0.8, 0.9, 0.95, 1.0)}
    f1 = rep["B1_lovo_symmetric_w9"]["fit_all5"]
    f2 = rep["B2_lovo_asym_wfree"]["fit_all5"]
    rules = {"current": (ys.SMOOTH_W, ys.T_LO, ys.T_HI),
             "sym_w9_fit5": (9, f1["t_lo"], f1["t_hi"]),
             "asym_fit5": (f2["w"], f2["t_lo"], f2["t_hi"])}
    rep["C_comma_ourlabeller"] = comma_eval(sys.argv[1], rules)
    p1 = rep["B1_lovo_symmetric_w9"].pop("_pred")
    p2 = rep["B2_lovo_asym_wfree"].pop("_pred")
    rep["boot_lovo_sym_minus_current"] = video_boot(lab, keep, y, p1, cur)
    rep["boot_lovo_asym_minus_current"] = video_boot(lab, keep, y, p2, cur)
    pd.DataFrame({"ID": lab.ID, "sample_index": lab.sample_index, "accel": lab.accel_label, "gt": y,
                  "yaw9": x9, "pred_current": cur, "pred_lovo_sym": p1, "pred_lovo_asym": p2}).to_csv(
        out_dir / "open_rows.csv", index=False)
    np.savez(out_dir / "open_yaw_series.npz", **ser)
    (out_dir / "report.json").write_text(json.dumps(rep, indent=1, default=str))
    print(json.dumps(rep, indent=1, default=str))


if __name__ == "__main__":
    main()
