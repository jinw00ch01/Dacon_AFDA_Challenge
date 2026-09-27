"""e005 val: lag cross-correlation of score (p_ACC - p_DEC) with aux accel proxy / speed, and episode-level AUROC.

A model that is right but time-shifted peaks at lag != 0 with positive corr; a sign-flipped model peaks negative
at lag 0. Episodes = contiguous runs of the same GT ACC/DEC label (effective sample size of the val AUROC).
usage: s3_e005_lagcorr.py --probs <val_probs.csv> --out <dir>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s3_accdec_auroc import ACC, DEC, AUX, load_all  # noqa: E402
from s3_stopped_gate import auroc  # noqa: E402


def lagcorr(a, b, L):
    if L >= 0:
        x, y = a[L:], b[:len(b) - L]  # score at t+L vs b at t
    else:
        x, y = a[:L], b[-L:]
    return float(np.corrcoef(x, y)[0, 1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probs", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    aux = load_all(AUX)
    p = pd.read_csv(a.probs).merge(aux[["source_id", "sample_index", "gt_accel", "acceleration_mps2_proxy"]],
                                   on=["source_id", "sample_index"])
    rep = {}
    for s, g in p.groupby("source_id"):
        g = g.sort_values("sample_index")
        sc = (g["p_ACCELERATING"] - g["p_DECELERATING"]).to_numpy(float)
        acc = g["acceleration_mps2_proxy"].to_numpy(float)
        spd = g["speed_mps"].to_numpy(float)
        lags = range(-100, 101, 5)
        ca = {L: lagcorr(sc, acc, L) for L in lags}
        cs = {L: lagcorr(sc, spd, L) for L in lags}
        # episodes
        lab = g["gt_accel"].to_numpy()
        run_id = np.r_[0, np.cumsum(lab[1:] != lab[:-1])]
        ep = pd.DataFrame({"run": run_id, "lab": lab, "sc": sc}).groupby("run").agg(lab=("lab", "first"),
                                                                                    sc=("sc", "mean"), n=("sc", "size"))
        ep = ep[ep["lab"].isin([ACC, DEC]) & (ep["n"] >= 5)]
        rep[s] = {"corr_acc_lag0": ca[0], "best_lag_acc": max(ca, key=ca.get), "best_corr_acc": max(ca.values()),
                  "min_lag_acc": min(ca, key=ca.get), "min_corr_acc": min(ca.values()),
                  "corr_speed_lag0": cs[0],
                  "episodes_acc": int((ep["lab"] == ACC).sum()), "episodes_dec": int((ep["lab"] == DEC).sum()),
                  "episode_auroc": auroc((ep["lab"] == ACC).to_numpy(), ep["sc"].to_numpy()),
                  "lag_unit": "samples (0.1s); positive = score later than label"}
    (a.out / "lagcorr.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()


def episode_table(probs_csv, min_len=5):
    aux = load_all(AUX)
    p = pd.read_csv(probs_csv).merge(aux[["source_id", "sample_index", "gt_accel"]], on=["source_id", "sample_index"])
    rows = []
    for s, g in p.groupby("source_id"):
        g = g.sort_values("sample_index")
        lab = g["gt_accel"].to_numpy()
        sc = (g["p_ACCELERATING"] - g["p_DECELERATING"]).to_numpy(float)
        rid = np.r_[0, np.cumsum(lab[1:] != lab[:-1])]
        for r in np.unique(rid):
            m = rid == r
            if lab[m][0] in (ACC, DEC) and m.sum() >= min_len:
                rows.append({"source_id": s, "label": lab[m][0], "n": int(m.sum()), "score_mean": float(sc[m].mean()),
                             "start": int(g["sample_index"].to_numpy()[m][0])})
    return pd.DataFrame(rows)


def episode_stats(ep, n_boot=5000, seed=0):
    y = (ep["label"] == ACC).to_numpy()
    s = ep["score_mean"].to_numpy()
    rng = np.random.default_rng(seed)
    obs = auroc(y, s)
    boots = []
    for _ in range(n_boot):
        i = rng.integers(0, len(ep), len(ep))
        a = auroc(y[i], s[i])
        if a is not None:
            boots.append(a)
    perm = [auroc(rng.permutation(y), s) for _ in range(n_boot)]
    return {"n_ep_acc": int(y.sum()), "n_ep_dec": int((~y).sum()), "episode_auroc": obs,
            "boot_ci95": [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))],
            "perm_p_le_obs": float(np.mean(np.array(perm) <= obs)),
            "perm_p_two_sided": float(np.mean(np.abs(np.array(perm) - 0.5) >= abs(obs - 0.5)))}
