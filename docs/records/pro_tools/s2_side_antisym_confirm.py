"""Pre-registered confirm test of the flip-antisymmetric side probe (s2_side_flip_audit).

Fixed BEFORE looking at confirm results (cycle a125b110ab85):
  window  = 8 frames linspace(c-45, c) at 30 fps (c = collision frame; v7: collision_frame,
            else entry_frame+30; confirm: nexar_event_frame)
  feature = D = mean_t f(x_t) - mean_t f(hflip x_t), f = ResNet18 IMAGENET1K_V1 GAP
  probe   = dual ridge lam=100 on standardised D, trained on all v7 side videos with flip
            augmentation (-D, 1-y); score > train prior -> RIGHT
  test    = 80 confirm videos of work/s2_side_confirm_r1 (triage side, unused by 12-C / v7)
  pass    = AUROC>0.5 with one-sided label-permutation p<0.05 (2000) AND Macro-F1 CI low > const LB
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "work/pro_tools"))
sys.path.insert(0, str(ROOT / "src"))
from s2_side_flip_audit import frames_for, auroc  # noqa: E402
from s2_side_flip_null import fit_score  # noqa: E402
from afda.models import build_stage2_backbone  # noqa: E402
from afda.preprocess import stage2_transform  # noqa: E402
from PIL import Image  # noqa: E402

OUT = ROOT / "work/s2_side_antisym_confirm"


def macro_f1(y, p):
    f = []
    for c in (0, 1):
        tp = ((p == c) & (y == c)).sum(); fp = ((p == c) & (y != c)).sum(); fn = ((p != c) & (y == c)).sum()
        f.append(0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn))
    return float(np.mean(f))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(4)
    from torchvision.models import ResNet18_Weights
    bb = build_stage2_backbone()
    bb.load_state_dict(ResNet18_Weights.IMAGENET1K_V1.get_state_dict(progress=False), strict=False)
    bb.eval(); tf = stage2_transform()

    def D_of(path, c, n):
        c = int(min(max(c, 45), n - 1))
        idx = np.linspace(c - 45, c, 8).round().astype(int)
        ims = frames_for(path, idx)
        if len(ims) != 8:
            return None
        with torch.inference_mode():
            a = bb(torch.stack([tf(Image.fromarray(im)) for im in ims])).numpy().mean(0)
            b = bb(torch.stack([tf(Image.fromarray(np.ascontiguousarray(im[:, ::-1]))) for im in ims])).numpy().mean(0)
        return a - b

    v7 = pd.read_csv(ROOT / "work/agent/outbox/stage2_labels_v7_files/stage2_merged_v7.csv", dtype={"video_id": str})
    v7 = v7[v7.side_valid == 1]
    Xtr, ytr, src = [], [], []
    for _, r in v7.iterrows():
        c = r.collision_frame if pd.notna(r.collision_frame) else r.entry_frame + 30
        d = D_of(ROOT / r.source_path, c, int(r.decoded_frames))
        if d is not None:
            Xtr.append(d); ytr.append(1 if r.entry_side == "RIGHT" else 0); src.append(r.label_source)
    Xtr, ytr = np.array(Xtr), np.array(ytr)

    conf = pd.read_csv(ROOT / "work/s2_side_confirm_r1/predictions.csv", dtype={"video_id": str})
    conf = conf.drop_duplicates("video_id")[["video_id", "y", "contact"]]
    overlap = sorted(set(conf.video_id) & set(v7.video_id))
    conf = conf[~conf.video_id.isin(overlap)]
    meta = pd.read_csv(ROOT / "work/nexar_v2/meta.csv", dtype={"video_id": str}).set_index("video_id")
    Xte, yte, ids, contact = [], [], [], []
    for _, r in conf.iterrows():
        m = meta.loc[r.video_id]
        d = D_of(ROOT / m.source_path, int(m.nexar_event_frame), int(m.decoded_frames))
        if d is not None:
            Xte.append(d); yte.append(1 if r.y == "RIGHT" else 0); ids.append(r.video_id); contact.append(r.contact)
    Xte, yte = np.array(Xte), np.array(yte)

    Xa = np.vstack([Xtr, -Xtr]); ya = np.concatenate([ytr, 1 - ytr]).astype(float)
    s = fit_score(Xa, ya, Xte, 100.0)
    pred = (s > ya.mean()).astype(int)
    rng = np.random.RandomState(0)
    a = auroc(yte, s); f1 = macro_f1(yte, pred)
    perm_a = np.array([auroc(rng.permutation(yte), s) for _ in range(2000)])
    perm_f = np.array([macro_f1(rng.permutation(yte), pred) for _ in range(2000)])
    bs = []
    for _ in range(2000):
        i = rng.randint(0, len(yte), len(yte)); bs.append(macro_f1(yte[i], pred[i]))
    maj = max(yte.mean(), 1 - yte.mean())
    const_lb = float(macro_f1(yte, np.full_like(yte, int(yte.mean() >= 0.5))))
    rep = {"n_train": int(len(ytr)), "train_right": int(ytr.sum()), "train_sources": pd.Series(src).value_counts().to_dict(),
           "n_confirm": int(len(yte)), "confirm_right": int(yte.sum()), "overlap_excluded": overlap,
           "auroc": a, "auroc_perm_p_high": float((1 + (perm_a >= a).sum()) / 2001),
           "macro_f1": f1, "macro_f1_ci": [float(np.quantile(bs, .025)), float(np.quantile(bs, .975))],
           "macro_f1_perm_p": float((1 + (perm_f >= f1).sum()) / 2001),
           "const_lb": const_lb, "majority_share": float(maj), "pred_right_share": float(pred.mean()),
           "acc": float((pred == yte).mean())}
    for cval in ("yes", "uncertain"):
        k = np.array(contact) == cval
        if k.sum() > 3 and 0 < yte[k].sum() < k.sum():
            rep[f"auroc_contact_{cval}"] = auroc(yte[k], s[k]); rep[f"n_contact_{cval}"] = int(k.sum())
    rep["pass"] = bool(a > 0.5 and rep["auroc_perm_p_high"] < 0.05 and rep["macro_f1_ci"][0] > const_lb)
    pd.DataFrame({"video_id": ids, "y_right": yte, "score": s, "pred_right": pred, "contact": contact}).to_csv(OUT / "predictions.csv", index=False)
    (OUT / "report.json").write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    print(json.dumps(rep, indent=1, default=str))


if __name__ == "__main__":
    main()
