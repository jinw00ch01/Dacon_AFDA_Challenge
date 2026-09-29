"""(1) module afda.s3_yaw_steer vs features.csv yaw_far on 2 comma sources; (2) reference metric on Baseline S3 OPEN examples.
Usage: s3_yaw_equiv_open.py <worktree_root> <features.csv> <out.json>"""
import json, sys
from pathlib import Path
import cv2, numpy as np, pandas as pd
wt = Path(sys.argv[1]); sys.path.insert(0, str(wt / "src")); sys.path.insert(0, "scripts/pro_s3_motion")
from afda import s3_yaw_steer as ys
import s3_motion_features as mf
sys.path.insert(0, "work/pro_tools"); from s3_yaw_steer_rule import mf1
feat = pd.read_csv(sys.argv[2]); aux = pd.read_csv(mf.AUX)
rep = {"equiv": {}}
import glob
for sid in ("SRC017", "SRC021"):
    g = aux[aux.source_id == sid].sort_values("sample_index")
    hv = glob.glob(str(mf.SEGMENTS / g.origin_group.iloc[0].replace("|", "_") / "*" / "video.hevc"))[0]
    idx = g.source_frame_index.astype(int).tolist()[:200]
    fr = mf.gray_frames(hv, idx)
    y = ys.yaw_series(np.stack([fr[i] for i in idx]))
    ref = feat[feat.source_id == sid].sort_values("sample_index").yaw_far.values[:200]
    rep["equiv"][sid] = {"n": len(idx), "max_abs_diff": float(np.max(np.abs(y[1:] - ref[1:])))}
lab = pd.read_csv("Baseline/data/stage3/labels.csv")
rows = []
for vid, g in lab.groupby("ID"):
    cap = cv2.VideoCapture(f"Baseline/data/stage3/videos/{vid}.mp4")
    fps = cap.get(cv2.CAP_PROP_FPS); frames = []
    while True:
        ok, f = cap.read()
        if not ok: break
        frames.append(f)
    cap.release()
    nz = g[g.sample_index > 0]; step = float((nz.frame_index / nz.sample_index).median())
    n10 = int(len(frames) / step)
    sel = [frames[min(len(frames) - 1, int(round(k * step)))] for k in range(n10)]
    pred = ys.predict_steer(sel)
    yaw = ys.smooth(ys.yaw_series(ys.to_gray(sel)))
    for r in g.itertuples():
        k = int(r.sample_index)
        rows.append({"ID": vid, "sample_index": k, "fps": fps, "wh": f"{frames[0].shape[1]}x{frames[0].shape[0]}", "accel": r.accel_label,
                     "gt": r.steer_label, "pred": pred[k] if k < len(pred) else None, "yaw_s": float(yaw[k]) if k < len(yaw) else None})
df = pd.DataFrame(rows)
s = df[(df.accel != "STOPPED") & df.pred.notna()]
rep["open"] = {"n_rows": len(df), "n_scored": len(s), "steer_macro_f1": round(mf1(s["gt"].values, s["pred"].values), 4),
               "acc": round(float((s["gt"] == s["pred"]).mean()), 4), "gt_counts": s["gt"].value_counts().to_dict(), "pred_counts": s["pred"].value_counts().to_dict(),
               "videos": df.groupby("ID").agg(fps=("fps", "first"), wh=("wh", "first"), n=("gt", "size")).to_dict("index")}
df.to_csv(Path(sys.argv[3]).with_suffix(".csv"), index=False)
open(sys.argv[3], "w").write(json.dumps(rep, indent=1, default=str)); print(json.dumps(rep, indent=1, default=str))
print(df[["ID","sample_index","accel","gt","pred","yaw_s"]].to_string())
