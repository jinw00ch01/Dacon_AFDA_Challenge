"""Diagnostic: does e002 speed_pred carry STOPPED signal at all? AUROC + extended-grid LOSO (0.5..25 m/s)."""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import s3_vstop_calib as C

def auroc(y, s):
    y = np.asarray(y, bool); s = np.asarray(s, float)
    r = pd.Series(s).rank().to_numpy(); n1 = y.sum(); n0 = (~y).sum()
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)) if n1 and n0 else None

pred = pd.read_csv(sys.argv[1], encoding="utf-8-sig")
val = C.load_val(C.ROOT / "data/derived/comma_subset_v1/s3_auxiliary_10hz.csv")
df = val.merge(pred[["source_id", "sample_index", "speed_pred", "steer_pred"]], on=["source_id", "sample_index"], validate="one_to_one")
y = df["accel_true_v1b"] == "STOPPED"
rep = {"auroc_low_speed_pred_is_stopped_pooled": auroc(y, -df["speed_pred"]),
       "auroc_within": {s: auroc(y[g.index], -g["speed_pred"]) for s, g in df.groupby("source_id") if y[g.index].any()},
       "speed_true_vs_pred_corr": {s: float(np.corrcoef(g["speed_mps"], g["speed_pred"])[0, 1]) for s, g in df.groupby("source_id")},
       "speed_mae": float((df["speed_mps"] - df["speed_pred"]).abs().mean()),
       "per_source_speed": {s: {"true_mean": float(g["speed_mps"].mean()), "pred_mean": float(g["speed_pred"].mean()),
                                "true_min": float(g["speed_mps"].min()), "pred_min": float(g["speed_pred"].min())} for s, g in df.groupby("source_id")}}
grid = [round(x, 2) for x in np.arange(0.5, 25.01, 0.5)]
preds = {t: C.derive(df, t) for t in grid}
gt = df["accel_true_v1b"].tolist()
pooled = [(t, C.macro_f1(gt, preds[t].tolist())) for t in grid]
bt, bf = max(pooled, key=lambda x: x[1])
rep["ext_grid_in_sample_best"] = {"v_stop_pred": bt, "accel_f1": bf, "stopped_f1": C.per_class(gt, preds[bt].tolist())["STOPPED"],
                                   "n_pred_stopped": int((preds[bt] == "STOPPED").sum())}
cv = pd.Series(index=df.index, dtype=object); loso = []
for held in sorted(df["source_id"].unique()):
    tr = df["source_id"] != held
    b = max(grid, key=lambda t: C.macro_f1(df.loc[tr, "accel_true_v1b"].tolist(), preds[t][tr].tolist()))
    cv[~tr] = preds[b][~tr]
    loso.append({"held_out": held, "chosen": b, "accel_f1_held": C.macro_f1(df.loc[~tr, "accel_true_v1b"].tolist(), preds[b][~tr].tolist()),
                 "accel_f1_held_v0.5": C.macro_f1(df.loc[~tr, "accel_true_v1b"].tolist(), preds[0.5][~tr].tolist())})
rep["ext_grid_loso"] = loso
rep["ext_grid_loso_stitched"] = {"accel_f1": C.macro_f1(gt, cv.tolist()), "per_class": C.per_class(gt, cv.tolist()),
                                 "n_pred_stopped": int((cv == "STOPPED").sum())}
out = C.ROOT / "work/s3_vstop_e002/diag.json"
out.write_text(json.dumps(rep, indent=2, default=float), encoding="utf-8")
print(json.dumps(rep, indent=1, default=float))
