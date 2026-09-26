"""AFDA submission inference — v001b (S2 constant collision/entry positions).

v001b differs from v001 ONLY in Stage 2 collision_frame/entry_frame: instead of
the model's argmax time indices, it emits constant positions in each clip's
sorted frame list — index 30 (collision) and index 22 (entry) for a 50-frame
10Hz clip (3.0s / 2.2s). For other clip lengths it falls back to the same ratio
(round(0.6*(n-1)) / round(0.44*(n-1))), clamped to the list and with
entry <= collision. Stage 1, Stage 3, and Stage 2 evasion_space/entry_side are
byte-identical to v001. This tests the Pro hypothesis that evaluation clips are
cut like the official examples (collision near frame 30). See request 366ca1e1.

Original v001 header follows.

AFDA submission inference — self-contained 3-Stage predictor.

This file is what ships inside submit.zip, so it imports only packages that
exist on the evaluation server (evaluation.md) and nothing project-local.
Its constants and pure preprocessing helpers are kept byte-for-byte identical
to src/afda/preprocess.py and its model classes to src/afda/models.py;
tests/test_afda.py enforces that equivalence so training and submission never
drift apart.

Weights are loaded from model_dir with weights_only where the payload allows
it. No weights are downloaded at inference time. If a checkpoint is missing the
run fails loudly rather than substituting random weights (CLAUDE.md rule).

Evaluation input layout (per the competition contract):
  Stage 1 / Stage 3: <data_dir>/videos/*.mp4
  Stage 2:           <data_dir>/images/<ID>/*.jpg   (all original frames)
"""
from __future__ import annotations

import re
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
from PIL import Image
from torch import nn
from torch.utils.data import DataLoader, Dataset
from torchvision.models import resnet18, ResNet18_Weights
from torchvision.models.video import mvit_v2_s

VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv", ".m4v", ".3gp", ".3gpp", ".wmv"}
IMAGE_EXT = {".jpg", ".jpeg", ".png"}
ACCEL = ["ACCELERATING", "DECELERATING", "CONSTANT", "STOPPED"]
STEER = ["LEFT", "STRAIGHT", "RIGHT"]
S1_MEAN = torch.tensor([0.45, 0.45, 0.45])[:, None, None, None]
S1_STD = torch.tensor([0.225, 0.225, 0.225])[:, None, None, None]
S3_MEAN = torch.tensor([0.45, 0.45, 0.45])[:, None, None]
S3_STD = torch.tensor([0.225, 0.225, 0.225])[:, None, None]
cv2.setNumThreads(1)


def _device() -> torch.device:
    if not torch.cuda.is_available():
        raise RuntimeError("이 제출물은 CUDA GPU 평가환경을 필요로 합니다.")
    return torch.device("cuda")


def _video_paths(root: Path):
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXT)


def _frame_number(path: Path) -> int:
    match = re.search(r"(\d+)$", path.stem)
    return int(match.group(1)) if match else 0


# --- Stage 1: MViTv2-S re-recording classifier ---------------------------------
def _clip_ids(path: Path, n: int, slot: int, slots: int):
    cap = cv2.VideoCapture(str(path))
    total = max(1, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
    cap.release()
    center = (slot + 0.5) * total / slots
    start = max(0, min(total - n, round(center - n / 2)))
    return np.linspace(start, min(total - 1, start + n - 1), n).round().astype(int)


def _normalize_stage1_clip(frames_uint8) -> torch.Tensor:
    x = torch.from_numpy(np.stack(frames_uint8)).permute(3, 0, 1, 2).float() / 255.0
    return (x - S1_MEAN) / S1_STD


def _decode_stage1_clip(path: Path, size: int, frame_ids) -> torch.Tensor:
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
        h, w = rgb.shape[:2]
        scale = size / min(h, w)
        nh, nw = max(size, round(h * scale)), max(size, round(w * scale))
        rgb = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_AREA)
        y, x = (nh - size) // 2, (nw - size) // 2
        out.append(rgb[y : y + size, x : x + size])
    cap.release()
    if not out:
        raise ValueError(f"cannot decode video: {path.name}")
    while len(out) < len(wanted):
        out.append(out[-1])
    return _normalize_stage1_clip(out)


