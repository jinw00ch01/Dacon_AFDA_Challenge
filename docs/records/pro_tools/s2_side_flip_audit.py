"""S2 side left/right audit (result c60576a3 requests_to_pro #2).

Questions:
  1. Label encoding/convention: v7 side labels by source, human vs agent agreement
     on videos labelled by both (agent CSV vs v7 human rows).
  2. Feature flip-invariance: frozen ResNet18 IMAGENET1K_V1 + GAP (the e001/e006
     cache backbone, stage2_transform). If f(hflip x) ~= f(x), a head on these
     features cannot learn LEFT/RIGHT from geometry, so train separation (0.985)
     must be memorised video identity and OOF sign is noise/prior artifact.
  3. Linear probe on per-video mean features (entry..collision frames), leave-one-
     video-out: plain vs flip-augmented (add f(flip x) with swapped label). Also the
     pairs test: any function g(f) scores exactly 0.5 on {x, flip x} pairs if f is
     flip-invariant; we measure how far from that the probe gets.

Usage: python s2_side_flip_audit.py --out work/s2_side_flip_audit
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from afda.models import build_stage2_backbone  # noqa: E402
from afda.preprocess import stage2_transform  # noqa: E402

V7 = ROOT / "work/agent/outbox/stage2_labels_v7_files/stage2_merged_v7.csv"
AGENT = ROOT / "data/derived/labels/agent/stage2_agent_labels.csv"


def auroc(y, s):
    y = np.asarray(y); s = np.asarray(s, float)
    pos, neg = s[y == 1], s[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    gt = (pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()
    return float(gt / (len(pos) * len(neg)))


def frames_for(path, idxs):
    cap = cv2.VideoCapture(str(path))
    out = []
    for i in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, fr = cap.read()
        if not ok:
            continue
        out.append(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB))
    cap.release()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="work/s2_side_flip_audit")
    ap.add_argument("--n-frames", type=int, default=8)
    args = ap.parse_args()
    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(4)

    v7 = pd.read_csv(V7, dtype={"video_id": str})
    sd = v7[v7.side_valid == 1].copy()
    rep = {"n_side_v7": int(len(sd)),
           "by_source_side": {f"{k[0]}|{k[1]}": int(v) for k, v in sd.groupby(["label_source", "entry_side"]).size().items()}}

    # 1. human vs agent agreement
    ag = pd.read_csv(AGENT, dtype={"video_id": str})
    ag = ag[ag.get("entry_side").notna()] if "entry_side" in ag else ag.iloc[0:0]
    hum = sd[sd.label_source == "human"][["video_id", "entry_side"]]
    j = hum.merge(ag[["video_id", "entry_side"]].drop_duplicates("video_id", keep="last"),
                  on="video_id", suffixes=("_human", "_agent"))
    rep["human_vs_agent"] = {"n_overlap": int(len(j)),
                             "agree": int((j.entry_side_human == j.entry_side_agent).sum()),
                             "rows": j.to_dict("records")}

    # 2/3. features
    from torchvision.models import ResNet18_Weights
    bb = build_stage2_backbone()
    bb.load_state_dict(ResNet18_Weights.IMAGENET1K_V1.get_state_dict(progress=False), strict=False)
    bb.eval()
    tf = stage2_transform()

    def feats(imgs):
        x = torch.stack([tf(Image.fromarray(im)) for im in imgs])
        with torch.inference_mode():
            return bb(x).numpy()

    vids, ys, F, Ff, adj_cos, flip_cos, adj_d, flip_d, norms = [], [], [], [], [], [], [], [], []
    for _, r in sd.iterrows():
        c = r.collision_frame if pd.notna(r.collision_frame) else None
        e = r.entry_frame if pd.notna(r.entry_frame) else None
        n = int(r.decoded_frames)
        if c is None and e is None:
            continue
        a = int(e) if e is not None else int(c) - 45
        b = int(c) if c is not None else int(e) + 30
        a, b = max(0, min(a, b - 8)), min(n - 2, max(b, a + 8))
        idxs = np.linspace(a, b, args.n_frames).round().astype(int)
        imgs = frames_for(ROOT / r.source_path, idxs)
        nxt = frames_for(ROOT / r.source_path, idxs + 1)
        if len(imgs) != len(idxs) or len(nxt) != len(idxs):
            continue
        f0 = feats(imgs)
        ff = feats([np.ascontiguousarray(im[:, ::-1]) for im in imgs])
        f1 = feats(nxt)
        cos = lambda p, q: (p * q).sum(1) / (np.linalg.norm(p, axis=1) * np.linalg.norm(q, axis=1))
        flip_cos += list(cos(f0, ff)); adj_cos += list(cos(f0, f1))
        flip_d += list(np.linalg.norm(f0 - ff, axis=1)); adj_d += list(np.linalg.norm(f0 - f1, axis=1))
        norms += list(np.linalg.norm(f0, axis=1))
        vids.append(r.video_id); ys.append(1 if r.entry_side == "RIGHT" else 0)
        F.append(f0.mean(0)); Ff.append(ff.mean(0))
    F, Ff, ys = np.array(F), np.array(Ff), np.array(ys)
    mu = F.mean(0)
    between_d = float(np.median(np.linalg.norm(F - mu, axis=1)))
    rep["invariance"] = {
        "n_videos": len(vids), "frames_per_video": args.n_frames,
        "cos_flip_median": float(np.median(flip_cos)), "cos_adjacent_frame_median": float(np.median(adj_cos)),
        "dist_flip_median": float(np.median(flip_d)), "dist_adjacent_frame_median": float(np.median(adj_d)),
        "dist_videomean_to_center_median": between_d,
        "feat_norm_median": float(np.median(norms)),
        "videomean_flip_dist_median": float(np.median(np.linalg.norm(F - Ff, axis=1))),
    }
    # antisymmetric component: side-relevant info must live in f(x)-f(flip x)
    D = F - Ff
    rep["invariance"]["antisym_energy_share"] = float((D ** 2).sum() / (((F - mu) ** 2).sum() + 1e-9))

    np.savez(out / "feats.npz", F=F, Ff=Ff, ys=ys, vids=np.array(vids))

    class StandardScaler:
        def fit(self, X):
            self.m, self.s = X.mean(0), X.std(0) + 1e-6
            return self

        def transform(self, X):
            return (X - self.m) / self.s

    class LogisticRegression:
        """L2 logistic (sklearn-style C) fit by full-batch LBFGS in torch."""
        def __init__(self, C=0.1, max_iter=200):
            self.C, self.it = C, max_iter

        def fit(self, X, y):
            X = torch.tensor(X, dtype=torch.float64); y = torch.tensor(y, dtype=torch.float64)
            w = torch.zeros(X.shape[1], dtype=torch.float64, requires_grad=True)
            b = torch.zeros(1, dtype=torch.float64, requires_grad=True)
            opt = torch.optim.LBFGS([w, b], max_iter=self.it, line_search_fn="strong_wolfe")

            def closure():
                opt.zero_grad()
                z = X @ w + b
                loss = torch.nn.functional.binary_cross_entropy_with_logits(z, y, reduction="sum") + 0.5 / self.C * (w ** 2).sum()
                loss.backward()
                return loss
            opt.step(closure)
            self.w, self.b = w.detach().numpy(), float(b.detach())
            return self

        def predict_proba(self, X):
            p = 1 / (1 + np.exp(-(X @ self.w + self.b)))
            return np.stack([1 - p, p], 1)

    def lovo(aug, feat_kind="raw", C=0.1):
        s_orig, s_flip = np.zeros(len(ys)), np.zeros(len(ys))
        for i in range(len(ys)):
            tr = np.arange(len(ys)) != i
            X = F[tr] if feat_kind == "raw" else D[tr]
            y = ys[tr]
            if aug:
                X2 = Ff[tr] if feat_kind == "raw" else -D[tr]
                X = np.vstack([X, X2]); y = np.concatenate([y, 1 - y])
            sc = StandardScaler().fit(X)
            m = LogisticRegression(C=C, max_iter=2000).fit(sc.transform(X), y)
            xi = F[i:i + 1] if feat_kind == "raw" else D[i:i + 1]
            xf = Ff[i:i + 1] if feat_kind == "raw" else -D[i:i + 1]
            s_orig[i] = m.predict_proba(sc.transform(xi))[0, 1]
            s_flip[i] = m.predict_proba(sc.transform(xf))[0, 1]
        pair_acc = float(np.mean(np.where(ys == 1, s_orig > s_flip, s_flip > s_orig)))
        return {"lovo_auroc_orig": auroc(ys, s_orig),
                "pairs_acc_orig_vs_flip": pair_acc,
                "mean_abs_score_change_on_flip": float(np.mean(np.abs(s_orig - s_flip)))}

    rep["probe"] = {"raw_plain": lovo(False), "raw_flipaug": lovo(True),
                    "antisym_plain": lovo(False, "antisym"), "antisym_flipaug": lovo(True, "antisym")}
    rep["n_right"] = int(ys.sum()); rep["n_left"] = int(len(ys) - ys.sum())
    (out / "report.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    pd.DataFrame({"video_id": vids, "side_right": ys}).to_csv(out / "videos.csv", index=False)
    print(json.dumps({k: v for k, v in rep.items() if k != "human_vs_agent"}, indent=1, default=str))
    print("human_vs_agent", rep["human_vs_agent"]["n_overlap"], rep["human_vs_agent"]["agree"])


if __name__ == "__main__":
    main()
