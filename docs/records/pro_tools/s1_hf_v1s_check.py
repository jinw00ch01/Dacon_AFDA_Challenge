"""v1s HF 방향 게이트 확인: manifest 기반으로 224 Laplacian HF의 SYN/ORIG 비율, HF 단독 AUROC(RERECORDED=양성)를 낸다."""
import argparse, json, os, sys
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
from s1_hf_probe import hf_stats


def auroc(pos, neg):
    pos, neg = np.asarray(pos), np.asarray(neg)
    gt = (pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()
    return float(gt / (len(pos) * len(neg)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=8)
    a = ap.parse_args()
    man = pd.read_csv(os.path.join(a.dir, "manifest.csv"))
    rows = []
    for r in man.itertuples():
        nat, sm = hf_stats(os.path.join(a.dir, r.file), a.n)
        rows.append(dict(file=r.file, source_id=r.source_id, split=r.split, variant=r.variant, hf_native=nat, hf_224=sm))
    v = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    v.to_csv(a.out.replace(".json", ".csv"), index=False)
    orig = v[v.variant == "ORIG"].set_index("source_id")
    syn = v[v.variant != "ORIG"].copy()
    rep = {"dir": a.dir, "n_orig": int(len(orig)), "n_syn": int(len(syn))}
    for m in ["hf_224", "hf_native"]:
        ratio = syn[m] / syn.source_id.map(orig[m])
        rep[m] = dict(median_ratio_syn_over_orig=float(ratio.median()), q10_q90=[float(ratio.quantile(.1)), float(ratio.quantile(.9))],
                      frac_syn_higher=float((ratio > 1).mean()), auroc_hf_only=auroc(syn[m].values, orig[m].values))
        rep[m]["by_split"] = {s: dict(median_ratio=float(ratio[g.index].median()), auroc=auroc(g[m].values, orig[orig.split == s][m].values))
                              for s, g in syn.groupby("split") if (orig.split == s).any()}
    g = rep["hf_224"]
    rep["gate"] = dict(auroc_ge_0p5=g["auroc_hf_only"] >= 0.5, median_ratio_ge_1=g["median_ratio_syn_over_orig"] >= 1.0,
                       frac_syn_higher_ge_0p5=g["frac_syn_higher"] >= 0.5)
    rep["gate"]["pass"] = all(rep["gate"].values())
    json.dump(rep, open(a.out, "w"), indent=1)
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
