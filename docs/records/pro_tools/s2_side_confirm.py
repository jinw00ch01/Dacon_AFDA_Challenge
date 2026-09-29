"""Decision 12-C follow-up: confirmatory test of the FROZEN side rule (afda.s2_scene_rule, obj_u_L10 > 0 -> LEFT)
on Nexar v2 videos that were NOT part of the 12-C evaluation (no merged entry_side label).

Pre-registered before running (cycle 7b09aa3eb6cd):
  labels  = triage side (LEFT/RIGHT) from work/nexar_v2/triage_results (agent triage sheet, 88.5 % agreement
            with detailed side labels on 26 overlapping videos -> label noise ~11 %).
  videos  = triage side in {LEFT, RIGHT}, contact in {yes, uncertain}, no LEFT/RIGHT entry_side in the merged v2 CSV.
  anchor  = nexar_event_frame (default collision per decision 8); windows 10 Hz x 50, K=4, p~U{0..49},
            u~U[-0.5,0.5), RandomState(0) - same construction as rule A r1.
  pipeline= frozen afda.s2_motion_rule.predict_collision -> frozen afda.s2_scene_rule.predict_side (no refit).
  primary = all selected videos, per-window Macro-F1; 4 conditions of decision 8c33234b (CI low > constant
            lower bound, max predicted share <= 0.9, permutation p < 0.05 (2000, seed 0), integrity).
  secondary = contact yes only; per-video majority vote.
Usage: s2_side_confirm.py <merged_v2.csv> <meta.csv> <out_dir> [workers]
"""
import glob
import json
import sys
from collections import Counter, defaultdict
from multiprocessing import Pool
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from afda.s2_motion_rule import predict_collision, to_gray  # noqa: E402
from afda.s2_scene_rule import predict_side, side_feature  # noqa: E402

T, HZ, K, PRE, POST = 50, 10.0, 4, 6.0, 6.0


def decode(path, lo, hi):
    cap = cv2.VideoCapture(str(ROOT / path))
    out, i = [], 0
    while i <= hi:
        ok, f = cap.read()
        if not ok:
            break
        if i >= lo:
            out.append(f)
        i += 1
    cap.release()
    return to_gray(out) if out else None


def work(a):
    vid, path, fps, anchor, windows = a
    lo = max(0, int(anchor - PRE * fps))
    g = decode(path, lo, int(anchor + POST * fps))
    res = []
    for win, idx in windows:
        if g is None or idx[-1] - lo >= len(g):
            res.append((vid, win, None, None, None))
            continue
        w = g[[i - lo for i in idx]]
        c = predict_collision(w, gray=True)
        res.append((vid, win, c, predict_side(w, c), side_feature(w, c)))
    return res


def macro_f1(y, p):
    fs = []
    for c in ("LEFT", "RIGHT"):
        tp = sum(1 for a, b in zip(y, p) if a == c and b == c)
        fp = sum(1 for a, b in zip(y, p) if a != c and b == c)
        fn = sum(1 for a, b in zip(y, p) if a == c and b != c)
        fs.append(0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn))
    return float(np.mean(fs))


def evaluate(df):
    y, p, v = df.y.tolist(), df.pred.tolist(), df.video_id.tolist()
    f1 = macro_f1(y, p)
    const = max(macro_f1(y, [c] * len(y)) for c in ("LEFT", "RIGHT"))
    by = defaultdict(list)
    for i, vid in enumerate(v):
        by[vid].append(i)
    vids = sorted(by)
    rng = np.random.RandomState(0)
    bs, bc = [], []
    for _ in range(2000):
        ix = [i for k in rng.choice(len(vids), len(vids)) for i in by[vids[k]]]
        yy, pp = [y[i] for i in ix], [p[i] for i in ix]
        bs.append(macro_f1(yy, pp))
        bc.append(max(macro_f1(yy, [c] * len(yy)) for c in ("LEFT", "RIGHT")))
    # permutation: shuffle labels across videos (video-level label is constant within a video)
    vy = {vid: y[by[vid][0]] for vid in vids}
    rng = np.random.RandomState(0)
    perm = []
    for _ in range(2000):
        sh = dict(zip(vids, rng.permutation([vy[k] for k in vids])))
        perm.append(macro_f1([sh[x] for x in v], p))
    pval = float((1 + sum(1 for s in perm if s >= f1)) / (1 + len(perm)))
    share = max(Counter(p).values()) / len(p)
    ci = [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]
    const_lo = float(np.percentile(bc, 2.5))
    vote = df.groupby("video_id").agg(y=("y", "first"), pred=("pred", lambda s: Counter(s).most_common(1)[0][0]))
    return {"n_windows": len(y), "n_videos": len(vids), "label_counts": dict(Counter(vy.values())),
            "macro_f1": round(f1, 4), "ci95": [round(x, 4) for x in ci], "acc": round(float(np.mean(np.array(y) == np.array(p))), 4),
            "const_macro_f1": round(const, 4), "const_ci_low": round(const_lo, 4),
            "max_pred_share": round(share, 4), "perm_p": round(pval, 4),
            "cond1_ci_low_gt_const_low": ci[0] > const_lo, "cond2_share_le_0.9": share <= 0.9, "cond3_perm_p_lt_0.05": pval < 0.05,
            "video_vote_macro_f1": round(macro_f1(vote.y.tolist(), vote.pred.tolist()), 4),
            "video_vote_acc": round(float((vote.y == vote.pred).mean()), 4)}


