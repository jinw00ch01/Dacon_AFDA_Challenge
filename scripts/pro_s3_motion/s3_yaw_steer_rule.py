"""S3 steering from the image yaw proxy alone (Pro, follow-up to decision 1a07c3d2 request).

pred = LEFT if smooth_w(yaw_far) > t_hi, RIGHT if < t_lo, else STRAIGHT. (w, t_lo, t_hi) chosen on TRAIN only
(grid, maximise steer Macro-F1 over rows whose GT accel is not STOPPED = official S3 steer scope).
Reported on validation / test / val+test with source-level bootstrap CI, per-source values, and the
official-score contribution 0.3 * steer Macro-F1. Labels: stage3_labels.add_labels default rule (v1b).
Usage: s3_yaw_steer_rule.py <features.csv> <out_dir>
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from afda.stage3_labels import add_labels  # noqa: E402

CL = ["LEFT", "STRAIGHT", "RIGHT"]


def mf1(y, p):
    fs = []
    for c in CL:
        tp = np.sum((y == c) & (p == c))
        fp = np.sum((y != c) & (p == c))
        fn = np.sum((y == c) & (p != c))
        if tp + fp + fn == 0:
            continue
        fs.append(2 * tp / (2 * tp + fp + fn))
    return float(np.mean(fs))


def predict(x, lo, hi):
    return np.where(x > hi, "LEFT", np.where(x < lo, "RIGHT", "STRAIGHT"))


def main():
    df = add_labels(pd.read_csv(sys.argv[1]))
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    df = df.sort_values(["source_id", "sample_index"])
    for w in (1, 3, 5, 7, 9):
        df[f"yf{w}"] = df.groupby("source_id").yaw_far.transform(lambda s: s.rolling(w, center=True, min_periods=1).mean())
    sc = df[df.accel_label != "STOPPED"]
    tr = sc[sc.split == "train"]
    best = None
    for w in (1, 3, 5, 7, 9):
        x = tr[f"yf{w}"].values
        qs = np.quantile(x, np.linspace(0.02, 0.98, 49))
        for lo in qs[qs < 0]:
            for hi in qs[qs > 0]:
                f = mf1(tr.steer_label.values, predict(x, lo, hi))
                if best is None or f > best[0]:
                    best = (f, w, float(lo), float(hi))
    f_tr, w, lo, hi = best
    df["pred_steer"] = predict(df[f"yf{w}"].values, lo, hi)
    sc = df[df.accel_label != "STOPPED"]
    rep = {"design": __doc__.split("Usage")[0].strip(),
           "chosen_on_train": {"smooth_w": w, "t_lo": lo, "t_hi": hi, "train_macro_f1": round(f_tr, 4)}}
    for sp, s in (("train", sc[sc.split == "train"]), ("validation", sc[sc.split == "validation"]),
                  ("test", sc[sc.split == "test"]), ("val_test", sc[sc.split.isin(["validation", "test"])])):
        y, p = s.steer_label.values, s.pred_steer.values
        srcs = s.source_id.unique()
        rng = np.random.RandomState(0)
        bs = []
        for _ in range(1000):
            pick = rng.choice(srcs, len(srcs))
            ss = pd.concat([s[s.source_id == k] for k in pick])
            bs.append(mf1(ss.steer_label.values, ss.pred_steer.values))
        cm = pd.crosstab(pd.Series(y, name="gt"), pd.Series(p, name="pred")).to_dict()
        rep[sp] = {"n_rows": len(s), "n_sources": len(srcs), "steer_macro_f1": round(mf1(y, p), 4),
                   "ci95_source_boot": [round(float(np.percentile(bs, 2.5)), 4), round(float(np.percentile(bs, 97.5)), 4)],
                   "official_contrib_0.3x": round(0.3 * mf1(y, p), 4),
                   "gt_counts": pd.Series(y).value_counts().to_dict(), "pred_counts": pd.Series(p).value_counts().to_dict(),
                   "confusion_pred_by_gt": cm,
                   "per_source": {k: round(mf1(s[s.source_id == k].steer_label.values, s[s.source_id == k].pred_steer.values), 3) for k in srcs}}
    df[["source_id", "sample_index", "split", "accel_label", "steer_label", f"yf{w}", "pred_steer"]].to_csv(out / "predictions.csv", index=False)
    (out / "report.json").write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in rep.items() if k != "design"}, indent=1, default=str))


if __name__ == "__main__":
    main()
