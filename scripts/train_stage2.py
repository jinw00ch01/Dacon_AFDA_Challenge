"""Train the Stage 2 BiGRU temporal head from cached ResNet18 features.

Matches inference (submission/inference.py ``predict_stage2`` /
src/afda/models.Stage2Temporal): a BiGRU runs over the per-frame 512-d ResNet18
feature sequence; ``tc``/``te`` give a per-frame logit whose argmax is the
predicted collision / entry frame; the ``scene`` head (fed the hidden states at
those two frames) predicts evasion_space (2-way) and entry_side (LEFT/RIGHT).
``scripts/cache_s2_features.py`` cached one (T,512) sequence per video with row
i == frame index i, so the label ``collision_frame`` / ``entry_frame`` is the
target position directly.

Training loss (per video, batch=1 because T varies):
  - collision: CrossEntropy over the T positions, target=collision_frame, only
    when collision_valid==1.
  - entry: same, target=entry_frame, only when entry_valid==1.
  - scene: hidden states gathered at the GROUND-TRUTH collision/entry positions
    (teacher forcing; falls back to argmax when a position label is absent);
    evasion CE when evasion_valid==1, side CE when side_valid==1.
Videos with zero valid targets (e.g. negatives) contribute no gradient and are
skipped in training -- the head has no "no-collision" output. Recorded, not hidden.

Validation reports time error in SECONDS (the eval metric converts frames->sec):
collision/entry mean-abs-error/fps, plus evasion/side accuracy. best.pt is the
epoch with the lowest mean time MAE. Checkpoint saved as {"model": state_dict}
so the submission loads it unchanged.

Proxy agent labels are NOT official GT (AGENTS.md); numbers are self-diagnostic
and carry the label source.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from afda.models import Stage2Temporal  # noqa: E402

DEFAULTS = {
    "cache_dir": "data/derived/s2_feat_cache_v1",
    "epochs": 30,
    "lr": 1e-3,
    "weight_decay": 1e-4,
    "grad_accum": 8,
    "seed": 0,
    "amp": True,
    "out_dir": "models/stage2",
    "max_videos": None,
    # e002 single change: random temporal crop of the training feature sequence so
    # the absolute collision/entry position stops being a shortcut. None => no crop
    # (e001 behaviour). Eval always uses the full sequence, so the val metric stays
    # comparable across e001/e002.
    "train_crop_frames": None,
}


def _f(x):
    return None if x is None else float(x)


def load_cache(cache_dir: Path, split: str, max_videos=None):
    """Return list of dicts: feats (T,512 float32), fps, and int/None targets."""
    manifest = json.loads((cache_dir / "manifest.json").read_text(encoding="utf-8"))
    items = []
    for v in manifest["videos"]:
        if v["split"] != split:
            continue
        npy = cache_dir / f"{v['video_id']}.npy"
        if not npy.exists():
            continue
        feats = np.load(npy).astype(np.float32)
        t = feats.shape[0]

        def _pos(name, valid_key):
            if int(v.get(valid_key, 0)) != 1 or v.get(name) is None:
                return None
            p = int(round(float(v[name])))
            return int(np.clip(p, 0, t - 1))

        items.append({
            "video_id": v["video_id"],
            "feats": feats,
            "fps": float(v["fps"]),
            "collision": _pos("collision_frame", "collision_valid"),
            "entry": _pos("entry_frame", "entry_valid"),
            "evasion": int(v["evasion_space"]) if int(v.get("evasion_valid", 0)) == 1 and v.get("evasion_space") is not None else None,
            "side": (1 if v["entry_side"] == "RIGHT" else 0) if int(v.get("side_valid", 0)) == 1 and v.get("entry_side") is not None else None,
        })
        if max_videos and len(items) >= int(max_videos):
            break
    return items


def class_weights(labels, n_classes):
    counts = np.bincount(np.asarray(labels), minlength=n_classes).astype(np.float64)
    counts = np.where(counts == 0, 1.0, counts)
    w = counts.sum() / (n_classes * counts)
    return torch.tensor(w, dtype=torch.float32)


def random_time_crop(feats, collision, entry, crop_frames, rng):
    """Crop a random window of length ``crop_frames`` from a (T,512) feature seq.

    Removes the absolute-position shortcut: the window is placed so that a randomly
    chosen present target (collision/entry) stays inside it, and each target is
    remapped to the window-relative index (or dropped to None if it falls outside).
    Returns (cropped_feats, new_collision, new_entry). No-op when crop_frames is
    None/<=0 or T <= crop_frames, so e001 runs are unchanged.
    """
    t = feats.shape[0]
    if not crop_frames or crop_frames <= 0 or t <= crop_frames:
        return feats, collision, entry
    length = int(crop_frames)
    anchors = [p for p in (collision, entry) if p is not None]
    if anchors:
        anchor = anchors[int(rng.randint(len(anchors)))]
        lo = max(0, anchor - length + 1)
        hi = min(anchor, t - length)  # keep anchor inside [start, start+length)
        start = int(rng.randint(lo, hi + 1)) if hi >= lo else max(0, min(anchor, t - length))
    else:
        start = int(rng.randint(0, t - length + 1))
    end = start + length

    def _remap(p):
        if p is None:
            return None
        q = p - start
        return q if 0 <= q < length else None

    return feats[start:end], _remap(collision), _remap(entry)


def const_baseline(train_items, val_items):
    """Constant-position predictor MAE (seconds) using the train median position.

    The decision (823680cb) requires reporting this alongside the model: it is the
    score to beat. Predicts the train-median collision/entry frame for every val
    video (clipped to that video's length), converted to seconds by the video fps.
    """
    def _median(items, key):
        vals = [it[key] for it in items if it[key] is not None]
        return int(round(float(np.median(vals)))) if vals else None

    def _mae(pos, key):
        errs = []
        for it in val_items:
            if it[key] is None or pos is None:
                continue
            t = it["feats"].shape[0]
            errs.append(abs(int(np.clip(pos, 0, t - 1)) - it[key]) / it["fps"])
        return float(np.mean(errs)) if errs else None

    c_pos, e_pos = _median(train_items, "collision"), _median(train_items, "entry")
    c_mae, e_mae = _mae(c_pos, "collision"), _mae(e_pos, "entry")
    finite = [m for m in (c_mae, e_mae) if m is not None]
    return {
        "collision_frame": c_pos, "entry_frame": e_pos,
        "collision_mae_s": c_mae, "entry_mae_s": e_mae,
        "time_mae_s": (float(np.mean(finite)) if finite else None),
    }


def _logits(model, x):
    """Shared forward that returns per-frame logits + hidden (training path)."""
    h, _ = model.r(x)  # (1,T,384)
    collision = model.tc(h).squeeze(-1)  # (1,T)
    entry = model.te(h).squeeze(-1)
    return h, collision, entry


def _scene(model, h, c_idx, e_idx):
    scene_in = torch.cat([h[0, c_idx], h[0, e_idx]], dim=-1).unsqueeze(0)  # (1,768)
    return model.scene(scene_in)  # (1,4)


@torch.inference_mode()
def evaluate(model, items, device, amp):
    model.eval()
    c_err, e_err = [], []
    ev_t, ev_p, sd_t, sd_p = [], [], [], []
    for it in items:
        x = torch.from_numpy(it["feats"]).unsqueeze(0).to(device)
        with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=amp):
            h, cl, el = _logits(model, x)
        c_pred, e_pred = int(cl.argmax(1)), int(el.argmax(1))
        if it["collision"] is not None:
            c_err.append(abs(c_pred - it["collision"]) / it["fps"])
        if it["entry"] is not None:
            e_err.append(abs(e_pred - it["entry"]) / it["fps"])
        scene = _scene(model, h.float(), c_pred, e_pred)
        if it["evasion"] is not None:
            ev_t.append(it["evasion"]); ev_p.append(int(scene[:, :2].argmax(1)))
        if it["side"] is not None:
            sd_t.append(it["side"]); sd_p.append(int(scene[:, 2:].argmax(1)))
    mae = lambda xs: (float(np.mean(xs)) if xs else None)
    acc = lambda t, p: (float(np.mean(np.asarray(t) == np.asarray(p))) if t else None)
    c_mae, e_mae = mae(c_err), mae(e_err)
    finite = [m for m in (c_mae, e_mae) if m is not None]
    return {
        "n": len(items),
        "collision_mae_s": c_mae, "n_collision": len(c_err),
        "entry_mae_s": e_mae, "n_entry": len(e_err),
        "evasion_acc": acc(ev_t, ev_p), "n_evasion": len(ev_t),
        "side_acc": acc(sd_t, sd_p), "n_side": len(sd_t),
        "time_mae_s": (float(np.mean(finite)) if finite else None),
    }


def load_config(path):
    cfg = dict(DEFAULTS)
    if path:
        cfg.update(json.loads(Path(path).read_text(encoding="utf-8")))
    return cfg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=None)
    ap.add_argument("--out-dir", type=Path, default=None)
    args = ap.parse_args()
    cfg = load_config(args.config)
    out_dir = Path(args.out_dir or cfg["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    torch.manual_seed(cfg["seed"])
    np.random.seed(cfg["seed"])
    rng = np.random.RandomState(cfg["seed"])
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    amp = bool(cfg["amp"]) and device.type == "cuda"

    cache_dir = ROOT / cfg["cache_dir"]
    train_all = load_cache(cache_dir, "train", cfg["max_videos"])
    val_items = load_cache(cache_dir, "validation", cfg["max_videos"])
    # only videos with at least one valid target drive gradients
    train = [it for it in train_all if any(it[k] is not None for k in ("collision", "entry", "evasion", "side"))]
    if not train:
        raise SystemExit("no trainable videos; is the feature cache built?")
    print(f"train videos={len(train)} (of {len(train_all)}) val={len(val_items)} device={device} amp={amp}", flush=True)

    ev_labels = [it["evasion"] for it in train if it["evasion"] is not None]
    sd_labels = [it["side"] for it in train if it["side"] is not None]
    ev_w = class_weights(ev_labels, 2).to(device) if ev_labels else None
    sd_w = class_weights(sd_labels, 2).to(device) if sd_labels else None

    model = Stage2Temporal().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=cfg["lr"], weight_decay=cfg["weight_decay"])
    scaler = torch.amp.GradScaler("cuda", enabled=amp)
    ce = nn.CrossEntropyLoss()
    grad_accum = max(1, int(cfg["grad_accum"]))

    best = {"time_mae_s": float("inf")}
    history = []
    for epoch in range(int(cfg["epochs"])):
        model.train()
        optimizer.zero_grad(set_to_none=True)
        order = list(range(len(train)))
        rng.shuffle(order)
        running, start = 0.0, time.time()
        for step, i in enumerate(order):
            it = train[i]
            feats, c_tgt, e_tgt = random_time_crop(
                it["feats"], it["collision"], it["entry"], cfg["train_crop_frames"], rng)
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
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad(set_to_none=True)
            running += float(loss.detach())
        metrics = evaluate(model, val_items, device, amp) if val_items else {}
        metrics["epoch"] = epoch
        metrics["train_loss"] = running / max(1, len(train))
        metrics["seconds"] = round(time.time() - start, 1)
        history.append(metrics)
        print(f"epoch {epoch}: {json.dumps(metrics)}", flush=True)
        score = metrics.get("time_mae_s")
        if score is not None and score < best["time_mae_s"]:
            best = metrics
            torch.save(
                {
                    "model": model.state_dict(),
                    "val_metrics": metrics,
                    "label_source": "agent_labels_v6 (not official GT)",
                },
                out_dir / "best.pt",
            )
            print(f"  saved best.pt (time_mae_s={score:.3f})", flush=True)

    # Always leave a checkpoint even if validation had no time labels.
    if not (out_dir / "best.pt").exists():
        torch.save({"model": model.state_dict(), "val_metrics": history[-1] if history else {},
                    "label_source": "agent_labels_v6 (not official GT)"}, out_dir / "best.pt")
        print("  saved best.pt (final epoch; no val time labels)", flush=True)

    const = const_baseline(train, val_items) if val_items else None
    if const:
        print(f"const baseline (train-median position): {json.dumps(const)}", flush=True)
    summary = {
        "config": cfg,
        "train_videos": len(train),
        "val_videos": len(val_items),
        "best": best if best["time_mae_s"] != float("inf") else None,
        "const_baseline": const,
        "history": history,
        "label_source": "agent_labels_v6 (not official GT)",
    }
    (out_dir / "metrics.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote {out_dir / 'metrics.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