def main():
    merged, meta, out = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    workers = int(sys.argv[4]) if len(sys.argv) > 4 else 4
    out.mkdir(parents=True, exist_ok=True)
    tri = {}
    for f in sorted(glob.glob(str(ROOT / "work/nexar_v2/triage_results/group_*.json"))):
        for r in json.load(open(f, encoding="utf-8")):
            tri[r["video_id"]] = r
    m = pd.read_csv(merged, dtype={"video_id": str}).set_index("video_id")
    me = pd.read_csv(meta, dtype={"video_id": str}).set_index("video_id")
    sel = []
    for vid, r in sorted(tri.items()):
        if r["side"] not in ("LEFT", "RIGHT") or r["contact"] not in ("yes", "uncertain"):
            continue
        es = m.entry_side.get(vid) if vid in m.index else None
        if isinstance(es, str) and es in ("LEFT", "RIGHT"):
            continue
        sel.append((vid, r))
    rng = np.random.RandomState(0)
    jobs, info = [], {}
    for vid, r in sel:
        mr = me.loc[vid]
        fps, anchor, n = float(mr.fps), int(mr.nexar_event_frame), int(mr.decoded_frames)
        step, wins, tries = fps / HZ, [], 0
        while len(wins) < K and tries < 200:
            tries += 1
            p, u = int(rng.randint(0, T)), float(rng.uniform(-0.5, 0.5))
            idx = [int(round(anchor + (k - p + u) * step)) for k in range(T)]
            if idx[0] < max(0, int(anchor - PRE * fps)) or idx[-1] >= n:
                continue
            wins.append((len(wins), idx))
        jobs.append((vid, mr.source_path, fps, anchor, wins))
        info[vid] = {"y": r["side"], "contact": r["contact"], "triage_conf": r.get("confidence")}
    rows = []
    with Pool(workers) as pool:
        for res in pool.imap_unordered(work, jobs):
            for vid, win, c, pred, feat in res:
                rows.append({"video_id": vid, "win": win, "contact": info[vid]["contact"], "y": info[vid]["y"],
                             "triage_conf": info[vid]["triage_conf"], "pred_collision": c, "pred": pred, "obj_u_L10": feat})
            print(res[0][0], flush=True)
    df = pd.DataFrame(rows).sort_values(["video_id", "win"])
    df.to_csv(out / "predictions.csv", index=False)
    ok = df[df.pred.notna()]
    integ = {"selected_videos": len(sel), "windows_expected": sum(len(j[4]) for j in jobs), "windows_scored": len(ok),
             "dup_rows": int(df.duplicated(["video_id", "win"]).sum()),
             "overlap_with_12C_side_set": 0}
    rep = {"design": __doc__.split("Usage")[0].strip(), "integrity": integ,
           "primary_all": evaluate(ok), "contact_yes": evaluate(ok[ok.contact == "yes"]),
           "contact_uncertain": evaluate(ok[ok.contact == "uncertain"])}
    for k in ("primary_all", "contact_yes", "contact_uncertain"):
        rep[k]["integrity"] = integ["dup_rows"] == 0 and integ["windows_scored"] == integ["windows_expected"]
    (out / "report.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({k: rep[k] for k in rep if k != "design"}, indent=1, default=str))


if __name__ == "__main__":
    main()
