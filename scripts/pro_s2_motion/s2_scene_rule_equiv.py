"""Check afda.s2_scene_rule (branch module) against the evaluation features.csv on all windows (pred anchor)."""
import sys
sys.path.insert(0, sys.argv[1])
import numpy as np, pandas as pd
from afda import s2_scene_rule as m
F = pd.read_csv("work/s2_scene_rule_r1/features.csv", dtype={"video_id": str}); F = F[F.anchor == "pred"].set_index(["video_id", "win"])
w = pd.read_csv("work/s2_motion_rule_r1/windows_pair.csv", dtype={"video_id": str})
agree_s = agree_e = n = 0; dmax = [0, 0]
for r in w.itertuples():
    z = np.load(f"work/s2_motion_cache/{r.video_id}.npz"); fr, first = z["frames"], int(z["first_idx"])
    g = fr[[int(i) - first for i in r.source_frame_indices.split()]]
    c = int(r.pred_pair); f = F.loc[(r.video_id, r.win)]
    xs, xe = m.side_feature(g, c), m.evasion_feature(g, c)
    ps = m.predict_side(g, c); pe = m.predict_evasion(g, c)
    rs = "LEFT" if (np.isnan(f.obj_u_L10) or f.obj_u_L10 > 0) else "RIGHT"
    re_ = 1 if (np.isnan(f.pre_mag_L5) or f.pre_mag_L5 <= m.EVASION_THR) else 0
    agree_s += ps == rs; agree_e += pe == re_; n += 1
    if xs is not None: dmax[0] = max(dmax[0], abs(xs - f.obj_u_L10))
    if xe is not None: dmax[1] = max(dmax[1], abs(xe - f.pre_mag_L5))
print("windows", n, "side agree", agree_s, "evasion agree", agree_e, "max abs diff", dmax)
