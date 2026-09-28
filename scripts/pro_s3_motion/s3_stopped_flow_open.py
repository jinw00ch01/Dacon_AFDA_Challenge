"""Reference only: conjunction STOPPED rule on the 5 public S3 examples (20 Hz decode -> gray[::2] = 10 Hz rows).
Usage: s3_stopped_flow_open.py <a_divfar_s15> <b_magall_s5> <out.json>"""
import json, sys
import cv2, numpy as np, pandas as pd
sys.path.insert(0, "work/pro_tools")
from s3_motion_features import step_features
a_thr, b_thr, out = float(sys.argv[1]), float(sys.argv[2]), sys.argv[3]


def sm(x, w):
    h = w // 2
    return np.array([x[max(0, i - h):i + h + 1].mean() for i in range(len(x))])


lab = pd.read_csv("Baseline/data/stage3/labels.csv"); rows = []
for vid, g in lab.groupby("ID"):
    cap = cv2.VideoCapture(f"Baseline/data/stage3/videos/{vid}.mp4"); gray = []
    while True:
        ok, bgr = cap.read()
        if not ok: break
        gray.append(cv2.resize(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), (160, 120), interpolation=cv2.INTER_AREA))
    cap.release(); gray = np.stack(gray)[::2]
    feats = [step_features(gray[k - 1], gray[k]) for k in range(1, len(gray))]
    df = [feats[0]] + feats
    dfar = sm(np.array([d["div_far"] for d in df]), 15); mag = sm(np.array([d["mag_all"] for d in df]), 5)
    for t in g.itertuples():
        k = min(int(t.sample_index), len(gray) - 1)
        rows.append({"ID": vid, "sample_index": int(t.sample_index), "accel": t.accel_label, "div_far_s15": float(dfar[k]),
                     "mag_all_s5": float(mag[k]), "rule_stop": bool(dfar[k] <= a_thr and mag[k] <= b_thr)})
d = pd.DataFrame(rows)
rep = {"n": len(d), "true_stopped": int((d.accel == "STOPPED").sum()), "rule_stop": int(d.rule_stop.sum()),
       "tp": int((d.rule_stop & (d.accel == "STOPPED")).sum()), "fp": int((d.rule_stop & (d.accel != "STOPPED")).sum()),
       "per_video": d.groupby("ID").apply(lambda x: {"true": int((x.accel == "STOPPED").sum()), "pred": int(x.rule_stop.sum())}).to_dict()}
d.to_csv(out.replace(".json", ".csv"), index=False)
open(out, "w").write(json.dumps(rep, indent=1)); print(json.dumps(rep, indent=1))
