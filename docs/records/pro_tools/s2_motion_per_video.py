"""Per-video summary of the S2 motion rule windows. Usage: s2_motion_per_video.py <windows_pair.csv> <out.csv>"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s2_motion_rule import hit  # noqa: E402

w = pd.read_csv(sys.argv[1], dtype={"video_id": str})
w["hit_pair"] = [hit(p, g) for p, g in zip(w.pred_pair, w.gt_collision)]
w["err_pair"] = w.pred_pair - w.gt_collision
keys = ["video_id", "group", "src", "label_source", "collision_frame_source", "e001_clean"]
v = w.groupby(keys).agg(windows=("win", "count"), acc_pair=("hit_pair", "mean"),
                        median_signed_err=("err_pair", "median")).reset_index()
v.to_csv(sys.argv[2], index=False)
print(len(v), v.groupby("group").acc_pair.mean().to_dict())
