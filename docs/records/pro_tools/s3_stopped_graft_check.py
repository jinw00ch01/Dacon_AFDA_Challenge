"""Check main b1eaa28 inline STOPPED graft vs Pro open_examples.csv (reference, gray[::2] 10 Hz rows)."""
import json, sys, importlib.util
import cv2, numpy as np, pandas as pd
spec = importlib.util.spec_from_file_location("inf", "submission/inference.py"); inf = importlib.util.module_from_spec(spec); spec.loader.exec_module(inf)
ref = pd.read_csv("work/s3_stopped_flow_r3/open_examples.csv")
lab = pd.read_csv("Baseline/data/stage3/labels.csv"); out = []
for vid, g in lab.groupby("ID"):
    cap = cv2.VideoCapture(f"Baseline/data/stage3/videos/{vid}.mp4"); gray = []
    while True:
        ok, bgr = cap.read()
        if not ok: break
        gray.append(cv2.resize(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), (160, 120), interpolation=cv2.INTER_AREA))
    cap.release(); gray = np.stack(gray)
    for name, gg in (("step2", gray[::2]), ("raw", gray)):
        m = inf._s3_motion_series(gg); stop = inf._s3_stopped_mask(m[:, 1], m[:, 2])
        steer_same = bool((inf._s3_classify(m[:, 0]) == inf._s3_predict_steer(gg)).all())
        for t in g.itertuples():
            k = min(int(t.sample_index), len(gg) - 1)
            out.append({"ID": vid, "mode": name, "sample_index": int(t.sample_index), "accel": t.accel_label, "inline_stop": bool(stop[k]), "steer_same": steer_same})
d = pd.DataFrame(out)
s2 = d[d["mode"] == "step2"].merge(ref[["ID", "sample_index", "rule_stop"]], on=["ID", "sample_index"])
rep = {"step2_n": len(s2), "step2_agree_with_pro": int((s2.inline_stop == s2.rule_stop).sum()),
       "steer_col_identical": bool(d.steer_same.all())}
for mode, x in d.groupby("mode"):
    rep[mode] = {"true_stopped": int((x.accel == "STOPPED").sum()), "pred": int(x.inline_stop.sum()),
                 "tp": int((x.inline_stop & (x.accel == "STOPPED")).sum()), "fp": int((x.inline_stop & (x.accel != "STOPPED")).sum())}
d.to_csv("work/s3_stopped_graft_check/rows.csv", index=False)
open("work/s3_stopped_graft_check/report.json", "w").write(json.dumps(rep, indent=1)); print(json.dumps(rep, indent=1))
