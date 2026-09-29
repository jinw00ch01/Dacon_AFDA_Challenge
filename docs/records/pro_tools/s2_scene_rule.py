"""Decision 12-C: S2 entry-side and evasion-space rules from motion, gated on HELD with decision 8c33234b.

Inputs: windows_pair.csv (rule A windows, FIT/HELD split, pred_pair = deployable collision index),
flow_grid.npz (s2_scene_flow.py: per window 49 x [u, v, |diff|] on a 16x9 grid), merged Nexar v2 label CSV.

Per flow step a global affine model u = a + b*rx + c*ry, v = d + e*rx + f*ry is fitted (one trimmed refit) and
removed; the residual (ru, rv) is object motion. Anchor c = collision index in the window (pred_pair: deployable;
gt: oracle, reported only). All features use only the 50 window frames.

Side (LEFT = victim came in from the left of the screen = moves right on screen):
  obj_u     energy-weighted mean ru over the lower-centre block, steps [c-L, c]   (> thr -> LEFT)
  centroid  energy-weighted x-centroid of residual energy, steps [c-L, c-L/2]   (< thr -> LEFT)
  diff_lr   (left - right) half |diff| share, steps [c-L, c]
Evasion: pre_div (mean affine expansion b+f, [c-L, c-1]) = ego speed proxy, pre_mag, post_mag ([c+2, c+12]),
  post_pre (post_mag - pre_mag), obj_e (residual energy pre), onset (steps from residual-energy onset to c).
Selection on FIT only: feature x L x direction x threshold (FIT quantiles or 0), maximising window Macro-F1.
Gate (HELD, decision 8c33234b): integrity, max predicted share <= 0.9, video-bootstrap CI low > constant floor,
video-level label permutation p < 0.05. Windows of one video stay together in bootstrap and permutation.

Usage: s2_scene_rule.py <windows_pair.csv> <flow_grid.npz> <merged.csv> <out_dir>
"""
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

GH, GW, T = 9, 16, 50
RX = np.tile((np.arange(GW) + 0.5) / GW - 0.5, (GH, 1))
RY = np.tile(((np.arange(GH) + 0.5) / GH - 0.5)[:, None], (1, GW))
A = np.c_[np.ones(GH * GW), RX.ravel(), RY.ravel()]


def affine_resid(x):
    y = x.ravel()
    coef = np.linalg.lstsq(A, y, rcond=None)[0]
    r = y - A @ coef
    keep = np.abs(r) <= np.quantile(np.abs(r), 0.8)
    coef = np.linalg.lstsq(A[keep], y[keep], rcond=None)[0]
    return (y - A @ coef).reshape(GH, GW), coef


def decompose(g):
    """g: (49, 3, 9, 16) -> per-step arrays; index s = flow into window frame s+1."""
    n = len(g)
    ru, rv = np.zeros((n, GH, GW)), np.zeros((n, GH, GW))
    div, mag = np.zeros(n), np.zeros(n)
    for s in range(n):
        u, v = g[s, 0].astype(np.float64), g[s, 1].astype(np.float64)
        ru[s], cu = affine_resid(u)
        rv[s], cv = affine_resid(v)
        div[s] = cu[1] + cv[2]
        mag[s] = float(np.mean(np.hypot(u[4:], v[4:])))
    return {"ru": ru, "rv": rv, "e": ru ** 2 + rv ** 2, "diff": g[:, 2].astype(np.float64), "div": div, "mag": mag}


def steps(c, lo, hi):
    """window frame range [c+lo, c+hi] -> flow step indices (frame k <- step k-1)."""
    a, b = max(1, c + lo), min(T - 1, c + hi)
    return list(range(a - 1, b)) if b >= a else []


