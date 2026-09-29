"""Pro review of S2 e002: reproduce Ultra's const_baseline (train-median absolute
frame) on the same split, and compute position-invariant baselines on 512-frame
val crops built exactly like training crops (random_time_crop), so the crop-trained
model can be judged on the distribution it was trained for.

usage: s2_review_e002.py --labels <merged_v6.csv> --out <dir>
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from s2_review import assign_splits


def random_time_crop(t, collision, entry, length, rng):
    # verbatim logic of scripts/train_stage2.random_time_crop on indices only
    if not length or t <= length:
        return 0, collision, entry
    anchors = [p for p in (collision, entry) if p is not None]
    if anchors:
        anchor = anchors[int(rng.randint(len(anchors)))]
        lo = max(0, anchor - length + 1)
        hi = min(anchor, t - length)
        start = int(rng.randint(lo, hi + 1)) if hi >= lo else max(0, min(anchor, t - length))
    else:
        start = int(rng.randint(0, t - length + 1))
    rm = lambda p: None if p is None or not 0 <= p - start < length else p - start
    return start, rm(collision), rm(entry)


def items(df):
    out = []
    for _, r in df.iterrows():
        t = int(r.decoded_frames)
        pos = lambda f, v: int(np.clip(int(round(float(r[f]))), 0, t - 1)) if int(r[v]) == 1 and not pd.isna(r[f]) else None
        c, e = pos("collision_frame", "collision_valid"), pos("entry_frame", "entry_valid")
        has = any(int(r[k]) == 1 for k in ("collision_valid", "entry_valid", "evasion_valid", "side_valid"))
        out.append({"video_id": r.video_id, "T": t, "fps": float(r.fps), "collision": c, "entry": e, "has": has})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--crop", type=int, default=512)
    ap.add_argument("--n-crops", type=int, default=5)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    lab = pd.read_csv(a.labels, dtype={"video_id": str}).reset_index(drop=True)
    lab["split"] = assign_splits(lab)
    tr = [i for i in items(lab[lab.split == "train"]) if i["has"]]
    va = items(lab[lab.split == "validation"])
    rep = {"n_train_with_target": len(tr), "n_val": len(va),
           "label_source_counts": lab.label_source.value_counts().to_dict()}

    # (1) Ultra const_baseline: train-median absolute frame, clipped to val T
    const = {}
    for k in ("collision", "entry"):
        med = int(round(float(np.median([i[k] for i in tr if i[k] is not None]))))
        errs = [abs(int(np.clip(med, 0, i["T"] - 1)) - i[k]) / i["fps"] for i in va if i[k] is not None]
        const[k] = {"frame": med, "mae_s": float(np.mean(errs)), "n": len(errs)}
    const["time_mae_s"] = (const["collision"]["mae_s"] + const["entry"]["mae_s"]) / 2
    rep["const_abs_frame_full_clip"] = const
    rep["val_T"] = {"min": min(i["T"] for i in va), "median": float(np.median([i["T"] for i in va])),
                    "max": max(i["T"] for i in va)}
    rep["train_T"] = {"min": min(i["T"] for i in tr), "median": float(np.median([i["T"] for i in tr])),
                      "max": max(i["T"] for i in tr)}

    # (2) seeded val crops (same sampler as training) + position-invariant baselines
    L = a.crop
    rng = np.random.RandomState(12345)
    rows = []
    for i in va:
        if i["collision"] is None and i["entry"] is None:
            continue
        for c in range(a.n_crops):
            start, cc, ee = random_time_crop(i["T"], i["collision"], i["entry"], L, rng)
            rows.append({"video_id": i["video_id"], "crop": c, "start": start, "fps": i["fps"],
                         "collision_in_crop": cc, "entry_in_crop": ee})
    crops = pd.DataFrame(rows)
    crops.to_csv(out / "val_crops_seed12345.csv", index=False)
    base = {}
    for k in ("collision", "entry"):
        s = crops[crops[f"{k}_in_crop"].notna()]
        tgt = s[f"{k}_in_crop"].astype(float)
        base[k] = {"n_crop_targets": len(s),
                   "center_mae_s": float(((L // 2 - tgt).abs() / s.fps).mean()),
                   "uniform_random_expected_mae_s": float(
                       np.mean([np.mean(np.abs(np.arange(L) - t)) / f for t, f in zip(tgt, s.fps)]))}
    base["time_mae_s_center"] = (base["collision"]["center_mae_s"] + base["entry"]["center_mae_s"]) / 2
    rep["crop_baselines"] = {"crop_frames": L, "n_crops_per_video": a.n_crops, "seed": 12345, **base}

    # (3) how far the full-clip eval is from the training input distribution
    rep["full_clip_len_over_crop"] = {"val_median": rep["val_T"]["median"] / L}
    (out / "report.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(rep, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
