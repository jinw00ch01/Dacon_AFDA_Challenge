"""Dump Stage 3 accel 4-class softmax probabilities from a trained checkpoint.

Purpose (Pro qa cc3a4dc1 / exp-780d1a80): the e005 accel head separates ACC/DEC
scenes but with an INVERTED sign (Pro hard-pred ACC-vs-DEC AUROC 0.288, well below
0.5). Pro asked for actual softmax probabilities on two inputs to tell undertraining
apart from a val cache/alignment bug:
  (A) train split (stride 10) -- does the head separate ACC/DEC on TRAIN at all?
  (B) val clips with the 16-frame window order REVERSED (idx[::-1]) -- does the sign
      flip when time is reversed? (i.e. is the model using temporal direction?)

This reuses the SAME S3ClipDataset window (clip(p-8+arange(16), 0, T-1)) and shared
mean/std so probabilities match training/inference; the only variation is the
optional reversed window. Output CSV columns: source_id, sample_index, split,
p_ACCELERATING, p_DECELERATING, p_CONSTANT, p_STOPPED (softmax of the accel head),
stopped_prob (sigmoid of the separate STOPPED head), accel_true, steer_true, speed_mps.

Not a training or gating step -- diagnostic only. Proxy labels (v1b) are self-diagnostic.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from afda import stage3_labels  # noqa: E402
from afda.models import Stage3MViT  # noqa: E402
from train_stage3 import S3ClipDataset, MEAN, STD, ACCEL, STEER  # noqa: E402

from torch.utils.data import DataLoader  # noqa: E402


class ReversibleS3Clip(S3ClipDataset):
    """S3ClipDataset with an optional reversed 16-frame window (B input)."""

    def __init__(self, *a, reverse_window=False, **k):
        super().__init__(*a, **k)
        self.reverse_window = bool(reverse_window)

    def __getitem__(self, index):
        sid, pos = self.samples[index]
        arr = self._array(sid)
        total = arr.shape[0]
        idx = np.clip(pos - self.window // 2 + np.arange(self.window), 0, total - 1)
        if self.reverse_window:
            idx = idx[::-1]
        clip = torch.from_numpy(np.ascontiguousarray(arr[idx])).permute(1, 0, 2, 3).float() / 255.0
        clip = (clip - MEAN) / STD
        return clip, self.accel[index], self.steer[index], self.speed[index]


@torch.inference_mode()
def run(ckpt, cache_dir, aux_csv, split, stride, reverse_window, out_csv, batch_size=2,
        num_workers=4):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    state = torch.load(ckpt, map_location="cpu", weights_only=False)
    rule = {**stage3_labels.DEFAULT_RULE, **state.get("rule", {})}
    predict_stopped = bool(state.get("predict_stopped", False))
    if state.get("head_kind") != "accel":
        raise SystemExit(f"{ckpt}: head_kind={state.get('head_kind')} not 'accel'; probs undefined")
    model = Stage3MViT(predict_speed=False, predict_stopped=predict_stopped)
    model.load_state_dict(state["model"])
    model.to(device).eval()

    aux = pd.read_csv(ROOT / aux_csv)
    ds = ReversibleS3Clip(ROOT / cache_dir, aux, split, rule, 16, stride,
                          reverse_window=reverse_window)
    if len(ds) == 0:
        raise SystemExit(f"no samples for split={split}; is the cache built?")
    loader = DataLoader(ds, batch_size=batch_size, shuffle=False, drop_last=False,
                        num_workers=num_workers, pin_memory=(device.type == "cuda"))
    ids = list(ds.samples)

    probs, stopped_p = [], []
    amp = device.type == "cuda"
    for clips, _a, _s, _sp in loader:
        with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=amp):
            out = model(clips.to(device, non_blocking=True))
        p = torch.softmax(out[0].float(), dim=1).cpu().numpy()
        probs.append(p)
        if predict_stopped:
            stopped_p.extend(torch.sigmoid(out[2].squeeze(-1).float()).cpu().tolist())
    probs = np.concatenate(probs, axis=0)

    df = pd.DataFrame({
        "source_id": [sid for sid, _ in ids],
        "sample_index": [pos for _, pos in ids],
        "split": split,
        "reverse_window": bool(reverse_window),
        "accel_true": [ACCEL[i] for i in ds.accel],
        "steer_true": [STEER[i] for i in ds.steer],
        "speed_mps": ds.speed,
    })
    for j, c in enumerate(ACCEL):
        df[f"p_{c}"] = probs[:, j]
    if predict_stopped:
        df["stopped_prob"] = stopped_p
    out_csv = Path(out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)
    print(f"wrote {out_csv} rows={len(df)} split={split} stride={stride} "
          f"reverse={reverse_window} device={device}", flush=True)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", default="models/stage3_e005/best.pt")
    ap.add_argument("--cache-dir", default="data/derived/s3_clip_cache_v1")
    ap.add_argument("--aux-csv",
                    default="data/derived/releases/s3-aux-rules-v1b-20260925/s3_auxiliary_10hz.csv")
    ap.add_argument("--split", required=True)
    ap.add_argument("--stride", type=int, default=1)
    ap.add_argument("--reverse-window", action="store_true")
    ap.add_argument("--out-csv", required=True)
    ap.add_argument("--batch-size", type=int, default=2)
    ap.add_argument("--num-workers", type=int, default=4)
    args = ap.parse_args()
    return run(args.ckpt, args.cache_dir, args.aux_csv, args.split, args.stride,
               args.reverse_window, args.out_csv, args.batch_size, args.num_workers)


if __name__ == "__main__":
    raise SystemExit(main())
