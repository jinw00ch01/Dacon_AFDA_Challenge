"""Decision 12-D: train-only feature selection by per-source robustness (median of per-train-source AUROC),
plus leave-one-source-out logistic on train. Writes val probs for the selected single feature and the
LOSO-selected logistic subset. usage: s3_motion_select.py <features.csv> <out_dir>"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from s3_accdec_auroc import ACC, DEC, AUX, load_all
from s3_stopped_gate import auroc
from s3_motion_gate import derive, fit_logreg

f = pd.read_csv(sys.argv[1]); out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
aux = load_all(AUX)
d = f.merge(aux[["source_id", "sample_index", "gt_accel"]], on=["source_id", "sample_index"], validate="one_to_one")
d = d.sort_values(["source_id", "sample_index"]).reset_index(drop=True)
der = pd.concat([derive(g) for _, g in d.groupby("source_id")]); d = pd.concat([d, der], axis=1); cols = list(der.columns)
m = d.gt_accel.isin([ACC, DEC]); tr = d[m & (d.split == "train")]; va = d[m & (d.split == "validation")]
rob = {}
for c in cols:
    per = [auroc((g.gt_accel == ACC).to_numpy(), g[c].to_numpy(float)) for _, g in tr.groupby("source_id")]
    per = [p for p in per if p is not None]
    rob[c] = {"median_src_auroc": float(np.median(per)), "frac_src_gt_0.5": float(np.mean(np.array(per) > 0.5)), "n_src": len(per),
              "val": auroc((va.gt_accel == ACC).to_numpy(), va[c].to_numpy(float))}
rank = sorted(rob, key=lambda c: -rob[c]["median_src_auroc"])
sel = rank[0]
# LOSO on train: logistic over the top-k robust features, k chosen by mean held-source AUROC
loso = {}
for k in (1, 3, 5, 8):
    feats = rank[:k]; aucs = []
    for s in tr.source_id.unique():
        a, b = tr[tr.source_id != s], tr[tr.source_id == s]
        mdl = fit_logreg(a[feats].to_numpy(float), (a.gt_accel == ACC).to_numpy(float))
        r = auroc((b.gt_accel == ACC).to_numpy(), mdl(b[feats].to_numpy(float)))
        if r is not None: aucs.append(r)
    loso[k] = float(np.mean(aucs))
kbest = max(loso, key=loso.get); feats = rank[:kbest]
mdl = fit_logreg(tr[feats].to_numpy(float), (tr.gt_accel == ACC).to_numpy(float))
v_all = d[d.split == "validation"]
p = mdl(v_all[feats].to_numpy(float))
pd.DataFrame({"source_id": v_all.source_id, "sample_index": v_all.sample_index, "p_ACCELERATING": p, "p_DECELERATING": 1 - p}).to_csv(out / "val_probs_loso.csv", index=False)
x = v_all[sel].to_numpy(float); s = 1 / (1 + np.exp(-(x - np.median(x)) / (x.std() + 1e-6)))
pd.DataFrame({"source_id": v_all.source_id, "sample_index": v_all.sample_index, "p_ACCELERATING": s, "p_DECELERATING": 1 - s}).to_csv(out / "val_probs_robust_single.csv", index=False)
rep = {"robust_top8": {c: rob[c] for c in rank[:8]}, "selected_single": sel, "loso_mean_auroc_by_k": loso, "k": kbest, "loso_feats": feats,
       "val_row_auroc_loso_model": auroc((va.gt_accel == ACC).to_numpy(), mdl(va[feats].to_numpy(float)))}
(out / "select.json").write_text(json.dumps(rep, indent=1)); print(json.dumps(rep, indent=1))
