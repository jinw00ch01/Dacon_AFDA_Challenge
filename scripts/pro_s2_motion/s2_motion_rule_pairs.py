"""Decision 12-A follow-up: pairwise sums of per-window z-scored motion scores (FIT-selected), from r1 series.npz.
Usage: s2_motion_rule_pairs.py <rule_dir>"""
import itertools, json, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from s2_motion_rule import FEATS, scores, smooth, hit, T

d = Path(sys.argv[1])
w = pd.read_csv(d / "windows.csv", dtype={"video_id": str})
S = np.load(d / "series.npz")
sc = []
for r in w.itertuples():
    s = {f: S[f"{r.video_id}_{r.win}_{f}"] for f in FEATS}
    z = {}
    for k, x in scores(s).items():
        x = smooth(x, 1)
        z[k] = (x - x.mean()) / (x.std() + 1e-6)
    sc.append(z)
names = list(sc[0])
fit = np.where(w.group == "FIT")[0]; held = np.where(w.group == "HELD")[0]
def acc(ix, f, lag):
    return float(np.mean([hit(int(np.clip(np.argmax(f(sc[i])) + lag, 0, T - 1)), w.gt_collision[i]) for i in ix]))
grid = []
for a, b in itertools.combinations_with_replacement(names, 2):
    for wb in ((0.5, 1.0) if a != b else (0.0,)):
        f = lambda z, a=a, b=b, wb=wb: z[a] + wb * z[b]
        for lag in range(-4, 3):
            grid.append((acc(fit, f, lag), a, b, wb, lag))
grid.sort(reverse=True)
out = {"top_fit": grid[:8]}
_, a, b, wb, lag = grid[0]
f = lambda z: z[a] + wb * z[b]
preds = np.array([int(np.clip(np.argmax(f(sc[i])) + lag, 0, T - 1)) for i in range(len(w))])
w["pred_pair"] = preds
h = w.iloc[held]
for name, sub in [("all", h), ("human", h[h.label_source == "human"]), ("e001_clean", h[h.e001_clean == 1]),
                  ("v1", h[h.src == "v1"]), ("v2", h[h.src == "v2"])]:
    out[name] = {"n": len(sub), "pair": round(float(np.mean([hit(p, g) for p, g in zip(sub.pred_pair, sub.gt_collision)])), 4),
                 "rule_r1": round(float(np.mean([hit(p, g) for p, g in zip(sub.pred_rule, sub.gt_collision)])), 4)}
print(json.dumps(out, indent=1))
(d / "pairs.json").write_text(json.dumps(out, indent=1))
