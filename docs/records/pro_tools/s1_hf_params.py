"""v1 합성 HF 비율(SYN/ORIG @224)과 생성 파라미터의 순위상관."""
import json, sys
import numpy as np
import pandas as pd

out = sys.argv[1]
v = pd.read_csv(f"{out}/v1_hf.csv")
man = pd.read_csv("data/derived/s1_synthetic_v1/manifest.csv").set_index("file")
orig = v[v.variant == "ORIG"].set_index("source_id").hf_224
syn = v[v.variant != "ORIG"].copy()
syn["ratio"] = syn.hf_224 / syn.source_id.map(orig)
P = pd.DataFrame([{k: val for k, val in json.loads(man.loc[f, "params"]).items() if not isinstance(val, list)} for f in syn.file])
res = {}
for c in P.columns:
    x = pd.to_numeric(P[c], errors="coerce")
    if x.nunique() > 2:
        res[c] = float(np.corrcoef(x.rank(), syn.ratio.rank().values)[0, 1])
res = dict(sorted(res.items(), key=lambda kv: -abs(kv[1])))
q = syn.ratio.quantile([0.1, 0.5, 0.9]).round(3).tolist()
lowblur = syn.ratio[(P.blur_sigma < 0.4).values]
rep = dict(spearman_ratio_vs_param=res, ratio_q10_50_90=q,
           ratio_median_blur_lt_0p4=float(lowblur.median()), n_blur_lt_0p4=int(len(lowblur)))
json.dump(rep, open(f"{out}/v1_hf_params.json", "w"), indent=1)
print(json.dumps(rep, indent=1))
