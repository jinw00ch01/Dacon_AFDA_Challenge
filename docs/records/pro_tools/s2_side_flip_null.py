"""Null distributions for s2_side_flip_audit probes (label shuffle), LOVO and 5-fold.

Loads work/s2_side_flip_audit/feats.npz (F, Ff, ys). Probe = ridge (closed form on
standardised features, score = linear) to keep 100s of refits cheap; ranks only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "work/s2_side_flip_audit"


def auroc(y, s):
    pos, neg = s[y == 1], s[y == 0]
    return float(((pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()) / (len(pos) * len(neg)))


def fit_score(Xtr, ytr, Xte, lam):
    m, s = Xtr.mean(0), Xtr.std(0) + 1e-6
    A = (Xtr - m) / s
    t = ytr - ytr.mean()  # centred target: intercept = train prior
    # dual ridge (n << d)
    K = A @ A.T
    alpha = np.linalg.solve(K + lam * np.eye(len(A)), t)
    w = A.T @ alpha
    return ((Xte - m) / s) @ w + ytr.mean()


def cv_scores(X, y, folds, aug_X=None, lam=100.0):
    sc = np.zeros(len(y))
    for f in np.unique(folds):
        tr, te = folds != f, folds == f
        Xtr, ytr = X[tr], y[tr]
        if aug_X is not None:
            Xtr = np.vstack([Xtr, aug_X[tr]]); ytr = np.concatenate([ytr, 1 - ytr])
        sc[te] = fit_score(Xtr, ytr.astype(float), X[te], lam)
    return sc


def main():
    d = np.load(OUT / "feats.npz")
    F, Ff, y = d["F"], d["Ff"], d["ys"].astype(int)
    D = F - Ff
    n = len(y)
    rng = np.random.RandomState(0)
    probes = {"raw_plain": (F, None), "raw_flipaug": (F, Ff), "antisym_plain": (D, None), "antisym_flipaug": (D, -D)}
    rep = {"n": int(n), "n_right": int(y.sum()), "lam": 100.0, "n_shuffle": 200}
    lovo = np.arange(n)
    fold_sets = [rng.permutation(np.arange(n) % 5) for _ in range(10)]
    for name, (X, aug) in probes.items():
        r = {}
        real_lovo = auroc(y, cv_scores(X, y, lovo, aug))
        real_5f = float(np.mean([auroc(y, cv_scores(X, y, fs, aug)) for fs in fold_sets]))
        null_lovo, null_5f = [], []
        for k in range(rep["n_shuffle"]):
            yp = rng.permutation(y)
            null_lovo.append(auroc(yp, cv_scores(X, yp, lovo, aug)))
            null_5f.append(auroc(yp, cv_scores(X, yp, fold_sets[k % 10], aug)))
        nl, n5 = np.array(null_lovo), np.array(null_5f)
        r["lovo"] = {"real": real_lovo, "null_mean": float(nl.mean()), "null_q05": float(np.quantile(nl, .05)),
                     "null_q95": float(np.quantile(nl, .95)),
                     "p_low": float((1 + (nl <= real_lovo).sum()) / (1 + len(nl))),
                     "p_high": float((1 + (nl >= real_lovo).sum()) / (1 + len(nl)))}
        r["fold5_mean10"] = {"real": real_5f, "null_mean": float(n5.mean()), "null_q05": float(np.quantile(n5, .05)),
                             "null_q95": float(np.quantile(n5, .95)),
                             "p_low": float((1 + (n5 <= real_5f).sum()) / (1 + len(n5))),
                             "p_high": float((1 + (n5 >= real_5f).sum()) / (1 + len(n5)))}
        rep[name] = r
        print(name, json.dumps(r), flush=True)
    (OUT / "null.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
