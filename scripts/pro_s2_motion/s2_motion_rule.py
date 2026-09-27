"""Decision 12-A: S2 collision-time rule from global motion, evaluated on official-format random windows.

Inputs: frame cache from s2_motion_cache.py, merged label CSV (collision_valid rows), e001 split (v6 merged CSV
re-split with the cache_s2_features.assign_splits logic, seed 0).

Split (parameters come from FIT only):
  FIT  = v1 videos in e001's v6 train split (non-human) + new Nexar v2 videos with even numeric id
  HELD = all human-reviewed collision videos + v1 videos in e001's v6 validation split + v2 videos with odd id
  e001_clean = video was not an e001 training video with a collision label (v6 train & v6 collision_valid).
Windows: 10 Hz, 50 frames. Per video K windows with collision position p ~ U{0..49} and sub-frame phase
u ~ U[-0.5, 0.5) (seed 0). GT = window index whose source frame is nearest the labelled collision frame.
Metric: official Acc@0.3s = |pred/10 - gt/10| <= 0.3 (IEEE float), i.e. +-3 frames at 10 Hz.

The rule only sees the 50 window frames. Motion series per step k (frame k-1 -> k, 160x90 gray):
  diff (mean abs diff), mag (median Farneback magnitude), dx/dy (median flow), div (radial expansion),
  res (flow energy after removing the median translation).
Rules: argmax of a score series (optionally 3-tap smoothed) + lag L; score families below. Also a numpy
logistic model over standardised features k-2..k+2 (target |k-gt|<=1), argmax of its probability.

Usage: s2_motion_rule.py <merged.csv> <v6_merged.csv> <cache_dir> <out_dir> [K]
"""
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s2_split_shift import assign_splits  # noqa: E402

T, HZ = 50, 10.0
FEATS = ["diff", "mag", "dx", "dy", "div", "res"]


def hit(p, g):
    return g is not None and p is not None and abs(p / HZ - g / HZ) <= 0.3


def motion_series(frames):
    """frames: (50, H, W) uint8 -> dict of (50,) arrays; step k compares k-1 -> k, k=0 copies k=1."""
    h, w = frames.shape[1:]
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    rx, ry = xs - w / 2, ys - h / 2
    r2 = rx ** 2 + ry ** 2 + 1.0
    out = {k: np.zeros(T, np.float32) for k in FEATS}
    for k in range(1, T):
        a, b = frames[k - 1], frames[k]
        fl = cv2.calcOpticalFlowFarneback(a, b, None, 0.5, 3, 13, 3, 5, 1.1, 0)
        u, v = fl[..., 0], fl[..., 1]
        mu, mv = float(np.median(u)), float(np.median(v))
        out["diff"][k] = float(np.mean(np.abs(a.astype(np.int16) - b.astype(np.int16))))
        out["mag"][k] = float(np.median(np.hypot(u, v)))
        out["dx"][k], out["dy"][k] = mu, mv
        out["div"][k] = float(np.mean((u * rx + v * ry) / r2))
        out["res"][k] = float(np.mean((u - mu) ** 2 + (v - mv) ** 2))
    for f in FEATS:
        out[f][0] = out[f][1]
    return out


def jump(x, n=5):
    """x minus median of the previous n values (causal)."""
    y = np.zeros_like(x)
    for k in range(len(x)):
        prev = x[max(0, k - n):k]
        y[k] = x[k] - (np.median(prev) if len(prev) else x[k])
    return y


def dabs(x):
    return np.abs(np.diff(x, prepend=x[0]))


def scores(s):
    return {
        "diff": s["diff"], "mag": s["mag"], "res": s["res"],
        "diff_jump": jump(s["diff"]), "mag_jump": jump(s["mag"]), "res_jump": jump(s["res"]),
        "jerk_xy": dabs(s["dx"]) + dabs(s["dy"]), "jerk_y": dabs(s["dy"]), "jerk_x": dabs(s["dx"]),
        "div_drop": -np.diff(s["div"], prepend=s["div"][0]), "ddiv_abs": dabs(s["div"]),
        "diff_x_jerk": s["diff"] * (dabs(s["dx"]) + dabs(s["dy"])),
    }


def smooth(x, m):
    return x if m == 0 else np.convolve(np.pad(x, 1, mode="edge"), np.ones(3) / 3, mode="valid")


def predict(sc, name, m, lag):
    return int(np.clip(int(np.argmax(smooth(sc[name], m))) + lag, 0, T - 1))


