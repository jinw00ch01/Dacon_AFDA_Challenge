"""AFDA submission inference — self-contained 3-Stage predictor.

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


# --- Stage 2 collision/entry timing rule from global camera motion (decision 12-A/12-B) --
# Logic is byte-identical to src/afda/s2_motion_rule.py (the module Pro validated on
# held-out windows); tests/test_afda.py enforces the equivalence so training/eval and
# submission never drift. Parameters (jerk_y + div_drop, LAG -2, ENTRY_K 8) were chosen
# only on the FIT split; the rule sees only the clip frames and uses no cross-file stats.
# On the same 50-frame 10Hz windows the rule beats the trained head on held-out
# Acc@0.3s (collision 0.649 vs 0.338, entry 0.356 vs 0.222), so it replaces the head's
# timing outputs while the scene head still supplies evasion_space / entry_side.
_S2_SIZE = (160, 90)
_S2_LAG = -2
_S2_ENTRY_K = 8


def _s2_to_gray(frames):
    """frames: iterable of BGR uint8 images (any size) -> (N, 90, 160) uint8."""
    return np.stack([cv2.cvtColor(cv2.resize(f, _S2_SIZE, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
                     for f in frames])


def _s2_motion_series(gray):
    n, h, w = gray.shape
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    rx, ry = xs - w / 2, ys - h / 2
    r2 = rx ** 2 + ry ** 2 + 1.0
    div, dy = np.zeros(n, np.float32), np.zeros(n, np.float32)
    for k in range(1, n):
        fl = cv2.calcOpticalFlowFarneback(gray[k - 1], gray[k], None, 0.5, 3, 13, 3, 5, 1.1, 0)
        u, v = fl[..., 0], fl[..., 1]
        dy[k] = float(np.median(v))
        div[k] = float(np.mean((u * rx + v * ry) / r2))
    if n > 1:
        div[0], dy[0] = div[1], dy[1]
    return {"div": div, "dy": dy}


def _s2_smooth3(x):
    return np.convolve(np.pad(x, 1, mode="edge"), np.ones(3) / 3, mode="valid")


def _s2_z(x):
    return (x - x.mean()) / (x.std() + 1e-6)


def _s2_collision_score(series):
    div, dy = series["div"], series["dy"]
    div_drop = -np.diff(div, prepend=div[0])
    jerk_y = np.abs(np.diff(dy, prepend=dy[0]))
    return _s2_z(_s2_smooth3(div_drop)) + _s2_z(_s2_smooth3(jerk_y))


def _s2_predict_collision(gray):
    """Sequence-relative collision index for one clip (gray: (N, 90, 160) uint8)."""
    if len(gray) < 3:
        return 0
    return int(np.clip(int(np.argmax(_s2_collision_score(_s2_motion_series(gray)))) + _S2_LAG, 0, len(gray) - 1))


def _s2_predict_entry(collision_idx):
    return int(max(0, collision_idx - _S2_ENTRY_K))


# --- Stage 2 evasion-space rule from object motion (decision 12-C, Pro qa) --
# Logic is byte-identical to src/afda/s2_scene_rule.py (the module Pro validated on
# held-out windows; 4-condition pre-registered gate passed). tests/test_afda.py
# enforces the equivalence. On the same 50-frame 10Hz windows the rule beats the
# trained scene head on held-out evasion Macro-F1 (0.697 vs 0.351; the head collapses
# to one class), so it replaces evasion_space. entry_side stays the trained head
# (the side rule was REJECTED, decision 37c252d7). c is the rule collision index,
# exactly as Pro evaluated it. EVASION_THR was chosen on the FIT split only.
_S2_POOL = 10
_S2_EVASION_L = 5
_S2_EVASION_THR = 1.721142750989563
_S2_EVASION_FALLBACK = 1


def _s2_pool(x):
    h, w = x.shape
    return x.reshape(h // _S2_POOL, _S2_POOL, w // _S2_POOL, _S2_POOL).mean((1, 3))


def _s2_scene_flow(gray, k):
    """pooled (u, v) of the flow into window frame k (k >= 1), float16-quantised."""
    fl = cv2.calcOpticalFlowFarneback(gray[k - 1], gray[k], None, 0.5, 3, 13, 3, 5, 1.1, 0)
    return (_s2_pool(fl[..., 0]).astype(np.float16).astype(np.float64),
            _s2_pool(fl[..., 1]).astype(np.float16).astype(np.float64))


def _s2_scene_frames(c, lo, hi, n):
    return list(range(max(1, c + lo), min(n - 1, c + hi) + 1))


def _s2_evasion_feature(gray, c):
    ks = _s2_scene_frames(c, -_S2_EVASION_L, -1, len(gray))
    if not ks:
        return None
    mags = []
    for k in ks:
        u, v = _s2_scene_flow(gray, k)
        mags.append(float(np.mean(np.hypot(u[4:], v[4:]))))
    return float(np.mean(mags))


def _s2_predict_evasion(gray, collision_idx):
    x = _s2_evasion_feature(np.asarray(gray), int(collision_idx))
    return _S2_EVASION_FALLBACK if x is None else int(x <= _S2_EVASION_THR)


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
            collision_idx, entry_idx, scene = temporal(sequence)
            frame_numbers = [_frame_number(path) for path in paths]
            # decision 12-A/12-B: timing from global camera motion (beats the trained
            # head on held-out Acc@0.3s). decision 12-C: evasion_space from object
            # motion (beats the head's collapsed evasion output). The scene head now
            # only supplies entry_side; it still consumes its own indices internally.
            gray = _s2_to_gray([cv2.imread(str(path)) for path in paths])
            rule_collision = _s2_predict_collision(gray)
            rule_entry = _s2_predict_entry(rule_collision)
            rows.append(
                {
                    "ID": folder.name,
                    "collision_frame": frame_numbers[rule_collision],
                    "entry_frame": frame_numbers[rule_entry],
                    "evasion_space": _s2_predict_evasion(gray, rule_collision),
                    "entry_side": "RIGHT" if int(scene[:, 2:].argmax(1)) else "LEFT",
                }
            )
    del backbone, temporal
    torch.cuda.empty_cache()
    return pd.DataFrame(
        rows, columns=["ID", "collision_frame", "entry_frame", "evasion_space", "entry_side"]
    )


# --- Stage 3: MViTv2-S multi-head (accel-class e001 OR speed-regression e002) --
S3_RULE = {"window": 5, "v_stop": 0.5, "a_db": 0.2, "s_th": 4.5, "bias": -0.3}


class _Stage3MViT(nn.Module):
    def __init__(self, predict_speed=False, predict_stopped=False):
        super().__init__()
        self.predict_speed = bool(predict_speed)
        self.predict_stopped = bool(predict_stopped)
        self.backbone = mvit_v2_s(weights=None)
        dimension = self.backbone.head[1].in_features
        self.backbone.head = nn.Identity()
        if self.predict_speed:
            self.speed = nn.Linear(dimension, 1)
        else:
            self.accel = nn.Linear(dimension, 4)
        self.steer = nn.Linear(dimension, 3)
        if self.predict_stopped:
            self.stopped = nn.Linear(dimension, 1)

    def forward(self, x):
        features = self.backbone(x)
        head = self.speed if self.predict_speed else self.accel
        if self.predict_stopped:
            return head(features), self.steer(features), self.stopped(features)
        return head(features), self.steer(features)


def _accel_from_speed(speeds, rule):
    """Derive accel-class labels from ONE video's predicted-speed sequence, matching
    afda.stage3_labels.accel_from_speed_series with uniform 10Hz (0.1s) spacing --
    the inference case (decimated video has no sensor timestamps)."""
    window = int(rule["window"])
    v_stop, a_db = rule["v_stop"], rule["a_db"]
    speed = np.asarray(speeds, dtype=np.float64)
    n = speed.shape[0]
    if n == 0:
        return []
    t = np.arange(n, dtype=np.float64) * 0.1
    accel = np.gradient(speed, t) if n >= 2 else np.zeros(n, dtype=np.float64)
    s_ma = pd.Series(speed).rolling(window, center=True, min_periods=1).mean().to_numpy()
    a_ma = pd.Series(accel).rolling(window, center=True, min_periods=1).mean().to_numpy()
    labels = []
    for s, a in zip(s_ma, a_ma):
        if s < v_stop:
            labels.append("STOPPED")
        elif a > a_db:
            labels.append("ACCELERATING")
        elif a < -a_db:
            labels.append("DECELERATING")
        else:
            labels.append("CONSTANT")
    return labels


# --- Stage 3 steering class from the image yaw proxy (decision 92483f83 / 12-D) --------
# Logic is byte-identical to src/afda/s3_yaw_steer.py (the module Pro validated on the
# comma TRAIN split); tests/test_afda.py enforces the equivalence so training/eval and
# submission never drift. yaw_far = median horizontal far-band flow (horizon region,
# dominated by ego rotation): yaw_far > 0 = LEFT. The private S3 input is 10 Hz with one
# decoded frame per sample_index (official notice, Pro qa 55c7cdc5), so consecutive
# decoded frames ARE 10 Hz steps -- no fps normalization (container fps ~480 is wrong).
# Thresholds are pixels at 160 px width and hold for the comma-format FOV. On the same
# rows the rule lifts steer Macro-F1 0.324 -> 0.719 over the e005 head, so it replaces
# the trained steer output; the accel head still comes from the model.
_S3_W, _S3_H = 160, 120
_S3_SMOOTH_W = 9
_S3_T_LO = -0.3031277992659145
_S3_T_HI = 0.19773931497501007
_S3_FAR = slice(int(np.ceil(0.25 * _S3_H)), int(np.ceil(0.47 * _S3_H)))


def _s3_yaw_series(gray):
    n = len(gray)
    out = np.zeros(n, np.float64)
    for k in range(1, n):
        fl = cv2.calcOpticalFlowFarneback(gray[k - 1], gray[k], None, 0.5, 4, 15, 3, 5, 1.1, 0)
        out[k] = float(np.median(fl[_S3_FAR, :, 0]))
    if n > 1:
        out[0] = out[1]
    return out


def _s3_smooth(x, w=_S3_SMOOTH_W):
    x = np.asarray(x, np.float64)
    h = w // 2
    return np.array([x[max(0, i - h):i + h + 1].mean() for i in range(len(x))])


def _s3_classify(yaw):
    s = _s3_smooth(yaw)
    return np.where(s > _S3_T_HI, "LEFT", np.where(s < _S3_T_LO, "RIGHT", "STRAIGHT"))


def _s3_predict_steer(gray):
    """gray: (N, 120, 160) uint8 at 10 Hz -> array of LEFT/STRAIGHT/RIGHT per frame."""
    g = np.asarray(gray)
    if len(g) < 2:
        return np.array(["STRAIGHT"] * len(g))
    return _s3_classify(_s3_yaw_series(g))


def _stage3_frames(path: Path):
    capture = cv2.VideoCapture(str(path))
    frames, gray = [], []
    while True:
        ok, bgr = capture.read()
        if not ok:
            break
        # yaw proxy: full-frame gray at 160x120, byte-identical to s3_yaw_steer.to_gray.
        gray.append(cv2.resize(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), (_S3_W, _S3_H),
                               interpolation=cv2.INTER_AREA))
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
    return torch.stack(frames), np.stack(gray)


def predict_stage3(data_dir, model_dir):
    device = _device()
    checkpoint = torch.load(Path(model_dir) / "best.pt", map_location="cpu", weights_only=False)
    state = checkpoint["model"]
    # e002 speed-regression checkpoints carry head_kind="speed" (or a speed.* weight);
    # e001 accel-class checkpoints keep the original path byte-for-byte.
    predict_speed = checkpoint.get("head_kind") == "speed" or "speed.weight" in state
    rule = checkpoint.get("rule", S3_RULE)
    # e003 checkpoints predict speed/speed_scale; recover m/s before the rule derive.
    # Default 1.0 keeps e001 (accel head) and e002 (no key) byte-identical.
    speed_scale = float(checkpoint.get("speed_scale", 1.0))
    # e004 checkpoints add a binary STOPPED head whose firing overrides the accel
    # class (the speed head cannot produce STOPPED). Absent key -> byte-identical.
    predict_stopped = bool(checkpoint.get("predict_stopped", False)) or "stopped.weight" in state
    stopped_threshold = float(checkpoint.get("stopped_threshold", 0.5))
    model = _Stage3MViT(predict_speed=predict_speed, predict_stopped=predict_stopped)
    model.load_state_dict(state)
    model.to(device).eval()
    videos = _video_paths(Path(data_dir) / "videos")
    rows = []
    with torch.inference_mode():
        for path in videos:
            frames, gray = _stage3_frames(path)
            count = len(frames)
            centers = np.arange(count)
            head_predictions, stopped_predictions = [], []
            for start in range(0, count, 8):
                center = centers[start : start + 8]
                indices = np.clip(center[:, None] - 8 + np.arange(16)[None, :], 0, count - 1)
                clips = frames[torch.from_numpy(indices)].permute(0, 2, 1, 3, 4).float() / 255.0
                clips = (clips - S3_MEAN[None, :, None, :, :]) / S3_STD[None, :, None, :, :]
                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    out = model(clips.to(device, non_blocking=True))
                head_logits = out[0]
                if predict_speed:
                    head_predictions.extend(head_logits.squeeze(-1).float().cpu().tolist())
                else:
                    head_predictions.extend(head_logits.argmax(1).cpu().tolist())
                if predict_stopped:
                    stopped_predictions.extend(torch.sigmoid(out[2].squeeze(-1).float()).cpu().tolist())
            if predict_speed:
                head_predictions = [v * speed_scale for v in head_predictions]
                accel_labels = _accel_from_speed(head_predictions, rule)
            else:
                accel_labels = [ACCEL[i] for i in head_predictions]
            if predict_stopped:
                accel_labels = [
                    "STOPPED" if p >= stopped_threshold else a
                    for p, a in zip(stopped_predictions, accel_labels)
                ]
            # decision 92483f83 / 12-D: steer from the yaw proxy (consecutive 10 Hz
            # decoded frames) replaces the trained steer head; accel stays from e005.
            steer_labels = _s3_predict_steer(gray)
            for sample_index, (accel_label, steer_label) in enumerate(zip(accel_labels, steer_labels)):
                rows.append(
                    {
                        "ID": path.stem,
                        "sample_index": sample_index,
                        "accel_label": accel_label,
                        "steer_label": steer_label,
                    }
                )
    del model
    torch.cuda.empty_cache()
    return pd.DataFrame(rows, columns=["ID", "sample_index", "accel_label", "steer_label"])
