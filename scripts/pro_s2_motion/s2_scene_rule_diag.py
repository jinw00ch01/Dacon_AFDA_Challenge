"""Decision 12-C diagnostic: per-feature window AUROC on FIT and HELD (both anchors) from s2_scene_rule features.csv.
Usage: s2_scene_rule_diag.py <rule_dir> <merged.csv>"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
d = Path(sys.argv[1]); F = pd.read_csv(d / "features.csv", dtype={"video_id": str})
lab = pd.read_csv(sys.argv[2], dtype={"video_id": str}).set_index("video_id")
def auroc(y, x):
    ok = ~np.isnan(x); y, x = y[ok], x[ok]
    pos, neg = x[y == 1], x[y == 0]
    return float(((pos[:, None] > neg[None]).sum() + 0.5 * (pos[:, None] == neg[None]).sum()) / (len(pos) * len(neg)))
out = {}
for head, vcol, col, enc in (("side", "side_valid", "entry_side", lambda v: int(v == "LEFT")),
                             ("evasion", "evasion_valid", "evasion_space", lambda v: int(float(v)))):
    valid = lab.index[lab[vcol] == 1]
    for anchor in ("pred", "gt"):
        D = F[(F.anchor == anchor) & F.video_id.isin(valid)].copy()
        D["y"] = [enc(lab.loc[v, col]) for v in D.video_id]
        feats = [c for c in D.columns if c not in ("video_id", "win", "group", "label_source", "pred_pair", "gt", "anchor", "y")]
        for f in feats:
            r = {g: round(auroc(x.y.values, x[f].values.astype(float)), 3) for g, x in D.groupby("group")}
            out.setdefault(f"{head}/{anchor}", {})[f] = r
for k, v in out.items():
    print(k)
    for f, r in v.items():
        print(f"   {f:16s} FIT {r['FIT']:.3f}  HELD {r['HELD']:.3f}")
json.dump(out, open(d / "feature_auroc.json", "w"), indent=1)
