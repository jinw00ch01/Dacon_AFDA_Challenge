"""S3 STOPPED from image motion (flow magnitude), fit on TRAIN only; evaluate on val/test and OR-combined with e005.
Features from work/s3_motion_feat_r2/features.csv (same Farneback params / 160x120 gray as the yaw graft).
Usage: s3_stopped_flow.py <out_dir>"""
import json, os, sys
import numpy as np, pandas as pd

OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
F = pd.read_csv("work/s3_motion_feat_r2/features.csv")
Y = pd.read_csv("work/s3_yaw_steer_r1/predictions.csv")[["source_id", "sample_index", "accel_label", "steer_label", "pred_steer"]]
D = F.merge(Y, on=["source_id", "sample_index"], how="inner")
E = pd.read_csv("data/derived/experiment_packets/inbox/91abe1adc95d4ed5a468dbe1ba5f4345/files/e005_val_predictions.csv")
ACC = ["ACCELERATING", "DECELERATING", "CONSTANT", "STOPPED"]


def mf1(y, p, cl):
    fs = []
    for c in cl:
        tp = np.sum((y == c) & (p == c)); fp = np.sum((y != c) & (p == c)); fn = np.sum((y == c) & (p != c))
        if tp + fp + fn: fs.append(2 * tp / (2 * tp + fp + fn))
    return float(np.mean(fs))


def smooth(x, w):
    h = w // 2
    return np.array([x[max(0, i - h):i + h + 1].mean() for i in range(len(x))])


def auroc(s, y):
    s = np.asarray(s, float); y = np.asarray(y, bool)
    r = pd.Series(s).rank().values; n1 = y.sum(); n0 = (~y).sum()
    return round(float((r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)), 4) if n1 and n0 else None


FEATS = ["mag_all", "diff_road", "rad_road", "spd_road", "div_far"]
FEATS_GRID = sys.argv[2].split(",") if len(sys.argv) > 2 else ["mag_all", "diff_road"]
rep = {"rows": len(D), "stopped_by_split": D[D.accel_label == "STOPPED"].groupby("split").size().to_dict(),
       "rows_by_split": D.groupby("split").size().to_dict()}
# per-feature AUROC of "low value => STOPPED" per split
rep["auroc_low_is_stopped"] = {f: {s: auroc(-g[f].values, g.accel_label.values == "STOPPED")
                                   for s, g in D.groupby("split")} for f in FEATS}

# smoothed within source; candidate grid fit on TRAIN only (maximise STOPPED F1 on train rows)
grid = []
for f in FEATS_GRID:
    for w in [1, 5, 9, 15]:
        col = f"{f}_s{w}"
        D = D.sort_values(["source_id", "sample_index"]).reset_index(drop=True)
        D[col] = D.groupby("source_id", sort=False)[f].transform(lambda x: pd.Series(smooth(x.values, w), index=x.index))
        tr = D[D.split == "train"]; ytr = tr.accel_label.values == "STOPPED"
        for q in np.unique(np.quantile(tr[col], np.linspace(0.01, 0.4, 80))):
            p = tr[col].values <= q
            tp = (p & ytr).sum(); fp = (p & ~ytr).sum(); fn = (~p & ytr).sum()
            f1 = 2 * tp / (2 * tp + fp + fn) if tp else 0.0
            prec = tp / (tp + fp) if tp + fp else 0.0
            grid.append({"col": col, "thr": float(q), "train_f1": f1, "train_prec": prec})
G = pd.DataFrame(grid)
# selection: best train F1 subject to train precision >= 0.9 (override must not destroy moving rows)
Gp = G[G.train_prec >= 0.9]
best = (Gp if len(Gp) else G).sort_values("train_f1", ascending=False).iloc[0].to_dict()
rep["selected_on_train"] = best
col, thr = best["col"], best["thr"]
D["flow_stop"] = D[col] <= thr

def eval_split(g):
    y = g.accel_label.values == "STOPPED"; p = g.flow_stop.values
    tp = (p & y).sum(); fp = (p & ~y).sum(); fn = (~p & y).sum()
    return {"n": int(len(g)), "n_true": int(y.sum()), "n_pred": int(p.sum()), "prec": round(tp / (tp + fp), 4) if tp + fp else None,
            "rec": round(tp / (tp + fn), 4) if tp + fn else None, "f1": round(2 * tp / (2 * tp + fp + fn), 4) if tp else 0.0}
rep["flow_stop_alone"] = {s: eval_split(g) for s, g in D.groupby("split")}
rep["flow_stop_alone_per_source"] = {k: eval_split(g) for k, g in D[D.split != "train"].groupby("source_id")}

# OR-combine with e005 on the same val rows; steer from yaw graft (pred_steer) as shipped
m = E.merge(D[["source_id", "sample_index", "flow_stop", "pred_steer", "accel_label"]], on=["source_id", "sample_index"], how="left")
integ = {"rows": len(E), "unmatched": int(m.flow_stop.isna().sum()), "gt_agree": float((m.accel_true == m.accel_label).mean())}
m["flow_stop"] = m.flow_stop.fillna(False).astype(bool)
m["accel_or"] = np.where(m.flow_stop, "STOPPED", m.accel_pred)

def s3(d, acol):
    a = mf1(d.accel_true.values, d[acol].values, ACC)
    s = d[d.accel_true != "STOPPED"]
    st = mf1(s.steer_true.values, s.pred_steer.values, ["LEFT", "STRAIGHT", "RIGHT"])
    per = {c: round(mf1(d.accel_true.values == c, d[acol].values == c, [True]), 4) for c in ACC}
    return {"accel_f1": round(a, 4), "steer_f1_yaw": round(st, 4), "S3": round(0.7 * a + 0.3 * st, 4), "per_class_f1": per,
            "n_pred_stopped": int((d[acol] == "STOPPED").sum())}
rep["val_integrity"] = integ
rep["val_e005_plus_yaw"] = s3(m, "accel_pred")
rep["val_e005_or_flowstop_plus_yaw"] = s3(m, "accel_or")
srcs = m.source_id.unique(); rng = np.random.RandomState(0); dl = []
for _ in range(2000):
    ss = pd.concat([m[m.source_id == k] for k in rng.choice(srcs, len(srcs))])
    dl.append(s3(ss, "accel_or")["S3"] - s3(ss, "accel_pred")["S3"])
rep["delta_S3_source_boot_ci95"] = [round(float(np.percentile(dl, 2.5)), 4), round(float(np.percentile(dl, 97.5)), 4)]
rep["per_source"] = {k: {"e005": s3(g, "accel_pred")["accel_f1"], "or": s3(g, "accel_or")["accel_f1"],
                         "n_true_stop": int((g.accel_true == "STOPPED").sum()), "e005_stop": int((g.accel_pred == "STOPPED").sum()),
                         "or_stop": int((g.accel_or == "STOPPED").sum())} for k, g in m.groupby("source_id")}
m[["source_id", "sample_index", "accel_true", "accel_pred", "flow_stop", "accel_or"]].to_csv(f"{OUT}/val_rows.csv", index=False)
G.sort_values("train_f1", ascending=False).head(30).to_csv(f"{OUT}/train_grid_top30.csv", index=False)
open(f"{OUT}/report.json", "w").write(json.dumps(rep, indent=1, default=float))
print(json.dumps({k: rep[k] for k in ["stopped_by_split", "auroc_low_is_stopped", "selected_on_train", "flow_stop_alone", "val_integrity",
                                      "val_e005_plus_yaw", "val_e005_or_flowstop_plus_yaw", "delta_S3_source_boot_ci95", "per_source"]}, indent=1, default=float))
