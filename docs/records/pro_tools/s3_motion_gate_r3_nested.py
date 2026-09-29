"""Nested leave-one-origin_group-out over ALL 23 comma sources (single-feature candidates from r3).

For each held-out origin_group: choose the single derived feature (and its sign) with the best episode AUROC on
the other 22 sources, then score the held-out group with it. Pooled held-out episode AUROC + CIs is an
unbiased estimate of the r3 selection procedure (no source ever scores itself). Supplements the fixed-val gate.
usage: s3_motion_gate_r3_nested.py <out_dir>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s3_accdec_auroc import ACC, DEC, AUX, load_all  # noqa: E402
from s3_stopped_gate import auroc  # noqa: E402
from s3_motion_gate_r3 import FEATS, derive, episodes, ep_stats  # noqa: E402


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    f = pd.read_csv(FEATS)
    aux = load_all(AUX)
    d = f.drop(columns=["split"]).merge(aux[["source_id", "sample_index", "split", "origin_group", "gt_accel"]],
                                        on=["source_id", "sample_index"], how="inner", validate="one_to_one")
    d = d.sort_values(["source_id", "sample_index"]).reset_index(drop=True)
    der = pd.concat([derive(g) for _, g in d.groupby("source_id", sort=False)])
    d = pd.concat([d, der], axis=1)
    cols = list(der.columns)
    # per-source episode table for every feature (episode mean of the feature)
    ept = {c: episodes(d.assign(score=d[c]), "score").merge(
        d[["source_id", "origin_group"]].drop_duplicates(), on="source_id") for c in cols}
    held_rows, picks = [], []
    for g in sorted(d.origin_group.unique()):
        best, bsg, ba = None, 1.0, -1
        for c in cols:
            e = ept[c][ept[c].origin_group != g]
            a = auroc((e.label == ACC).to_numpy(), e.score_mean.to_numpy())
            if a is None:
                continue
            sg = 1.0 if a >= 0.5 else -1.0
            if max(a, 1 - a) > ba:
                best, bsg, ba = c, sg, max(a, 1 - a)
        e = ept[best][ept[best].origin_group == g].copy()
        e["score_mean"] = bsg * e["score_mean"]
        e["feature"] = best
        held_rows.append(e)
        picks.append({"origin_group": g, "feature": best, "sign": bsg, "fit_auroc": ba,
                      "split": d[d.origin_group == g].split.iloc[0]})
    ep = pd.concat(held_rows, ignore_index=True)
    ep = ep.merge(d[["source_id", "split"]].drop_duplicates(), on="source_id")
    ep.to_csv(out / "nested_heldout_episodes.csv", index=False)
    rep = {"picks": picks, "pick_counts": pd.Series([p["feature"] for p in picks]).value_counts().to_dict(),
           "all23": ep_stats(ep), "train15": ep_stats(ep[ep.split == "train"]),
           "val4": ep_stats(ep[ep.split == "validation"]), "test4": ep_stats(ep[ep.split == "test"]),
           "per_source": {s: auroc((g.label == ACC).to_numpy(), g.score_mean.to_numpy())
                          for s, g in ep.groupby("source_id")}}
    (out / "nested_report.json").write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: rep[k] for k in ["pick_counts", "all23", "train15", "val4", "test4", "per_source"]},
                     indent=1, default=str))


if __name__ == "__main__":
    main()
