"""Codec-aligned Stage 1 evaluation on the real S23 re-recorded footage.

This is the highest-priority S1 validation criterion (decisions 3/9, decision
c85dd4a7): measure how a Stage 1 checkpoint separates REAL re-recorded captures
from their ORIGINAL comma-playback sources on the frozen release
``s1-s23-real-v1-20260926``.

Per decision c85dd4a7 the two members of every pair are scored with IDENTICAL
S1 preprocessing over the SAME real-time 5 s overlap window:
  - capture (RERECORDED, label 1): window [0, window_s)
  - original (ORIGINAL,   label 0): window [orig_start_s_final, +window_s)
Both windows are sampled at the model's own ``frames`` count (e001: 16), then
resized/normalised through submission.inference._decode_stage1_clip so the pixels
the model sees here are byte-identical to what it would see at submission time.
The HEVC-vs-h264 codec difference is NOT removed here (that is the separate v1c
re-encode track); this harness answers "does e001 generalise to real re-recording
when the temporal crop is aligned", with leaderboard S1 as the final judge.

Proxy caveat: val/test are 8 pairs (16 clips) each; one flip moves Macro-F1 by
~0.06-0.08 (release small_sample_caveat). Numbers are self-diagnostic, not GT.
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
from torch import nn
from torchvision.models.video import mvit_v2_s

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "submission"))

from submission.inference import _decode_stage1_clip  # noqa: E402
from src.afda import metrics as M  # noqa: E402

RELEASE = ROOT / "data/derived/releases/s1-s23-real-v1-20260926"


def _fps(path: Path) -> float:
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    if fps is None or fps <= 0:
        raise ValueError(f"bad fps for {path}")
    return float(fps), max(1, total)


def _frame_ids(t0: float, window_s: float, n_frames: int, fps: float, total: int):
    """n_frames timestamps evenly spaced (start-aligned) across [t0, t0+window_s)."""
    times = t0 + (np.arange(n_frames) / n_frames) * window_s
    ids = np.round(times * fps).astype(int)
    return np.clip(ids, 0, total - 1)


def _clip(path: Path, t0: float, window_s: float, size: int, n_frames: int):
    fps, total = _fps(path)
    ids = _frame_ids(t0, window_s, n_frames, fps, total)
    return _decode_stage1_clip(path, size, ids)  # (3, n_frames, size, size)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", default="models/stage1")
    ap.add_argument("--tag", default="e001")
    ap.add_argument("--window-s", type=float, default=5.0)
    ap.add_argument("--out-dir", default="work/agent/outbox/s1_s23_eval")
    args = ap.parse_args()

    manifest = json.loads((RELEASE / "manifest.json").read_text(encoding="utf-8"))
    video_root = ROOT / manifest["video_root"]
    df = pd.read_csv(RELEASE / manifest["alignment_csv"])

    ckpt = torch.load(Path(args.model_dir) / "best.pt", map_location="cpu", weights_only=False)
    size, frames = int(ckpt["size"]), int(ckpt["frames"])
    model = mvit_v2_s(weights=None)
    model.head[1] = nn.Linear(model.head[1].in_features, 2)
    model.load_state_dict(ckpt["model"])
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device).eval()

    rows = []
    for _, r in df.iterrows():
        cap_path = video_root / r["file"]
        orig_path = ROOT / r["original_path"]
        overlap = float(r["overlap_s_final"])
        win = min(args.window_s, overlap)
        clips, meta = [], []
        # capture = RERECORDED (label 1)
        clips.append(_clip(cap_path, 0.0, win, size, frames))
        meta.append(("RERECORDED", 1))
        # original = ORIGINAL (label 0), cropped at orig_start_s_final
        clips.append(_clip(orig_path, float(r["orig_start_s_final"]), win, size, frames))
        meta.append(("ORIGINAL", 0))
        batch = torch.stack(clips).to(device)
        with torch.inference_mode():
            if device.type == "cuda":
                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    prob = torch.softmax(model(batch), 1)[:, 1]
            else:
                prob = torch.softmax(model(batch), 1)[:, 1]
        prob = prob.float().cpu().tolist()
        for (label, y), p, kind in zip(meta, prob, ["capture", "original"]):
            rows.append({
                "source_id": r["source_id"], "condition": r["condition"],
                "split": r["split"], "kind": kind, "file": r["file"],
                "true": label, "prob_rerecorded": round(float(p), 6),
                "pred": "RERECORDED" if p >= 0.5 else "ORIGINAL",
                "correct": int(("RERECORDED" if p >= 0.5 else "ORIGINAL") == label),
            })

    out = pd.DataFrame(rows)
    out_dir = ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    pred_csv = out_dir / f"s1_s23_predictions_{args.tag}.csv"
    out.to_csv(pred_csv, index=False)

    def _split_metrics(sub: pd.DataFrame) -> dict:
        yt = sub["true"].tolist()
        yp = sub["pred"].tolist()
        return {
            "n_clips": int(len(sub)),
            "n_pairs": int(len(sub) // 2),
            "macro_f1": round(M.stage1_score(yt, yp), 6),
            "accuracy": round(float(sub["correct"].mean()), 6),
            "orig_recall": round(float(sub[sub.true == "ORIGINAL"]["correct"].mean()), 6),
            "rerec_recall": round(float(sub[sub.true == "RERECORDED"]["correct"].mean()), 6),
        }

    result = {"release": manifest["release_id"], "model_dir": args.model_dir,
              "tag": args.tag, "window_s": args.window_s, "size": size,
              "frames": frames, "by_split": {}, "overall": _split_metrics(out)}
    for sp in ["validation", "test", "train"]:
        sub = out[out.split == sp]
        if len(sub):
            result["by_split"][sp] = _split_metrics(sub)

    metrics_json = out_dir / f"s1_s23_metrics_{args.tag}.json"
    metrics_json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"\nwrote {pred_csv}\nwrote {metrics_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
