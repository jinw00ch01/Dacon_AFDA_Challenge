"""Reference only: div_far_lr30 (r3 selected, train-fixed thresholds) on the 5 public S3 examples' official labels.

20 Hz decode -> gray[::2] = 10 Hz rows (Pro qa 23a9759a), flow via s3_motion_features.step_features (same
definition as inference _s3_motion_series). Labeled rows are sample_index 0,60,...,540 (10 per video).
usage: s3_motion_accel_open.py <accel_rule_report.json> <out.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s3_motion_features import step_features  # noqa: E402
from s3_motion_gate_r3 import derive  # noqa: E402
from s3_stopped_gate import auroc  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def main():
    thr = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["thresholds_train"]
    lab = pd.read_csv(ROOT / "work/s3_stopped_flow_r3/open_examples.csv")
    rows = []
    for vid, g in lab.groupby("ID"):
        cap = cv2.VideoCapture(str(ROOT / f"Baseline/data/stage3/videos/{vid}.mp4"))
        gray = []
        while True:
            ok, bgr = cap.read()
            if not ok:
                break
            gray.append(cv2.resize(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), (160, 120), interpolation=cv2.INTER_AREA))
        cap.release()
        gray = np.stack(gray)[::2]
        fs = [step_features(gray[k - 1], gray[k]) for k in range(1, len(gray))]
        s = pd.DataFrame([fs[0]] + fs)
        s["yaw_far"] = s.get("yaw_far", 0.0)
        der = derive(s)
        for _, t in g.iterrows():
            k = min(int(t.sample_index), len(der) - 1)
            x = float(der["div_far_lr30"].iloc[k])
            pred = "DECELERATING" if x < thr["t_dec"] else ("ACCELERATING" if x > thr["t_acc"] else "CONSTANT")
            rows.append({"ID": vid, "sample_index": int(t.sample_index), "accel": t.accel, "div_far_lr30": x,
                         "rule3": "STOPPED" if bool(t.rule_stop) else pred})
    r = pd.DataFrame(rows)
    ad = r[r.accel.isin(["ACCELERATING", "DECELERATING"])]
    rep = {"n_rows": len(r), "acc_dec_rows": int(len(ad)),
           "acc_vs_dec_row_auroc": auroc((ad.accel == "ACCELERATING").to_numpy(), ad.div_far_lr30.to_numpy()),
           "confusion": pd.crosstab(r.accel, r.rule3).to_dict()}
    r.to_csv(Path(sys.argv[2]).with_suffix(".csv"), index=False)
    Path(sys.argv[2]).write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    print(json.dumps(rep, indent=1, default=str))


if __name__ == "__main__":
    main()
