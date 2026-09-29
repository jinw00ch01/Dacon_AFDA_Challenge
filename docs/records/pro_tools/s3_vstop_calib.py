"""STOPPED threshold calibration for a speed-regression S3 head (proposal in review ae25318b).

Input: val_predictions.csv with source_id, sample_index, speed_pred (m/s), steer_pred (accel_true optional).
GT = v1b labels recomputed from the aux CSV. ACC/DEC/CON use the v1b rule on predicted speed unchanged;
only the STOPPED speed threshold v_stop_pred is swept. Leave-one-source-out over val sources: pick the
threshold maximizing accel Macro-F1 on the other sources, score the held-out source; also pooled results.

usage: s3_vstop_calib.py --pred val_predictions.csv [--aux ...] [--out dir]
       s3_vstop_calib.py --selftest [--out dir]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from afda import stage3_labels  # noqa: E402
from official_metrics import macro_f1, s3_score  # noqa: E402

R = stage3_labels.DEFAULT_RULE
GRID = [round(x, 2) for x in np.arange(0.5, 5.01, 0.25)]


def derive(df, v_stop):
    """v1b rule on predicted speed per source, with only the STOPPED threshold replaced."""
    out = pd.Series(index=df.index, dtype=object)
    for _, g in df.groupby("source_id", sort=False):
        g = g.sort_values("sample_index")
        v = g["speed_pred"].to_numpy(dtype=float)
        a = np.gradient(v, 0.1) if len(v) >= 2 else np.zeros(len(v))
        sm = lambda x: pd.Series(x).rolling(int(R["window"]), center=True, min_periods=1).mean().to_numpy()
        out.loc[g.index] = [stage3_labels.classify_accel(s, ac, v_stop, R["a_db"]) for s, ac in zip(sm(v), sm(a))]
    return out


def per_class(gt, pred):
    return {c: macro_f1([g == c for g in gt], [p == c for p in pred], [True]) for c in stage3_labels.ACCEL_CLASSES}


def run(df, out_dir):
    rep = {"rows": int(len(df)), "sources": sorted(df["source_id"].unique().tolist()), "grid": GRID}
    preds = {t: derive(df, t) for t in GRID}
    gt = df["accel_true_v1b"].tolist()
    rep["pooled"] = []
    for t in GRID:
        p = preds[t].tolist()
        rep["pooled"].append({"v_stop_pred": t, "accel_f1": macro_f1(gt, p),
                              "stopped_f1": per_class(gt, p)["STOPPED"], "n_pred_stopped": int(sum(x == "STOPPED" for x in p))})
    base = next(r for r in rep["pooled"] if r["v_stop_pred"] == 0.5)
    rep["baseline_v_stop_0.5"] = base
    loso = []
    for held in rep["sources"]:
        tr = df["source_id"] != held
        best = max(GRID, key=lambda t: macro_f1(df.loc[tr, "accel_true_v1b"].tolist(), preds[t][tr].tolist()))
        te = ~tr
        g, p = df.loc[te, "accel_true_v1b"].tolist(), preds[best][te].tolist()
        p0 = preds[0.5][te].tolist()
        loso.append({"held_out": held, "chosen": best, "n": int(te.sum()), "n_true_stopped": int(sum(x == "STOPPED" for x in g)),
                     "accel_f1_held": macro_f1(g, p), "accel_f1_held_v0.5": macro_f1(g, p0),
                     "stopped_f1_held": per_class(g, p)["STOPPED"] if "STOPPED" in g else None})
    rep["loso"] = loso
    # held-out predictions stitched together -> one pooled cross-validated score
    cv = pd.Series(index=df.index, dtype=object)
    for r in loso:
        m = df["source_id"] == r["held_out"]
        cv[m] = preds[r["chosen"]][m]
    cvp = cv.tolist()
    rep["loso_stitched"] = {"accel_f1": macro_f1(gt, cvp), "per_class": per_class(gt, cvp),
                            "delta_vs_v0.5": macro_f1(gt, cvp) - base["accel_f1"]}
    rep["final_v_stop_pred_median"] = float(np.median([r["chosen"] for r in loso]))
    if "steer_pred" in df:
        s = s3_score(gt, cvp, df["steer_true_v1b"].tolist(), df["steer_pred"].tolist())
        s0 = s3_score(gt, preds[0.5].tolist(), df["steer_true_v1b"].tolist(), df["steer_pred"].tolist())
        rep["official_s3"] = {"v0.5": s0, "loso_stitched": s}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False, default=float), encoding="utf-8")
    print(json.dumps({k: rep[k] for k in ("baseline_v_stop_0.5", "loso", "loso_stitched", "final_v_stop_pred_median")},
                     indent=1, default=float))
    return rep


def load_val(aux_path):
    aux = pd.read_csv(aux_path, encoding="utf-8-sig")
    aux = aux[aux["source_id"] != "SRC014"].sort_values(["source_id", "sample_index"]).reset_index(drop=True)
    lab = stage3_labels.add_labels(aux)
    aux["accel_true_v1b"] = lab["accel_label"].to_numpy()
    aux["steer_true_v1b"] = lab["steer_label"].to_numpy()
    return aux[aux["split"] == "validation"].reset_index(drop=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", type=Path)
    ap.add_argument("--aux", type=Path, default=ROOT / "data/derived/comma_subset_v1/s3_auxiliary_10hz.csv")
    ap.add_argument("--out", type=Path, default=ROOT / "work/s3_vstop_calib")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    val = load_val(args.aux)
    if args.selftest:
        # shrink-to-mean regression error: pred = 0.85*v + 0.15*mean + AR noise -> stops sit near ~3.8 m/s
        rng = np.random.default_rng(0)
        df = val[["source_id", "sample_index", "accel_true_v1b", "steer_true_v1b"]].copy()
        e = np.zeros(len(val))
        for _, idx in val.groupby("source_id").indices.items():
            x = rng.normal(0, 0.3, len(idx))
            for i in range(1, len(idx)):
                x[i] = 0.95 * x[i - 1] + np.sqrt(1 - 0.95**2) * x[i]
            e[idx] = x
        df["speed_pred"] = 0.85 * val["speed_mps"] + 0.15 * 25.5 + e
        df["steer_pred"] = "STRAIGHT"
        rep = run(df, args.out)
        ok = rep["baseline_v_stop_0.5"]["n_pred_stopped"] == 0 and rep["loso_stitched"]["per_class"]["STOPPED"] > 0.5
        print("SELFTEST", "PASS" if ok else "FAIL")
        return 0 if ok else 1
    pred = pd.read_csv(args.pred, encoding="utf-8-sig")
    df = val.merge(pred[["source_id", "sample_index", "speed_pred"] + (["steer_pred"] if "steer_pred" in pred else [])],
                   on=["source_id", "sample_index"], how="left", validate="one_to_one")
    miss = int(df["speed_pred"].isna().sum())
    if miss:
        print(f"missing speed_pred rows: {miss}")
        return 2
    run(df, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
