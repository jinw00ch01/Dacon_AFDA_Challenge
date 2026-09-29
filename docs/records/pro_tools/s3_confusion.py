"""Confusion matrices, per-source breakdown and trivial-prior references for an S3 val_predictions.csv.

usage: s3_confusion.py <val_predictions.csv> [--aux path] [--out out.json]
Uses the trainer's *_true columns (already checked equal to recomputed GT by s3_review.py).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "work" / "pro_tools"))
from afda import stage3_labels  # noqa: E402
from s3_review import macro_f1  # noqa: E402

ACCEL = stage3_labels.ACCEL_CLASSES
STEER = stage3_labels.STEER_CLASSES


def confusion(true, pred, classes):
    ct = pd.crosstab(pd.Categorical(true, classes), pd.Categorical(pred, classes), dropna=False)
    return {t: {p: int(ct.loc[t, p]) for p in classes} for t in classes}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pred", type=Path)
    ap.add_argument("--aux", type=Path, default=ROOT / "data/derived/comma_subset_v1/s3_auxiliary_10hz.csv")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    df = pd.read_csv(args.pred, encoding="utf-8-sig")
    mov = df[df["accel_true"] != "STOPPED"]

    aux = stage3_labels.add_labels(pd.read_csv(args.aux, encoding="utf-8-sig"))
    tr = aux[(aux["split"] == "train") & (aux["source_id"] != "SRC014")]
    trm = tr[tr["accel_label"] != "STOPPED"]

    per_source = {}
    for sid, g in df.groupby("source_id"):
        gm = g[g["accel_true"] != "STOPPED"]
        per_source[sid] = {
            "n": int(len(g)),
            "accel_true": g["accel_true"].value_counts().to_dict(),
            "accel_pred": g["accel_pred"].value_counts().to_dict(),
            "accel_f1": macro_f1(g["accel_true"], g["accel_pred"], ACCEL)[0],
            "steer_true_excl_stopped": gm["steer_true"].value_counts().to_dict(),
            "steer_pred_excl_stopped": gm["steer_pred"].value_counts().to_dict(),
        }

    refs = {}
    for c in ACCEL:
        refs[f"accel_all_{c}"] = macro_f1(df["accel_true"], [c] * len(df), ACCEL)[0]
    refs["steer_all_STRAIGHT_official"] = macro_f1(mov["steer_true"], ["STRAIGHT"] * len(mov), STEER)[0]

    report = {
        "accel_confusion_true_x_pred": confusion(df["accel_true"], df["accel_pred"], ACCEL),
        "steer_confusion_excl_stopped_true_x_pred": confusion(mov["steer_true"], mov["steer_pred"], STEER),
        "accel_pred_counts": df["accel_pred"].value_counts().to_dict(),
        "steer_pred_counts_excl_stopped": mov["steer_pred"].value_counts().to_dict(),
        "trivial_prior_refs": refs,
        "train_gt_counts": {
            "accel": tr["accel_label"].value_counts().to_dict(),
            "steer_excl_stopped": trm["steer_label"].value_counts().to_dict(),
        },
        "per_source": per_source,
    }
    text = json.dumps(report, indent=2, ensure_ascii=False, default=float)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
