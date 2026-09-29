"""S3 e005 3-stage decomposition (decision fe3b9e1b / 2fbcd9ce): (a) e001 base, (b) e005 raw argmax, (c) e005 override.

Per stage: official S3, accel 4-class per-class F1, non-STOPPED 3-class accel Macro-F1 (mean of ACC/DEC/CONST
per-class F1 from the 4-class scoring, same definition as Ultra's 0.242026), accel confusion, and the oracle
ceiling (GT STOPPED rows overridden to STOPPED) on top of each raw predictor. Independent GT via s3_stopped_gate.

usage: s3_e005_decomp.py --pred e005.csv --base e001_base.csv --out dir
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from s3_stopped_gate import ROOT, ST, attach, f1_bin, load_val, scores
from afda import stage3_labels

NS3 = ["ACCELERATING", "CONSTANT", "DECELERATING"]


def stage(df, col):
    s = scores(df, col)
    s["nonstopped_accel3_macro_f1"] = sum(s["accel_per_class"][c] for c in NS3) / 3
    s["confusion"] = pd.crosstab(df["gt_accel"], df[col]).to_dict()
    s["pred_dist"] = df[col].value_counts().to_dict()
    orc = df.copy()
    orc["_o"] = orc[col].where(orc["gt_accel"] != ST, ST)
    orc.loc[(orc["gt_accel"] != ST) & (orc["_o"] == ST), "_o"] = "CONSTANT"  # oracle also removes false STOPPED
    s["oracle_ceiling_S3"] = scores(orc, "_o")["S3"]
    per_src = {}
    for src, g in df.groupby("source_id"):
        per_src[src] = {"n": int(len(g)), "accel_acc": float((g[col] == g["gt_accel"]).mean()),
                        "dec_true": int((g["gt_accel"] == "DECELERATING").sum()),
                        "dec_pred": int((g[col] == "DECELERATING").sum())}
    s["per_source"] = per_src
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", type=Path, required=True)
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--aux", type=Path, default=ROOT / "data/derived/comma_subset_v1/s3_auxiliary_10hz.csv")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    val = load_val(a.aux)
    df, integ = attach(val, a.pred)
    bdf, binteg = attach(val, a.base)
    rep = {"integrity": integ, "base_integrity": binteg,
           "a_e001_base": stage(bdf, "accel_pred"),
           "b_e005_raw": stage(df, "accel_pred_raw"),
           "c_e005_override": stage(df, "accel_pred")}
    b, c, base = rep["b_e005_raw"], rep["c_e005_override"], rep["a_e001_base"]
    rep["delta"] = {"raw_minus_base": b["S3"] - base["S3"], "override_minus_raw": c["S3"] - b["S3"],
                    "total": c["S3"] - base["S3"]}
    rep["cond7"] = {"value": b["nonstopped_accel3_macro_f1"], "min": 0.222,
                    "pass": b["nonstopped_accel3_macro_f1"] >= 0.222}
    rep["raw_vs_base_agree"] = {"accel": float((df["accel_pred_raw"] == bdf["accel_pred"]).mean()),
                                "steer": float((df["steer_pred"] == bdf["steer_pred"]).mean())}
    rep["raw_stopped_nonzero"] = int((df["accel_pred_raw"] == ST).sum())
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "decomp.json").write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    for k in ("a_e001_base", "b_e005_raw", "c_e005_override"):
        r = rep[k]
        print(k, "S3=%.6f accel=%.6f steer=%.6f ns3=%.6f oracle=%.4f" % (
            r["S3"], r["accel_f1"], r["steer_f1"], r["nonstopped_accel3_macro_f1"], r["oracle_ceiling_S3"]),
            {c: round(v, 4) for c, v in r["accel_per_class"].items()}, r["pred_dist"])
    print("delta", rep["delta"], "cond7", rep["cond7"], "agree", rep["raw_vs_base_agree"],
          "raw_STOPPED", rep["raw_stopped_nonzero"])
    for k in ("b_e005_raw", "c_e005_override"):
        print(k, "confusion(pred->gt)", rep[k]["confusion"])


if __name__ == "__main__":
    main()
