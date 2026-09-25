"""Train the Stage 3 accel/steer MViTv2-S from the 10Hz clip cache.

Why this matches inference exactly (docs/STATUS.md, submission/inference.py):
the eval server feeds Stage 3 a 10Hz video and asks for a class per 0.1s
sample. ``scripts/cache_s3_clips.py`` already decoded each comma source with the
eval decoder and decimated to 10Hz, so cache row position == eval sample_index.
For sample position ``p`` we build the SAME 16-frame window inference uses --
``clip(p - 8 + arange(16), 0, T-1)`` -> (3,16,224,224) normalized with the shared
S3 mean/std -- and the proxy target is ``stage3_labels`` v1b for that row. The
checkpoint is saved as ``{"model": state_dict}`` so submission ``_Stage3MViT``
loads it unchanged.

Proxy targets are NOT official ground truth (AGENTS.md): validation numbers here
are a self-diagnostic against the v1b proxy rule, reported with the label source.

Config JSON (configs/exp/s3_e001.json) keys: cache_dir, aux_csv, rule, epochs,
batch_size, grad_accum, lr, weight_decay, seed, num_workers, window, train_stride,
val_stride, init_pretrained, amp, out_dir, max_train_batches.
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
from afda import stage3_labels  # noqa: E402
from afda.models import Stage3MViT  # noqa: E402

ACCEL = stage3_labels.ACCEL_CLASSES
STEER = stage3_labels.STEER_CLASSES
STOPPED_IDX = ACCEL.index("STOPPED")  # evaluation.md excludes STOPPED rows from steer scoring
MEAN = torch.tensor([0.45, 0.45, 0.45]).view(3, 1, 1, 1)
STD = torch.tensor([0.225, 0.225, 0.225]).view(3, 1, 1, 1)

DEFAULTS = {
    "cache_dir": "data/derived/s3_clip_cache_v1",
    "aux_csv": "data/derived/releases/s3-aux-rules-v1b-20260925/s3_auxiliary_10hz.csv",
    "rule": stage3_labels.DEFAULT_RULE,
    "epochs": 2,
    "batch_size": 2,
    "grad_accum": 2,
    "lr": 3e-4,
    "weight_decay": 0.05,
    "seed": 0,
    "num_workers": 4,
    "window": 16,
    "train_stride": 2,
    "val_stride": 1,
    "init_pretrained": True,
    "amp": True,
    "out_dir": "models/stage3",
    "max_train_batches": None,
}


class S3ClipDataset(Dataset):
    """One item = one 10Hz sample -> (3,window,224,224) clip + accel/steer target."""

    def __init__(self, cache_dir, aux, split, rule, window, stride):
        self.window = int(window)
        self.paths = {}
        self._arrays = {}  # lazy mmap per worker
        self.samples, self.accel, self.steer = [], [], []
        labeled = stage3_labels.add_labels(aux, rule)
        labeled = labeled[labeled["split"] == split]
        for sid, group in labeled.groupby("source_id", sort=True):
            npy = Path(cache_dir) / split / f"{sid}.npy"
            if not npy.exists():
                continue
            group = group.sort_values("sample_index")
            n_cache = int(np.load(npy, mmap_mode="r").shape[0])
            if len(group) != n_cache:
                raise ValueError(
                    f"{sid}: {len(group)} aux rows != {n_cache} cached frames; "
                    "cache/aux misaligned"
                )
            self.paths[sid] = npy
            accel = [ACCEL.index(x) for x in group["accel_label"]]
            steer = [STEER.index(x) for x in group["steer_label"]]
            for pos in range(0, n_cache, int(stride)):
                self.samples.append((sid, pos))
                self.accel.append(accel[pos])
                self.steer.append(steer[pos])

    def _array(self, sid):
        arr = self._arrays.get(sid)
        if arr is None:
            arr = np.load(self.paths[sid], mmap_mode="r")
            self._arrays[sid] = arr
        return arr

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, index):
        sid, pos = self.samples[index]
        arr = self._array(sid)
        total = arr.shape[0]
        idx = np.clip(pos - self.window // 2 + np.arange(self.window), 0, total - 1)
        clip = torch.from_numpy(np.ascontiguousarray(arr[idx])).permute(1, 0, 2, 3).float() / 255.0
        clip = (clip - MEAN) / STD
        return clip, self.accel[index], self.steer[index]


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


def init_backbone(model, enabled):
    if not enabled:
        return "scratch"
    try:
        from torchvision.models.video import MViT_V2_S_Weights, mvit_v2_s

        pretrained = mvit_v2_s(weights=MViT_V2_S_Weights.KINETICS400_V1)
        result = model.backbone.load_state_dict(pretrained.state_dict(), strict=False)
        return f"kinetics400 (missing={len(result.missing_keys)}, unexpected={len(result.unexpected_keys)})"
    except Exception as exc:  # training-only init; a scratch start is still valid
        return f"scratch (pretrained load failed: {exc})"


def steer_metrics(a_true, s_true, s_pred):
    """Steer macro-F1 both ways. `official` drops rows whose true accel is STOPPED
    (evaluation.md excludes stopped frames from steering scoring); `incl_stopped`
    keeps every row (proxy STOPPED rows are steer-masked to STRAIGHT upstream)."""
    a_true = np.asarray(a_true)
    s_true = np.asarray(s_true)
    s_pred = np.asarray(s_pred)
    incl = macro_f1(s_true, s_pred, len(STEER))
    keep = a_true != STOPPED_IDX
    official = macro_f1(s_true[keep], s_pred[keep], len(STEER)) if keep.any() else 0.0
    return official, incl, int((~keep).sum())


@torch.inference_mode()
def evaluate(model, loader, device, amp, identities=None):
    """Return summary metrics and, if `identities` (list of (source_id, sample_index))
    aligned to the loader's fixed order is given, per-sample prediction records."""
    model.eval()
    a_true, a_pred, s_true, s_pred = [], [], [], []
    for clips, accel, steer in loader:
        with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=amp):
            accel_logits, steer_logits = model(clips.to(device, non_blocking=True))
        a_pred.extend(accel_logits.argmax(1).cpu().tolist())
        s_pred.extend(steer_logits.argmax(1).cpu().tolist())
        a_true.extend(accel.tolist())
        s_true.extend(steer.tolist())
    accel_f1 = macro_f1(a_true, a_pred, len(ACCEL))
    steer_f1_official, steer_f1_incl, n_stopped = steer_metrics(a_true, s_true, s_pred)
    accel_acc = float(np.mean(np.asarray(a_true) == np.asarray(a_pred))) if a_true else 0.0
    steer_acc = float(np.mean(np.asarray(s_true) == np.asarray(s_pred))) if s_true else 0.0
    metrics = {
        "n": len(a_true),
        "n_stopped_true": n_stopped,
        "accel_macro_f1": accel_f1,
        # official = STOPPED-excluded (evaluation.md); incl_stopped kept for reference
        "steer_macro_f1": steer_f1_official,
        "steer_macro_f1_incl_stopped": steer_f1_incl,
        "accel_acc": accel_acc,
        "steer_acc": steer_acc,
        # best.pt selection uses the official (STOPPED-excluded) steer F1
        "mean_macro_f1": (accel_f1 + steer_f1_official) / 2,
    }
    records = None
    if identities is not None:
        if len(identities) != len(a_true):
            raise ValueError(
                f"identities ({len(identities)}) != predictions ({len(a_true)}); "
                "val loader must be shuffle=False, drop_last=False"
            )
        records = pd.DataFrame(
            {
                "source_id": [sid for sid, _ in identities],
                "sample_index": [pos for _, pos in identities],
                "split": "validation",
                "accel_pred": [ACCEL[i] for i in a_pred],
                "steer_pred": [STEER[i] for i in s_pred],
                "accel_true": [ACCEL[i] for i in a_true],
                "steer_true": [STEER[i] for i in s_true],
            }
        )
    return metrics, records


