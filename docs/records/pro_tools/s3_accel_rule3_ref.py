"""Graft reference for registered probe s3-accel-rule3 (decision 3dcccfb3).

div_far_lr30 is NOT the raw _s3_motion_series[:, 1]: it is
  s = centered rolling median(5) -> centered rolling mean(5) (min_periods=1, clipped at clip edges)
  lr30[t] = log((max(s[t+30],0)+0.05) / (max(s[t-30],0)+0.05)), s[t+30] -> s[-1] past the end, s[t-30] -> s[0] before start
Rows are 10 Hz decoded frames (private contract). Public examples are 20 Hz, so they use gray[::2].

Checks:
 1. numpy _s3_div_far_lr30 == pandas derive() (the gate/threshold code) on comma features cache (all sources)
    and on the 5 public examples.
 2. public examples: inference _s3_motion_series(gray[::2])[:,1] == s3_motion_features div_far used in the gate.
 3. rule3 labels on public 50 rows reproduce open_examples_accel.csv (non-STOPPED rows).
 4. what happens if the raw div_far (no lr30) were thresholded instead (the likely wrong graft).
usage: s3_accel_rule3_ref.py <out_dir>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "submission"))
from s3_motion_gate_r3 import FEATS, derive  # noqa: E402
from s3_motion_features import step_features  # noqa: E402
import inference as inf  # noqa: E402

T_DEC = -0.4614734710351057
T_ACC = 0.6364508695014027
H, EPS = 30, 0.05


# ---- proposed inline code for submission/inference.py (numpy only) ----
def _s3_centered(x, w, fn):
    h = w // 2
    return np.array([fn(x[max(0, i - h):i + h + 1]) for i in range(len(x))])


def _s3_div_far_lr30(div_far):
    x = np.asarray(div_far, np.float64)
    s = _s3_centered(_s3_centered(x, 5, np.median), 5, np.mean)
    n = len(s)
    idx = np.arange(n)
    fwd = np.where(idx + H < n, s[np.minimum(idx + H, n - 1)], s[-1])
    bwd = np.where(idx - H >= 0, s[np.maximum(idx - H, 0)], s[0])
    return np.log((np.maximum(fwd, 0) + EPS) / (np.maximum(bwd, 0) + EPS))


def _s3_accel_rule3(div_far, accel_labels):
    lr = _s3_div_far_lr30(div_far)
    rule = np.where(lr < T_DEC, "DECELERATING", np.where(lr > T_ACC, "ACCELERATING", "CONSTANT"))
    return ["STOPPED" if a == "STOPPED" else r for a, r in zip(accel_labels, rule)]
# ------------------------------------------------------------------------


def main():
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    rep = {}
    # 1a. comma cache
    f = pd.read_csv(FEATS).sort_values(["source_id", "sample_index"]).reset_index(drop=True)
    maxdiff, nrows, nsrc = 0.0, 0, 0
    lens = []
    for _, g in f.groupby("source_id", sort=False):
        ref = derive(g)["div_far_lr30"].to_numpy()
        mine = _s3_div_far_lr30(g["div_far"].to_numpy())
        maxdiff = max(maxdiff, float(np.max(np.abs(ref - mine))))
        nrows += len(g); nsrc += 1; lens.append(len(g))
    rep["comma_cache"] = {"sources": nsrc, "rows": nrows, "max_abs_diff_vs_pandas": maxdiff,
                          "rows_per_source_min_median_max": [int(np.min(lens)), float(np.median(lens)), int(np.max(lens))]}
    # 1b/2/3. public examples
    prev = pd.read_csv(ROOT / "work/s3_motion_gate_r3/open_examples_accel.csv")
    pub, per_row = {}, []
    for vid, g in prev.groupby("ID"):
        cap = cv2.VideoCapture(str(ROOT / f"Baseline/data/stage3/videos/{vid}.mp4"))
        gray = []
        while True:
            ok, bgr = cap.read()
            if not ok:
                break
            gray.append(cv2.resize(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), (160, 120), interpolation=cv2.INTER_AREA))
        cap.release()
        gray10 = np.stack(gray)[::2]
        div_inf = inf._s3_motion_series(gray10)[:, 1]
        fs = [step_features(gray10[k - 1], gray10[k]) for k in range(1, len(gray10))]
        s = pd.DataFrame([fs[0]] + fs)
        s["yaw_far"] = s.get("yaw_far", 0.0)
        div_tool = s["div_far"].to_numpy()
        lr_inf = _s3_div_far_lr30(div_inf)
        lr_pd = derive(s)["div_far_lr30"].to_numpy()
        pub[vid] = {"rows10hz": len(gray10), "div_far_inf_vs_tool_max_abs": float(np.max(np.abs(div_inf - div_tool))),
                    "lr30_inf_numpy_vs_tool_pandas_max_abs": float(np.max(np.abs(lr_inf - lr_pd)))}
        rule_all = _s3_accel_rule3(div_inf, ["CONSTANT"] * len(div_inf))
        raw = np.where(div_inf < T_DEC, "DECELERATING", np.where(div_inf > T_ACC, "ACCELERATING", "CONSTANT"))
        for _, t in g.iterrows():
            k = int(t.sample_index)
            per_row.append({"ID": vid, "sample_index": k, "gt_accel": t.accel,
                            "div_far_lr30_ref": round(float(lr_inf[k]), 6),
                            "rule3_nonstopped": rule_all[k], "prev_tool_rule3": t.rule3,
                            "raw_div_far_threshold": raw[k]})
        pub[vid]["raw_div_far_pred_counts"] = pd.Series(raw).value_counts().to_dict()
        pub[vid]["rule3_pred_counts"] = pd.Series(rule_all).value_counts().to_dict()
    r = pd.DataFrame(per_row)
    ns = r[r.prev_tool_rule3 != "STOPPED"]
    rep["public"] = pub
    rep["public_rule3_matches_prev_tool_nonstopped"] = f"{int((ns.rule3_nonstopped == ns.prev_tool_rule3).sum())}/{len(ns)}"
    gt3 = r[r.gt_accel != "STOPPED"]

    def mf1(y, p, labels=("ACCELERATING", "CONSTANT", "DECELERATING")):
        fs = []
        for c in labels:
            tp = ((y == c) & (p == c)).sum(); fp = ((y != c) & (p == c)).sum(); fn = ((y == c) & (p != c)).sum()
            fs.append(0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn))
        return round(float(np.mean(fs)), 4)
    rep["public_3class_macro_f1_gt_nonstopped"] = {"n": len(gt3), "rule3_lr30": mf1(gt3.gt_accel, gt3.rule3_nonstopped),
                                                   "raw_div_far_same_thresholds": mf1(gt3.gt_accel, gt3.raw_div_far_threshold)}
    r.to_csv(out / "public_rows_reference.csv", index=False)
    (out / "report.json").write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    print(json.dumps(rep, indent=1, default=str))


if __name__ == "__main__":
    main()
