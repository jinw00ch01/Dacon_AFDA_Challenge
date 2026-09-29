"""Ultra request (decision 1a07c3d2): check the sign of the image yaw proxy against comma steering.

Physics: when the car turns LEFT the far scene moves RIGHT on screen (median horizontal flow u > 0).
Under stage3_labels.POSITIVE_STEER_IS_LEFT=True, positive centred steering should give positive yaw_far.
Reports Spearman correlation of yaw_far / yaw_all with steering and speed*steering (per split, per source),
and AUROC of yaw proxies for LEFT vs RIGHT steer labels (default rule v1b), excluding STOPPED rows.
Usage: s3_yaw_sign.py <features.csv> <out.json>
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from afda.stage3_labels import POSITIVE_STEER_IS_LEFT, add_labels  # noqa: E402


def spearman(a, b):
    ra, rb = pd.Series(a).rank().values, pd.Series(b).rank().values
    return float(np.corrcoef(ra, rb)[0, 1])


def auroc(pos, neg):
    x = np.r_[pos, neg]
    r = pd.Series(x).rank().values
    n1, n0 = len(pos), len(neg)
    return float((r[:n1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)) if n1 and n0 else None


def main():
    df = pd.read_csv(sys.argv[1])
    df = add_labels(df)
    mov = df[(df.accel_label != "STOPPED") & (df.speed_mps > 2.0)].copy()
    mov["steer_c"] = mov.steering_angle_deg + 0.3
    mov["vsteer"] = mov.speed_mps * mov.steer_c
    rep = {"positive_steer_is_left": POSITIVE_STEER_IS_LEFT, "n_moving_rows": len(mov)}
    for sp in ("train", "validation", "test", "all"):
        s = mov if sp == "all" else mov[mov.split == sp]
        if s.empty:
            continue
        r = {"n": len(s)}
        for f in ("yaw_far", "yaw_all"):
            r[f + "_vs_steer"] = round(spearman(s[f], s.steer_c), 4)
            r[f + "_vs_speed_x_steer"] = round(spearman(s[f], s.vsteer), 4)
            r[f + "_auroc_LEFT_vs_RIGHT"] = auroc(s[f][s.steer_label == "LEFT"].values, s[f][s.steer_label == "RIGHT"].values)
        r["steer_counts"] = s.steer_label.value_counts().to_dict()
        rep[sp] = r
    per = {}
    for sid, s in mov.groupby("source_id"):
        if s.steer_c.abs().max() < 4.5:
            continue
        per[sid] = {"split": s.split.iloc[0], "n": len(s), "yaw_far_vs_speed_x_steer": round(spearman(s.yaw_far, s.vsteer), 3)}
    rep["per_source"] = per
    rep["n_sources_positive"] = sum(1 for v in per.values() if v["yaw_far_vs_speed_x_steer"] > 0)
    rep["n_sources"] = len(per)
    Path(sys.argv[2]).write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
