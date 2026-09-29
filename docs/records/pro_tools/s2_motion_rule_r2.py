"""Decision 12-A r2: richer score families from r1 series.npz (same windows/splits), FIT-only selection.

New families (per window, 50 steps, only window frames):
  step_div   : mean(div[k-n:k]) - mean(div[k:k+n])       (expansion collapses after contact -> stop step)
  step_mag   : same for mag
  shake_y/x  : |second difference| of dy / dx           (impulse, braking pitch is smooth)
  shake_xy   : shake_x + shake_y
  rstd_y     : rolling std of dy over 3 steps
  late_peak  : argmax restricted to the latest peak whose value >= frac * max (braking precedes contact)
Combos: z-sum of up to 3 families (weights 0.5/1), lag -4..2, argmax or late-peak(frac).
Selection: best FIT accuracy; generalisation of the *selection procedure* estimated by 5-fold video CV on FIT.
Usage: s2_motion_rule_r2.py <r1_dir> <out_dir>
"""
import itertools
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s2_motion_rule import FEATS, T, hit, scores, smooth  # noqa: E402


def d2abs(x):
    return np.abs(np.diff(x, n=2, prepend=[x[0], x[0]]))


def step(x, n):
    y = np.zeros_like(x)
    for k in range(len(x)):
        a, b = x[max(0, k - n):k], x[k:k + n]
        y[k] = (a.mean() if len(a) else x[k]) - (b.mean() if len(b) else x[k])
    return y