def design(s):
    """per-window standardised features, stacked over k-2..k+2 -> (50, 5*F)."""
    z = []
    for f in FEATS + ["jerk"]:
        x = s[f] if f != "jerk" else dabs(s["dx"]) + dabs(s["dy"])
        x = (x - x.mean()) / (x.std() + 1e-6)
        z.append(x)
    z = np.stack(z, 1)
    pad = np.pad(z, ((2, 2), (0, 0)), mode="edge")
    return np.concatenate([pad[i:i + T] for i in range(5)], 1)


def fit_logreg(X, y, l2=1.0, iters=400, lr=0.5):
    mu, sd = X.mean(0), X.std(0) + 1e-6
    Xs = np.c_[(X - mu) / sd, np.ones(len(X))]
    w = np.zeros(Xs.shape[1])
    pw = (len(y) - y.sum()) / max(1, y.sum())
    sw = np.where(y == 1, pw, 1.0)
    for _ in range(iters):
        p = 1 / (1 + np.exp(-Xs @ w))
        g = Xs.T @ (sw * (p - y)) / sw.sum() + l2 * np.r_[w[:-1], 0] / len(y)
        w -= lr * g
    return mu, sd, w


def lr_predict(model, X):
    mu, sd, w = model
    return int(np.argmax(np.c_[(X - mu) / sd, np.ones(len(X))] @ w))


