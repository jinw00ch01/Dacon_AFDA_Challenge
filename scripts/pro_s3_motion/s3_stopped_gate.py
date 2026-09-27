"""S3 e004 gate check (decision 4fb9418c): binary STOPPED head on top of a base accel predictor.

Input: val_predictions.csv from scripts/train_stage3.py (source_id, sample_index, accel_pred, steer_pred,
accel_true, steer_true, [speed_pred], [stopped_prob], [accel_pred_raw]). Optional --base: the same-config run
without predict_stopped (for the gate's "> base official_s3").

Independent of Ultra metrics: GT = v1b labels recomputed from the aux CSV (SRC014 excluded), scored with
work/pro_tools/official_metrics.py (0.7*accel Macro-F1 + 0.3*steer Macro-F1 excluding GT STOPPED rows).

Reports: integrity (1:1 join, GT agreement), official S3 / accel / steer / per-class F1, STOPPED F1,
n steer classes, the e004 gate, and — when the raw (pre-override) accel is recoverable (accel_pred_raw column,
or speed_pred re-derived with the v1b rule) — AUROC/AP of stopped_prob and a leave-one-source-out sweep of
the override threshold (and per-source temporal smoothing of stopped_prob).

usage: s3_stopped_gate.py --pred val_predictions.csv [--base base_val_predictions.csv] [--out dir]
       s3_stopped_gate.py --selftest [--out dir]
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

THR = [round(x, 2) for x in np.arange(0.05, 0.951, 0.05)]
SMOOTH = [1, 3, 5, 9]
ST = "STOPPED"


def load_val(aux_path):
    aux = pd.read_csv(aux_path, encoding="utf-8-sig")
    aux = aux[aux["source_id"] != "SRC014"].sort_values(["source_id", "sample_index"]).reset_index(drop=True)
    lab = stage3_labels.add_labels(aux)
    aux["gt_accel"] = lab["accel_label"].to_numpy()
    aux["gt_steer"] = lab["steer_label"].to_numpy()
    return aux[aux["split"] == "validation"][["source_id", "sample_index", "gt_accel", "gt_steer"]].reset_index(drop=True)


def f1_bin(gt, pred, c=ST):
    return macro_f1([g == c for g in gt], [p == c for p in pred], [True])


def auroc(y, s):
    y, s = np.asarray(y, bool), np.asarray(s, float)
    if y.all() or (~y).all():
        return None
    r = pd.Series(s).rank().to_numpy()
    return float((r[y].sum() - y.sum() * (y.sum() + 1) / 2) / (y.sum() * (~y).sum()))


def avg_precision(y, s):
    y = np.asarray(y, bool)
    o = np.argsort(-np.asarray(s, float), kind="stable")
    tp = np.cumsum(y[o])
    prec = tp / np.arange(1, len(y) + 1)
    return float((prec * y[o]).sum() / max(y.sum(), 1))


def scores(df, accel_col):
    a = df[accel_col].tolist()
    s = s3_score(df["gt_accel"].tolist(), a, df["gt_steer"].tolist(), df["steer_pred"].tolist())
    per = {c: f1_bin(df["gt_accel"].tolist(), a, c) for c in stage3_labels.ACCEL_CLASSES}
    nst = df.loc[df["gt_accel"] != ST, "steer_pred"].nunique()
    return {**s, "accel_per_class": per, "stopped_f1": per[ST], "n_pred_stopped": int(sum(x == ST for x in a)),
            "n_steer_classes_pred": int(nst)} if isinstance(s, dict) else s


def attach(val, pred_path):
    pred = pd.read_csv(pred_path, encoding="utf-8-sig")
    rep = {"rows_pred": int(len(pred)), "dup_keys": int(pred.duplicated(["source_id", "sample_index"]).sum())}
    df = val.merge(pred, on=["source_id", "sample_index"], how="left", validate="one_to_one", indicator=True)
    rep["missing"] = int((df["_merge"] != "both").sum())
    rep["extra"] = int(len(pred) - (df["_merge"] == "both").sum())
    if "accel_true" in df:
        rep["gt_accel_agree"] = float((df["accel_true"] == df["gt_accel"]).mean())
        rep["gt_steer_agree"] = float((df["steer_true"] == df["gt_steer"]).mean())
    rep["integrity_pass"] = rep["dup_keys"] == 0 and rep["missing"] == 0 and rep["extra"] == 0 and \
        rep.get("gt_accel_agree", 1.0) == 1.0 and rep.get("gt_steer_agree", 1.0) == 1.0
    return df.drop(columns="_merge"), rep


def raw_accel(df):
    if "accel_pred_raw" in df:
        return df["accel_pred_raw"], "accel_pred_raw column"
    if "speed_pred" in df:
        return stage3_labels.derive_accel_column(df, "speed_pred"), "re-derived from speed_pred (v1b rule)"
    return None, "unavailable (argmax base, no accel_pred_raw) - threshold sweep skipped"


def smooth_prob(df, w):
    if w == 1:
        return df["stopped_prob"].to_numpy(float)
    out = np.empty(len(df))
    for _, idx in df.groupby("source_id", sort=False).indices.items():
        g = df.iloc[idx].sort_values("sample_index")
        out[g.index] = g["stopped_prob"].rolling(w, center=True, min_periods=1).mean().to_numpy()
    return out


def sweep(df, raw):
    gt = df["gt_accel"].tolist()
    y = [g == ST for g in gt]
    rep = {"auroc": auroc(y, df["stopped_prob"]), "avg_precision": avg_precision(y, df["stopped_prob"]),
           "prevalence": float(np.mean(y))}
    raw = np.asarray(raw, dtype=object)
    probs = {w: smooth_prob(df, w) for w in SMOOTH}
    pred = {(w, t): np.where(probs[w] >= t, ST, raw) for w in SMOOTH for t in THR}
    rep["raw_no_override"] = scores(df.assign(_a=raw), "_a")
    rep["pooled"] = [{"smooth": w, "thr": t, "accel_f1": macro_f1(gt, list(pred[(w, t)])),
                      "stopped_f1": f1_bin(gt, list(pred[(w, t)])), "n_pred_stopped": int((pred[(w, t)] == ST).sum())}
                     for w in SMOOTH for t in THR]
    srcs = sorted(df["source_id"].unique())
    cv = np.empty(len(df), dtype=object)
    loso = []
    for held in srcs:
        tr = (df["source_id"] != held).to_numpy()
        gtr = [g for g, m in zip(gt, tr) if m]
        best = max(pred, key=lambda k: (macro_f1(gtr, list(pred[k][tr])), -abs(k[1] - 0.5), -k[0]))
        cv[~tr] = pred[best][~tr]
        gte = [g for g, m in zip(gt, ~tr) if m]
        loso.append({"held_out": held, "smooth": best[0], "thr": best[1], "n": int((~tr).sum()),
                     "n_true_stopped": int(sum(g == ST for g in gte)),
                     "accel_f1_held": macro_f1(gte, list(pred[best][~tr])),
                     "accel_f1_held_default": macro_f1(gte, list(pred[(1, 0.5)][~tr]))})
    rep["loso"] = loso
    d = scores(df.assign(_a=pred[(1, 0.5)]), "_a")
    c = scores(df.assign(_a=cv), "_a")
    rep["default_smooth1_thr0.5"] = d
    rep["loso_stitched"] = c
    rep["loso_delta_official_vs_default"] = c["S3"] - d["S3"] if "S3" in c else None
    return rep


CEILING = 0.4330  # oracle STOPPED override on e001 base (work/s3_stopped_ceiling_e001)
STOP_SOURCES = {"SRC017", "SRC020"}


def refined_gate(df, a, b, bdf):
    """Ultra decision 844c6074: precision/recall/margin/no-spurious-source/ceiling position + base preservation."""
    gt = (df["gt_accel"] == ST).to_numpy()
    pr = (df["accel_pred"] == ST).to_numpy()
    tp, fp = int((gt & pr).sum()), int((~gt & pr).sum())
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / int(gt.sum()) if gt.sum() else None
    per_src = {}
    for s, g in df.assign(_g=gt, _p=pr).groupby("source_id"):
        if g["_p"].any() or g["_g"].any():
            per_src[s] = {"n_true_stopped": int(g["_g"].sum()), "n_fired": int(g["_p"].sum()),
                          "fp": int((g["_p"] & ~g["_g"]).sum())}
    spurious = {s: v for s, v in per_src.items() if s not in STOP_SOURCES and v["n_fired"] > 0}
    r = {"tp": tp, "fp": fp, "stopped_precision": prec, "stopped_recall": rec, "per_source": per_src,
         "spurious_sources": spurious, "ceiling": CEILING, "ceiling_position": a["S3"] / CEILING}
    r["checks"] = {"necessary_official_gt_base_and_steer": (a["S3"] > b["S3"] and a["n_steer_classes_pred"] > 1) if b else None,
                   "precision_ge_0.80": prec is not None and prec >= 0.80,
                   "recall_ge_0.50": rec is not None and rec >= 0.50,
                   "margin_ge_base_plus_0.05": (a["S3"] >= b["S3"] + 0.05) if b else None,
                   "no_spurious_source": not spurious,
                   "official_ge_0.35": a["S3"] >= 0.35}
    # accel_pred_raw must equal the base argmax on every row; non-STOPPED rows of accel_pred must equal base too
    if bdf is not None:
        m = df[["source_id", "sample_index", "accel_pred", "steer_pred"] + (["accel_pred_raw"] if "accel_pred_raw" in df else [])].merge(
            bdf[["source_id", "sample_index", "accel_pred", "steer_pred"]], on=["source_id", "sample_index"], suffixes=("", "_base"))
        keep = m["accel_pred"] != ST
        r["base_preservation"] = {
            "non_stopped_accel_equal": float((m.loc[keep, "accel_pred"] == m.loc[keep, "accel_pred_base"]).mean()),
            "steer_equal": float((m["steer_pred"] == m["steer_pred_base"]).mean()),
            "raw_equal_base": float((m["accel_pred_raw"] == m["accel_pred_base"]).mean()) if "accel_pred_raw" in m else None}
        bp = r["base_preservation"]
        r["checks"]["base_preserved"] = bp["non_stopped_accel_equal"] == 1.0 and bp["steer_equal"] == 1.0 and \
            bp["raw_equal_base"] in (None, 1.0)
    r["pass"] = all(v for v in r["checks"].values() if v is not None) and b is not None
    return r


def run(pred_path, base_path, val, out_dir):
    rep = {"pred": str(pred_path), "base": str(base_path) if base_path else None}
    df, rep["integrity"] = attach(val, pred_path)
    if rep["integrity"]["missing"]:
        df = df.dropna(subset=["accel_pred"])
    rep["as_submitted"] = scores(df, "accel_pred")
    rep["n_true_stopped"] = int((df["gt_accel"] == ST).sum())
    if base_path:
        bdf, rep["base_integrity"] = attach(val, base_path)
        rep["base"] = scores(bdf.dropna(subset=["accel_pred"]), "accel_pred")
    if "stopped_prob" in df:
        raw, how = raw_accel(df)
        rep["raw_source"] = how
        if raw is not None:
            chk = np.where(df["stopped_prob"].to_numpy(float) >= 0.5, ST, np.asarray(raw, dtype=object))
            rep["override_reproduces_accel_pred"] = float((chk == df["accel_pred"].to_numpy()).mean())
            rep["threshold"] = sweep(df, raw)
    a = rep["as_submitted"]
    b = rep.get("base")
    rep["gate"] = {"official_gt_base": (a["S3"] > b["S3"]) if b else None, "stopped_f1_gt_0": a["stopped_f1"] > 0,
                   "steer_not_collapsed": a["n_steer_classes_pred"] >= 2}
    rep["gate"]["pass"] = all(v for v in rep["gate"].values() if v is not None) and b is not None
    rep["refined_gate"] = refined_gate(df, a, b, bdf if base_path else None)
    rep["gate"]["refined_pass"] = rep["refined_gate"]["pass"]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False, default=float), encoding="utf-8")
    show = {k: rep.get(k) for k in ("integrity", "as_submitted", "base", "gate", "refined_gate", "raw_source",
                                    "override_reproduces_accel_pred")}
    if "threshold" in rep:
        t = rep["threshold"]
        show["threshold"] = {k: t[k] for k in ("auroc", "avg_precision", "prevalence", "loso", "loso_delta_official_vs_default")}
        show["threshold"]["loso_stitched_s3"] = t["loso_stitched"]["S3"]
    print(json.dumps(show, indent=1, default=float))
    return rep


def selftest(val, out):
    """Synthetic e002-like base (speed shrunk to mean -> no STOPPED) + a noisy STOPPED head."""
    aux = pd.read_csv(ROOT / "data/derived/comma_subset_v1/s3_auxiliary_10hz.csv", encoding="utf-8-sig")
    v = val.merge(aux[["source_id", "sample_index", "speed_mps"]], on=["source_id", "sample_index"])
    rng = np.random.default_rng(0)
    df = v[["source_id", "sample_index"]].copy()
    df["split"] = "validation"
    df["accel_true"], df["steer_true"] = v["gt_accel"], v["gt_steer"]
    df["speed_pred"] = 0.85 * v["speed_mps"] + 0.15 * 25.5 + rng.normal(0, 0.3, len(v))
    raw = stage3_labels.derive_accel_column(df, "speed_pred")
    steer = np.where(rng.random(len(v)) < 0.6, v["gt_steer"], "STRAIGHT")
    df["steer_pred"] = steer
    stop = (v["gt_accel"] == ST).to_numpy()
    # calibrated-too-low head: stops score ~0.35, moving ~0.1 -> default 0.5 misses most, LOSO should lower thr
    df["stopped_prob"] = np.clip(np.where(stop, 0.38, 0.08) + rng.normal(0, 0.08, len(v)), 0, 1)
    df["accel_pred"] = np.where(df["stopped_prob"] >= 0.5, ST, raw)
    base = df.drop(columns="stopped_prob").assign(accel_pred=raw)
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "sim_pred.csv", index=False)
    base.to_csv(out / "sim_base.csv", index=False)
    rep = run(out / "sim_pred.csv", out / "sim_base.csv", val, out)
    t = rep["threshold"]
    ok = rep["integrity"]["integrity_pass"] and rep["override_reproduces_accel_pred"] == 1.0 and \
        t["auroc"] > 0.95 and t["loso_delta_official_vs_default"] > 0.05 and \
        np.median([r["thr"] for r in t["loso"]]) < 0.4
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", type=Path)
    ap.add_argument("--base", type=Path)
    ap.add_argument("--aux", type=Path, default=ROOT / "data/derived/comma_subset_v1/s3_auxiliary_10hz.csv")
    ap.add_argument("--out", type=Path, default=ROOT / "work/s3_stopped_gate")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    val = load_val(a.aux)
    if a.selftest:
        return selftest(val, a.out)
    run(a.pred, a.base, val, a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
