"""S2 scene-head video-unit 5-fold CV → out-of-fold (OOF) prediction CSV.

Implements the CV that feeds the pre-registered 4-condition scene gate
(decision 8c33234b, supersedes 9bb29d60). Labor split: Ultra (this script)
trains the scene head per fold on GPU and emits the OOF prediction CSV; Pro
independently recomputes the bootstrap CI / permutation-null / AUROC from that
CSV. This script ALSO computes the 4 conditions inline as a cross-check, but the
CSV is the authoritative hand-off (columns match the accepted contract).

Gate (decision 8c33234b), per head (evasion, side) independently:
  1. OOF Macro-F1 bootstrap 95% CI lower (video resample, 2000x, seed0)
     > constant lower bound (evasion all-1 = 0.3939, side all-RIGHT = 0.3462).
  2. mode(pred) ratio <= 0.90 (class-collapse guard).
  3. permutation-null p < 0.05: keep the prediction MULTISET, shuffle only the
     video<->true pairing (2000x, seed0). Practical OOF Macro-F1 ~0.63-0.65 at
     n=40/51 (matches Pro's selftest: random p=0.18/0.066, oracle p=0.0005).
  4. integrity: each head's v7 scene-labelled video is OOF exactly once.
AND of all four -> graft that head from e006 into v001; else keep v001.

Recipe per fold mirrors e006 EXACTLY (full-clip path, no resample/window/prior):
random_time_crop(crop=None), full-sequence evaluate at ARGMAX collision/entry
positions (deployment-faithful, matches train_stage2.evaluate). Fixed epoch
budget (default 12, ~e006 scene-F1 peak epoch 10-11) applied identically to
every fold and to the permutation null via Pro -> no per-fold cherry-picking.

CSV columns: model,head,video_id,fold,true,pred,prob  (prob = P(class==1);
evasion 1 = space available, side 1 = RIGHT). Labels are agent+human v7 PROXY
(NOT official GT); LB S2 remains the final arbiter.

Usage:
  python scripts/cv_stage2_scene.py --cache data/derived/s2_feat_cache_v7 \
      --folds 5 --epochs 12 --seed 0 --model-tag e006cv \
      --out-csv work/s2_scene_cv/oof.csv --out-json work/s2_scene_cv/report.json
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from afda.models import Stage2Temporal  # noqa: E402
from afda import metrics as afda_metrics  # noqa: E402
from train_stage2 import (  # noqa: E402
    load_cache, class_weights, random_time_crop, _logits, _scene,
)

CONST_LB = {"evasion": 0.3939, "side": 0.3462}  # decision 8c33234b constant lower bounds


def build_folds(items, n_folds, seed):
    """Assign each SCENE-labelled video to exactly one fold (video-unit, seed0).

    Union of evasion|side labelled videos. Non-scene videos never held out (they
    carry no scene label to OOF-score) and always train the backbone.
    """
    scene_ids = sorted({it["video_id"] for it in items
                        if it["evasion"] is not None or it["side"] is not None})
    rng = np.random.RandomState(seed)
    order = list(scene_ids)
    rng.shuffle(order)
    fold_of = {vid: (i % n_folds) for i, vid in enumerate(order)}
    return fold_of, scene_ids


def train_fold(train_items, epochs, lr, wd, grad_accum, seed, device, amp):
    """Train a full Stage2Temporal on train_items (e006 full-clip recipe)."""
    torch.manual_seed(seed)
    np.random.seed(seed)
    rng = np.random.RandomState(seed)
    ev_labels = [it["evasion"] for it in train_items if it["evasion"] is not None]
    sd_labels = [it["side"] for it in train_items if it["side"] is not None]
    ev_w = class_weights(ev_labels, 2).to(device) if ev_labels else None
    sd_w = class_weights(sd_labels, 2).to(device) if sd_labels else None

    model = Stage2Temporal().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=wd)
    scaler = torch.amp.GradScaler("cuda", enabled=amp)
    ce = nn.CrossEntropyLoss()
    grad_accum = max(1, int(grad_accum))

    for _ in range(int(epochs)):
        model.train()
        opt.zero_grad(set_to_none=True)
        order = list(range(len(train_items)))
        rng.shuffle(order)
        for step, i in enumerate(order):
            it = train_items[i]
            feats, c_tgt, e_tgt = random_time_crop(
                it["feats"], it["collision"], it["entry"], None, rng, bias=None)
            x = torch.from_numpy(feats).unsqueeze(0).to(device)
            with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=amp):
                h, cl, el = _logits(model, x)
                loss = torch.zeros((), device=device)
                if c_tgt is not None:
                    loss = loss + ce(cl, torch.tensor([c_tgt], device=device))
                if e_tgt is not None:
                    loss = loss + ce(el, torch.tensor([e_tgt], device=device))
                c_idx = c_tgt if c_tgt is not None else int(cl.argmax(1))
                e_idx = e_tgt if e_tgt is not None else int(el.argmax(1))
                scene = _scene(model, h, c_idx, e_idx)
                if it["evasion"] is not None:
                    loss = loss + nn.functional.cross_entropy(
                        scene[:, :2], torch.tensor([it["evasion"]], device=device), weight=ev_w)
                if it["side"] is not None:
                    loss = loss + nn.functional.cross_entropy(
                        scene[:, 2:], torch.tensor([it["side"]], device=device), weight=sd_w)
            scaler.scale(loss / grad_accum).backward()
            if (step + 1) % grad_accum == 0:
                scaler.step(opt); scaler.update()
                opt.zero_grad(set_to_none=True)
    return model


@torch.inference_mode()
def predict_oof(model, held_items, device, amp):
    """Argmax-position scene predictions for held-out videos (deployment-faithful)."""
    model.eval()
    rows = []
    for it in held_items:
        x = torch.from_numpy(it["feats"]).unsqueeze(0).to(device)
        with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=amp):
            h, cl, el = _logits(model, x)
        c_pred, e_pred = int(cl.argmax(1)), int(el.argmax(1))
        scene = _scene(model, h.float(), c_pred, e_pred)
        ev_logits = scene[:, :2].float().softmax(1).cpu().numpy().ravel()
        sd_logits = scene[:, 2:].float().softmax(1).cpu().numpy().ravel()
        if it["evasion"] is not None:
            rows.append({"head": "evasion", "video_id": it["video_id"],
                         "true": int(it["evasion"]), "pred": int(ev_logits.argmax()),
                         "prob": float(ev_logits[1])})
        if it["side"] is not None:
            rows.append({"head": "side", "video_id": it["video_id"],
                         "true": int(it["side"]), "pred": int(sd_logits.argmax()),
                         "prob": float(sd_logits[1])})
    return rows


def macro_f1(t, p):
    return afda_metrics.macro_f1(list(t), list(p), labels=[0, 1])


def gate_for_head(rows, head, seed):
    """Compute the 4 gate conditions for one head from its OOF rows."""
    hr = [r for r in rows if r["head"] == head]
    t = np.array([r["true"] for r in hr]); p = np.array([r["pred"] for r in hr])
    n = len(hr)
    oof_f1 = macro_f1(t, p)
    # (1) bootstrap CI over videos
    rng = np.random.RandomState(seed)
    boots = []
    for _ in range(2000):
        idx = rng.randint(0, n, n)
        boots.append(macro_f1(t[idx], p[idx]))
    ci_lo, ci_hi = float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))
    # (2) mode ratio of predictions
    _, cnts = np.unique(p, return_counts=True)
    mode_ratio = float(cnts.max() / n)
    # (3) permutation null: keep pred multiset, shuffle true<->pred pairing
    rng2 = np.random.RandomState(seed)
    null = []
    for _ in range(2000):
        perm = rng2.permutation(n)
        null.append(macro_f1(t, p[perm]))
    null = np.array(null)
    p_perm = float((null >= oof_f1).mean())
    lb = CONST_LB[head]
    cond1 = ci_lo > lb
    cond2 = mode_ratio <= 0.90
    cond3 = p_perm < 0.05
    return {
        "head": head, "n": n, "oof_macro_f1": oof_f1,
        "bootstrap_ci95": [ci_lo, ci_hi], "const_lb": lb,
        "mode_ratio": mode_ratio,
        "perm_null_mean": float(null.mean()), "perm_null_q95": float(np.percentile(null, 95)),
        "perm_p": p_perm,
        "true_class1_ratio": float(t.mean()), "pred_class1_ratio": float(p.mean()),
        "cond1_ci_gt_const": bool(cond1), "cond2_mode_le_090": bool(cond2),
        "cond3_perm_p_lt_005": bool(cond3),
        "gate_pass_3stat": bool(cond1 and cond2 and cond3),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", type=Path, default=ROOT / "data/derived/s2_feat_cache_v7")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--wd", type=float, default=1e-4)
    ap.add_argument("--grad-accum", type=int, default=8)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--model-tag", default="e006cv")
    ap.add_argument("--out-csv", type=Path, default=ROOT / "work/s2_scene_cv/oof.csv")
    ap.add_argument("--out-json", type=Path, default=ROOT / "work/s2_scene_cv/report.json")
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    amp = device.type == "cuda"
    items = load_cache(args.cache, "train", None) + load_cache(args.cache, "validation", None)
    by_id = {it["video_id"]: it for it in items}
    fold_of, scene_ids = build_folds(items, args.folds, args.seed)
    n_ev = sum(1 for it in items if it["evasion"] is not None)
    n_sd = sum(1 for it in items if it["side"] is not None)
    print(f"cache={args.cache.name} total={len(items)} scene_videos={len(scene_ids)} "
          f"evasion={n_ev} side={n_sd} folds={args.folds} epochs={args.epochs} device={device}",
          flush=True)

    all_rows = []
    for f in range(args.folds):
        held_ids = [vid for vid in scene_ids if fold_of[vid] == f]
        held = [by_id[vid] for vid in held_ids]
        train_items = [it for it in items if it["video_id"] not in set(held_ids)
                       and any(it[k] is not None for k in ("collision", "entry", "evasion", "side"))]
        t0 = time.time()
        model = train_fold(train_items, args.epochs, args.lr, args.wd, args.grad_accum,
                           args.seed, device, amp)
        rows = predict_oof(model, held, device, amp)
        for r in rows:
            r["model"] = args.model_tag; r["fold"] = f
        all_rows.extend(rows)
        del model
        if device.type == "cuda":
            torch.cuda.empty_cache()
        print(f"fold {f}: held={len(held)} train={len(train_items)} rows={len(rows)} "
              f"{round(time.time()-t0,1)}s", flush=True)

    # integrity: each scene-labelled video OOF exactly once per head
    integ = {}
    for head in ("evasion", "side"):
        vids = [r["video_id"] for r in all_rows if r["head"] == head]
        expect = sorted(it["video_id"] for it in items
                        if (it["evasion"] if head == "evasion" else it["side"]) is not None)
        integ[head] = bool(sorted(vids) == expect and len(vids) == len(set(vids)))

    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["model", "head", "video_id", "fold", "true", "pred", "prob"])
        w.writeheader()
        for r in all_rows:
            w.writerow({k: r[k] for k in w.fieldnames})

    gates = {}
    for head in ("evasion", "side"):
        g = gate_for_head(all_rows, head, args.seed)
        g["integrity"] = integ[head]
        g["gate_pass"] = bool(g["gate_pass_3stat"] and integ[head])
        gates[head] = g
        print(f"GATE[{head}]: oof_f1={g['oof_macro_f1']:.3f} ci={g['bootstrap_ci95']} "
              f"mode={g['mode_ratio']:.3f} perm_p={g['perm_p']:.4f} "
              f"pass={g['gate_pass']}", flush=True)

    out = {
        "cache": str(args.cache), "model_tag": args.model_tag,
        "folds": args.folds, "epochs": args.epochs, "seed": args.seed,
        "scene_videos": len(scene_ids), "n_evasion": n_ev, "n_side": n_sd,
        "gates": gates,
        "label_source": "agent+human v7 proxy (NOT official GT); LB S2 final arbiter",
        "note": "Ultra OOF CSV for decision 8c33234b; Pro recomputes CI/perm/AUROC independently.",
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {args.out_csv} and {args.out_json}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
