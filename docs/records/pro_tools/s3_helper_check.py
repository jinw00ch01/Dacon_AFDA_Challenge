"""Independent CPU check of origin/main 21da08c stage3_labels.accel_from_speed_series /
derive_accel_column (S3 e002 accel post-processing).

Checks on the frozen aux CSV (SRC014 excluded), oracle TRUE speed as speed_pred:
  A. derive_accel_column with elapsed_seconds  -> accuracy vs add_labels per split
  B. same, elapsed_seconds dropped (inference case: uniform 0.1s)
  C. per-clip application (source cut into chunks of N rows, helper applied per chunk)
     -> boundary effect if test videos are shorter clips than the aux recordings
  D. dt statistics of elapsed_seconds (how far from 0.1s)

usage: s3_helper_check.py --helper <stage3_labels copy.py> [--out report.json]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def load(path):
    spec = importlib.util.spec_from_file_location("s3l_helper", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def macro_f1(true, pred, classes):
    vals = []
    for c in classes:
        tp = ((pred == c) & (true == c)).sum()
        fp = ((pred == c) & (true != c)).sum()
        fn = ((pred != c) & (true == c)).sum()
        d = 2 * tp + fp + fn
        vals.append(0.0 if d == 0 else 2 * tp / d)
    return float(np.mean(vals))


def score(aux, pred, classes):
    out = {}
    for split in ["train", "validation", "test"]:
        m = (aux["split"] == split).to_numpy()
        t = aux.loc[m, "accel_label"].to_numpy()
        p = np.asarray(pred)[m]
        out[split] = {"n": int(m.sum()), "acc": float((p == t).mean()), "macro_f1": macro_f1(t, p, classes)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--helper", type=Path, required=True)
    ap.add_argument("--aux", type=Path, default=ROOT / "data/derived/comma_subset_v1/s3_auxiliary_10hz.csv")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    h = load(args.helper)
    C = h.ACCEL_CLASSES
    aux = pd.read_csv(args.aux, encoding="utf-8-sig")
    aux = aux[aux["source_id"] != "SRC014"].sort_values(["source_id", "sample_index"]).reset_index(drop=True)
    aux["accel_label"] = h.add_labels(aux)["accel_label"].to_numpy()
    aux["speed_pred"] = aux["speed_mps"]
    rep = {"helper": str(args.helper), "rows": int(len(aux)), "rule": h.DEFAULT_RULE}

    dts = aux.groupby("source_id")["elapsed_seconds"].diff().dropna()
    rep["dt"] = {"mean": float(dts.mean()), "min": float(dts.min()), "max": float(dts.max()),
                 "frac_abs_dev_gt_5ms": float(((dts - 0.1).abs() > 0.005).mean())}
    rep["rows_per_source"] = {"min": int(aux.groupby("source_id").size().min()),
                              "max": int(aux.groupby("source_id").size().max())}

    rep["A_elapsed"] = score(aux, h.derive_accel_column(aux, "speed_pred").to_numpy(), C)
    no_t = aux.drop(columns=["elapsed_seconds"])
    rep["B_uniform_0p1s"] = score(aux, h.derive_accel_column(no_t, "speed_pred").to_numpy(), C)

    rep["C_chunked_uniform"] = {}
    for n in [50, 100, 200, 300]:
        chunk = no_t.copy()
        pos = chunk.groupby("source_id").cumcount()
        chunk["source_id"] = chunk["source_id"] + "_c" + (pos // n).astype(str)
        pred = h.derive_accel_column(chunk, "speed_pred").to_numpy()
        rep["C_chunked_uniform"][f"chunk{n}"] = score(aux, pred, C)["validation"]

    # shuffled input order: helper must sort by sample_index itself
    shuf = aux.sample(frac=1.0, random_state=0)
    ps = h.derive_accel_column(shuf, "speed_pred").reindex(aux.index).to_numpy()
    rep["shuffled_input_acc_all"] = float((ps == aux["accel_label"].to_numpy()).mean())

    txt = json.dumps(rep, indent=2, ensure_ascii=False)
    print(txt)
    if args.out:
        args.out.write_text(txt, encoding="utf-8")


if __name__ == "__main__":
    main()
