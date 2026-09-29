"""Pro check: grafted submission/inference.py (25a7047) steer path vs Pro equiv_open.csv on Baseline S3 OPEN examples (reference only)."""
import json, sys, time, importlib.util
from pathlib import Path
import numpy as np, pandas as pd
spec = importlib.util.spec_from_file_location("inf", "work/s3_graft_check/inference_25a7047.py")
inf = importlib.util.module_from_spec(spec); spec.loader.exec_module(inf)
ref = pd.read_csv("work/s3_yaw_steer_r1/equiv_open.csv")
out, rows = {}, []
for vid, g in ref.groupby("ID"):
    t = time.time()
    frames, gray = inf._stage3_frames(Path(f"Baseline/data/stage3/videos/{vid}.mp4"))
    t_dec = time.time() - t; t = time.time()
    pred = inf._s3_predict_steer(gray); t_flow = time.time() - t
    g = g.sort_values("sample_index")
    p = [pred[k] if k < len(pred) else None for k in g.sample_index]
    same = int(sum(a == b for a, b in zip(p, g["pred"])))
    out[vid] = {"n_decoded": len(gray), "n_label_rows": len(g), "same_as_pro": same, "dec_s": round(t_dec, 1), "flow_s": round(t_flow, 1)}
    for (k, gt, acc, pp) in zip(g.sample_index, g["gt"], g["accel"], p): rows.append((vid, k, gt, acc, pp))
df = pd.DataFrame(rows, columns=["ID", "sample_index", "gt", "accel", "pred"])
s = df[(df.accel != "STOPPED") & df.pred.notna()]
sys.path.insert(0, "work/pro_tools"); from s3_yaw_steer_rule import mf1
out["_total"] = {"same": int(sum(v["same_as_pro"] for v in out.values())), "rows": len(ref), "steer_macro_f1_open": round(mf1(s["gt"].values, s["pred"].values), 4)}
json.dump(out, open("work/s3_graft_check/report.json", "w"), indent=1); print(json.dumps(out, indent=1))
