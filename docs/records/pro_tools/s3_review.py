"""Recompute Stage 3 validation metrics from a per-sample predictions CSV (Pro review tool).

Ground truth = src/afda/stage3_labels.add_labels(aux, rule) on the same aux CSV Ultra used.
Official rule (evaluation.md): steer Macro-F1 excludes frames whose (true) accel is STOPPED.
Also reports the STOPPED-inclusive steer F1 the trainer logs, so the two can be compared.

usage: s3_review.py --pred preds.csv [--aux path] [--split validation] [--rule rule.json] [--out out.json]
preds.csv columns: source_id, sample_index, accel_pred, steer_pred (class name or index); optional split.
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
STEER = stage3_labels.STEER_CLASSES


def macro_f1(true, pred, classes):
    true, pred = np.asarray(true), np.asarray(pred)
    per = {}
    for c in classes:
        tp = int(((pred == c) & (true == c)).sum())
        fp = int(((pred == c) & (true != c)).sum())
        fn = int(((pred != c) & (true == c)).sum())
        denom = 2 * tp + fp + fn
        per[c] = None if denom == 0 else 2 * tp / denom
    vals = [0.0 if v is None else v for v in per.values()]
    return (float(np.mean(vals)) if len(true) else None), per


def to_name(series, classes):
    def conv(x):
        if isinstance(x, (int, np.integer)) or (isinstance(x, str) and x.isdigit()):
            return classes[int(x)]
        return str(x).strip().upper()
    return series.map(conv)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", type=Path, required=True)
    ap.add_argument("--aux", type=Path, default=ROOT / "data/derived/comma_subset_v1/s3_auxiliary_10hz.csv")
    ap.add_argument("--split", default="validation")
    ap.add_argument("--rule", type=Path, default=None)
    ap.add_argument("--exclude", nargs="*", default=["SRC014"])
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    rule = json.loads(args.rule.read_text(encoding="utf-8")) if args.rule else None
    aux = pd.read_csv(args.aux, encoding="utf-8-sig")
    gt = stage3_labels.add_labels(aux, rule)
    gt_split = gt[(gt["split"] == args.split) & (~gt["source_id"].isin(args.exclude))]
    gt_split = gt_split[["source_id", "sample_index", "accel_label", "steer_label"]]

    pred = pd.read_csv(args.pred, encoding="utf-8-sig")
    issues = []
    pred["accel_pred"] = to_name(pred["accel_pred"], ACCEL)
    pred["steer_pred"] = to_name(pred["steer_pred"], STEER)
    bad_a = sorted(set(pred["accel_pred"]) - set(ACCEL))
    bad_s = sorted(set(pred["steer_pred"]) - set(STEER))
    if bad_a or bad_s:
        issues.append(f"unknown classes accel={bad_a} steer={bad_s}")

    key = ["source_id", "sample_index"]
    dup = int(pred.duplicated(key).sum())
    if dup:
        issues.append(f"duplicate prediction keys: {dup}")
    if "split" in pred.columns:
        wrong = sorted(set(pred["split"]) - {args.split})
        if wrong:
            issues.append(f"prediction rows from other splits: {wrong}")
    other = gt[(gt["split"] != args.split)][key]
    leak = pred.merge(other, on=key, how="inner")
    if len(leak):
        issues.append(f"prediction keys belonging to non-{args.split} sources: {len(leak)}")
    excl = pred[pred["source_id"].isin(args.exclude)]
    if len(excl):
        issues.append(f"rows from excluded sources {args.exclude}: {len(excl)}")

    joined = gt_split.merge(pred.drop_duplicates(key), on=key, how="left", indicator=True)
    missing = joined[joined["_merge"] == "left_only"]
    if len(missing):
        issues.append(f"missing predictions: {len(missing)} of {len(gt_split)}")
    extra = pred.merge(gt, on=key, how="left", indicator=True)
    out_range = int((extra["_merge"] == "left_only").sum())
    if out_range:
        issues.append(f"prediction keys outside aux frame range: {out_range}")

    scored = joined[joined["_merge"] == "both"]
    # trainer CSVs (commit 20161cf+) also carry accel_true/steer_true: they must match our GT
    label_check = None
    if {"accel_true", "steer_true"} <= set(scored.columns):
        a_t = to_name(scored["accel_true"], ACCEL)
        s_t = to_name(scored["steer_true"], STEER)
        mov = scored["accel_label"] != "STOPPED"
        label_check = {
            "accel_mismatch": int((a_t != scored["accel_label"]).sum()),
            "steer_mismatch_excl_stopped": int((s_t[mov] != scored.loc[mov, "steer_label"]).sum()),
        }
        if label_check["accel_mismatch"] or label_check["steer_mismatch_excl_stopped"]:
            issues.append(f"trainer *_true labels differ from recomputed GT: {label_check}")
    accel_f1, accel_per = macro_f1(scored["accel_label"], scored["accel_pred"], ACCEL)
    moving = scored[scored["accel_label"] != "STOPPED"]
    steer_f1, steer_per = macro_f1(moving["steer_label"], moving["steer_pred"], STEER)
    steer_incl, _ = macro_f1(scored["steer_label"], scored["steer_pred"], STEER)

    report = {
        "split": args.split,
        "gt_rows": int(len(gt_split)),
        "scored_rows": int(len(scored)),
        "steer_scored_rows_excl_stopped": int(len(moving)),
        "sources": sorted(scored["source_id"].unique().tolist()),
        "accel_macro_f1": accel_f1,
        "accel_per_class": accel_per,
        "steer_macro_f1_official_excl_stopped": steer_f1,
        "steer_per_class": steer_per,
        "steer_macro_f1_incl_stopped": steer_incl,
        "mean_macro_f1_official": None if accel_f1 is None or steer_f1 is None else (accel_f1 + steer_f1) / 2,
        "gt_class_counts": {
            "accel": scored["accel_label"].value_counts().to_dict(),
            "steer_excl_stopped": moving["steer_label"].value_counts().to_dict(),
        },
        "trainer_label_check": label_check,
        "integrity_issues": issues,
        "integrity_pass": not issues,
        "label_source": "proxy rule (not official GT)",
        "rule": {**stage3_labels.DEFAULT_RULE, **(rule or {})},
    }
    text = json.dumps(report, indent=2, ensure_ascii=False, default=float)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
