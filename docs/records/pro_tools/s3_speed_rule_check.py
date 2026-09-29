"""Pre-check for S3 e002 (speed_mps regression -> v1b rule), Pro-side, CPU only.

1. How acceleration_mps2_proxy relates to speed_mps (which finite difference / dt).
2. Oracle: true speed -> derived accel -> classify_accel reproduces v1b accel labels?
   (several derivative conventions)
3. Sensitivity: accel Macro-F1 on validation when predicted speed = true + noise
   (iid and temporally correlated AR(1) noise, several sigma).
4. Constant-speed baseline MAE (train mean) on validation (decision's rejection criterion).

usage: s3_speed_rule_check.py [--aux path] [--out out.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from afda import stage3_labels  # noqa: E402

ACCEL = stage3_labels.ACCEL_CLASSES
R = stage3_labels.DEFAULT_RULE


def macro_f1(true, pred):
    true, pred = np.asarray(true), np.asarray(pred)
    vals = []
    for c in ACCEL:
        tp = ((pred == c) & (true == c)).sum()
        fp = ((pred == c) & (true != c)).sum()
        fn = ((pred != c) & (true == c)).sum()
        d = 2 * tp + fp + fn
        vals.append(0.0 if d == 0 else 2 * tp / d)
    return float(np.mean(vals))


def smooth(s):
    return s.rolling(int(R["window"]), center=True, min_periods=1).mean()


def derive_accel(df, speed_col, mode):
    """Per source: accel series from a speed series, then v1b smoothing of accel."""
    out = []
    for _, g in df.groupby("source_id", sort=False):
        g = g.sort_values("sample_index")
        v = g[speed_col]
        t = g["elapsed_seconds"]
        if mode == "fwd_dt":          # (v[t+1]-v[t])/dt, last row repeats
            a = (v.shift(-1) - v) / (t.shift(-1) - t)
            a = a.ffill()
        elif mode == "bwd_dt":        # (v[t]-v[t-1])/dt, first row repeats
            a = (v - v.shift(1)) / (t - t.shift(1))
            a = a.bfill()
        elif mode == "grad_dt":       # np.gradient (central, one-sided at ends)
            a = pd.Series(np.gradient(v.to_numpy(), t.to_numpy()), index=g.index)
        elif mode == "grad_smooth_speed":  # plan wording: diff of smoothed speed
            vs = smooth(v)
            a = pd.Series(np.gradient(vs.to_numpy(), t.to_numpy()), index=g.index)
        else:
            raise ValueError(mode)
        out.append(pd.DataFrame({"a_raw": a, "a_ma": smooth(a), "v_ma": smooth(v)}, index=g.index))
    return pd.concat(out).loc[df.index]


def classify(df, speed_col, mode):
    d = derive_accel(df, speed_col, mode)
    return [stage3_labels.classify_accel(v, a, R["v_stop"], R["a_db"]) for v, a in zip(d["v_ma"], d["a_ma"])], d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aux", type=Path, default=ROOT / "data/derived/comma_subset_v1/s3_auxiliary_10hz.csv")
    ap.add_argument("--out", type=Path, default=ROOT / "work/s3_e002_precheck/report.json")
    ap.add_argument("--seeds", type=int, default=5)
    args = ap.parse_args()

    aux = pd.read_csv(args.aux, encoding="utf-8-sig")
    aux = aux[aux["source_id"] != "SRC014"].sort_values(["source_id", "sample_index"]).reset_index(drop=True)
    lab = stage3_labels.add_labels(aux)
    aux["accel_label"] = lab["accel_label"].to_numpy()
    rep = {"aux": str(args.aux), "rule": R, "rows": int(len(aux))}

    # 1. proxy relation
    dts = aux.groupby("source_id")["elapsed_seconds"].diff().dropna()
    rep["dt"] = {"median": float(dts.median()), "min": float(dts.min()), "max": float(dts.max()),
                 "frac_off_0.1_by_gt_5ms": float((dts.sub(0.1).abs() > 0.005).mean())}
    rel = {}
    for mode in ["fwd_dt", "bwd_dt", "grad_dt"]:
        d = derive_accel(aux, "speed_mps", mode)
        err = (d["a_raw"] - aux["acceleration_mps2_proxy"]).abs()
        rel[mode] = {"mae": float(err.mean()), "p99": float(err.quantile(0.99)), "max": float(err.max())}
    rep["proxy_vs_speed_diff"] = rel

    # 2. oracle
    orc = {}
    for split in ["train", "validation", "test"]:
        m = aux["split"] == split
        orc[split] = {}
        for mode in ["fwd_dt", "bwd_dt", "grad_dt", "grad_smooth_speed"]:
            pred, _ = classify(aux, "speed_mps", mode)
            pred = np.asarray(pred)[m.to_numpy()]
            true = aux.loc[m, "accel_label"].to_numpy()
            orc[split][mode] = {"acc": float((pred == true).mean()), "macro_f1": macro_f1(true, pred)}
    rep["oracle_true_speed"] = orc

    # 3. sensitivity on validation (predictions are computed over all rows, scored on val)
    best_mode = max(orc["validation"], key=lambda k: orc["validation"][k]["macro_f1"])
    rep["sensitivity_mode"] = best_mode
    val = (aux["split"] == "validation").to_numpy()
    true_v = aux.loc[val, "accel_label"].to_numpy()
    rng = np.random.default_rng(0)
    sens = []
    for kind, rho in [("iid", 0.0), ("ar1_0.9", 0.9), ("ar1_0.99", 0.99)]:
        for sigma in [0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 3.0]:
            f1s, maes = [], []
            for _ in range(args.seeds):
                noise = np.empty(len(aux))
                for _, idx in aux.groupby("source_id", sort=False).indices.items():
                    e = rng.normal(0, sigma, len(idx))
                    if rho > 0:
                        e2 = np.empty_like(e)
                        e2[0] = e[0]
                        for i in range(1, len(e)):
                            e2[i] = rho * e2[i - 1] + np.sqrt(1 - rho**2) * e[i]
                        e = e2
                    noise[idx] = e
                aux["speed_noisy"] = aux["speed_mps"] + noise
                pred, _ = classify(aux, "speed_noisy", best_mode)
                f1s.append(macro_f1(true_v, np.asarray(pred)[val]))
                maes.append(float(np.abs(noise[val]).mean()))
            sens.append({"noise": kind, "sigma": sigma, "val_mae": float(np.mean(maes)),
                         "accel_macro_f1_mean": float(np.mean(f1s)), "accel_macro_f1_min": float(np.min(f1s))})
    rep["sensitivity_val"] = sens

    # 4. constant baseline
    tr_mean = float(aux.loc[aux["split"] == "train", "speed_mps"].mean())
    rep["constant_baseline"] = {"train_mean_speed": tr_mean,
                                "val_mae": float((aux.loc[val, "speed_mps"] - tr_mean).abs().mean()),
                                "val_rows": int(val.sum())}
    rep["val_class_counts"] = pd.Series(true_v).value_counts().to_dict()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(rep, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
