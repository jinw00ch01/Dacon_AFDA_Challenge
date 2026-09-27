"""Decision 12-D: ACC-vs-DEC discrimination from motion features only (train-fit, val judged by gate 7).

Derived per source (centered windows, 10 Hz): proxy p smoothed by rolling median (5) then mean (L); slope of
p over +-H samples: (p[t+H] - p[t-H]) / (2H/10). Also log-ratio slope for positive proxies.
Single-feature AUROC (train and val; sign chosen on train), then a numpy logistic regression over all slopes
fit on train ACC/DEC rows. Val scores are written as a probs CSV for s3_gate7.py (p_ACC = sigmoid, p_DEC = 1-p).

usage: s3_motion_gate.py <features.csv> <out_dir>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s3_accdec_auroc import ACC, DEC, AUX, load_all  # noqa: E402
from s3_stopped_gate import auroc  # noqa: E402

PROXIES = ["rad_road", "spd_road", "mag_all", "div_all", "div_far", "div_mid", "diff_road"]
HS = [5, 10, 20]


def derive(g):
    out = {}
    for p in PROXIES:
        s = g[p].rolling(5, center=True, min_periods=1).median().rolling(5, center=True, min_periods=1).mean()
        for h in HS:
            fwd, bwd = s.shift(-h), s.shift(h)
            fwd, bwd = fwd.fillna(s.iloc[-1]), bwd.fillna(s.iloc[0])
            out[f"{p}_slope{h}"] = (fwd - bwd) / (2 * h / 10)
            out[f"{p}_lr{h}"] = np.log((fwd.clip(lower=0) + 0.05) / (bwd.clip(lower=0) + 0.05))
    for c in ["yaw_far", "yaw_all"]:
        out[f"{c}_s"] = g[c].rolling(5, center=True, min_periods=1).median()
    return pd.DataFrame(out, index=g.index)


def fit_logreg(X, y, l2=1.0, iters=600, lr=0.3):
    mu, sd = X.mean(0), X.std(0) + 1e-6
    Xs = np.c_[(X - mu) / sd, np.ones(len(X))]
    w = np.zeros(Xs.shape[1])
    sw = np.where(y == 1, (len(y) - y.sum()) / max(1, y.sum()), 1.0)
    for _ in range(iters):
        p = 1 / (1 + np.exp(-Xs @ w))
        w -= lr * (Xs.T @ (sw * (p - y)) / sw.sum() + l2 * np.r_[w[:-1], 0] / len(y))
    return lambda Z: 1 / (1 + np.exp(-(np.c_[(Z - mu) / sd, np.ones(len(Z))] @ w)))


def main():
    feats, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    f = pd.read_csv(feats)
    aux = load_all(AUX)
    d = f.merge(aux[["source_id", "sample_index", "gt_accel", "gt_steer"]], on=["source_id", "sample_index"],
                how="inner", validate="one_to_one")
    d = d.sort_values(["source_id", "sample_index"]).reset_index(drop=True)
    der = pd.concat([derive(g) for _, g in d.groupby("source_id")])
    d = pd.concat([d, der], axis=1)
    cols = list(der.columns)
    m = d["gt_accel"].isin([ACC, DEC])
    tr, va = d[m & (d.split == "train")], d[m & (d.split == "validation")]
    ytr, yva = (tr.gt_accel == ACC).to_numpy(), (va.gt_accel == ACC).to_numpy()
    single = {}
    for c in cols:
        a_tr = auroc(ytr, tr[c].to_numpy(float))
        sgn = 1 if (a_tr or 0.5) >= 0.5 else -1
        single[c] = {"train": round(max(a_tr, 1 - a_tr), 4) if a_tr is not None else None, "sign": sgn,
                     "val_signed": auroc(yva, sgn * va[c].to_numpy(float))}
    rank = sorted(single.items(), key=lambda kv: -(kv[1]["train"] or 0))
    model = fit_logreg(tr[cols].to_numpy(float), ytr.astype(float))
    ptr, pva = model(tr[cols].to_numpy(float)), model(va[cols].to_numpy(float))
    rep = {"rows": {"train_accdec": int(len(tr)), "val_accdec": int(len(va)), "train_acc": int(ytr.sum()),
                    "val_acc": int(yva.sum())},
           "single_top10_by_train": rank[:10],
           "logreg": {"train_auroc": auroc(ytr, ptr), "val_auroc": auroc(yva, pva),
                      "val_auroc_per_source": {s: auroc((g.gt_accel == ACC).to_numpy(), model(g[cols].to_numpy(float)))
                                               for s, g in va.groupby("source_id")}},
           "speed_corr_train": {p: float(d[d.split == "train"][[p, "speed_mps"]].corr().iloc[0, 1]) for p in PROXIES}}
    # probs CSV over all val rows (gate 7 uses ACC/DEC episodes)
    v_all = d[d.split == "validation"]
    pv = model(v_all[cols].to_numpy(float))
    pd.DataFrame({"source_id": v_all.source_id, "sample_index": v_all.sample_index,
                  "p_ACCELERATING": pv, "p_DECELERATING": 1 - pv}).to_csv(out / "val_probs.csv", index=False)
    # same fixed model on the proxy test split (secondary; nothing is selected on it)
    t_all = d[d.split == "test"]
    pt = model(t_all[cols].to_numpy(float))
    pd.DataFrame({"source_id": t_all.source_id, "sample_index": t_all.sample_index,
                  "p_ACCELERATING": pt, "p_DECELERATING": 1 - pt}).to_csv(out / "test_probs.csv", index=False)
    pd.concat([pd.read_csv(out / "val_probs.csv"), pd.read_csv(out / "test_probs.csv")]).to_csv(
        out / "valtest_probs.csv", index=False)
    best = rank[0][0]
    sv = single[best]["sign"] * v_all[best].to_numpy(float)
    sv = 1 / (1 + np.exp(-(sv - np.median(sv)) / (np.std(sv) + 1e-6)))
    pd.DataFrame({"source_id": v_all.source_id, "sample_index": v_all.sample_index,
                  "p_ACCELERATING": sv, "p_DECELERATING": 1 - sv}).to_csv(out / "val_probs_single_best.csv", index=False)
    rep["single_best"] = best
    (out / "report.json").write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    print(json.dumps(rep, indent=1, default=str)[:4000])


if __name__ == "__main__":
    main()