def main():
    merged, v6p, cache, out = sys.argv[1], sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4])
    K = int(sys.argv[5]) if len(sys.argv) > 5 else 4
    out.mkdir(parents=True, exist_ok=True)
    import pandas as pd
    v6 = pd.read_csv(v6p, dtype={"video_id": str})
    v6["split"] = assign_splits(v6)
    v6 = v6.set_index("video_id")
    rows = [r for r in csv.DictReader(open(merged, encoding="utf-8-sig")) if r["collision_valid"] == "1"]
    rng = np.random.RandomState(0)
    wins = []
    for r in rows:
        vid = r["video_id"]
        z = np.load(cache / f"{vid}.npz")
        fr, first, fps, col = z["frames"], int(z["first_idx"]), float(z["fps"]), int(z["col"])
        human = r["label_source"] == "human"
        if vid in v6.index:
            sp = v6.loc[vid, "split"]
            group = "HELD" if (human or sp == "validation") else "FIT"
            e001_clean = not (sp == "train" and int(v6.loc[vid, "collision_valid"]) == 1)
            src = "v1"
        else:
            group = "FIT" if int(vid) % 2 == 0 else "HELD"
            e001_clean, src = True, "v2"
        ent = int(float(r["entry_frame"])) if r["entry_frame"] and r["entry_valid"] == "1" else None
        step = fps / HZ
        made = tries = 0
        while made < K and tries < 200:
            tries += 1
            p, u = int(rng.randint(0, T)), float(rng.uniform(-0.5, 0.5))
            idx = [int(round(col + (k - p + u) * step)) for k in range(T)]
            if idx[0] < first or idx[-1] >= first + len(fr):
                continue
            gt = int(np.argmin([abs(i - col) for i in idx]))
            egt = None
            if ent is not None and idx[0] <= ent <= idx[-1]:
                egt = int(np.argmin([abs(i - ent) for i in idx]))
            s = motion_series(fr[[i - first for i in idx]])
            wins.append({"video_id": vid, "win": made, "group": group, "src": src, "e001_clean": e001_clean,
                         "label_source": r["label_source"], "col_source": r["collision_frame_source"],
                         "p": p, "gt": gt, "entry_gt": egt, "entry_frame": ent, "collision_frame": col,
                         "fps": fps, "idx": idx, "s": s})
            made += 1
        print(vid, group, made, flush=True)

    fit = [w for w in wins if w["group"] == "FIT"]
    held = [w for w in wins if w["group"] == "HELD"]
    for w in wins:
        w["sc"] = scores(w["s"])

    # grid search on FIT
    grid = []
    for name in wins[0]["sc"]:
        for m in (0, 1):
            for lag in range(-4, 5):
                acc = np.mean([hit(predict(w["sc"], name, m, lag), w["gt"]) for w in fit])
                grid.append((float(acc), name, m, lag))
    grid.sort(reverse=True)
    best = grid[0]
    # logistic model on FIT
    X = np.concatenate([design(w["s"]) for w in fit])
    y = np.concatenate([(np.abs(np.arange(T) - w["gt"]) <= 1).astype(float) for w in fit])
    lrm = fit_logreg(X, y)
    fit_lr = float(np.mean([hit(lr_predict(lrm, design(w["s"])), w["gt"]) for w in fit]))
    # constant baseline fitted on FIT
    cst = max(range(T), key=lambda c: np.mean([hit(c, w["gt"]) for w in fit]))

    def evaluate(ws):
        res = {}
        for w in ws:
            w["pred_rule"] = predict(w["sc"], best[1], best[2], best[3])
            w["pred_lr"] = lr_predict(lrm, design(w["s"]))
            w["pred_const"] = cst
        subsets = {"all": ws, "human": [w for w in ws if w["label_source"] == "human"],
                   "agent_frame": [w for w in ws if w["label_source"] == "agent" and w["col_source"] == "agent"],
                   "nexar_event": [w for w in ws if w["col_source"] == "nexar_event"],
                   "e001_clean": [w for w in ws if w["e001_clean"]],
                   "v1": [w for w in ws if w["src"] == "v1"], "v2": [w for w in ws if w["src"] == "v2"],
                   "p_30_41": [w for w in ws if 30 <= w["p"] <= 41]}
        for k, sub in subsets.items():
            if not sub:
                continue
            res[k] = {"n_windows": len(sub), "n_videos": len({w["video_id"] for w in sub})}
            for pk in ("pred_rule", "pred_lr", "pred_const"):
                hits = [hit(w[pk], w["gt"]) for w in sub]
                res[k][pk] = round(float(np.mean(hits)), 4)
            # video-level bootstrap CI for rule and lr
            vids = sorted({w["video_id"] for w in sub})
            by = defaultdict(list)
            for w in sub:
                by[w["video_id"]].append(w)
            brng = np.random.RandomState(0)
            for pk in ("pred_rule", "pred_lr"):
                bs = []
                for _ in range(1000):
                    pick = brng.choice(len(vids), len(vids))
                    hs = [hit(w[pk], w["gt"]) for i in pick for w in by[vids[i]]]
                    bs.append(np.mean(hs))
                res[k][pk + "_ci95"] = [round(float(np.percentile(bs, 2.5)), 4), round(float(np.percentile(bs, 97.5)), 4)]
            res[k]["abs_err_rule_median"] = float(np.median([abs(w["pred_rule"] - w["gt"]) for w in sub]))
            res[k]["abs_err_lr_median"] = float(np.median([abs(w["pred_lr"] - w["gt"]) for w in sub]))
        return res

    report = {
        "design": __doc__.split("Usage")[0].strip(),
        "counts": {g: {"windows": len(ws), "videos": len({w["video_id"] for w in ws}),
                       "label_source": dict(Counter(w["label_source"] for w in ws if w["win"] == 0)),
                       "collision_frame_source": dict(Counter(w["col_source"] for w in ws if w["win"] == 0)),
                       "e001_clean_videos": len({w["video_id"] for w in ws if w["e001_clean"]})}
                   for g, ws in (("FIT", fit), ("HELD", held))},
        "chance_uniform_position": round(float(np.mean([min(g + 3, T - 1) - max(g - 3, 0) + 1 for g in range(T)]) / T), 4),
        "fit_best_rules_top10": [{"acc": a, "score": n, "smooth": m, "lag": l} for a, n, m, l in grid[:10]],
        "chosen_rule": {"score": best[1], "smooth3": best[2], "lag": best[3], "fit_acc": best[0]},
        "logreg_fit_acc": round(fit_lr, 4), "const_from_fit": cst,
        "fit": evaluate(fit), "held": evaluate(held),
    }
    (out / "report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    np.savez(out / "logreg_model.npz", mu=lrm[0], sd=lrm[1], w=lrm[2], feats=np.array(FEATS + ["jerk"]))
    with open(out / "windows.csv", "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["video_id", "win", "group", "src", "e001_clean", "label_source", "collision_frame_source",
                     "fps", "collision_frame", "entry_frame", "p", "gt_collision", "gt_entry",
                     "pred_rule", "pred_logreg", "pred_const", "source_frame_indices"])
        for w in wins:
            wr.writerow([w["video_id"], w["win"], w["group"], w["src"], int(w["e001_clean"]), w["label_source"],
                         w["col_source"], w["fps"], w["collision_frame"], w["entry_frame"], w["p"], w["gt"],
                         "" if w["entry_gt"] is None else w["entry_gt"], w["pred_rule"], w["pred_lr"],
                         w["pred_const"], " ".join(map(str, w["idx"]))])
    np.savez_compressed(out / "series.npz", **{f"{w['video_id']}_{w['win']}_{f}": w["s"][f] for w in wins for f in FEATS})
    print(json.dumps({k: report[k] for k in ("counts", "chosen_rule", "logreg_fit_acc", "chance_uniform_position")}, indent=1))
    print("FIT", json.dumps(report["fit"]["all"]))
    for k, v in report["held"].items():
        print("HELD", k, json.dumps(v))


if __name__ == "__main__":
    main()
