"""Check main 72bcf5f: threaded _s3_motion_series/_s3_yaw_series == serial (workers=1), and timing on Pro CPU."""
import json, time, importlib.util
import cv2, numpy as np, pandas as pd
spec = importlib.util.spec_from_file_location("inf", "submission/inference.py"); inf = importlib.util.module_from_spec(spec); spec.loader.exec_module(inf)
lab = pd.read_csv("Baseline/data/stage3/labels.csv"); rep = {"workers_default": inf._S3_FLOW_WORKERS, "cv2_threads": cv2.getNumThreads(), "videos": {}}
for vid in sorted(lab.ID.unique()):
    cap = cv2.VideoCapture(f"Baseline/data/stage3/videos/{vid}.mp4"); gray = []
    while True:
        ok, bgr = cap.read()
        if not ok: break
        gray.append(cv2.resize(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), (160, 120), interpolation=cv2.INTER_AREA))
    cap.release(); gray = np.stack(gray); r = {"n": len(gray)}
    for w in (1, inf._S3_FLOW_WORKERS):
        inf._S3_FLOW_WORKERS = w
        t = time.perf_counter(); m = inf._s3_motion_series(gray); y = inf._s3_yaw_series(gray); r[f"sec_w{w}"] = round(time.perf_counter() - t, 2)
        r[f"m{w}"], r[f"y{w}"] = m, y
    wd = rep["workers_default"]; inf._S3_FLOW_WORKERS = wd
    r["motion_identical"] = bool(np.array_equal(r.pop("m1"), r.pop(f"m{wd}")))
    r["yaw_identical"] = bool(np.array_equal(r.pop("y1"), r.pop(f"y{wd}")))
    rep["videos"][vid] = r
rep["all_identical"] = all(v["motion_identical"] and v["yaw_identical"] for v in rep["videos"].values())
open("work/s3_parallel_check/report.json", "w").write(json.dumps(rep, indent=1)); print(json.dumps(rep, indent=1))