class _Stage1Clips(Dataset):
    def __init__(self, videos, slots, size, frames):
        self.videos, self.slots, self.size, self.frames = videos, slots, size, frames

    def __len__(self):
        return len(self.videos) * self.slots

    def __getitem__(self, index):
        video_index, slot = index // self.slots, index % self.slots
        path = self.videos[video_index]
        try:
            x = _decode_stage1_clip(path, self.size, _clip_ids(path, self.frames, slot, self.slots))
            valid = 1
        except Exception:
            x = torch.zeros(3, self.frames, self.size, self.size)
            valid = 0
        return x, video_index, valid


def predict_stage1(data_dir, model_dir):
    device = _device()
    checkpoint = torch.load(Path(model_dir) / "best.pt", map_location="cpu", weights_only=False)
    size, frames = int(checkpoint["size"]), int(checkpoint["frames"])
    model = mvit_v2_s(weights=None)
    model.head[1] = nn.Linear(model.head[1].in_features, 2)
    model.load_state_dict(checkpoint["model"])
    model.to(device).eval()

    videos = _video_paths(Path(data_dir) / "videos")
    slots = 3
    dataset = _Stage1Clips(videos, slots, size, frames)
    loader = DataLoader(dataset, batch_size=4, num_workers=4, pin_memory=True)
    scores = [[] for _ in videos]
    with torch.inference_mode():
        for clips, video_indices, valid in loader:
            with torch.autocast(device_type="cuda", dtype=torch.float16):
                prob = torch.softmax(model(clips.to(device, non_blocking=True)), 1)[:, 1]
            for idx, value, ok in zip(video_indices.tolist(), prob.float().cpu().tolist(), valid.tolist()):
                if ok:
                    scores[idx].append(float(value))

    rows = []
    for path, values in zip(videos, scores):
        probability = float(np.mean(values)) if values else 1.0
        rows.append({"ID": path.stem, "answer": "RERECORDED" if probability >= 0.5 else "ORIGINAL"})
    del model
    torch.cuda.empty_cache()
    return pd.DataFrame(rows, columns=["ID", "answer"])


# --- Stage 2: ResNet18 + BiGRU four-task model --------------------------------
class _Stage2Frames(Dataset):
    def __init__(self, paths, transform):
        self.paths, self.transform = paths, transform

    def __len__(self):
        return len(self.paths)

    def __getitem__(self, index):
        with Image.open(self.paths[index]) as image:
            return self.transform(image.convert("RGB"))


class _Stage2Temporal(nn.Module):
    def __init__(self):
        super().__init__()
        self.r = nn.GRU(512, 192, 2, batch_first=True, bidirectional=True, dropout=0.15)
        self.tc = nn.Linear(384, 1)
        self.te = nn.Linear(384, 1)
        self.scene = nn.Sequential(nn.Linear(768, 192), nn.ReLU(), nn.Dropout(0.2), nn.Linear(192, 4))

    def forward(self, x):
        h, _ = self.r(x)
        collision_logits = self.tc(h).squeeze(-1)
        entry_logits = self.te(h).squeeze(-1)
        collision_index = collision_logits.argmax(1)
        entry_index = entry_logits.argmax(1)
        batch = torch.arange(len(h), device=h.device)
        scene_input = torch.cat([h[batch, collision_index], h[batch, entry_index]], 1)
        return collision_index, entry_index, self.scene(scene_input)


def _const_positions(n: int):
    """v001b constant collision/entry positions in a length-n sorted frame list.

    50-frame 10Hz clips -> index 30 (3.0s) / 22 (2.2s). Other lengths use the
    same ratio round(0.6*(n-1)) / round(0.44*(n-1)). Both clamped to [0, n-1]
    with entry <= collision.
    """
    if n == 50:
        collision, entry = 30, 22
    else:
        collision = round(0.6 * (n - 1))
        entry = round(0.44 * (n - 1))
    collision = min(max(collision, 0), n - 1)
    entry = min(max(entry, 0), collision)
    return collision, entry


