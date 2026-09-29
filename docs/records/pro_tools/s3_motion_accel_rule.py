"""What div_far_lr30 (r3 selected feature) would do to accel Macro-F1 if used as a 3-way rule on e005 non-STOPPED rows.

Thresholds (t_dec < t_acc on div_far_lr30) chosen on TRAIN rows with gt != STOPPED to maximise 3-class Macro-F1
(ACC/DEC/CONSTANT). Val: e005 accel preds (work/s3_stopped_flow_r3/val_rows.csv, 2396 rows); rows e005 calls
STOPPED stay STOPPED, the rest get the rule class. 4-class accel Macro-F1 = official S3 accel term.
Test (no e005 preds on Pro): rule-only with gt STOPPED rows held out as a secondary 3-class check.
usage: s3_motion_accel_rule.py <out_dir>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s3_accdec_auroc import AUX, load_all  # noqa: E402
from s3_motion_gate_r3 import FEATS, derive  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
F = "div_far_lr30"
C4 = ["ACCELERATING", "CONSTANT", "DECELERATING", "STOPPED"]
C3 = ["ACCELERATING", "CONSTANT", "DECELERATING"]


def macro_f1(y, p, labels):
    y, p = np.asarray(y), np.asarray(p)
    fs = {}
    for c in labels:
        tp = np.sum((y == c) & (p == c)); fp = np.sum((y != c) & (p == c)); fn = np.sum((y == c) & (p != c))
        fs[c] = 0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn)
    return float(np.mean(list(fs.values()))), {k: round(v, 4) for k, v in fs.items()}


def rule(x, lo, hi):
    return np.where(x < lo, "DECELERATING", np.where(x > hi, "ACCELERATING", "CONSTANT"))


def main():
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    f = pd.read_csv(FEATS)
    aux = load_all(AUX)
    d = f.drop(columns=["split"]).merge(aux[["source_id", "sample_index", "split", "gt_accel"]],
                                        on=["source_id", "sample_index"], validate="one_to_one")
    d = d.sort_values(["source_id", "sample_index"]).reset_index(drop=True)
    d = pd.concat([d, pd.concat([derive(g) for _, g in d.groupby("source_id", sort=False)])], axis=1)
    tr = d[(d.split == "train") & (d.gt_accel != "STOPPED")]
    qs = np.quantile(tr[F], np.linspace(0.02, 0.98, 49))
    best = (-1, None, None)
    for i, lo in enumerate(qs):
        for hi in qs[i + 1:]:
            m, _ = macro_f1(tr.gt_accel, rule(tr[F].to_numpy(), lo, hi), C3)
            if m > best[0]:
                best = (m, float(lo), float(hi))
    _, lo, hi = best
    v = pd.read_csv(ROOT / "work/s3_stopped_flow_r3/val_rows.csv").merge(
        d[["source_id", "sample_index", F]], on=["source_id", "sample_index"], validate="one_to_one")
    assert len(v) == 2396 and (v.accel_true == d.set_index(["source_id", "sample_index"]).loc[
        list(zip(v.source_id, v.sample_index)), "gt_accel"].to_numpy()).all()
    newp = np.where(v.accel_pred == "STOPPED", "STOPPED", rule(v[F].to_numpy(), lo, hi))
    e005 = macro_f1(v.accel_true, v.accel_pred, C4)
    mix = macro_f1(v.accel_true, newp, C4)
    # e005 keeps its ACC calls, rule only adds DEC (minimal change variant)
    add_dec = np.where((v.accel_pred != "STOPPED") & (v[F].to_numpy() < lo), "DECELERATING", v.accel_pred)
    mix_dec = macro_f1(v.accel_true, add_dec, C4)
    # source-block bootstrap of the delta
    rng = np.random.default_rng(0)
    srcs = v.source_id.unique()
    deltas = {"rule3": [], "add_dec": []}
    for _ in range(2000):
        idx = np.concatenate([np.where(v.source_id == s)[0] for s in rng.choice(srcs, len(srcs))])
        base = macro_f1(v.accel_true.to_numpy()[idx], v.accel_pred.to_numpy()[idx], C4)[0]
        deltas["rule3"].append(macro_f1(v.accel_true.to_numpy()[idx], newp[idx], C4)[0] - base)
        deltas["add_dec"].append(macro_f1(v.accel_true.to_numpy()[idx], add_dec[idx], C4)[0] - base)
    te = d[(d.split == "test") & (d.gt_accel != "STOPPED")]
    rep = {"feature": F, "thresholds_train": {"t_dec": lo, "t_acc": hi, "train_3class_macro_f1": best[0]},
           "val_e005_accel_macro_f1": e005, "val_e005_plus_rule3": mix, "val_e005_plus_dec_only": mix_dec,
           "val_delta_source_boot_ci95": {k: [float(np.percentile(x, 2.5)), float(np.percentile(x, 97.5))]
                                          for k, x in deltas.items()},
           "val_pred_counts": {"e005": v.accel_pred.value_counts().to_dict(),
                               "rule3": pd.Series(newp).value_counts().to_dict()},
           "test_rule_only_3class_nonstopped": macro_f1(te.gt_accel, rule(te[F].to_numpy(), lo, hi), C3),
           "val_rule_only_3class_nonstopped": macro_f1(v[v.accel_true != "STOPPED"].accel_true,
                                                       rule(v[v.accel_true != "STOPPED"][F].to_numpy(), lo, hi), C3)}
    pd.DataFrame({"source_id": v.source_id, "sample_index": v.sample_index, "accel_true": v.accel_true,
                  "e005": v.accel_pred, F: v[F], "e005_plus_rule3": newp, "e005_plus_dec_only": add_dec}
                 ).to_csv(out / "val_accel_rule_rows.csv", index=False)
    (out / "accel_rule_report.json").write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    print(json.dumps(rep, indent=1, default=str))


if __name__ == "__main__":
    main()
