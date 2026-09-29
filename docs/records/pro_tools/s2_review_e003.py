"""Pro review of S2 e003 (10Hz resample + 50-frame windows).

Independently reproduces (no Ultra module import):
  (1) const_baseline at 10Hz (train-median frame on the FULL resampled clip),
  (2) windowed eval centre MAE (same _window_starts sampler, seed 12345, 5 windows),
  (3) official Acc@0.3s on the 5 Baseline examples for e001 / e003 / constants,
and quantifies where the collision falls inside the e003 eval windows vs the official examples.

usage: s2_review_e003.py --labels <merged_v6.csv> --report <report_e003.json> --out <dir>
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

HZ = 10.0
W = 50


def resample_len(t, fps):
    return int(np.floor((t - 1) * HZ / fps)) + 1


def items(df):
    out = []
    for _, r in df.iterrows():
        t0, fps = int(r.decoded_frames), float(r.fps)
        pos0 = lambda f, v: (int(np.clip(int(round(float(r[f]))), 0, t0 - 1))
                             if int(r[v]) == 1 and not pd.isna(r[f]) else None)
        t = resample_len(t0, fps)
        rm = lambda p: None if p is None else int(np.clip(int(round(p * HZ / fps)), 0, t - 1))
        c, e = rm(pos0("collision_frame", "collision_valid")), rm(pos0("entry_frame", "entry_valid"))
        has = any(int(r[k]) == 1 for k in ("collision_valid", "entry_valid", "evasion_valid", "side_valid"))
        out.append({"video_id": r.video_id, "T": t, "collision": c, "entry": e, "has": has})
    return out


def window_starts(t_len, anchor, window, n, rng):
    # verbatim logic of scripts/train_stage2._window_starts
    s = []
    for _ in range(n):
        if t_len <= window:
            s.append(0)
        elif anchor is not None:
            lo, hi = max(0, anchor - window + 1), min(anchor, t_len - window)
            s.append(int(rng.randint(lo, hi + 1)) if hi >= lo else max(0, min(anchor, t_len - window)))
        else:
            s.append(int(rng.randint(0, t_len - window + 1)))
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    lab = pd.read_csv(a.labels, dtype={"video_id": str}).reset_index(drop=True)
    lab["split"] = assign_splits(lab)
    tr = [i for i in items(lab[lab.split == "train"]) if i["has"]]
    va = items(lab[lab.split == "validation"])
    rep = {"n_train_with_target": len(tr), "n_val": len(va),
           "label_source_counts": lab.label_source.value_counts().to_dict()}

    # (1) const_baseline at 10Hz on full clips
    const = {}
    for k in ("collision", "entry"):
        med = int(round(float(np.median([i[k] for i in tr if i[k] is not None]))))
        errs = [abs(int(np.clip(med, 0, i["T"] - 1)) - i[k]) / HZ for i in va if i[k] is not None]
        const[k] = {"frame": med, "mae_s": float(np.mean(errs)), "n": len(errs)}
    const["time_mae_s"] = (const["collision"]["mae_s"] + const["entry"]["mae_s"]) / 2
    const["val_T_10hz"] = {"min": min(i["T"] for i in va), "median": float(np.median([i["T"] for i in va]))}
    rep["const_baseline_full_clip_10hz"] = const

    # (2) windowed eval: same sampler; centre MAE and Acc@0.3 of constant positions on those windows
    rng = np.random.RandomState(12345)
    rows = []
    for i in va:
        anchor = i["collision"] if i["collision"] is not None else i["entry"]
        for wi, st in enumerate(window_starts(i["T"], anchor, W, 5, rng)):
            wl = min(st + W, i["T"]) - st
            rmw = lambda p: None if p is None or not 0 <= p - st < wl else p - st
            rows.append({"video_id": i["video_id"], "w": wi, "start": st, "wlen": wl,
                         "c": rmw(i["collision"]), "e": rmw(i["entry"])})
    win = pd.DataFrame(rows)
    win.to_csv(out / "val_windows_seed12345.csv", index=False)
    wr = {}
    for k in ("c", "e"):
        s = win[win[k].notna()]
        tgt = s[k].astype(int).tolist()
        cen = [min(W // 2, l - 1) for l in s.wlen]
        best = max(((acc_at(tgt, [p] * len(tgt), [HZ] * len(tgt))[0], p) for p in range(W)))
        wr[k] = {"n": len(tgt),
                 "center_mae_s": float(np.mean([abs(c - t) / HZ for c, t in zip(cen, tgt)])),
                 "center_acc03": acc_at(tgt, cen, [HZ] * len(tgt))[0],
                 "best_const_acc03": best[0], "best_const_frame": best[1],
                 "target_pos_quantiles": np.percentile(tgt, [10, 25, 50, 75, 90]).tolist(),
                 "share_in_official_30_41": float(np.mean([30 <= t <= 41 for t in tgt]))}
    rep["windowed_eval"] = wr

    # (3) official 5 examples: Acc@0.3 (float and frame-safe) for the models in Ultra's report
    r = json.loads(Path(a.report).read_text(encoding="utf-8"))
    gt = r["baseline_stage2_examples"]["t_collision_gt"]
    ids = sorted(gt)
    g = [gt[i] for i in ids]
    off = {}
    cands = {name: [m["pred_frame"][i] for i in ids] for name, m in r["models"].items()}
    for p in (24, 25, 30, 31, 32, 33):
        cands[f"const_{p}"] = [p] * 5
    for name, p in cands.items():
        off[name] = {"pred": p,
                     "mae_s": float(np.mean([abs(x - y) / HZ for x, y in zip(p, g)])),
                     "acc03_float": acc_at(g, p, [HZ] * 5)[0],
                     "acc03_frames": acc_at(g, p, [HZ] * 5, tol_mode="frames")[0]}
    rep["official_5ex"] = {"gt": dict(zip(ids, g)), "by_candidate": off}

    # (4) checkpoint-selection noise: spread of per-epoch windowed metrics
    hist = json.loads((Path(a.report).parent / "metrics_e003.json").read_text(encoding="utf-8"))["history"]
    tm = [h["time_mae_s"] for h in hist]
    cm = [h["collision_mae_s"] for h in hist]
    ev = [h["evasion_acc"] for h in hist]
    rep["epoch_spread"] = {"time_mae_s": {"min": min(tm), "median": float(np.median(tm)), "max": max(tm)},
                           "collision_mae_s": {"min": min(cm), "median": float(np.median(cm)), "max": max(cm)},
                           "epochs_collision_below_center": int(sum(c < 1.3133 for c in cm)),
                           "evasion_acc_values": sorted(set(round(x, 3) for x in ev)),
                           "n_epochs": len(hist)}
    (out / "report.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(rep, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
