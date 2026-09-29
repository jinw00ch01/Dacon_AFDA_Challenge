"""S2 scene OOF 진단: 헤드별 fold 내 AUROC, fold별 정답/예측 비율, 반전 예측 F1, AUROC 순열 p.

사용: s2_scene_oof_diag.py <oof.csv> <out.json>
"""
import json, sys
import numpy as np
import pandas as pd

sys.path.insert(0, "work/pro_tools")
from s2_scene_oof import macro_f1  # noqa: E402


def auroc(t, s):
    pos, neg = s[t == 1], s[t == 0]
    if len(pos) == 0 or len(neg) == 0:
        return None
    return float(((pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()) / (len(pos) * len(neg)))


df = pd.read_csv(sys.argv[1], dtype={"video_id": str})
out = {}
rng = np.random.default_rng(0)
for hd, g in df.groupby("head"):
    t, p, s = g["true"].values.astype(int), g["pred"].values.astype(int), g["prob"].values.astype(float)
    a = auroc(t, s)
    perm = np.array([auroc(rng.permutation(t), s) for _ in range(5000)])
    folds = {}
    for f, gf in g.groupby("fold"):
        tf, sf = gf["true"].values.astype(int), gf["prob"].values.astype(float)
        rest = g[g.fold != f]["true"].values.astype(int)
        folds[str(f)] = {"n": int(len(gf)), "true1_share": float(tf.mean()), "pred1_share": float(gf["pred"].mean()),
                         "train_true1_share": float(rest.mean()), "auroc_within": auroc(tf, sf)}
    # fold 내 순위만 쓰는 AUROC(fold 간 확률 수준 차이를 제거): 각 fold 내 prob 순위 백분위
    g2 = g.copy()
    g2["rk"] = g2.groupby("fold")["prob"].rank(pct=True)
    a_rank = auroc(t, g2["rk"].values)
    flip = 1 - p
    fperm = np.array([macro_f1(t, rng.permutation(flip)) for _ in range(5000)])
    out[hd] = {
        "n": int(len(g)), "auroc": a, "auroc_perm_p_low": float((1 + (perm <= a).sum()) / 5001),
        "auroc_perm_p_high": float((1 + (perm >= a).sum()) / 5001),
        "auroc_fold_rank": a_rank, "accuracy": float((t == p).mean()),
        "macro_f1": macro_f1(t, p), "flipped_macro_f1": macro_f1(t, flip),
        "flipped_perm_p": float((1 + (fperm >= macro_f1(t, flip)).sum()) / 5001),
        "prob_mean_by_true": {str(c): float(s[t == c].mean()) for c in (0, 1)},
        "folds": folds,
        "corr_train_prior_vs_pred_share": float(np.corrcoef([v["train_true1_share"] for v in folds.values()],
                                                            [v["pred1_share"] for v in folds.values()])[0, 1]),
    }
json.dump(out, open(sys.argv[2], "w"), indent=1)
print(json.dumps(out, indent=1))
