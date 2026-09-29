"""S3 gate 7 (ACC-vs-DEC) ruling per decision df308177: row AUROC + episode AUROC with bootstrap CI and perm p.

Rule: episode CI95 contains 0.5 -> 'hold' (판정 보류, not a blocker);
      else pass iff episode AUROC > baseline (e005 0.2639) and > 0.5; otherwise fail.
Hard gate only once each class has >= --hard-min episodes (comma expansion).
usage: s3_gate7.py --probs <val_probs.csv> [--probs-reversed <csv>] --out <dir> [--baseline 0.2639]
       s3_gate7.py --selftest --out <dir>
Probs CSV columns: source_id, sample_index, p_ACCELERATING, p_DECELERATING (other p_* optional).
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
from s3_e005_lagcorr import episode_table, episode_stats  # noqa: E402
from s3_stopped_gate import auroc  # noqa: E402

E005_BASELINE = 0.2639


def row_auroc(probs_csv):
    aux = load_all(AUX)
    p = pd.read_csv(probs_csv)
    dup = int(p.duplicated(["source_id", "sample_index"]).sum())
    m = p.merge(aux[["source_id", "sample_index", "gt_accel"]], on=["source_id", "sample_index"], how="left")
    unmatched = int(m["gt_accel"].isna().sum())
    d = m[m["gt_accel"].isin([ACC, DEC])]
    y = (d["gt_accel"] == ACC).to_numpy()
    s = (d["p_ACCELERATING"] - d["p_DECELERATING"]).to_numpy(float)
    return {"rows": int(len(p)), "duplicates": dup, "unmatched_rows": unmatched,
            "n_acc_rows": int(y.sum()), "n_dec_rows": int((~y).sum()), "row_auroc": auroc(y, s),
            "row_auroc_per_source": {src: auroc((g["gt_accel"] == ACC).to_numpy(),
                                                (g["p_ACCELERATING"] - g["p_DECELERATING"]).to_numpy(float))
                                     for src, g in d.groupby("source_id")}}


def rule(st, baseline, hard_min):
    lo, hi = st["boot_ci95"]
    a = st["episode_auroc"]
    hard = min(st["n_ep_acc"], st["n_ep_dec"]) >= hard_min
    if a is None:
        v = "undefined"
    elif lo <= 0.5 <= hi:
        v = "hold"
    elif a > 0.5 and a > baseline:
        v = "pass"
    else:
        v = "fail"
    return {"verdict": v, "hard_gate_active": hard, "blocking": bool(hard and v == "fail"),
            "baseline_episode_auroc": baseline, "hard_min_episodes_per_class": hard_min}


def evaluate(probs_csv, baseline, hard_min, n_boot):
    ep = episode_table(probs_csv)
    st = episode_stats(ep, n_boot=n_boot, seed=0)
    per_src = {s: {"n_acc": int((g["label"] == ACC).sum()), "n_dec": int((g["label"] == DEC).sum()),
                   "episode_auroc": auroc((g["label"] == ACC).to_numpy(), g["score_mean"].to_numpy())}
               for s, g in ep.groupby("source_id")}
    return {"row": row_auroc(probs_csv), "episode": st, "episode_per_source": per_src,
            "ruling": rule(st, baseline, hard_min)}, ep


def selftest(out):
    aux = load_all(AUX)
    val_src = sorted(aux.loc[aux["split"] == "validation", "source_id"].unique()) if "split" in aux else []
    v = aux[aux["source_id"].isin(val_src)][["source_id", "sample_index", "gt_accel"]].copy()
    res = {}
    for name, sgn in [("oracle", 1.0), ("inverted", -1.0), ("random", 0.0)]:
        rng = np.random.default_rng(1)
        base = np.where(v["gt_accel"] == ACC, 1.0, np.where(v["gt_accel"] == DEC, -1.0, 0.0)) * sgn
        z = base * 0.3 + rng.normal(0, 0.05 if sgn else 0.3, len(v))
        df = v[["source_id", "sample_index"]].copy()
        df["p_ACCELERATING"] = 0.5 + z / 2
        df["p_DECELERATING"] = 0.5 - z / 2
        f = out / f"selftest_{name}.csv"
        df.to_csv(f, index=False)
        r, _ = evaluate(f, E005_BASELINE, 40, 1000)
        res[name] = {"episode_auroc": r["episode"]["episode_auroc"], "ci": r["episode"]["boot_ci95"],
                     "verdict": r["ruling"]["verdict"]}
    ok = (res["oracle"]["verdict"] == "pass" and res["inverted"]["verdict"] == "fail"
          and res["random"]["verdict"] in ("hold", "pass", "fail"))
    res["selftest"] = "PASS" if ok else "FAIL"
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probs", type=Path)
    ap.add_argument("--probs-reversed", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--baseline", type=float, default=E005_BASELINE)
    ap.add_argument("--hard-min", type=int, default=40)
    ap.add_argument("--n-boot", type=int, default=5000)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    if a.selftest:
        rep = selftest(a.out)
    else:
        rep, ep = evaluate(a.probs, a.baseline, a.hard_min, a.n_boot)
        ep.to_csv(a.out / "episodes.csv", index=False)
        if a.probs_reversed:
            rr, _ = evaluate(a.probs_reversed, a.baseline, a.hard_min, a.n_boot)
            rep["reversed"] = {"row_auroc": rr["row"]["row_auroc"], "episode": rr["episode"]}
    (a.out / "gate7.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(rep, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
