"""False-positive / false-negative anatomy of the train-selected flow STOPPED rule (div_far smoothed w, thr).
Usage: s3_stopped_flow_fp.py <col_feature> <w> <thr> <out.json>"""
import json, sys
import numpy as np, pandas as pd
f, w, thr, out = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
F = pd.read_csv("work/s3_motion_feat_r2/features.csv")
Y = pd.read_csv("work/s3_yaw_steer_r1/predictions.csv")[["source_id", "sample_index", "accel_label"]]
D = F.merge(Y, on=["source_id", "sample_index"]).sort_values(["source_id", "sample_index"]).reset_index(drop=True)
h = w // 2
D["s"] = D.groupby("source_id", sort=False)[f].transform(lambda x: pd.Series([x.values[max(0, i - h):i + h + 1].mean() for i in range(len(x))], index=x.index))
D["p"] = D.s <= thr
D["y"] = D.accel_label == "STOPPED"
rep = {}
for name, sub in [("fp", D[D.p & ~D.y]), ("fn", D[~D.p & D.y])]:
    rep[name] = {"n": int(len(sub)), "by_split_source": sub.groupby(["split", "source_id"]).size().astype(int).to_dict(),
                 "speed_q": [round(float(v), 3) for v in np.quantile(sub.speed_mps, [0, 0.25, 0.5, 0.75, 1])] if len(sub) else None,
                 "true_class": sub.accel_label.value_counts().to_dict()}
rep["fp"]["by_split_source"] = {f"{a}/{b}": v for (a, b), v in rep["fp"]["by_split_source"].items()}
rep["fn"]["by_split_source"] = {f"{a}/{b}": v for (a, b), v in rep["fn"]["by_split_source"].items()}
# speed distribution of predicted-stopped rows
rep["pred_stop_speed_lt_1"] = float((D[D.p].speed_mps < 1.0).mean())
rep["pred_stop_speed_lt_2"] = float((D[D.p].speed_mps < 2.0).mean())
# threshold sensitivity (train-chosen thr x factor) on every split
sens = {}
for k in [0.7, 0.85, 1.0, 1.15, 1.3]:
    p = D.s <= thr * k
    sens[str(k)] = {s: {"pred": int(p[g.index].sum()), "tp": int((p & D.y)[g.index].sum()), "true": int(D.y[g.index].sum())} for s, g in D.groupby("split")}
rep["thr_sensitivity"] = sens
open(out, "w").write(json.dumps(rep, indent=1)); print(json.dumps(rep, indent=1))
