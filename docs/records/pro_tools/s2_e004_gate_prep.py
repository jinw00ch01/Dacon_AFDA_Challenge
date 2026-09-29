"""Prep for the S2 e004 falsification gate (decision a41f4f79): how the val-window placement rule decides
the score of the same-window constant (collision 30 / entry 22) that e004 must beat.

Placements compared (collision index inside a 50-frame 10Hz window):
  uniform_25_41 : every index 25..41 once per val video (deterministic version of the proposed train/val sampler)
  official_5    : the 5 official example positions (32,30,31,41,30) once per val video
  random_k      : k random draws from U{25..41} per video, many seeds (noise of a sampled val set)

usage: s2_e004_gate_prep.py --labels <merged_v6.csv> --out <dir>
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from s2_review import assign_splits  # noqa: E402
from official_metrics import acc_at  # noqa: E402
from s2_review_e003 import items  # noqa: E402

HZ, W = 10.0, 50
OFFICIAL = [32, 30, 31, 41, 30]


def windows(va, placements):
    """One row per (video, placement). Collision sits at index p; entry keeps its gap to collision."""
    rows = []
    for i in va:
        if i["collision"] is None:
            continue
        for p in placements:
            st = i["collision"] - p
            if st < 0 or st + W > i["T"]:
                continue
            e = None if i["entry"] is None else i["entry"] - st
            rows.append({"video_id": i["video_id"], "p": p, "c": p,
                         "e": e if e is not None and 0 <= e < W else None,
                         "entry_labeled": i["entry"] is not None})
    return pd.DataFrame(rows)


def const_scores(win):
    out = {"n_windows": len(win), "n_videos": int(win.video_id.nunique())}
    for k, cands in (("c", (25, 28, 30, 31, 32, 33, 35)), ("e", (18, 20, 22, 24, 26))):
        s = win[win[k].notna()]
        g = s[k].astype(int).tolist()
        if not g:
            out[k] = None
            continue
        best = max((acc_at(g, [p] * len(g), [HZ] * len(g))[0], p) for p in range(W))
        out[k] = {"n": len(g),
                  "acc03_at": {str(p): acc_at(g, [p] * len(g), [HZ] * len(g))[0] for p in cands},
                  "best_const": {"frame": best[1], "acc03": best[0]}}
    lab = win[win.entry_labeled]
    out["entry_inside_share"] = float(lab.e.notna().mean()) if len(lab) else None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    lab = pd.read_csv(a.labels, dtype={"video_id": str}).reset_index(drop=True)
    lab["split"] = assign_splits(lab)
    va = items(lab[lab.split == "validation"])
    rep = {"label_source_counts": lab.label_source.value_counts().to_dict(),
           "n_val_videos": len(va), "n_val_collision": sum(i["collision"] is not None for i in va)}

    uni = windows(va, range(25, 42))
    off = windows(va, OFFICIAL)
    uni.to_csv(out / "val_windows_uniform_25_41.csv", index=False)
    off.to_csv(out / "val_windows_official5.csv", index=False)
    rep["uniform_25_41"] = const_scores(uni)
    rep["official_5"] = const_scores(off)

    # sampled val sets: spread of const-30 collision Acc@0.3 across seeds
    vids = [i for i in va if i["collision"] is not None]
    spread = {}
    for k in (1, 5):
        accs = []
        for seed in range(2000):
            rng = np.random.RandomState(seed)
            ps = rng.randint(25, 42, size=(len(vids), k)).ravel().tolist()
            accs.append(acc_at(ps, [30] * len(ps), [HZ] * len(ps))[0])
        q = np.percentile(accs, [5, 50, 95]).tolist()
        spread[f"k{k}"] = {"n_windows": len(vids) * k, "p5_p50_p95": q, "std": float(np.std(accs))}
    rep["random_uniform_const30_collision"] = spread

    # float edge check on the constants used
    rep["float_edge_const30"] = {str(g): abs(30 / HZ - g / HZ) <= 0.3 for g in range(26, 35)}
    (out / "report.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(rep, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
