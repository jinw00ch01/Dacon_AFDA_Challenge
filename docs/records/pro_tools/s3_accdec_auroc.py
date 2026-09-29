"""S3 ACC-vs-DEC speed-shortcut diagnostic (decision c6903fd5: e006 mandatory diagnostic + gate 7).

Parts
  data   : per split (train/validation) ACC/DEC row counts by speed bin and the AUROC of raw speed for
           "ACC vs DEC" (label ACC=1). Opposite sides of 0.5 in train vs val = the speed context flips, so a model
           that learned speed as a proxy is pushed below 0.5 on val.
  weights: train-only speed-bin x class inverse-frequency weights that make ACC and DEC equally likely inside
           each speed bin (proposal for e006 balanced sampling; never fitted on val).
  pred   : (optional --pred with p_acc,p_dec) AUROC of (p_acc - p_dec) on GT ACC/DEC rows, overall, per source,
           and speed-stratified (rows compared only inside the same speed bin -> separation beyond speed).
           Verdict: separates_beyond_speed (both > 0.5) / speed_shortcut (overall <= 0.5, ~0.5 within bins) /
           fails_beyond_speed (<= 0.5 even within speed bins -> speed is not the cause).

usage: s3_accdec_auroc.py --out dir [--pred val_predictions.csv]
       s3_accdec_auroc.py --selftest --out dir
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s3_stopped_gate import ROOT, attach, auroc, load_val  # noqa: E402
from afda import stage3_labels  # noqa: E402

AUX = ROOT / "data/derived/comma_subset_v1/s3_auxiliary_10hz.csv"
ACC, DEC = "ACCELERATING", "DECELERATING"
BINS = [0, 5, 10, 15, 20, 25, 30, 100]  # m/s


def load_all(aux_path):
    aux = pd.read_csv(aux_path, encoding="utf-8-sig")
    aux = aux[aux["source_id"] != "SRC014"].sort_values(["source_id", "sample_index"]).reset_index(drop=True)
    lab = stage3_labels.add_labels(aux)
    aux["gt_accel"] = lab["accel_label"].to_numpy()
    aux["gt_steer"] = lab["steer_label"].to_numpy()
    aux["speed_bin"] = pd.cut(aux["speed_mps"], BINS, right=False).astype(str)
    return aux


def stratified_auroc(y, s, strata):
    """Pairs compared only within the same stratum (weighted by #pairs)."""
    num = den = 0.0
    for _, idx in pd.Series(strata).groupby(strata).indices.items():
        yy, ss = np.asarray(y)[idx], np.asarray(s)[idx]
        a = auroc(yy, ss)
        if a is None:
            continue
        w = yy.sum() * (~yy.astype(bool)).sum()
        num += a * w
        den += w
    return float(num / den) if den else None


def data_part(aux):
    out = {}
    for sp in ["train", "validation"]:
        d = aux[(aux["split"] == sp) & aux["gt_accel"].isin([ACC, DEC])]
        y = (d["gt_accel"] == ACC).to_numpy()
        tab = pd.crosstab(d["speed_bin"], d["gt_accel"])
        out[sp] = {"n_acc": int(y.sum()), "n_dec": int((~y).sum()),
                   "speed_median": {c: float(d.loc[d["gt_accel"] == c, "speed_mps"].median()) for c in [ACC, DEC]},
                   "speed_auroc_acc": auroc(y, d["speed_mps"].to_numpy()),
                   "bin_counts": {b: {c: int(tab.loc[b, c]) if c in tab else 0 for c in [ACC, DEC]} for b in tab.index},
                   "per_source_speed_auroc": {s: auroc((g["gt_accel"] == ACC).to_numpy(), g["speed_mps"].to_numpy())
                                              for s, g in d.groupby("source_id")}}
    return out


def weights_part(aux):
    tr = aux[aux["split"] == "train"]
    cnt = pd.crosstab(tr["speed_bin"], tr["gt_accel"])
    w = {}
    for b in cnt.index:
        na, nd = int(cnt.loc[b].get(ACC, 0)), int(cnt.loc[b].get(DEC, 0))
        if na and nd:
            m = (na + nd) / 2
            w[b] = {ACC: round(m / na, 3), DEC: round(m / nd, 3), "n_acc": na, "n_dec": nd}
        else:
            w[b] = {ACC: 1.0, DEC: 1.0, "n_acc": na, "n_dec": nd, "note": "one class missing in bin - left 1.0"}
    # effect check on train: speed AUROC after reweighting (weighted rank AUROC via bin-stratified = 0.5 by design)
    d = tr[tr["gt_accel"].isin([ACC, DEC])]
    y = (d["gt_accel"] == ACC).to_numpy()
    return {"bins_mps": BINS, "weights": w,
            "train_speed_auroc_within_bins": stratified_auroc(y, d["speed_mps"].to_numpy(), d["speed_bin"].to_numpy()),
            "note": "train-only; weights make ACC and DEC equal mass per speed bin, so speed alone carries no ACC/DEC "
                    "information between bins. Do not fit on validation."}


def pred_part(val_aux, pred_path):
    val = val_aux[["source_id", "sample_index", "gt_accel", "gt_steer"]]
    df, integ = attach(val, pred_path)
    miss = [c for c in ["p_acc", "p_dec"] if c not in df]
    if miss:
        return {"integrity": integ, "error": f"missing columns {miss}"}
    df = df.merge(val_aux[["source_id", "sample_index", "speed_mps", "speed_bin"]], on=["source_id", "sample_index"])
    d = df[df["gt_accel"].isin([ACC, DEC])]
    y = (d["gt_accel"] == ACC).to_numpy()
    s = (d["p_acc"] - d["p_dec"]).to_numpy(float)
    rep = {"integrity": integ, "n_acc": int(y.sum()), "n_dec": int((~y).sum()),
           "auroc_overall": auroc(y, s),
           "auroc_speed_stratified": stratified_auroc(y, s, d["speed_bin"].to_numpy()),
           "auroc_per_source": {src: auroc((g["gt_accel"] == ACC).to_numpy(), (g["p_acc"] - g["p_dec"]).to_numpy(float))
                                for src, g in d.groupby("source_id")},
           "corr_score_speed": float(np.corrcoef(s, d["speed_mps"])[0, 1]) if len(d) > 2 else None}
    ov, st = rep["auroc_overall"], rep["auroc_speed_stratified"]
    if ov is None or st is None:
        rep["verdict"] = "undefined"
    elif ov > 0.5 and st > 0.5:
        rep["verdict"] = "separates_beyond_speed"
    elif ov <= 0.5 and abs(st - 0.5) < abs(ov - 0.5) and st > 0.45:
        rep["verdict"] = "speed_shortcut"  # below 0.5 overall, ~0.5 once speed is held fixed
    else:
        rep["verdict"] = "fails_beyond_speed"  # <=0.5 even within speed bins: speed does not explain it
    return rep


def selftest(out):
    aux = load_all(AUX)
    va = aux[aux["split"] == "validation"].copy()
    rng = np.random.default_rng(0)
    res = {}
    cases = {
        "oracle": lambda g: np.where(g == ACC, 0.9, np.where(g == DEC, 0.05, 0.3)),
        "random": lambda g: rng.random(len(g)),
    }
    for name, fn in cases.items():
        p = va[["source_id", "sample_index"]].copy()
        p["p_acc"] = fn(va["gt_accel"].to_numpy())
        p["p_dec"] = 1 - p["p_acc"] if name == "random" else np.where(va["gt_accel"] == DEC, 0.9, 0.05)
        path = out / f"selftest_{name}.csv"
        p.to_csv(path, index=False)
        res[name] = pred_part(va, path)
    # speed shortcut: train says ACC at low speed -> p_acc = -speed
    p = va[["source_id", "sample_index"]].copy()
    p["p_acc"] = -va["speed_mps"].to_numpy()
    p["p_dec"] = 0.0
    path = out / "selftest_speed.csv"
    p.to_csv(path, index=False)
    res["speed_shortcut"] = pred_part(va, path)
    checks = {"oracle_1": res["oracle"]["auroc_overall"] == 1.0 and res["oracle"]["verdict"] == "separates_beyond_speed",
              "random_near_half": abs(res["random"]["auroc_overall"] - 0.5) < 0.06,
              "speed_stratified_near_half": abs(res["speed_shortcut"]["auroc_speed_stratified"] - 0.5) < 0.2,
              "speed_verdict": res["speed_shortcut"]["verdict"] == "speed_shortcut",
              "integrity": all(r["integrity"]["integrity_pass"] for r in res.values())}
    return {"results": {k: {kk: v[kk] for kk in ["auroc_overall", "auroc_speed_stratified", "verdict"]}
                        for k, v in res.items()}, "checks": checks, "pass": all(checks.values())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--pred", type=Path)
    ap.add_argument("--aux", type=Path, default=AUX)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    if a.selftest:
        rep = selftest(a.out)
    else:
        aux = load_all(a.aux)
        rep = {"data": data_part(aux), "weights": weights_part(aux)}
        if a.pred:
            rep["pred"] = pred_part(aux[aux["split"] == "validation"].reset_index(drop=True), a.pred)
    (a.out / "report.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps(rep, indent=1, ensure_ascii=False, default=str)[:6000])


if __name__ == "__main__":
    main()