def rstd(x, n=3):
    p = np.pad(x, n // 2, mode="edge")
    return np.array([p[i:i + n].std() for i in range(len(x))])


def families(s):
    f = scores(s)
    f["step_div4"] = step(s["div"], 4)
    f["step_div8"] = step(s["div"], 8)
    f["step_mag4"] = step(s["mag"], 4)
    f["step_mag8"] = step(s["mag"], 8)
    f["shake_y"] = d2abs(s["dy"])
    f["shake_x"] = d2abs(s["dx"])
    f["shake_xy"] = f["shake_x"] + f["shake_y"]
    f["rstd_y"] = rstd(s["dy"])
    f["diff_d2"] = d2abs(s["diff"])
    return f


def zs(x):
    x = smooth(x, 1)
    return (x - x.mean()) / (x.std() + 1e-6)


def pick(score, lag, frac):
    if frac >= 1.0:
        k = int(np.argmax(score))
    else:
        thr = score.min() + frac * (score.max() - score.min())
        peaks = [i for i in range(T) if score[i] >= thr and (i == 0 or score[i] >= score[i - 1])
                 and (i == T - 1 or score[i] >= score[i + 1])]
        k = peaks[-1] if peaks else int(np.argmax(score))
    return int(np.clip(k + lag, 0, T - 1))


def main():
    r1, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    w = pd.read_csv(r1 / "windows_pair.csv", dtype={"video_id": str})
    S = np.load(r1 / "series.npz")
    Z = []
    for r in w.itertuples():
        s = {f: S[f"{r.video_id}_{r.win}_{f}"] for f in FEATS}
        Z.append({k: zs(v) for k, v in families(s).items()})
    names = sorted(Z[0])
    gt = w.gt_collision.values
    fit = np.where(w.group == "FIT")[0]
    held = np.where(w.group == "HELD")[0]

    combos = [(a,) for a in names]
    combos += [c for c in itertools.combinations(names, 2)]
    lags = range(-4, 3)
    fracs = (1.0, 0.85, 0.7)

    # cache combined score per (combo, weights) for all windows
    def comb_scores(c, wts):
        return [sum(wt * Z[i][n] for n, wt in zip(c, wts)) for i in range(len(w))]

    cands = []
    for c in combos:
        for wts in ([(1.0,)] if len(c) == 1 else [(1.0, 1.0), (1.0, 0.5), (0.5, 1.0)]):
            sc = comb_scores(c, wts)
            for frac in fracs:
                base = {i: pick(sc[i], 0, frac) for i in range(len(w))}
                for lag in lags:
                    pred = np.array([int(np.clip(base[i] + lag, 0, T - 1)) for i in range(len(w))])
                    hits = np.array([hit(pred[i], gt[i]) for i in range(len(w))])
                    cands.append({"combo": c, "w": wts, "frac": frac, "lag": lag, "hits": hits})
    print("candidates", len(cands), flush=True)

    fit_acc = np.array([c["hits"][fit].mean() for c in cands])
    order = np.argsort(-fit_acc)
    best = cands[order[0]]

    # 5-fold video CV of the selection procedure on FIT
    vids = np.array(sorted(w.video_id.iloc[fit].unique()))
    rng = np.random.RandomState(0)
    fold_of = dict(zip(rng.permutation(vids), np.arange(len(vids)) % 5))
    fv = w.video_id.iloc[fit].map(fold_of).values
    H = np.stack([c["hits"][fit] for c in cands])  # (C, nfit)
    cv_hits = np.zeros(len(fit))
    cv_hits_r1 = np.zeros(len(fit))
    r1_idx = [j for j, c in enumerate(cands) if c["combo"] == ("div_drop", "jerk_y") and c["w"] == (1.0, 1.0)
              and c["frac"] == 1.0]
    for f in range(5):
        tr, te = fv != f, fv == f
        j = int(np.argmax(H[:, tr].mean(1)))
        cv_hits[te] = H[j, te]
        j1 = r1_idx[int(np.argmax(H[r1_idx][:, tr].mean(1)))]
        cv_hits_r1[te] = H[j1, te]

    def summ(ix, hits):
        by = defaultdict(list)
        for i in ix:
            by[w.video_id.iloc[i]].append(hits[i])
        v = sorted(by)
        br = np.random.RandomState(0)
        bs = [np.mean([h for k in br.choice(len(v), len(v)) for h in by[v[k]]]) for _ in range(1000)]
        return {"acc": round(float(np.mean(hits[ix])), 4), "n_windows": len(ix), "n_videos": len(v),
                "ci95": [round(float(np.percentile(bs, 2.5)), 4), round(float(np.percentile(bs, 97.5)), 4)]}

    r1_best = cands[max(r1_idx, key=lambda j: fit_acc[j])]
    subsets = {"all": held, "human": held[w.label_source.iloc[held].values == "human"],
               "agent": held[w.label_source.iloc[held].values != "human"],
               "e001_clean": held[w.e001_clean.iloc[held].values == 1],
               "v1": held[w.src.iloc[held].values == "v1"], "v2": held[w.src.iloc[held].values == "v2"]}
    rep = {
        "design": __doc__.split("Usage")[0].strip(),
        "n_candidates": len(cands),
        "fit_top10": [{"combo": cands[j]["combo"], "w": cands[j]["w"], "frac": cands[j]["frac"],
                       "lag": cands[j]["lag"], "fit_acc": round(float(fit_acc[j]), 4)} for j in order[:10]],
        "chosen": {"combo": best["combo"], "w": best["w"], "frac": best["frac"], "lag": best["lag"],
                   "fit_acc": round(float(fit_acc[order[0]]), 4)},
        "fit_cv5_selection_acc": round(float(cv_hits.mean()), 4),
        "fit_cv5_r1_family_acc": round(float(cv_hits_r1.mean()), 4),
        "r1_rule_in_this_grid": {"frac": r1_best["frac"], "lag": r1_best["lag"],
                                 "fit_acc": round(float(r1_best["hits"][fit].mean()), 4)},
        "held_chosen": {k: summ(ix, best["hits"]) for k, ix in subsets.items() if len(ix)},
        "held_r1": {k: summ(ix, r1_best["hits"]) for k, ix in subsets.items() if len(ix)},
    }
    (out / "report.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: rep[k] for k in ("fit_top10", "chosen", "fit_cv5_selection_acc", "fit_cv5_r1_family_acc",
                                          "r1_rule_in_this_grid")}, indent=0))
    for k in ("held_chosen", "held_r1"):
        print(k, json.dumps(rep[k]))


if __name__ == "__main__":
    main()
