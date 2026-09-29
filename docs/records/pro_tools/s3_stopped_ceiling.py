"""Ceiling / sensitivity of a STOPPED override on the e001 argmax base (decision cfafb2ad, e004 base = e001).

Override rows predicted STOPPED by a simulated head with recall r (on GT STOPPED rows) and false-positive rate f
(on GT non-STOPPED rows), sampled per source-contiguous blocks is not modelled: rows are drawn iid (optimistic
for FP, since real errors are temporally clustered). Scored with official_metrics.s3_score.

usage: s3_stopped_ceiling.py --base e001_base_val_predictions.csv --out work/s3_stopped_ceiling_e001
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from s3_stopped_gate import ST, ROOT, attach, load_val, scores


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=ROOT / "work/s3_stopped_ceiling_e001")
    a = ap.parse_args()
    val = load_val(ROOT / "data/derived/comma_subset_v1/s3_auxiliary_10hz.csv")
    df, integ = attach(val, a.base)
    stop = (df["gt_accel"] == ST).to_numpy()
    base = df["accel_pred"].to_numpy(object)
    rep = {"base": str(a.base), "integrity": integ, "n": int(len(df)), "n_true_stopped": int(stop.sum()),
           "base_scores": scores(df, "accel_pred")}
    rep["base_pred_on_true_stopped"] = df.loc[stop, "accel_pred"].value_counts().to_dict()
    oracle = np.where(stop, ST, base)
    rep["oracle_override"] = scores(df.assign(_a=oracle), "_a")
    rng = np.random.default_rng(0)
    grid = []
    for r in (0.25, 0.5, 0.75, 0.9):
        for f in (0.0, 0.01, 0.02, 0.05, 0.1):
            vals = []
            for _ in range(20):
                hit = np.where(stop, rng.random(len(df)) < r, rng.random(len(df)) < f)
                vals.append(scores(df.assign(_a=np.where(hit, ST, base)), "_a"))
            grid.append({"recall": r, "fp_rate": f, "S3_mean": float(np.mean([v["S3"] for v in vals])),
                         "accel_f1_mean": float(np.mean([v["accel_f1"] for v in vals])),
                         "stopped_f1_mean": float(np.mean([v["stopped_f1"] for v in vals]))})
    rep["iid_head_grid"] = grid
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "report.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False, default=float), encoding="utf-8")
    print(json.dumps({k: rep[k] for k in ("integrity", "n_true_stopped", "base_pred_on_true_stopped")}, default=float))
    print("base", rep["base_scores"]["S3"], "oracle", rep["oracle_override"]["S3"], rep["oracle_override"]["accel_per_class"])
    for g in grid:
        print(g)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
