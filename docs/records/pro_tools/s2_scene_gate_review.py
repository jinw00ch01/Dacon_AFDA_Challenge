"""S2 scene 게이트 result 독립 재계산: 첨부 true/pred 배열로 Macro-F1·acc, 1건 뒤집기 민감도, v7 val 라벨 출처 수."""
import json, sys
import numpy as np
import pandas as pd


def macro_f1(t, p, labels=(0, 1)):
    t, p = np.asarray(t), np.asarray(p)
    f = []
    for c in labels:
        tp = ((p == c) & (t == c)).sum(); fp = ((p == c) & (t != c)).sum(); fn = ((p != c) & (t == c)).sum()
        f.append(0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn))
    return float(np.mean(f))


rep_path, out = sys.argv[1], sys.argv[2]
r = json.load(open(rep_path))["results"]
res = {}
for m, x in r.items():
    e = {}
    for k, (tk, pk) in {"evasion": ("evasion_true", "evasion_pred"), "dir": ("side_true", "side_pred")}.items():
        t, p = x[tk], x[pk]
        base = macro_f1(t, p)
        flips = [macro_f1(t, [1 - v if j == i else v for j, v in enumerate(p)]) for i in range(len(p))]
        e[k] = dict(n=len(t), macro_f1=base, acc=float(np.mean(np.array(t) == np.array(p))), true_counts=np.bincount(t, minlength=2).tolist(),
                    pred_counts=np.bincount(p, minlength=2).tolist(), one_flip_min=min(flips), one_flip_max=max(flips),
                    const_pred_f1=max(macro_f1(t, [c] * len(t)) for c in (0, 1)))
    res[m] = e
res["same_truth_arrays"] = r["e001"]["evasion_true"] == r["e005"]["evasion_true"] and r["e001"]["side_true"] == r["e005"]["side_true"]
m = pd.read_csv("data/derived/nexar_subset_v1/stage2_review_with_metadata.csv", dtype={"video_id": str})
v = pd.read_csv("work/agent/outbox/stage2_labels_v7_files/stage2_merged_v7.csv", dtype={"video_id": str})
m["video_id"] = m.video_id.str.zfill(5); v["video_id"] = v.video_id.str.zfill(5)
d = v.merge(m[["video_id", "split"]], on="video_id", how="left")
val = d[d.split == "validation"]
res["pro_v7_validation"] = {"rows": int(len(val)), "split_counts_all": d.split.value_counts(dropna=False).to_dict()}
for c in ["evasion_valid", "side_valid", "collision_valid", "entry_valid"]:
    s = val[val[c] == 1]
    res["pro_v7_validation"][c] = {"n": int(len(s)), "label_source": s.label_source.value_counts().to_dict()}
res["pro_v7_validation"]["evasion_dist"] = val[val.evasion_valid == 1].evasion_space.value_counts().to_dict()
res["pro_v7_validation"]["side_dist"] = val[val.side_valid == 1].entry_side.value_counts().to_dict()
json.dump(res, open(out, "w"), indent=1, default=str)
print(json.dumps(res, indent=1, default=str))
