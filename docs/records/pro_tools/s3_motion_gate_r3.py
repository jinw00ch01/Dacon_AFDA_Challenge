"""Ultra request 4362cffd (decision 13 / 12-D): ACC-vs-DEC from INFERENCE-IDENTICAL motion channels only, gate 7.

Channels (byte-identical definitions to submission/inference.py _s3_motion_series, already cached per 10 Hz
row in work/s3_motion_feat_r2/features.csv, equivalence checked in s3_stopped_flow_equiv): yaw_far, div_far,
mag_all. Derived per source, centered windows (offline inference sees the whole clip):
  s = rolling median(5) then mean(5) of the channel;
  slope_h = (s[t+h] - s[t-h]) / (2h/10)                      (px / s^2 proxy of accel)
  lr_h    = log((s[t+h]+eps) / (s[t-h]+eps))                 (scale-free: d log speed, robust to FOV/res change)
  level   = s                                                 (speed level)
  |yaw|   = |rolling median5 yaw_far|                         (turning covariate)
h in {5, 10, 20, 30}.
Selection protocol (pre-registered, TRAIN ONLY): leave-one-origin_group-out over the 15 train sources.
  Candidates: every single derived feature (sign fit in the fold) + logistic on lr_* only + logistic on all.
  Pick the candidate with the highest pooled LOGO OOF episode AUROC on train. Then fit on all train and
  score validation (4 fixed sources) and test (4 sources) ONCE. Gate 7: episode AUROC 95% bootstrap CI
  lower bound > 0.5 and zero train<->val/test origin_group overlap.
usage: s3_motion_gate_r3.py <out_dir>
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
from s3_motion_gate import fit_logreg  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FEATS = ROOT / "work/s3_motion_feat_r2/features.csv"
HS = [5, 10, 20, 30]
EPS = 0.05
E005_VAL_EP = 0.2639


def derive(g):
    out = {}
    for p in ["div_far", "mag_all"]:
        s = g[p].rolling(5, center=True, min_periods=1).median().rolling(5, center=True, min_periods=1).mean()
        out[f"{p}_level"] = s
        for h in HS:
            fwd, bwd = s.shift(-h).fillna(s.iloc[-1]), s.shift(h).fillna(s.iloc[0])
            out[f"{p}_slope{h}"] = (fwd - bwd) / (2 * h / 10)
            out[f"{p}_lr{h}"] = np.log((fwd.clip(lower=0) + EPS) / (bwd.clip(lower=0) + EPS))
    out["absyaw"] = g["yaw_far"].rolling(5, center=True, min_periods=1).median().abs()
    return pd.DataFrame(out, index=g.index)


def episodes(df, score_col, min_len=5):
    rows = []
    for s, g in df.groupby("source_id"):
        g = g.sort_values("sample_index")
        lab = g["gt_accel"].to_numpy()
        sc = g[score_col].to_numpy(float)
        rid = np.r_[0, np.cumsum(lab[1:] != lab[:-1])]
        for r in np.unique(rid):
            m = rid == r
            if lab[m][0] in (ACC, DEC) and m.sum() >= min_len:
                rows.append({"source_id": s, "label": lab[m][0], "n": int(m.sum()), "score_mean": float(sc[m].mean()),
                             "start": int(g["sample_index"].to_numpy()[m][0])})
    return pd.DataFrame(rows)


def ep_stats(ep, n_boot=5000, seed=0):
    if len(ep) == 0:
        return {"n_ep_acc": 0, "n_ep_dec": 0, "episode_auroc": None}
    y = (ep["label"] == ACC).to_numpy()
    s = ep["score_mean"].to_numpy()
    rng = np.random.default_rng(seed)
    obs = auroc(y, s)
    boots = [a for a in (auroc(y[i], s[i]) for i in (rng.integers(0, len(ep), len(ep)) for _ in range(n_boot)))
             if a is not None]
    # source-cluster bootstrap (episodes within a drive are not independent)
    srcs = ep["source_id"].unique()
    cb = []
    for _ in range(2000):
        pick = rng.choice(srcs, len(srcs))
        e = pd.concat([ep[ep.source_id == x] for x in pick])
        a = auroc((e["label"] == ACC).to_numpy(), e["score_mean"].to_numpy())
        if a is not None:
            cb.append(a)
    perm = np.array([auroc(rng.permutation(y), s) for _ in range(n_boot)])
    return {"n_ep_acc": int(y.sum()), "n_ep_dec": int((~y).sum()), "episode_auroc": obs,
            "boot_ci95": [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))],
            "source_cluster_ci95": [float(np.percentile(cb, 2.5)), float(np.percentile(cb, 97.5))] if cb else None,
            "perm_p_one_sided_ge": float(np.mean(perm >= obs)) if obs is not None else None}


def make_scorer(kind, cols, tr):
    y = (tr.gt_accel == ACC).to_numpy()
    if kind == "single":
        c = cols[0]
        a = auroc(y, tr[c].to_numpy(float))
        sg = 1.0 if (a if a is not None else 0.5) >= 0.5 else -1.0
        return lambda Z: sg * Z[c].to_numpy(float), {"sign": sg}
    m = fit_logreg(tr[cols].to_numpy(float), y.astype(float))
    return lambda Z: m(Z[cols].to_numpy(float)), {}


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    f = pd.read_csv(FEATS)
    aux = load_all(AUX)
    d = f.drop(columns=["split"]).merge(
        aux[["source_id", "sample_index", "split", "origin_group", "gt_accel"]],
        on=["source_id", "sample_index"], how="inner", validate="one_to_one")
    d = d.sort_values(["source_id", "sample_index"]).reset_index(drop=True)
    der = pd.concat([derive(g) for _, g in d.groupby("source_id", sort=False)])
    d = pd.concat([d, der], axis=1)
    cols = list(der.columns)
    lr_cols = [c for c in cols if "_lr" in c]
    cands = {f"single:{c}": ("single", [c]) for c in cols}
    cands["logreg:lr_all"] = ("logreg", lr_cols)
    cands["logreg:all"] = ("logreg", cols)

    grp = d.groupby("split")["origin_group"].apply(lambda s: set(s.unique())).to_dict()
    leak = {"train_val": sorted(grp["train"] & grp["validation"]), "train_test": sorted(grp["train"] & grp["test"]),
            "val_test": sorted(grp["validation"] & grp["test"])}

    tr_all = d[d.split == "train"]
    tr = tr_all[tr_all.gt_accel.isin([ACC, DEC])]
    groups = sorted(tr_all.origin_group.unique())
    # LOGO OOF on train
    oof = {k: pd.Series(np.nan, index=tr_all.index) for k in cands}
    for gname in groups:
        fit = tr[tr.origin_group != gname]
        hold = tr_all[tr_all.origin_group == gname]
        for k, (kind, cc) in cands.items():
            sc, _ = make_scorer(kind, cc, fit)
            oof[k].loc[hold.index] = sc(hold)
    sel = []
    for k in cands:
        tmp = tr_all.assign(score=oof[k].to_numpy())
        # per-held-group z-norm is NOT used: scores are compared across groups as a deployed model would
        ep = episodes(tmp, "score")
        a = auroc((ep.label == ACC).to_numpy(), ep.score_mean.to_numpy()) if len(ep) else None
        ra = auroc((tmp[tmp.gt_accel.isin([ACC, DEC])].gt_accel == ACC).to_numpy(),
                   tmp[tmp.gt_accel.isin([ACC, DEC])].score.to_numpy(float))
        sel.append({"cand": k, "train_logo_episode_auroc": a, "train_logo_row_auroc": ra})
    sel = sorted(sel, key=lambda r: -(r["train_logo_episode_auroc"] or 0))
    best = sel[0]["cand"]
    kind, cc = cands[best]
    scorer, info = make_scorer(kind, cc, tr)

    rep = {"request": "4362cffd406a47979f0fd4cb7b0fcfd4", "features_file": str(FEATS.relative_to(ROOT)),
           "channels": ["yaw_far", "div_far", "mag_all"], "derived": cols, "origin_group_overlap": leak,
           "n_sources": d.groupby("split").source_id.nunique().to_dict(),
           "selection_train_logo_top10": sel[:10], "selected": best, "selected_info": info}
    res = {}
    tr_oof = tr_all.assign(score=oof[best].to_numpy())
    res["train_logo_oof"] = ep_stats(episodes(tr_oof, "score"))
    for sp, name in [("validation", "val"), ("test", "test")]:
        z = d[d.split == sp].copy()
        z["score"] = scorer(z)
        res[name] = ep_stats(episodes(z, "score"))
        zz = z[z.gt_accel.isin([ACC, DEC])]
        res[name]["row_auroc"] = auroc((zz.gt_accel == ACC).to_numpy(), zz.score.to_numpy(float))
        res[name]["row_auroc_per_source"] = {s: auroc((g.gt_accel == ACC).to_numpy(), g.score.to_numpy(float))
                                             for s, g in zz.groupby("source_id")}
        # probs CSV (monotone map; AUROC only uses order)
        sc = z["score"].to_numpy(float)
        p = 1 / (1 + np.exp(-(sc - np.median(tr_oof.score.dropna())) / (np.std(tr_oof.score.dropna()) + 1e-9))) \
            if kind == "single" else sc
        pd.DataFrame({"source_id": z.source_id, "sample_index": z.sample_index, "origin_group": z.origin_group,
                      "gt_accel": z.gt_accel, "score": sc, "p_ACCELERATING": p, "p_DECELERATING": 1 - p}
                     ).to_csv(out / f"{name}_probs.csv", index=False)
        episodes(z, "score").to_csv(out / f"{name}_episodes.csv", index=False)
    vt = d[d.split.isin(["validation", "test"])].copy()
    vt["score"] = scorer(vt)
    res["val_plus_test"] = ep_stats(episodes(vt, "score"))
    tr_oof[["source_id", "sample_index", "origin_group", "gt_accel", "score"]].to_csv(out / "train_logo_oof.csv", index=False)
    # also report every candidate on val (transparency; selection used train only)
    allval = {}
    zv = d[d.split == "validation"]
    for k, (kd, c2) in cands.items():
        s2, _ = make_scorer(kd, c2, tr)
        allval[k] = ep_stats(episodes(zv.assign(score=s2(zv)), "score"), n_boot=500)["episode_auroc"]
    rep["all_candidates_val_episode_auroc"] = dict(sorted(allval.items(), key=lambda kv: -(kv[1] or 0)))
    rep["results"] = res
    lo = res["val"].get("boot_ci95", [0, 1])[0]
    rep["gate7"] = {"rule": "val episode AUROC CI95 lower > 0.5 AND origin_group overlap 0",
                    "val_ci_lower": lo, "overlap_zero": not any(leak.values()),
                    "pass": bool(lo > 0.5 and not any(leak.values())),
                    "e005_val_episode_baseline": E005_VAL_EP}
    (out / "report.json").write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: rep[k] for k in ["selected", "selected_info", "origin_group_overlap", "gate7"]}, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str))
    print(json.dumps(sel[:8], indent=1, default=str))


if __name__ == "__main__":
    main()
