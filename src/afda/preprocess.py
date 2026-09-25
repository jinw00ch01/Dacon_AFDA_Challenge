"""Shared decode/preprocess for AFDA Stages 1-3.

These functions are the single source of truth for how videos and frames are
turned into model tensors. Training modules import them directly; the
self-contained submission ``inference.py`` inlines the same constants and pure
numeric helpers (`normalize_stage1_clip`, `normalize_stage3_clip`,
`stage2_transform`). Keeping the numeric path identical avoids the
train/inference preprocessing mismatch flagged in docs/CODE_REVIEW.md.
"""
from __future__ import annotations

import re
from pathlib import Path

import cv2
import numpy as np
import torch

VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv", ".m4v", ".3gp", ".3gpp", ".wmv"}
IMAGE_EXT = {".jpg", ".jpeg", ".png"}
ACCEL = ["ACCELERATING", "DECELERATING", "CONSTANT", "STOPPED"]
STEER = ["LEFT", "STRAIGHT", "RIGHT"]

# ImageNet-ish normalization used by the baseline clips (matches src/baseline_inference.py).
S1_MEAN = torch.tensor([0.45, 0.45, 0.45])[:, None, None, None]
S1_STD = torch.tensor([0.225, 0.225, 0.225])[:, None, None, None]
S3_MEAN = torch.tensor([0.45, 0.45, 0.45])[:, None, None]
S3_STD = torch.tensor([0.225, 0.225, 0.225])[:, None, None]

# Limit OpenCV threads so DataLoader workers stay predictable under the 60min budget.
cv2.setNumThreads(1)


def video_paths(root: Path):
    root = Path(root)
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXT)


def frame_number(path: Path) -> int:
    match = re.search(r"(\d+)$", Path(path).stem)
    return int(match.group(1)) if match else 0


def clip_frame_ids(path: Path, n: int, slot: int, slots: int):
    """Evenly spaced frame indices centred on temporal slot `slot` of `slots`."""
    cap = cv2.VideoCapture(str(path))
    total = max(1, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
    cap.release()
    center = (slot + 0.5) * total / slots
    start = max(0, min(total - n, round(center - n / 2)))
    return np.linspace(start, min(total - 1, start + n - 1), n).round().astype(int)


def _center_crop_resize(rgb: np.ndarray, size: int) -> np.ndarray:
    h, w = rgb.shape[:2]
    scale = size / min(h, w)
    nh, nw = max(size, round(h * scale)), max(size, round(w * scale))
    rgb = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_AREA)
    y, x = (nh - size) // 2, (nw - size) // 2
    return rgb[y : y + size, x : x + size]


def normalize_stage1_clip(frames_uint8: np.ndarray) -> torch.Tensor:
    """Pure: (T, H, W, 3) uint8 RGB -> (3, T, H, W) normalized float tensor."""
    x = torch.from_numpy(np.stack(frames_uint8)).permute(3, 0, 1, 2).float() / 255.0
    return (x - S1_MEAN) / S1_STD


def decode_stage1_clip(path: Path, size: int, frame_ids) -> torch.Tensor:
    cap = cv2.VideoCapture(str(path))
    out = []
    wanted = [int(x) for x in frame_ids]
    cap.set(cv2.CAP_PROP_POS_FRAMES, wanted[0])
    pos = wanted[0]
    for idx in wanted:
        ok = False
        bgr = None
        while pos <= idx:
            ok, bgr = cap.read()
            pos += 1
            if not ok:
                break
        if not ok or bgr is None:
            continue
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        out.append(_center_crop_resize(rgb, size))
    cap.release()
    if not out:
        raise ValueError(f"cannot decode video: {Path(path).name}")
    while len(out) < len(wanted):
        out.append(out[-1])
    return normalize_stage1_clip(out)


def decode_stage3_frames(path: Path) -> torch.Tensor:
    """All frames of a video as a (T, 3, 224, 224) uint8 tensor (256-short-side, center crop)."""
    from PIL import Image

    capture = cv2.VideoCapture(str(path))
    frames = []
    while True:
        ok, bgr = capture.read()
        if not ok:
            break
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb)
        width, height = image.size
        scale = 256 / min(width, height)
        image = image.resize((round(width * scale), round(height * scale)))
        width, height = image.size
        x, y = (width - 224) // 2, (height - 224) // 2
        image = image.crop((x, y, x + 224, y + 224))
        frames.append(torch.from_numpy(np.asarray(image).copy()).permute(2, 0, 1).to(torch.uint8))
    capture.release()
    if not frames:
        raise ValueError(f"cannot decode video: {Path(path).name}")
    return torch.stack(frames)


def stage3_clip_indices(count: int, start: int, window: int = 16, span: int = 8):
    """Frame indices for the `span` sample centres starting at `start` (baseline layout)."""
    centers = np.arange(count)[start : start + span]
    return np.clip(centers[:, None] - window // 2 + np.arange(window)[None, :], 0, count - 1)


def normalize_stage3_clip(frames_uint8: torch.Tensor, indices: np.ndarray) -> torch.Tensor:
    """Pure: uint8 (T,3,H,W) + index matrix -> (B,3,window,H,W) normalized float tensor."""
    clips = frames_uint8[torch.from_numpy(indices)].permute(0, 2, 1, 3, 4).float() / 255.0
    return (clips - S3_MEAN[None, :, None, :, :]) / S3_STD[None, :, None, :, :]


def stage2_transform():
    """ResNet18 ImageNet inference transform (same object the baseline uses)."""
    from torchvision.models import ResNet18_Weights

    return ResNet18_Weights.IMAGENET1K_V1.transforms()
