"""STOPPED rule sensitivity to flow-magnitude scale (FOV/resolution/frame-rate shift).
div_far and mag_all are linear in flow, so a domain whose per-step flow is s x comma's
is equivalent to thresholds / s. Uses cached r3 row features (comma, 10 Hz)."""
import json
import numpy as np, pandas as pd

def f1_score(y, p, labels, average=None, zero_division=0):
    y = np.asarray(y); p = np.asarray(p); r = []
    for c in labels:
        tp = np.sum((y == c) & (p == c)); fp = np.sum((y != c) & (p == c)); fn = np.sum((y == c) & (p != c))
        r.append(0.0 if 2 * tp + fp + fn == 0 else 2 * tp / (2 * tp + fp + fn))
    return float(np.mean(r)) if average == "macro" else r
A, B = 0.18678625586132247, 0.11957117766141878
rows = pd.read_csv("work/s3_stopped_flow_r3/all_rows.csv")
val = pd.read_csv("work/s3_stopped_flow_r3/val_rows.csv")
v = val.merge(rows[["source_id", "sample_index", "a", "mag_all_s5", "speed_mps"]], on=["source_id", "sample_index"], how="left")
assert v["a"].notna().all() and len(v) == len(val)
L = ["ACCELERATING", "CONSTANT", "DECELERATING", "STOPPED"]
out = {"note": "flow scale s: private per-step flow = s * comma; rule fires where a<=A/s... i.e. s*a<=A", "by_scale": []}
base = f1_score(v.accel_true, v.accel_pred, labels=L, average="macro", zero_division=0)
for s in [1.25, 1.0, 0.8, 0.67, 0.5, 0.33]:
    fire_all = (s * rows.a <= A) & (s * rows.mag_all_s5 <= B)
    fire = (s * v.a <= A) & (s * v.mag_all_s5 <= B)
    pred = np.where(fire, "STOPPED", v.accel_pred)
    f = f1_score(v.accel_true, pred, labels=L, average="macro", zero_division=0)
    per = f1_score(v.accel_true, pred, labels=L, average=None, zero_division=0)
    moving = rows.speed_mps > 0.5
    rec = {"s": s,
           "val_accel_macroF1_e005_or": round(f, 4), "delta_vs_e005": round(f - base, 4),
           "delta_S3_official": round(0.7 * (f - base), 4),
           "val_perclass": dict(zip(L, [round(x, 3) for x in per])),
           "val_fire_rate": round(float(fire.mean()), 4),
           "val_true_stopped_rate": round(float((v.accel_true == "STOPPED").mean()), 4),
           "all_splits_fire_rate_moving_gt0.5": round(float(fire_all[moving].mean()), 4),
           "all_splits_fire_rate_moving_by_speed": {f"{lo}-{hi}": round(float(fire_all[(rows.speed_mps > lo) & (rows.speed_mps <= hi)].mean()), 4)
                                                    for lo, hi in [(0.5, 3), (3, 8), (8, 15), (15, 40)]}}
    out["by_scale"].append(rec)
    print(json.dumps(rec, ensure_ascii=False))
out["val_e005_accel_macroF1"] = round(base, 4)
out["n_val_rows"] = len(v); out["n_all_rows"] = len(rows)
json.dump(out, open("work/s3_stopped_scale/report.json", "w"), ensure_ascii=False, indent=1)
