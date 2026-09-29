"""Module equivalence: src/afda/s3_stopped_flow.py (worktree) vs evaluation features / rule predictions on given sources.
Also times the flow per frame. Usage: s3_stopped_flow_equiv.py <module_src_dir> <out.json> SRC020 SRC021 ..."""
import glob, json, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, sys.argv[1]); sys.path.insert(0, "work/pro_tools")
from afda import s3_stopped_flow as sf, s3_yaw_steer as ys
from s3_motion_features import gray_frames, SEGMENTS, AUX
aux = pd.read_csv(AUX, encoding="utf-8-sig"); feats = pd.read_csv("work/s3_motion_feat_r2/features.csv")
rule = pd.read_csv("work/s3_stopped_flow_r3/all_rows.csv"); yaw = pd.read_csv("work/s3_yaw_steer_r1/predictions.csv")
rep = {}
for sid in sys.argv[3:]:
    g = aux[aux.source_id == sid].sort_values("sample_index")
    hv = glob.glob(str(SEGMENTS / g.origin_group.iloc[0].replace("|", "_") / "*" / "video.hevc"))[0]
    idx = g.source_frame_index.to_numpy().astype(int); fr = gray_frames(hv, idx)
    gray = np.stack([fr[int(i)] for i in idx])
    t = time.time(); m = sf.motion_series(gray); dt = time.time() - t
    stop = sf.stopped_mask(m[:, 1], m[:, 2])
    f = feats[feats.source_id == sid].sort_values("sample_index"); r = rule[rule.source_id == sid].sort_values("sample_index")
    y = yaw[yaw.source_id == sid].sort_values("sample_index")
    steer_from_shared = ys.classify(m[:, 0])
    rep[sid] = {"n": len(gray), "max_abs_diff_yaw_far": float(np.max(np.abs(m[:, 0] - f.yaw_far.values))),
                "max_abs_diff_div_far": float(np.max(np.abs(m[:, 1] - f.div_far.values))),
                "max_abs_diff_mag_all": float(np.max(np.abs(m[:, 2] - f.mag_all.values))),
                "stop_agree": int((stop == r.p.values.astype(bool)).sum()), "stop_pred": int(stop.sum()),
                "steer_agree_with_yaw_rule": int((steer_from_shared == y.pred_steer.values).sum()),
                "sec_per_frame": round(dt / len(gray), 4)}
open(sys.argv[2], "w").write(json.dumps(rep, indent=1)); print(json.dumps(rep, indent=1))
