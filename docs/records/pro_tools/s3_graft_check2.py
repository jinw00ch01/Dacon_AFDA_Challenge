"""Variants of grafted steer on OPEN examples: all frames (graft as-is) / frames[::2] / all frames but row k->pred[2k]."""
import json, sys, importlib.util
import cv2, numpy as np, pandas as pd
spec = importlib.util.spec_from_file_location("inf", "work/s3_graft_check/inference_25a7047.py")
inf = importlib.util.module_from_spec(spec); spec.loader.exec_module(inf)
sys.path.insert(0, "work/pro_tools"); from s3_yaw_steer_rule import mf1
lab = pd.read_csv("Baseline/data/stage3/labels.csv"); ref = pd.read_csv("work/s3_yaw_steer_r1/equiv_open.csv")
rows = []
for vid, g in lab.groupby("ID"):
    cap = cv2.VideoCapture(f"Baseline/data/stage3/videos/{vid}.mp4"); gray = []
    while True:
        ok, bgr = cap.read()
        if not ok: break
        gray.append(cv2.resize(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), (160, 120), interpolation=cv2.INTER_AREA))
    cap.release(); gray = np.stack(gray)
    p_all = inf._s3_predict_steer(gray); p_half = inf._s3_predict_steer(gray[::2])
    r = ref[ref.ID == vid].set_index("sample_index")["pred"]
    for t in g.itertuples():
        k = int(t.sample_index)
        rows.append({"ID": vid, "k": k, "frame_index": int(t.frame_index), "gt": t.steer_label, "accel": t.accel_label,
                     "graft_as_is": p_all[k], "graft_sub2": p_half[k], "graft_all_at_2k": p_all[min(2 * k, len(p_all) - 1)], "pro_ref": r.get(k)})
df = pd.DataFrame(rows); s = df[df.accel != "STOPPED"]
rep = {v: round(mf1(s["gt"].values, s[v].values), 4) for v in ("graft_as_is", "graft_sub2", "graft_all_at_2k", "pro_ref")}
rep["sub2_equals_pro_ref"] = int((df.graft_sub2 == df.pro_ref).sum()); rep["n"] = len(df); rep["n_scored"] = len(s)
rep["pred_counts"] = {v: s[v].value_counts().to_dict() for v in ("graft_as_is", "graft_sub2", "graft_all_at_2k")}
df.to_csv("work/s3_graft_check/open_variants.csv", index=False)
json.dump(rep, open("work/s3_graft_check/open_variants.json", "w"), indent=1); print(json.dumps(rep, indent=1))