def load_config(path):
    cfg = dict(DEFAULTS)
    if path:
        user = json.loads(Path(path).read_text(encoding="utf-8"))
        cfg.update(user)
        cfg["rule"] = {**stage3_labels.DEFAULT_RULE, **user.get("rule", {})}
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

    aux = pd.read_csv(ROOT / cfg["aux_csv"])
    cache_dir = ROOT / cfg["cache_dir"]
    train_set = S3ClipDataset(cache_dir, aux, "train", cfg["rule"], cfg["window"], cfg["train_stride"])
    val_set = S3ClipDataset(cache_dir, aux, "validation", cfg["rule"], cfg["window"], cfg["val_stride"])
    if len(train_set) == 0:
        raise SystemExit("no train samples; is the clip cache built?")
    print(f"train samples={len(train_set)} val samples={len(val_set)} device={device} amp={amp}", flush=True)

    train_loader = DataLoader(
        train_set, batch_size=cfg["batch_size"], shuffle=True, drop_last=True,
        num_workers=cfg["num_workers"], pin_memory=(device.type == "cuda"),
    )
    val_loader = DataLoader(
        val_set, batch_size=cfg["batch_size"], shuffle=False,
        num_workers=cfg["num_workers"], pin_memory=(device.type == "cuda"),
    )

    model = Stage3MViT()
    init = init_backbone(model, cfg["init_pretrained"])
    model.to(device)
    print(f"backbone init: {init}", flush=True)

    accel_w = class_weights(train_set.accel, len(ACCEL)).to(device)
    steer_w = class_weights(train_set.steer, len(STEER)).to(device)
    accel_loss = nn.CrossEntropyLoss(weight=accel_w)
    steer_loss = nn.CrossEntropyLoss(weight=steer_w)
    optimizer = torch.optim.AdamW(model.parameters(), lr=cfg["lr"], weight_decay=cfg["weight_decay"])
    scaler = torch.amp.GradScaler("cuda", enabled=amp)
    grad_accum = max(1, int(cfg["grad_accum"]))

    val_ids = list(val_set.samples)  # (source_id, sample_index) aligned to val_loader order
    best = {"mean_macro_f1": -1.0}
    history = []
    for epoch in range(int(cfg["epochs"])):
        model.train()
        optimizer.zero_grad(set_to_none=True)
        start = time.time()
        running = 0.0
        for step, (clips, accel, steer) in enumerate(train_loader):
            if cfg["max_train_batches"] and step >= int(cfg["max_train_batches"]):
                break
            clips = clips.to(device, non_blocking=True)
            accel = accel.to(device, non_blocking=True)
            steer = steer.to(device, non_blocking=True)
            with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=amp):
                accel_logits, steer_logits = model(clips)
                loss = (accel_loss(accel_logits, accel) + steer_loss(steer_logits, steer)) / grad_accum
            scaler.scale(loss).backward()
            if (step + 1) % grad_accum == 0:
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad(set_to_none=True)
            running += float(loss) * grad_accum
            if step % 100 == 0:
                print(f"  epoch {epoch} step {step} loss {float(loss) * grad_accum:.4f}", flush=True)
        if len(val_set):
            metrics, records = evaluate(model, val_loader, device, amp, identities=val_ids)
        else:
            metrics, records = {}, None
        metrics["epoch"] = epoch
        metrics["train_loss"] = running / max(1, step + 1)
        metrics["seconds"] = round(time.time() - start, 1)
        history.append(metrics)
        print(f"epoch {epoch} done: {json.dumps(metrics)}", flush=True)
        if metrics.get("mean_macro_f1", -1) > best["mean_macro_f1"]:
            best = metrics
            if records is not None:
                records.to_csv(out_dir / "val_predictions.csv", index=False)
                print(f"  wrote val_predictions.csv ({len(records)} rows)", flush=True)
            torch.save(
                {
                    "model": model.state_dict(),
                    "classes": {"accel": ACCEL, "steer": STEER},
                    "rule": cfg["rule"],
                    "init": init,
                    "val_metrics": metrics,
                    "label_source": "proxy_rule_v1b (not official GT)",
                },
                out_dir / "best.pt",
            )
            print(f"  saved best.pt (mean_macro_f1={metrics['mean_macro_f1']:.4f})", flush=True)

    summary = {
        "config": {k: (v if k != "rule" else cfg["rule"]) for k, v in cfg.items()},
        "train_samples": len(train_set),
        "val_samples": len(val_set),
        "init": init,
        "best": best,
        "history": history,
        "label_source": "proxy_rule_v1b (not official GT)",
    }
    (out_dir / "metrics.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote {out_dir / 'metrics.json'}; best mean_macro_f1={best['mean_macro_f1']:.4f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
