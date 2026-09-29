"""Conjunction STOPPED rule: div_far_s15 <= a AND <guard>_s<w> <= b, both chosen on TRAIN only (max train F1).
Guard removes high-speed flow-failure rows (div_far ~0 on fast textureless highway).
Reports train/val/test STOPPED P/R/F1, high-speed FP count, and val official S3 with e005 accel OR rule, steer = yaw graft.
Usage: s3_stopped_flow_and.py <out_dir>"""
import json, os, sys
import numpy as np, pandas as pd
OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
F = pd.read_csv("work/s3_motion_feat_r2/features.csv")
Y = pd.read_csv("work/s3_yaw_steer_r1/predictions.csv")[["source_id", "sample_index", "accel_label", "pred_steer"]]
D = F.merge(Y, on=["source_id", "sample_index"]).sort_values(["source_id", "sample_index"]).reset_index(drop=True)
E = pd.read_csv("data/derived/experiment_packets/inbox/91abe1adc95d4ed5a468dbe1ba5f4345/files/e005_val_predictions.csv")
ACC = ["ACCELERATING", "DECELERATING", "CONSTANT", "STOPPED"]


def sm(f, w):
    h = w // 2
    return D.groupby("source_id", sort=False)[f].transform(lambda x: pd.Series([x.values[max(0, i - h):i + h + 1].mean() for i in range(len(x))], index=x.index))


def mf1(y, p, cl):
    fs = []
    for c in cl:
        tp = np.sum((y == c) & (p == c)); fp = np.sum((y != c) & (p == c)); fn = np.sum((y == c) & (p != c))
        if tp + fp + fn: fs.append(2 * tp / (2 * tp + fp + fn))
    return float(np.mean(fs))


D["a"] = sm("div_far", 15)
y = (D.accel_label == "STOPPED").values
tr = (D.split == "train").values
cands = []
aq = np.unique(np.quantile(D.a[tr], np.linspace(0.02, 0.2, 37)))
for g in ["diff_road", "mag_all", "rad_road"]:
    for w in [1, 5, 15]:
        D[f"{g}_s{w}"] = sm(g, w)
        bq = np.unique(np.quantile(D[f"{g}_s{w}"][tr], np.linspace(0.02, 0.6, 59)))
        av = D.a.values[tr]; bv = D[f"{g}_s{w}"].values[tr]; yt = y[tr]
        for a in aq:
            pa = av <= a
            for b in bq:
                p = pa & (bv <= b)
                tp = (p & yt).sum(); fp = (p & ~yt).sum(); fn = (~p & yt).sum()
                cands.append((2 * tp / (2 * tp + fp + fn) if tp else 0.0, f"{g}_s{w}", float(a), float(b), int(fp)))
C = pd.DataFrame(cands, columns=["train_f1", "guard", "a", "b", "train_fp"]).sort_values(["train_f1", "b"], ascending=[False, False])
best = C.iloc[0].to_dict()
D["p"] = (D.a <= best["a"]) & (D[best["guard"]] <= best["b"])
rep = {"selected_on_train": best, "top10_train": C.head(10).to_dict("records")}


def prf(g):
    yy = g.accel_label.values == "STOPPED"; p = g.p.values
    tp = (p & yy).sum(); fp = (p & ~yy).sum(); fn = (~p & yy).sum()
    return {"n": int(len(g)), "true": int(yy.sum()), "pred": int(p.sum()), "tp": int(tp), "fp": int(fp),
            "fp_speed_gt5": int((p & ~yy & (g.speed_mps.values > 5)).sum()), "f1": round(2 * tp / (2 * tp + fp + fn), 4) if tp else 0.0}
rep["by_split"] = {s: prf(g) for s, g in D.groupby("split")}
rep["fp_by_source"] = {f"{a}/{b}": int(v) for (a, b), v in D[D.p & ~(D.accel_label == "STOPPED")].groupby(["split", "source_id"]).size().items()}
m = E.merge(D[["source_id", "sample_index", "p", "pred_steer"]], on=["source_id", "sample_index"], how="left")
rep["val_integrity"] = {"rows": len(E), "unmatched": int(m.p.isna().sum())}
m["p"] = m.p.fillna(False).astype(bool)
m["accel_or"] = np.where(m.p, "STOPPED", m.accel_pred)


def s3(d, col):
    a = mf1(d.accel_true.values, d[col].values, ACC)
    s = d[d.accel_true != "STOPPED"]
    st = mf1(s.steer_true.values, s.pred_steer.values, ["LEFT", "STRAIGHT", "RIGHT"])
    return {"accel_f1": round(a, 4), "stopped_f1": round(mf1(d.accel_true.values == "STOPPED", d[col].values == "STOPPED", [True]), 4),
            "steer_f1_yaw": round(st, 4), "S3": round(0.7 * a + 0.3 * st, 4)}
rep["val_e005_plus_yaw"] = s3(m, "accel_pred")
rep["val_e005_or_rule_plus_yaw"] = s3(m, "accel_or")
# bootstrap over rows-within-source blocks is dominated by 2 STOPPED sources; report source-level and pooled-row CIs
srcs = m.source_id.unique(); rng = np.random.RandomState(0); ds, dr = [], []
for _ in range(1000):
    ss = pd.concat([m[m.source_id == k] for k in rng.choice(srcs, len(srcs))])
    ds.append(s3(ss, "accel_or")["S3"] - s3(ss, "accel_pred")["S3"])
    # 30-row block bootstrap within the pooled val set
    blocks = [m.iloc[i:i + 30] for i in range(0, len(m), 30)]
    bb = pd.concat([blocks[j] for j in rng.randint(0, len(blocks), len(blocks))])
    dr.append(s3(bb, "accel_or")["S3"] - s3(bb, "accel_pred")["S3"])
rep["delta_S3_source_boot_ci95"] = [round(float(np.percentile(ds, q)), 4) for q in (2.5, 97.5)]
rep["delta_S3_block30_boot_ci95"] = [round(float(np.percentile(dr, q)), 4) for q in (2.5, 97.5)]
m[["source_id", "sample_index", "accel_true", "accel_pred", "p", "accel_or"]].to_csv(f"{OUT}/val_rows.csv", index=False)
D[["source_id", "sample_index", "split", "speed_mps", "accel_label", "a", best["guard"], "p"]].to_csv(f"{OUT}/all_rows.csv", index=False)
open(f"{OUT}/report.json", "w").write(json.dumps(rep, indent=1, default=float)); print(json.dumps({k: v for k, v in rep.items() if k != "top10_train"}, indent=1, default=float))
