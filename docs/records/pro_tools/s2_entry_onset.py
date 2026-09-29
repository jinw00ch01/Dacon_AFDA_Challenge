"""Decision 12-B candidate 2: entry frame = onset of the cutting-in car's lateral motion before the rule-A collision.

Uses the 12-C flow grid (same windows as rule A / e001, windows_pair.csv): per step k (frames k-1 -> k), u, v, |diff|
pooled to 9x16. Lateral signal s(k) = aggregate over an image region of |u - median_row(u)| (row median removes
ego yaw). Onset = first k in [c - kmax, c - kmin] where smoothed s exceeds alpha * max(s in that range);
optional blend with c - 8 (current graft). All parameters picked on FIT windows only (maximise entry Acc@0.3s
= |p - g| <= 3 frames), HELD reported once, compared with c - 8 on the same windows.
Usage: s2_entry_onset.py <windows_pair.csv> <flow_grid.npz> <out_dir>
"""
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REGIONS = {"lowmid": (slice(4, 9), slice(3, 13)), "mid": (slice(3, 7), slice(2, 14)), "all": (slice(0, 9), slice(0, 16)),
           "low": (slice(5, 9), slice(0, 16))}


def signal(g, region, agg):
    u = g[:, 0].astype(np.float32)
    ur = np.abs(u - np.median(u, axis=2, keepdims=True))
    r = ur[:, REGIONS[region][0], REGIONS[region][1]].reshape(len(u), -1)
    s = r.max(1) if agg == "max" else (np.percentile(r, 90, axis=1) if agg == "p90" else r.mean(1))
    return np.r_[s[0], s]          # index by frame k (frame 0 copies step 1)


def onset(s, c, kmin, kmax, alpha, sm):
    if sm > 1:
        s = np.convolve(np.pad(s, sm // 2, mode="edge"), np.ones(sm) / sm, mode="valid")
    lo, hi = max(0, c - kmax), max(0, c - kmin)
    if hi <= lo:
        return max(0, c - 8)
    seg = s[lo:hi + 1]
    m = seg.max()
    idx = np.nonzero(seg >= alpha * m)[0]
    return int(lo + idx[0]) if len(idx) else max(0, c - 8)


def main():
    w = pd.read_csv(sys.argv[1], dtype={"video_id": str})
    z = np.load(sys.argv[2])
    out = Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    w = w[w.gt_entry.notna()].copy()
    w["key"] = w.video_id + "_" + w.win.astype(str)
    w = w[w.key.isin(z.files)]
    w["gt_entry"] = w.gt_entry.astype(int)
    w["base"] = (w.pred_rule - 8).clip(lower=0)
    sigs = {}
    grid = list(itertools.product(REGIONS, ["max", "p90", "mean"], [4], [14, 20], [0.3, 0.5, 0.7, 0.9], [1, 3], [0.0, 0.5]))
    for reg, agg in {(g[0], g[1]) for g in grid}:
        sigs[(reg, agg)] = {k: signal(z[k], reg, agg) for k in w.key}

    def preds(d, prm):
        reg, agg, kmin, kmax, alpha, sm, blend = prm
        p = np.array([onset(sigs[(reg, agg)][k], int(c), kmin, kmax, alpha, sm) for k, c in zip(d.key, d.pred_rule)])
        return np.rint((1 - blend) * p + blend * d.base.values).astype(int)

    def acc(d, p):
        return float(np.mean(np.abs(p - d.gt_entry.values) <= 3))

    fit, held = w[w.group == "FIT"], w[w.group == "HELD"]
    res = sorted(((acc(fit, preds(fit, prm)), prm) for prm in grid), key=lambda x: -x[0])
    best = res[0][1]
    # FIT video-grouped 5-fold CV of the selection procedure (honest estimate of the procedure, not of `best`)
    vids = np.array(sorted(fit.video_id.unique()))
    rng = np.random.RandomState(0)
    rng.shuffle(vids)
    folds = np.array_split(vids, 5)
    cv_hits, cv_base = [], []
    for f in folds:
        tr, te = fit[~fit.video_id.isin(f)], fit[fit.video_id.isin(f)]
        prm = max(grid, key=lambda q: acc(tr, preds(tr, q)))
        cv_hits += list(np.abs(preds(te, prm) - te.gt_entry.values) <= 3)
        cv_base += list(np.abs(te.base.values - te.gt_entry.values) <= 3)
    rep = {"design": __doc__.split("Usage")[0].strip(), "n_fit_windows": len(fit), "n_fit_videos": fit.video_id.nunique(),
           "n_held_windows": len(held), "n_held_videos": held.video_id.nunique(),
           "chosen_on_fit": dict(zip(["region", "agg", "kmin", "kmax", "alpha", "smooth", "blend_with_c_minus_8"], best)),
           "fit_acc_best": round(res[0][0], 4), "fit_acc_c_minus_8": round(acc(fit, fit.base.values), 4),
           "fit_cv5_procedure": round(float(np.mean(cv_hits)), 4), "fit_cv5_c_minus_8": round(float(np.mean(cv_base)), 4),
           "top5_fit": [[round(a, 4), list(p)] for a, p in res[:5]]}
    ph = preds(held, best)
    hb = np.abs(ph - held.gt_entry.values) <= 3
    bb = np.abs(held.base.values - held.gt_entry.values) <= 3
    hum = (held.label_source == "human").values
    rep["held"] = {"onset_acc": round(float(hb.mean()), 4), "c_minus_8_acc": round(float(bb.mean()), 4),
                   "human_n": int(hum.sum()), "human_onset": round(float(hb[hum].mean()), 4) if hum.any() else None,
                   "human_c_minus_8": round(float(bb[hum].mean()), 4) if hum.any() else None}
    vs = held.video_id.values
    uv = np.unique(vs)
    d = []
    r2 = np.random.RandomState(1)
    for _ in range(2000):
        pick = r2.choice(uv, len(uv))
        m = np.concatenate([np.nonzero(vs == v)[0] for v in pick])
        d.append(hb[m].mean() - bb[m].mean())
    rep["held"]["delta_ci95_video_boot"] = [round(float(np.percentile(d, 2.5)), 4), round(float(np.percentile(d, 97.5)), 4)]
    held.assign(pred_onset=ph)[["video_id", "win", "label_source", "gt_collision", "pred_rule", "gt_entry", "base", "pred_onset"]].to_csv(out / "held_predictions.csv", index=False)
    (out / "report.json").write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in rep.items() if k != "design"}, indent=1, default=str))


if __name__ == "__main__":
    main()
