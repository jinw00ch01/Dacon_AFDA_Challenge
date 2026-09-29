"""Pro review of an Ultra S2 result: recompute metrics from val_predictions.csv,
check integrity against the agent label release, and compare with trivial
train-derived baselines (constant time-fraction prior, majority class).

usage: s2_review.py --pred <val_predictions.csv> --labels <merged.csv> --out <dir>
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def assign_splits(df, val_frac=0.2, seed=0):
    # verbatim copy of scripts/cache_s2_features.assign_splits (avoid torch import)
    rng = np.random.RandomState(seed)
    split = pd.Series("train", index=df.index)
    for _, idx in df.groupby(df["collision_valid"].astype(int)).groups.items():
        idx = list(idx)
        rng.shuffle(idx)
        n_val = max(1, round(len(idx) * val_frac)) if len(idx) >= 3 else 0
        for i in idx[:n_val]:
            split[i] = "validation"
    return split


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    lab = pd.read_csv(a.labels, dtype={"video_id": str}).reset_index(drop=True)
    lab["split"] = assign_splits(lab)
    pred = pd.read_csv(a.pred, dtype={"video_id": str})
    rep = {"pred_rows": len(pred), "label_rows": len(lab),
           "label_source_counts": lab["label_source"].value_counts().to_dict()}

    val_ids = set(lab.loc[lab.split == "validation", "video_id"])
    train = lab[lab.split == "train"]
    rep["n_val_expected"] = len(val_ids)
    rep["n_train"] = len(train)
    rep["n_train_with_target"] = int((train[["collision_valid", "entry_valid", "evasion_valid", "side_valid"]].sum(1) > 0).sum())
    rep["dup_pred_ids"] = int(pred.video_id.duplicated().sum())
    rep["missing_from_pred"] = sorted(val_ids - set(pred.video_id))
    rep["extra_in_pred"] = sorted(set(pred.video_id) - val_ids)
    rep["train_in_pred"] = sorted(set(pred.video_id) & set(train.video_id))

    m = pred.merge(lab, on="video_id", how="left", suffixes=("", "_lab"))
    issues = []
    for _, r in m.iterrows():
        if int(r["T"]) != int(r["decoded_frames"]):
            issues.append(f"{r.video_id}: T {r['T']} != decoded {r.decoded_frames}")
        for name, frame_col, valid in (("collision", "collision_frame", "collision_valid"),
                                       ("entry", "entry_frame", "entry_valid")):
            t = r[f"{name}_true_frame"]
            exp = r[frame_col] if int(r[valid]) == 1 else np.nan
            if not ((pd.isna(t) and pd.isna(exp)) or (not pd.isna(t) and not pd.isna(exp) and int(t) == int(exp))):
                issues.append(f"{r.video_id}: {name}_true {t} != label {exp}")
            p = int(r[f"{name}_pred_frame"])
            if not 0 <= p < int(r["T"]):
                issues.append(f"{r.video_id}: {name}_pred {p} out of [0,T)")
        ev_exp = int(r.evasion_space) if int(r.evasion_valid) == 1 else None
        ev_t = None if pd.isna(r.evasion_true) else int(r.evasion_true)
        if ev_exp != ev_t:
            issues.append(f"{r.video_id}: evasion_true {ev_t} != label {ev_exp}")
        sd_exp = r.entry_side if int(r.side_valid) == 1 else None
        sd_t = None if pd.isna(r.side_true) else r.side_true
        if sd_exp != sd_t:
            issues.append(f"{r.video_id}: side_true {sd_t} != label {sd_exp}")
    rep["label_mismatch"] = issues

    # recompute reported metrics
    met = {}
    for name in ("collision", "entry"):
        s = m[m[f"{name}_true_frame"].notna()]
        err = (s[f"{name}_pred_frame"] - s[f"{name}_true_frame"]).abs() / s["fps"]
        met[f"{name}_mae_s"] = float(err.mean())
        met[f"{name}_median_s"] = float(err.median())
        met[f"n_{name}"] = len(s)
        met[f"{name}_within_1s"] = int((err <= 1.0).sum())
    s = m[m.evasion_true.notna()]
    met["evasion_acc"] = float((s.evasion_pred == s.evasion_true).mean())
    met["n_evasion"] = len(s)
    met["evasion_true_counts"] = s.evasion_true.astype(int).value_counts().to_dict()
    s = m[m.side_true.notna()]
    met["side_acc"] = float((s.side_pred == s.side_true).mean())
    met["n_side"] = len(s)
    met["side_true_counts"] = s.side_true.value_counts().to_dict()
    met["time_mae_s"] = (met["collision_mae_s"] + met["entry_mae_s"]) / 2
    met["pred_side_counts_all_val"] = m.side_pred.value_counts().to_dict()
    rep["recomputed"] = met

    # trivial baselines from TRAIN labels only (no val leakage)
    base = {}
    for name, frame_col, valid in (("collision", "collision_frame", "collision_valid"),
                                   ("entry", "entry_frame", "entry_valid")):
        tr = train[train[valid] == 1]
        frac = float((tr[frame_col] / tr["decoded_frames"]).median())
        sec = float((tr[frame_col] / tr["fps"]).median())
        s = m[m[f"{name}_true_frame"].notna()]
        e_frac = ((np.round(frac * s["T"]) - s[f"{name}_true_frame"]).abs() / s["fps"])
        e_sec = ((np.round(sec * s["fps"]) - s[f"{name}_true_frame"]).abs() / s["fps"])
        base[name] = {"n_train": len(tr), "train_median_fraction": frac, "train_median_sec": sec,
                      "const_fraction_mae_s": float(e_frac.mean()), "const_fraction_median_s": float(e_frac.median()),
                      "const_sec_mae_s": float(e_sec.mean())}
    tr = train[train.evasion_valid == 1]
    maj_ev = int(tr.evasion_space.astype(int).mode()[0])
    s = m[m.evasion_true.notna()]
    base["evasion"] = {"train_counts": tr.evasion_space.astype(int).value_counts().to_dict(),
                       "majority": maj_ev, "majority_acc": float((s.evasion_true == maj_ev).mean())}
    tr = train[train.side_valid == 1]
    maj_sd = tr.entry_side.mode()[0]
    s = m[m.side_true.notna()]
    base["side"] = {"train_counts": tr.entry_side.value_counts().to_dict(),
                    "majority": maj_sd, "majority_acc": float((s.side_true == maj_sd).mean())}
    base["time_mae_s_const_fraction"] = (base["collision"]["const_fraction_mae_s"] + base["entry"]["const_fraction_mae_s"]) / 2
    rep["baselines_train_prior"] = base

    # all-label time-fraction distribution (descriptive, all splits)
    pos = lab[lab.collision_valid == 1]
    f = pos.collision_frame / pos.decoded_frames
    rep["collision_fraction_all"] = {"n": len(pos), "min": float(f.min()), "p10": float(f.quantile(.1)),
                                     "median": float(f.median()), "p90": float(f.quantile(.9)), "max": float(f.max())}

    rep["integrity_pass"] = not (rep["dup_pred_ids"] or rep["missing_from_pred"] or rep["extra_in_pred"]
                                 or rep["train_in_pred"] or issues)
    (out / "report.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(rep, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
