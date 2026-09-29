"""Probe: does shifting e005/e001 accel predictions in time (within source) change official S3? (alignment check)"""
import sys, json
from pathlib import Path
import pandas as pd
from s3_stopped_gate import ROOT, attach, load_val, scores
val = load_val(ROOT / "data/derived/comma_subset_v1/s3_auxiliary_10hz.csv")
out = {}
for name, p, col in [("e005_raw", sys.argv[1], "accel_pred_raw"), ("e001", sys.argv[2], "accel_pred")]:
    df, _ = attach(val, p)
    df = df.sort_values(["source_id", "sample_index"]).reset_index(drop=True)
    res = {}
    for k in range(-40, 41, 5):
        d = df.copy()
        d["_s"] = d.groupby("source_id")[col].shift(k)
        d["_s"] = d["_s"].fillna(d[col])
        r = scores(d, "_s")
        res[k] = (round(r["S3"], 4), round(r["accel_f1"], 4), {c: round(v, 3) for c, v in r["accel_per_class"].items()})
    out[name] = res
    for k, v in res.items(): print(name, k, v)
Path(sys.argv[3]).write_text(json.dumps(out, indent=1), encoding="utf-8")