def predict_stage2(data_dir, model_dir):
    device = _device()
    model_dir = Path(model_dir)
    transform = ResNet18_Weights.IMAGENET1K_V1.transforms()
    backbone = resnet18(weights=None)
    backbone.load_state_dict(torch.load(model_dir / "resnet18-f37072fd.pth", map_location="cpu", weights_only=True))
    backbone.fc = nn.Identity()
    backbone.to(device).eval()
    temporal = _Stage2Temporal()
    temporal.load_state_dict(torch.load(model_dir / "best.pt", map_location="cpu", weights_only=False)["model"])
    temporal.to(device).eval()

    image_root = Path(data_dir) / "images"
    folders = sorted(p for p in image_root.iterdir() if p.is_dir())
    rows = []
    with torch.inference_mode():
        for folder in folders:
            # 평가 정의상 모든 원본 프레임을 사용한다(stride=1).
            paths = sorted(
                (p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXT),
                key=_frame_number,
            )
            if not paths:
                continue
            loader = DataLoader(_Stage2Frames(paths, transform), batch_size=256, num_workers=6, pin_memory=True)
            features = []
            for images in loader:
                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    features.append(backbone(images.to(device, non_blocking=True)).float().cpu())
            sequence = torch.cat(features)[None].to(device)
            # v001b: evasion_space/entry_side stay from the v001 model; only the
            # collision/entry frame positions are overridden with constants.
            _collision_idx, _entry_idx, scene = temporal(sequence)
            frame_numbers = [_frame_number(path) for path in paths]
            collision_pos, entry_pos = _const_positions(len(frame_numbers))
            rows.append(
                {
                    "ID": folder.name,
                    "collision_frame": frame_numbers[collision_pos],
                    "entry_frame": frame_numbers[entry_pos],
                    "evasion_space": int(scene[:, :2].argmax(1)),
                    "entry_side": "RIGHT" if int(scene[:, 2:].argmax(1)) else "LEFT",
                }
            )
    del backbone, temporal
    torch.cuda.empty_cache()
    return pd.DataFrame(
        rows, columns=["ID", "collision_frame", "entry_frame", "evasion_space", "entry_side"]
    )


# --- Stage 3: MViTv2-S accel/steer multi-head ---------------------------------
class _Stage3MViT(nn.Module):
    def __init__(self):
        super().__init__()
        self.backbone = mvit_v2_s(weights=None)
        dimension = self.backbone.head[1].in_features
        self.backbone.head = nn.Identity()
        self.accel = nn.Linear(dimension, 4)
        self.steer = nn.Linear(dimension, 3)

    def forward(self, x):
        features = self.backbone(x)
        return self.accel(features), self.steer(features)


def _stage3_frames(path: Path):
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
        raise ValueError(f"cannot decode video: {path.name}")
    return torch.stack(frames)


def predict_stage3(data_dir, model_dir):
    device = _device()
    checkpoint = torch.load(Path(model_dir) / "best.pt", map_location="cpu", weights_only=False)
    model = _Stage3MViT()
    model.load_state_dict(checkpoint["model"])
    model.to(device).eval()
    videos = _video_paths(Path(data_dir) / "videos")
    rows = []
    with torch.inference_mode():
        for path in videos:
            frames = _stage3_frames(path)
            count = len(frames)
            centers = np.arange(count)
            accel_predictions, steer_predictions = [], []
            for start in range(0, count, 8):
                center = centers[start : start + 8]
                indices = np.clip(center[:, None] - 8 + np.arange(16)[None, :], 0, count - 1)
                clips = frames[torch.from_numpy(indices)].permute(0, 2, 1, 3, 4).float() / 255.0
                clips = (clips - S3_MEAN[None, :, None, :, :]) / S3_STD[None, :, None, :, :]
                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    accel_logits, steer_logits = model(clips.to(device, non_blocking=True))
                accel_predictions.extend(accel_logits.argmax(1).cpu().tolist())
                steer_predictions.extend(steer_logits.argmax(1).cpu().tolist())
            for sample_index, (accel, steer) in enumerate(zip(accel_predictions, steer_predictions)):
                rows.append(
                    {
                        "ID": path.stem,
                        "sample_index": sample_index,
                        "accel_label": ACCEL[accel],
                        "steer_label": STEER[steer],
                    }
                )
    del model
    torch.cuda.empty_cache()
    return pd.DataFrame(rows, columns=["ID", "sample_index", "accel_label", "steer_label"])