def feats(d, c):
    out = {}
    for L in (5, 10, 20):
        st = steps(c, -L, 0)
        if st:
            e = d["e"][st][:, 3:, 3:13]
            out[f"obj_u_L{L}"] = float((d["ru"][st][:, 3:, 3:13] * e).sum() / (e.sum() + 1e-9))
            dl, dr = d["diff"][st][:, 3:, :GW // 2].sum(), d["diff"][st][:, 3:, GW // 2:].sum()
            out[f"diff_lr_L{L}"] = float((dl - dr) / (dl + dr + 1e-9))
        st2 = steps(c, -L, -L // 2)
        if st2:
            e = d["e"][st2][:, 2:]
            out[f"centroid_L{L}"] = float((e * RX[2:]).sum() / (e.sum() + 1e-9))
        st3 = steps(c, -L, -1)
        if st3:
            out[f"pre_div_L{L}"] = float(d["div"][st3].mean())
            out[f"pre_mag_L{L}"] = float(d["mag"][st3].mean())
            out[f"obj_e_L{L}"] = float(d["e"][st3][:, 3:, 3:13].mean())
    post = steps(c, 2, 12)
    if post:
        out["post_mag"] = float(d["mag"][post].mean())
        pre = steps(c, -10, -1)
        if pre:
            out["post_pre"] = out["post_mag"] - float(d["mag"][pre].mean())
    st = steps(c, -30, 0)
    if len(st) >= 5:
        ec = d["e"][st][:, 3:, 3:13].mean((1, 2))
        on = int(np.argmax(ec >= 0.5 * ec.max()))
        out["onset"] = float(len(st) - on)
    return out


def macro_f1(t, p):
    f = []
    for c in (0, 1):
        tp = ((p == c) & (t == c)).sum(); fp = ((p == c) & (t != c)).sum(); fn = ((p != c) & (t == c)).sum()
        f.append(0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn))
    return float(np.mean(f))


def apply(x, direc, thr, fallback):
    if np.isnan(x):
        return fallback
    return int(x > thr) if direc > 0 else int(x <= thr)


def select(df, head, names, fallback):
    best = None
    for f in names:
        x = df[f].values.astype(float)
        ok = ~np.isnan(x)
        if ok.sum() < 20:
            continue
        thrs = sorted(set([0.0] + list(np.nanquantile(x, np.linspace(0.1, 0.9, 17)))))
        for direc in (1, -1):
            for thr in thrs:
                p = np.array([apply(v, direc, thr, fallback) for v in x])
                s = macro_f1(df.y.values, p)
                if best is None or s > best[0]:
                    best = (s, f, direc, float(thr))
    return best


def gate(df, pred, n_boot=2000):
    t = df.y.values
    vids = df.video_id.values
    uv = np.unique(vids)
    idx = {v: np.where(vids == v)[0] for v in uv}
    f1 = macro_f1(t, pred)
    floor = max(macro_f1(t, np.full_like(t, c)) for c in (0, 1))
    rng = np.random.default_rng(0)
    bs = []
    for _ in range(n_boot):
        ii = np.concatenate([idx[v] for v in rng.choice(uv, len(uv))])
        bs.append(macro_f1(t[ii], pred[ii]))
    lo, hi = np.percentile(bs, [2.5, 97.5])
    # video-level permutation: each video's windows get the label of another video
    vy = {v: t[idx[v][0]] for v in uv}
    prng = np.random.default_rng(0)
    perm = []
    for _ in range(n_boot):
        sh = dict(zip(uv, prng.permutation([vy[v] for v in uv])))
        perm.append(macro_f1(np.array([sh[v] for v in vids]), pred))
    perm_p = float((1 + (np.array(perm) >= f1).sum()) / (1 + n_boot))
    share = float(max((pred == 0).mean(), (pred == 1).mean()))
    verdict = ("collapsed" if share > 0.9 else "not_above_constant" if lo <= floor
               else "not_above_chance" if perm_p >= 0.05 else "candidate")
    return {"n_windows": int(len(t)), "n_videos": int(len(uv)), "macro_f1": round(f1, 4),
            "ci95": [round(float(lo), 4), round(float(hi), 4)], "constant_floor": round(floor, 4),
            "pred_share_max": round(share, 4), "perm_p": round(perm_p, 4),
            "perm_null_q95": round(float(np.percentile(perm, 95)), 4), "accuracy": round(float((t == pred).mean()), 4),
            "verdict": verdict}


def main():
    wp, fg, merged, out = sys.argv[1], sys.argv[2], sys.argv[3], Path(sys.argv[4])
    out.mkdir(parents=True, exist_ok=True)
    w = pd.read_csv(wp, dtype={"video_id": str})
    lab = pd.read_csv(merged, dtype={"video_id": str}).set_index("video_id")
    G = np.load(fg)
    rows = []
    for r in w.itertuples():
        d = decompose(G[f"{r.video_id}_{r.win}"])
        base = {"video_id": r.video_id, "win": r.win, "group": r.group, "label_source": lab.loc[r.video_id, "label_source"],
                "pred_pair": r.pred_pair, "gt": r.gt_collision}
        for anchor, c in (("pred", int(r.pred_pair)), ("gt", int(r.gt_collision))):
            rows.append({**base, "anchor": anchor, **feats(d, c)})
    F = pd.DataFrame(rows)
    F.to_csv(out / "features.csv", index=False)
    heads = {
        "side": ("side_valid", lambda v: int(v == "LEFT"), [c for c in F if c.startswith(("obj_u", "centroid", "diff_lr"))]),
        "evasion": ("evasion_valid", lambda v: int(float(v)),
                    [c for c in F if c.startswith(("pre_div", "pre_mag", "obj_e", "post_", "onset"))]),
    }
    report = {"design": __doc__.split("Usage")[0].strip(), "heads": {}}
    preds = []
    for head, (vcol, enc, names) in heads.items():
        valid = lab.index[lab[vcol] == 1]
        col = "entry_side" if head == "side" else "evasion_space"
        H = {}
        for anchor in ("pred", "gt"):
            D = F[(F.anchor == anchor) & F.video_id.isin(valid)].copy()
            D["y"] = [enc(lab.loc[v, col]) for v in D.video_id]
            fit, held = D[D.group == "FIT"], D[D.group == "HELD"]
            fb = int(fit.y.mean() >= 0.5)
            s, f, direc, thr = select(fit, head, names, fb)
            res = {"rule": {"feature": f, "direction": direc, "threshold": thr, "fallback_class": fb, "fit_macro_f1": round(s, 4)},
                   "counts": {g: {"windows": int(len(x)), "videos": int(x.video_id.nunique()),
                                  "label_source": dict(Counter(x.drop_duplicates("video_id").label_source)),
                                  "class1_videos": int(x.drop_duplicates("video_id").y.sum())}
                              for g, x in (("FIT", fit), ("HELD", held))}}
            for g, x in (("FIT", fit), ("HELD", held)):
                p = np.array([apply(v, direc, thr, fb) for v in x[f].values.astype(float)])
                res[g] = gate(x, p)
                res[g]["nan_fallback_windows"] = int(np.isnan(x[f].values.astype(float)).sum())
                if g == "HELD":
                    hu = (x.label_source == "human").values
                    res["HELD_human"] = {"n_windows": int(hu.sum()), "n_videos": int(x[hu].video_id.nunique()),
                                         "macro_f1": round(macro_f1(x.y.values[hu], p[hu]), 4) if hu.any() else None,
                                         "accuracy": round(float((x.y.values[hu] == p[hu]).mean()), 4) if hu.any() else None}
                    w0 = (x.win == 0).values
                    res["HELD_win0"] = gate(x[w0], p[w0], 2000)
                    # sign-only (thr 0, no fitted threshold) for the chosen feature family, as a robustness check
                    for name in names:
                        xv = x[name].values.astype(float)
                        fv = fit[name].values.astype(float)
                        dsign = 1 if macro_f1(fit.y.values, np.array([apply(v, 1, 0.0, fb) for v in fv])) >= \
                            macro_f1(fit.y.values, np.array([apply(v, -1, 0.0, fb) for v in fv])) else -1
                        res.setdefault("HELD_all_features_thr0_fitsign", {})[name] = round(
                            macro_f1(x.y.values, np.array([apply(v, dsign, 0.0, fb) for v in xv])), 4)
                    if anchor == "pred":
                        for (i, rr), pp in zip(x.iterrows(), p):
                            preds.append({"head": head, "video_id": rr.video_id, "win": rr.win, "group": g,
                                          "label_source": rr.label_source, "y_true": int(rr.y), "pred": int(pp),
                                          "feature": f, "value": rr[f]})
            H[anchor] = res
        report["heads"][head] = H
    (out / "report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    pd.DataFrame(preds).to_csv(out / "held_predictions.csv", index=False)
    for head, H in report["heads"].items():
        for anchor, res in H.items():
            print(head, anchor, json.dumps(res["rule"]), "FIT", res["FIT"]["macro_f1"], "HELD", json.dumps(res["HELD"]),
                  "human", json.dumps(res["HELD_human"]))


if __name__ == "__main__":
    main()
