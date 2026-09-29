"""Join yaw steer rule predictions with e005 val predictions (result 91abe1ad); official S3 with steer swapped.
Usage: s3_yaw_vs_e005.py <yaw_predictions.csv> <e005_val_predictions.csv> <out.json>"""
import json, sys
import numpy as np, pandas as pd
sys.path.insert(0, "work/pro_tools")
from s3_yaw_steer_rule import mf1
y = pd.read_csv(sys.argv[1]); e = pd.read_csv(sys.argv[2])
m = e.merge(y[["source_id", "sample_index", "steer_label", "accel_label", "pred_steer"]], on=["source_id", "sample_index"], how="left")
integ = {"rows": len(e), "unmatched": int(m.pred_steer.isna().sum()), "dup": int(e.duplicated(["source_id", "sample_index"]).sum()),
         "steer_gt_agree": float((m.steer_true == m.steer_label).mean()), "accel_gt_agree": float((m.accel_true == m.accel_label).mean())}
def s3(d, steer_col):
    acc = mf1_accel(d.accel_true.values, d.accel_pred.values)
    s = d[d.accel_true != "STOPPED"]
    st = mf1(s.steer_true.values, s[steer_col].values)
    return {"accel_f1": round(acc, 4), "steer_f1": round(st, 4), "S3": round(0.7 * acc + 0.3 * st, 4)}
def mf1_accel(yv, pv):
    cl = ["ACCELERATING", "DECELERATING", "CONSTANT", "STOPPED"]
    fs = []
    for c in cl:
        tp = np.sum((yv == c) & (pv == c)); fp = np.sum((yv != c) & (pv == c)); fn = np.sum((yv == c) & (pv != c))
        if tp + fp + fn: fs.append(2 * tp / (2 * tp + fp + fn))
    return float(np.mean(fs))
rep = {"integrity": integ, "e005_as_submitted": s3(m, "steer_pred"), "e005_accel_plus_yaw_steer": s3(m, "pred_steer")}
srcs = m.source_id.unique(); rng = np.random.RandomState(0); d = []
for _ in range(2000):
    ss = pd.concat([m[m.source_id == k] for k in rng.choice(srcs, len(srcs))])
    d.append(s3(ss, "pred_steer")["S3"] - s3(ss, "steer_pred")["S3"])
rep["delta_S3_source_boot_ci95"] = [round(float(np.percentile(d, 2.5)), 4), round(float(np.percentile(d, 97.5)), 4)]
rep["per_source_steer"] = {k: {"e005": round(mf1(g[g.accel_true != "STOPPED"].steer_true.values, g[g.accel_true != "STOPPED"].steer_pred.values), 3),
                               "yaw": round(mf1(g[g.accel_true != "STOPPED"].steer_true.values, g[g.accel_true != "STOPPED"].pred_steer.values), 3)} for k, g in m.groupby("source_id")}
open(sys.argv[3], "w").write(json.dumps(rep, indent=1)); print(json.dumps(rep, indent=1))
