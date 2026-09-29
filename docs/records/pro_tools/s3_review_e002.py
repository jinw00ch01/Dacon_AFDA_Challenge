"""Pro review of S3 e002 (result 182256b5, exp-7a701d04). CPU only, no val_predictions attached.

A. official_s3 recomputed from reported components; all-STRAIGHT steer on proxy val (collapse check).
B. accel chance baselines on val: random predictor with e002's / e001's / GT marginal (expected F1, analytic).
C. STOPPED: both e001 and e002 predict 0 STOPPED -> class F1 0 caps accel macro at 0.75. Bound on what a
   STOPPED fix is worth for e002 (lower/upper estimate from marginals).
D. e002 speed RMSE implied by train_loss (loss = MSE + steer CE; CE of a collapsed head ~ train steer entropy)
   and the speed_scale=30 term size at start vs late training.
E. Class distribution: official Baseline S3 50 rows vs proxy v1b train/val/test; a_db / window sweep to see
   which proxy rule matches the official class mix. Constant-predictor official S3 on the 50 official rows.

usage: s3_review_e002.py [--aux ...] [--official Baseline/data/stage3/labels.csv] [--out ...]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from afda import stage3_labels  # noqa: E402
from official_metrics import macro_f1, s3_score  # noqa: E402  (Pro's independent implementation)

ACCEL = stage3_labels.ACCEL_CLASSES
E002 = {"accel": 0.29462748803804417, "steer": 0.3072903497682259, "official": 0.29842634655709865,
        "pred_counts": {"DECELERATING": 1045, "ACCELERATING": 926, "CONSTANT": 425, "STOPPED": 0},
        "train_loss": [134.2459070987569, 8.820221670164003, 2.074891548289193]}
E001 = {"accel": 0.18152, "steer": 0.40817, "official": 0.24951,
        "pred_counts": {"CONSTANT": 2138, "ACCELERATING": 237, "DECELERATING": 21, "STOPPED": 0}}


def expected_random_f1(true_counts, pred_counts):
    """Expected per-class F1 when predictions are independent of truth with the given marginal."""
    n = sum(true_counts.values())
    out = {}
    for c in ACCEL:
        t, p = true_counts.get(c, 0), pred_counts.get(c, 0)
        out[c] = 0.0 if (t + p) == 0 else 2 * t * (p / n) / (t + p)
    return out, float(np.mean(list(out.values())))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aux", type=Path, default=ROOT / "data/derived/comma_subset_v1/s3_auxiliary_10hz.csv")
    ap.add_argument("--official", type=Path, default=ROOT / "Baseline/data/stage3/labels.csv")
    ap.add_argument("--out", type=Path, default=ROOT / "work/s3_review_e002/report.json")
    args = ap.parse_args()

    aux = pd.read_csv(args.aux, encoding="utf-8-sig")
    aux = aux[aux["source_id"] != "SRC014"].sort_values(["source_id", "sample_index"]).reset_index(drop=True)
    lab = stage3_labels.add_labels(aux)
    aux["accel_label"] = lab["accel_label"].to_numpy()
    aux["steer_label"] = lab["steer_label"].to_numpy()
    val = aux[aux["split"] == "validation"]
    rep = {"aux": str(args.aux), "rows": int(len(aux)), "val_rows": int(len(val))}

    # A. reproduce
    ga, gs = val["accel_label"].tolist(), val["steer_label"].tolist()
    straight = s3_score(ga, ["CONSTANT"] * len(ga), gs, ["STRAIGHT"] * len(gs))
    rep["A_reproduce"] = {
        "e002_official_from_components": 0.7 * E002["accel"] + 0.3 * E002["steer"],
        "e002_official_reported": E002["official"],
        "e001_official_from_components": 0.7 * E001["accel"] + 0.3 * E001["steer"],
        "all_STRAIGHT_steer_official_val": straight["steer_f1"],
        "e002_steer_reported": E002["steer"],
        "steer_collapse_confirmed": abs(straight["steer_f1"] - E002["steer"]) < 1e-9,
        "n_val": len(ga), "n_val_steer": straight["n_steer"],
    }

    # B. chance baselines
    tc = val["accel_label"].value_counts().to_dict()
    b = {"val_true_counts": tc}
    for name, pc in [("e002_marginal", E002["pred_counts"]), ("e001_marginal", E001["pred_counts"]),
                     ("gt_marginal", tc)]:
        per, m = expected_random_f1(tc, pc)
        b[name] = {"per_class": per, "macro": m}
    b["all_CONSTANT"] = macro_f1(ga, ["CONSTANT"] * len(ga))
    b["e002_minus_own_marginal_chance"] = E002["accel"] - b["e002_marginal"]["macro"]
    b["e001_minus_own_marginal_chance"] = E001["accel"] - b["e001_marginal"]["macro"]
    rep["B_accel_chance"] = b

    # C. STOPPED
    non_stop_mean = E002["accel"] * 4 / 3  # mean F1 of the three non-STOPPED classes (STOPPED F1 = 0)
    rep["C_stopped"] = {
        "val_stopped_rows": int(tc.get("STOPPED", 0)),
        "e001_pred_stopped": 0, "e002_pred_stopped": 0,
        "e002_mean_f1_non_stopped_classes": non_stop_mean,
        "accel_macro_cap_without_stopped": 0.75,
        "e002_accel_if_stopped_f1_0.5": (3 * non_stop_mean + 0.5) / 4,
        "e002_accel_if_stopped_f1_0.8": (3 * non_stop_mean + 0.8) / 4,
        "official_s3_gain_per_0.1_stopped_f1": 0.7 * 0.1 / 4,
        "note": "lower-bound style: ignores the FP removed from other classes when STOPPED rows stop being mislabeled",
    }
    # How separable is STOPPED by true speed (oracle): speed_ma < v_stop defines it; share of STOPPED rows
    # whose true speed is < 1.0 / 2.0 m/s -> a regression head with MAE ~1 m/s near zero cannot hit 0.5.
    sp = val["speed_mps"].rolling(5, center=True, min_periods=1).mean()
    rep["C_stopped"]["val_speed_ma_quantiles_when_not_stopped"] = {
        q: float(sp[val["accel_label"] != "STOPPED"].quantile(q)) for q in (0.01, 0.05, 0.1)}

    # D. loss scale
    tr = aux[aux["split"] == "train"].copy()
    st = tr["steer_label"].where(tr["accel_label"] != "STOPPED", "STRAIGHT")  # trainer masks STOPPED -> STRAIGHT
    p = st.value_counts(normalize=True)
    h = float(-(p * np.log(p)).sum())
    mse2 = E002["train_loss"][2] - h
    sd = float(tr["speed_mps"].std())
    rep["D_loss_scale"] = {
        "train_steer_prior_entropy_nats": h,
        "train_steer_dist": p.to_dict(),
        "e002_ep2_speed_mse_implied": mse2, "e002_ep2_speed_rmse_implied": math.sqrt(max(mse2, 0)),
        "train_speed_mean": float(tr["speed_mps"].mean()), "train_speed_std": sd,
        "scale30_speed_term_ep0": E002["train_loss"][0] / 900, "scale30_speed_term_ep2_if_same_rmse": mse2 / 900,
        "ratio_steer_CE_to_scale30_speed_term_late": h / (mse2 / 900) if mse2 > 0 else None,
        "zscore_speed_term_late": mse2 / sd**2,
        "note": "train_loss is an epoch mean with augmentation; RMSE is a rough implied value, not a val metric",
    }

    # E. distributions
    off = pd.read_csv(args.official, encoding="utf-8-sig")
    offd = off["accel_label"].value_counts(normalize=True).reindex(ACCEL, fill_value=0)
    e = {"official_n": int(len(off)), "official_accel": offd.to_dict(),
         "official_steer": off["steer_label"].value_counts(normalize=True).to_dict(), "proxy_v1b": {}}
    for split in ["train", "validation", "test"]:
        d = aux.loc[aux["split"] == split, "accel_label"].value_counts(normalize=True).reindex(ACCEL, fill_value=0)
        e["proxy_v1b"][split] = {"dist": d.to_dict(), "tv_to_official": float(0.5 * (d - offd).abs().sum())}
    sweep = []
    for w in [5, 11, 21]:
        for adb in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8]:
            rule = {**stage3_labels.DEFAULT_RULE, "window": w, "a_db": adb}
            l2 = stage3_labels.add_labels(aux, rule)["accel_label"]
            d = l2.value_counts(normalize=True).reindex(ACCEL, fill_value=0)
            sweep.append({"window": w, "a_db": adb, "dist": {k: round(v, 3) for k, v in d.items()},
                          "tv_to_official": round(float(0.5 * (d - offd).abs().sum()), 4)})
    e["rule_sweep_all_splits"] = sorted(sweep, key=lambda r: r["tv_to_official"])
    oa, os_ = off["accel_label"].tolist(), off["steer_label"].tolist()
    e["official50_const_CONSTANT_STRAIGHT"] = s3_score(oa, ["CONSTANT"] * 50, os_, ["STRAIGHT"] * 50)
    rep["E_distribution"] = e

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rep, indent=2, ensure_ascii=False, default=float), encoding="utf-8")
    print(json.dumps(rep, indent=1, ensure_ascii=False, default=float)[:6000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
