"""Self-test for s3_review.py: oracle / majority / stopped-straight-only predictions on validation."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from afda import stage3_labels  # noqa: E402

out = ROOT / "work/s3_review_selftest"
out.mkdir(parents=True, exist_ok=True)
aux = pd.read_csv(ROOT / "data/derived/comma_subset_v1/s3_auxiliary_10hz.csv", encoding="utf-8-sig")
gt = stage3_labels.add_labels(aux)
val = gt[(gt["split"] == "validation") & (gt["source_id"] != "SRC014")].copy()
key = ["source_id", "sample_index", "split"]

oracle = val[key].assign(accel_pred=val["accel_label"], steer_pred=val["steer_label"])
oracle.to_csv(out / "oracle.csv", index=False)
# Oracle accel, but steer always STRAIGHT: shows how STOPPED rows inflate the inclusive steer F1.
straight = val[key].assign(accel_pred=val["accel_label"], steer_pred="STRAIGHT")
straight.to_csv(out / "all_straight.csv", index=False)
# Corrupted: drop 5 rows, duplicate 3, add one train row.
bad = pd.concat([oracle.iloc[5:], oracle.iloc[:3]])
tr = gt[gt["split"] == "train"].iloc[:1]
bad = pd.concat([bad, tr[key].assign(accel_pred=tr["accel_label"], steer_pred=tr["steer_label"])])
bad.to_csv(out / "corrupted.csv", index=False)
# Trainer format (commit 20161cf val_predictions.csv): *_true columns; STOPPED steer_true masked to STRAIGHT.
tf = val[key].assign(accel_pred=val["accel_label"], steer_pred=val["steer_label"],
                     accel_true=val["accel_label"],
                     steer_true=val["steer_label"].where(val["accel_label"] != "STOPPED", "STRAIGHT"))
tf.to_csv(out / "trainer_format.csv", index=False)
# Same, but trainer GT disagrees on 7 moving rows (e.g. different rule version).
tfm = tf.copy()
idx = tfm.index[tfm["accel_true"] != "STOPPED"][:7]
tfm.loc[idx, "steer_true"] = tfm.loc[idx, "steer_true"].map({"LEFT": "RIGHT", "RIGHT": "LEFT", "STRAIGHT": "LEFT"})
tfm.to_csv(out / "trainer_mismatch.csv", index=False)
print("val rows", len(val), "stopped", int((val["accel_label"] == "STOPPED").sum()))
