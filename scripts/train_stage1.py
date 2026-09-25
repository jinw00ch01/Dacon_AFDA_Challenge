"""Train the Stage 1 screen-recapture discriminator (MViTv2-S, 2 classes).

Why this matches inference exactly (submission/inference.py ``predict_stage1``):
the eval server gives Stage 1 a video per ID and asks ORIGINAL vs RERECORDED.
Inference samples ``slots`` evenly spaced clips of ``frames`` frames at ``size``
(via ``clip_frame_ids`` + ``decode_stage1_clip``), softmaxes class 1 (RERECORDED)
per clip, and averages the per-clip probabilities per video (threshold 0.5). This
trainer reuses the SAME ``afda.preprocess`` decode helpers and the SAME
``build_stage1_model`` head, and stores ``{"model","size","frames"}`` so the
submission ``mvit_v2_s`` loads the checkpoint unchanged.

Data: the frozen ``s1-synth-v1`` release (manifest.csv pins per-file split/label).
label ``original`` -> class 0 (ORIGINAL), ``recapture_synthetic`` -> class 1
(RERECORDED). Split is per-source (16 train / 4 val / 4 test) so original and its
recaptures never straddle the split. These recaptures are SYNTHETIC (AGENTS.md):
every score here is reported as *synthetic*, not an official-GT measurement.

Config JSON (configs/exp/s1_e001.json) keys: manifest_csv, video_root, epochs,
batch_size, grad_accum, lr, weight_decay, seed, num_workers, size, frames, slots,
init_pretrained, amp, out_dir, max_train_batches.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from afda.models import build_stage1_model  # noqa: E402
from afda.preprocess import clip_frame_ids, decode_stage1_clip  # noqa: E402

# class 1 == RERECORDED (submission/inference.py thresholds softmax[:,1] >= 0.5)
LABEL_TO_CLASS = {"original": 0, "recapture_synthetic": 1}
CLASSES = ["ORIGINAL", "RERECORDED"]

DEFAULTS = {
    "manifest_csv": "data/derived/releases/s1-synth-v1-20260925/manifest.csv",
    "video_root": "data/derived/s1_synthetic_v1",
    "epochs": 3,
    "batch_size": 2,
    "grad_accum": 4,
    "lr": 2e-4,
    "weight_decay": 0.05,
    "seed": 0,
    "num_workers": 4,
    "size": 224,
    "frames": 16,
    "slots": 3,
    "init_pretrained": True,
    "amp": True,
    "out_dir": "models/stage1",
    "max_train_batches": None,
}


def read_split(manifest_csv, video_root, split):
    """Rows of the release for one split whose mp4 exists, with class + identity.
    Returns list of dicts: {file, source_id, path, label}."""
    df = pd.read_csv(manifest_csv)
    df = df[df["split"] == split]
    rows = []
    for _, r in df.iterrows():
        if r["label"] not in LABEL_TO_CLASS:
            raise ValueError(f"unknown label {r['label']!r} in manifest")
        path = Path(video_root) / str(r["file"])
        if not path.exists():
            continue
        rows.append(
            {
                "file": str(r["file"]),
                "source_id": str(r["source_id"]),
                "path": path,
                "label": LABEL_TO_CLASS[r["label"]],
            }
        )
    return rows


class S1ClipDataset(Dataset):
    """One item = one (video, slot) clip -> (3,frames,size,size) + class + video index.

    Every slot of a video is a separate training example (same evenly spaced clips
    inference averages over), so training and eval see the identical decode path.
    """

    def __init__(self, rows, size, frames, slots):
        self.size, self.frames, self.slots = int(size), int(frames), int(slots)
        self.rows = rows
        self.items = [(vi, slot) for vi in range(len(rows)) for slot in range(self.slots)]

    def __len__(self):
        return len(self.items)

    def __getitem__(self, index):
        video_index, slot = self.items[index]
        row = self.rows[video_index]
        ids = clip_frame_ids(row["path"], self.frames, slot, self.slots)
        clip = decode_stage1_clip(row["path"], self.size, ids)  # (3,frames,size,size)
        return clip, row["label"], video_index


def class_weights(labels, n_classes):
    counts = np.bincount(np.asarray(labels), minlength=n_classes).astype(np.float64)
    counts = np.where(counts == 0, 1.0, counts)
    weights = counts.sum() / (n_classes * counts)
    return torch.tensor(weights, dtype=torch.float32)


def macro_f1(true, pred, n_classes):
    true, pred = np.asarray(true), np.asarray(pred)
    f1s = []
    for c in range(n_classes):
        tp = int(((pred == c) & (true == c)).sum())
        fp = int(((pred == c) & (true != c)).sum())
        fn = int(((pred != c) & (true == c)).sum())
        denom = 2 * tp + fp + fn
        f1s.append(0.0 if denom == 0 else 2 * tp / denom)
    return float(np.mean(f1s))


def init_stage1(enabled):
    """MViTv2-S with a fresh 2-class head; kinetics400 backbone when available."""
    if not enabled:
        return build_stage1_model(), "scratch"
    try:
        from torchvision.models.video import MViT_V2_S_Weights, mvit_v2_s

        model = mvit_v2_s(weights=MViT_V2_S_Weights.KINETICS400_V1)
        model.head[1] = nn.Linear(model.head[1].in_features, 2)
        return model, "kinetics400"
    except Exception as exc:  # training-only init; a scratch start is still valid
        return build_stage1_model(), f"scratch (pretrained load failed: {exc})"


@torch.inference_mode()
def evaluate(model, loader, device, amp, rows):
    """Aggregate per-clip RERECORDED prob to a per-video mean (== inference), then
    threshold 0.5. Returns video-level metrics + per-video prediction records."""
    model.eval()
    prob_sum = np.zeros(len(rows), dtype=np.float64)
    prob_cnt = np.zeros(len(rows), dtype=np.int64)
    for clips, _labels, video_index in loader:
        with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=amp):
            prob = torch.softmax(model(clips.to(device, non_blocking=True)), 1)[:, 1]
        for vi, p in zip(video_index.tolist(), prob.float().cpu().tolist()):
            prob_sum[vi] += p
            prob_cnt[vi] += 1
    prob = np.where(prob_cnt > 0, prob_sum / np.maximum(prob_cnt, 1), 1.0)  # inference default 1.0
    pred = (prob >= 0.5).astype(int)
    true = np.array([r["label"] for r in rows], dtype=int)
    metrics = {
        "n_videos": len(rows),
        "macro_f1": macro_f1(true, pred, len(CLASSES)),
        "acc": float(np.mean(pred == true)) if len(true) else 0.0,
    }
    records = pd.DataFrame(
        {
            "file": [r["file"] for r in rows],
            "source_id": [r["source_id"] for r in rows],
            "split": "validation",
            "prob_rerecorded": prob,
            "pred": [CLASSES[i] for i in pred],
            "true": [CLASSES[i] for i in true],
        }
    )
    return metrics, records


def load_config(path):
    cfg = dict(DEFAULTS)
    if path:
        cfg.update(json.loads(Path(path).read_text(encoding="utf-8")))
    return cfg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=None)
    ap.add_argument("--out-dir", type=Path, default=None, help="override cfg out_dir (e.g. run dir)")
    args = ap.parse_args()
    cfg = load_config(args.config)
    out_dir = Path(args.out_dir or cfg["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    torch.manual_seed(cfg["seed"])
    np.random.seed(cfg["seed"])
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    amp = bool(cfg["amp"]) and device.type == "cuda"

    manifest_csv = ROOT / cfg["manifest_csv"]
    video_root = ROOT / cfg["video_root"]
    train_rows = read_split(manifest_csv, video_root, "train")
    val_rows = read_split(manifest_csv, video_root, "validation")
    if not train_rows:
        raise SystemExit("no train videos; is the s1-synth release present?")
    train_set = S1ClipDataset(train_rows, cfg["size"], cfg["frames"], cfg["slots"])
    val_set = S1ClipDataset(val_rows, cfg["size"], cfg["frames"], cfg["slots"])
    print(
        f"train videos={len(train_rows)} clips={len(train_set)} "
        f"val videos={len(val_rows)} clips={len(val_set)} device={device} amp={amp}",
        flush=True,
    )

    train_loader = DataLoader(
        train_set, batch_size=cfg["batch_size"], shuffle=True, drop_last=True,
        num_workers=cfg["num_workers"], pin_memory=(device.type == "cuda"),
    )
    val_loader = DataLoader(
        val_set, batch_size=cfg["batch_size"], shuffle=False,
        num_workers=cfg["num_workers"], pin_memory=(device.type == "cuda"),
    )

    model, init = init_stage1(cfg["init_pretrained"])
    model.to(device)
    print(f"backbone init: {init}", flush=True)

    weights = class_weights([r["label"] for r in train_rows], len(CLASSES)).to(device)
    criterion = nn.CrossEntropyLoss(weight=weights)
    optimizer = torch.optim.AdamW(model.parameters(), lr=cfg["lr"], weight_decay=cfg["weight_decay"])
    scaler = torch.amp.GradScaler("cuda", enabled=amp)
    grad_accum = max(1, int(cfg["grad_accum"]))

    best = {"macro_f1": -1.0}
    history = []
    for epoch in range(int(cfg["epochs"])):
        model.train()
        optimizer.zero_grad(set_to_none=True)
        start = time.time()
        running = 0.0
        step = -1
        for step, (clips, labels, _vi) in enumerate(train_loader):
            if cfg["max_train_batches"] and step >= int(cfg["max_train_batches"]):
                break
            clips = clips.to(device, non_blocking=True)
            labels = labels.to(device, non_blocking=True)
            with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=amp):
                loss = criterion(model(clips), labels) / grad_accum
            scaler.scale(loss).backward()
            if (step + 1) % grad_accum == 0:
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad(set_to_none=True)
            running += float(loss) * grad_accum
            if step % 20 == 0:
                print(f"  epoch {epoch} step {step} loss {float(loss) * grad_accum:.4f}", flush=True)
        if val_rows:
            metrics, records = evaluate(model, val_loader, device, amp, val_rows)
        else:
            metrics, records = {"macro_f1": -1.0}, None
        metrics["epoch"] = epoch
        metrics["train_loss"] = running / max(1, step + 1)
        metrics["seconds"] = round(time.time() - start, 1)
        history.append(metrics)
        print(f"epoch {epoch} done: {json.dumps(metrics)}", flush=True)
        if metrics.get("macro_f1", -1) > best["macro_f1"]:
            best = metrics
            if records is not None:
                records.to_csv(out_dir / "val_predictions.csv", index=False)
                print(f"  wrote val_predictions.csv ({len(records)} rows)", flush=True)
            torch.save(
                {
                    "model": model.state_dict(),
                    "size": int(cfg["size"]),
                    "frames": int(cfg["frames"]),
                    "classes": CLASSES,
                    "init": init,
                    "val_metrics": metrics,
                    "label_source": "s1_synthetic_v1 (synthetic recapture, not official GT)",
                },
                out_dir / "best.pt",
            )
            print(f"  saved best.pt (macro_f1={metrics['macro_f1']:.4f})", flush=True)

    summary = {
        "config": cfg,
        "train_videos": len(train_rows),
        "val_videos": len(val_rows),
        "init": init,
        "best": best,
        "history": history,
        "label_source": "s1_synthetic_v1 (synthetic recapture, not official GT)",
    }
    (out_dir / "metrics.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote {out_dir / 'metrics.json'}; best macro_f1={best['macro_f1']:.4f} (synthetic)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
