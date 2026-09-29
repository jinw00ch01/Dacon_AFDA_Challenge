"""게이트 배열을 영상에 매핑(cache manifest 순서 = v7 라벨 CSV 행 순서)하고, e001 학습 split(v6)에 있던 영상을 뺀 비오염 부분집합으로 재계산."""
import json, sys
import numpy as np
import pandas as pd
sys.path.insert(0, "work/pro_tools")
from s2_split_shift import assign_splits


def macro_f1(t, p, labels=(0, 1)):
    t, p = np.asarray(t), np.asarray(p)
    f = []
    for c in labels:
        tp = ((p == c) & (t == c)).sum(); fp = ((p == c) & (t != c)).sum(); fn = ((p != c) & (t == c)).sum()
        f.append(0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn))
    return float(np.mean(f))


side_map = {"LEFT": 0, "RIGHT": 1}
rep = json.load(open(sys.argv[1]))["results"]
d = {}
for ver in ["v6", "v7"]:
    df = pd.read_csv(f"work/agent/outbox/stage2_labels_{ver}_files/stage2_merged_{ver}.csv", dtype={"video_id": str})
    df["split"] = assign_splits(df)
    d[ver] = df
v7, v6 = d["v7"], d["v6"].set_index("video_id")
val = v7[v7.split == "validation"]
ev = val[val.evasion_valid == 1]; sd = val[val.side_valid == 1]
out = {"order_check": {"evasion_true_matches": ev.evasion_space.astype(int).tolist() == rep["e001"]["evasion_true"],
                       "side_true_matches_LEFT0_RIGHT1": sd.entry_side.map(side_map).tolist() == rep["e001"]["side_true"]}}
for name, sub, tk, pk, lab in [("evasion", ev, "evasion_true", "evasion_pred", "evasion_valid"), ("dir", sd, "side_true", "side_pred", "side_valid")]:
    trained = np.array([v6.loc[v, "split"] == "train" and v6.loc[v, lab] == 1 for v in sub.video_id])
    ent = {"videos": sub.video_id.tolist(), "trained_by_e001_with_label": trained.astype(int).tolist(),
           "label_source": sub.label_source.tolist()}
    for m in ["e001", "e005"]:
        t = np.array(rep[m][tk]); p = np.array(rep[m][pk])
        for part, mask in [("contaminated", trained), ("clean", ~trained)]:
            ent[f"{m}_{part}"] = {"n": int(mask.sum()), "acc": float((t[mask] == p[mask]).mean()) if mask.any() else None,
                                  "macro_f1": macro_f1(t[mask], p[mask]) if mask.any() else None,
                                  "true": t[mask].tolist(), "pred": p[mask].tolist()}
    out[name] = ent
json.dump(out, open(sys.argv[2], "w"), indent=1)
print(json.dumps(out, indent=1))
