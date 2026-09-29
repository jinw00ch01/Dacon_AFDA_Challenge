"""v1c 계열 HF 비율과 S23 HF 단독 AUROC (s1_hf_probe.py 보조)."""
import json, os, sys
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
from s1_hf_probe import hf_stats


def auc(y, s):
    y = np.asarray(y); s = np.asarray(s)
    pos, neg = s[y == 1], s[y == 0]
    return float(np.mean([(p > n) + 0.5 * (p == n) for p in pos for n in neg]))


out = sys.argv[1]
rep = {}
for name in ["s1_synthetic_v1c_r2", "s1_synthetic_v1c_cm"]:
    base = os.path.join("data/derived", name)
    man = pd.read_csv(os.path.join(base, "manifest.csv"))
    man["hf_224"] = [hf_stats(os.path.join(base, f))[1] for f in man.file]
    man.to_csv(os.path.join(out, name + "_hf.csv"), index=False)
    orig = man[man.label == "original"].groupby(["source_id", "window"]).hf_224.mean()
    rr = man[man.label != "original"].copy()
    rr["ratio"] = [h / orig.get((s, w), np.nan) for h, s, w in zip(rr.hf_224, rr.source_id, rr.window)]
    rep[name] = dict(n=int(rr.ratio.notna().sum()), median_ratio=float(rr.ratio.median()),
                     frac_rerec_higher=float((rr.ratio > 1).mean()),
                     hf_only_auroc=auc((man.label != "original").astype(int), man.hf_224),
                     by_codec={c: float(g.ratio.median()) for c, g in rr.groupby("codec")})
s = pd.read_csv(os.path.join(out, "s23_hf.csv"))
rep["s23_hf_only_auroc"] = {}
for c, g in s.groupby("codec"):
    vt = g[g.split != "train"]
    rep["s23_hf_only_auroc"][c] = dict(all=auc(g.kind == "capture", g.hf_224), val_test=auc(vt.kind == "capture", vt.hf_224))
v = pd.read_csv(os.path.join(out, "v1_hf.csv"))
rep["v1_hf_only_auroc"] = auc(v.variant != "ORIG", v.hf_224)
json.dump(rep, open(os.path.join(out, "report_v1c.json"), "w"), indent=1)
print(json.dumps(rep, indent=1))
