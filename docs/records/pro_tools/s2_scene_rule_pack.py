"""Pack decision 12-C qa attachments: per-window predictions of the adopted rules + evaluation reports."""
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

R = Path("work/s2_scene_rule_r1")
O = Path("work/agent/outbox/s2_scene_rule_v1_files")
O.mkdir(parents=True, exist_ok=True)
THR = 1.721142750989563
F = pd.read_csv(R / "features.csv", dtype={"video_id": str})
F = F[F.anchor == "pred"]
lab = pd.read_csv("work/agent/outbox/nexar_v2_labels_v2_files/stage2_merged_nexar_v2.csv", dtype={"video_id": str}).set_index("video_id")
rows = []
for r in F.itertuples():
    L = lab.loc[r.video_id]
    rows.append({"video_id": r.video_id, "win": r.win, "group": r.group, "label_source": r.label_source,
                 "pred_collision_idx": r.pred_pair, "gt_collision_idx": r.gt,
                 "side_valid": int(L.side_valid), "side_true": L.entry_side if L.side_valid == 1 else "",
                 "obj_u_L10": r.obj_u_L10,
                 "side_pred": "LEFT" if (np.isnan(r.obj_u_L10) or r.obj_u_L10 > 0) else "RIGHT",
                 "evasion_valid": int(L.evasion_valid),
                 "evasion_true": int(L.evasion_space) if L.evasion_valid == 1 else "", "pre_mag_L5": r.pre_mag_L5,
                 "evasion_pred": 1 if (np.isnan(r.pre_mag_L5) or r.pre_mag_L5 <= THR) else 0})
pd.DataFrame(rows).to_csv(O / "window_predictions.csv", index=False)
for f in ("report.json", "fixed_rules.json", "side_fixed_all.json", "feature_auroc.json", "features.csv"):
    shutil.copy(R / f, O / f)
print(len(rows), sorted(p.name for p in O.iterdir()))
