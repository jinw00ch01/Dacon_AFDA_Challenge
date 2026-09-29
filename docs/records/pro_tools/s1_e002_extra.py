"""S1 e002 추가 진단: 실촬영 S23 val+test 합산 AUROC, 클래스별 prob 분위수, source 단위 bootstrap 95% CI.

사용: s1_e002_extra.py <real_pred.csv> <fmt_pred.csv> <out.json>
"""
import json, sys
import numpy as np
import pandas as pd


def auroc(pos, neg):
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    if len(pos) == 0 or len(neg) == 0:
        return None
    return float(((pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()) / (len(pos) * len(neg)))


def block(df, label_col, pos_val, n_boot=2000):
    pos = df[df[label_col] == pos_val].prob_rerecorded.values
    neg = df[df[label_col] != pos_val].prob_rerecorded.values
    a = auroc(pos, neg)
    rng = np.random.default_rng(0)
    srcs = df.source_id.unique()
    bs = []
    for _ in range(n_boot):
        pick = rng.choice(srcs, len(srcs))
        d = pd.concat([df[df.source_id == s] for s in pick])
        v = auroc(d[d[label_col] == pos_val].prob_rerecorded.values, d[d[label_col] != pos_val].prob_rerecorded.values)
        if v is not None:
            bs.append(v)
    q = lambda x: {k: float(np.percentile(x, p)) for k, p in (("q10", 10), ("q50", 50), ("q90", 90))}
    return {"n": int(len(df)), "n_sources": int(len(srcs)), "auroc": a,
            "ci95_source_bootstrap": [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))],
            "prob_pos": q(pos), "prob_neg": q(neg),
            "pred_rerecorded_share": float((df.prob_rerecorded >= 0.5).mean())}


real = pd.read_csv(sys.argv[1])
fmt = pd.read_csv(sys.argv[2])
out = {"real_s23": {}, "format_matched": {}}
for name, sel in (("val_test", ["validation", "test"]), ("validation", ["validation"]), ("test", ["test"]), ("all", None)):
    d = real if sel is None else real[real.split.isin(sel)]
    out["real_s23"][name] = block(d, "kind", "capture")
    for codec in ("x264", "mp4v"):
        f = fmt[fmt.codec == codec]
        f = f if sel is None else f[f.split.isin(sel)]
        out["format_matched"][f"{codec}_{name}"] = block(f, "kind", "capture")
json.dump(out, open(sys.argv[3], "w"), indent=1)
print(json.dumps({k: {n: {x: v[x] for x in ("n", "auroc", "ci95_source_bootstrap")} for n, v in d.items()} for k, d in out.items()}, indent=1))
