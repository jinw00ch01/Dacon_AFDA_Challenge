"""Cache per-frame ResNet18 features for Stage 2 temporal training.

Why this matches inference (submission/inference.py ``predict_stage2``):
the eval server gives Stage 2 pre-extracted frame folders and processes EVERY
frame (stride=1) through the SAME ResNet18 (``resnet18-f37072fd.pth``,
IMAGENET1K_V1) with ``fc=Identity`` to get a 512-d feature per frame, then a
BiGRU over that sequence predicts collision/entry frame + scene heads. So we
cache one (T, 512) float16 feature sequence per labelled video where cache row
position ``i`` == frame index ``i`` (0-based, the same index the agent labels
``collision_frame`` / ``entry_frame`` reference -- see stage2_agent_label.py,
which bounds both to ``0..decoded_frames-1``).

Caveat (recorded, not hidden): training decodes frames from the source .mp4
with cv2, while eval reads already-extracted image files. The per-frame
ResNet18 transform is identical, but the decode path differs (codec/extraction).
Proxy agent labels are NOT official GT (AGENTS.md); metrics carry the source.

The ResNet18 weights are downloaded once (training-time only) and copied to
``models/stage2/resnet18-f37072fd.pth`` so the submission loads the SAME weights.

Output: ``<out_dir>/<video_id>.npy`` (T,512 float16) + ``manifest.json`` with per
-video SHA256, decoded frame count, split, and the label columns needed to train.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from PIL import Image
from torch.utils.data import DataLoader, Dataset

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from afda.models import build_stage2_backbone  # noqa: E402
from afda.preprocess import stage2_transform  # noqa: E402

try:  # decode with cv2 (same lib the eval Stage 3 decoder uses)
    import cv2
except Exception as exc:  # pragma: no cover - environment guard
    raise SystemExit(f"cv2 required for frame decode: {exc}")


def assign_splits(df: pd.DataFrame, val_frac: float = 0.2, seed: int = 0) -> pd.Series:
    """Deterministic per-video split, stratified by has-collision-label.

    Each Nexar clip is an independent accident, so a per-video split leaks no
    frames. We stratify on ``collision_valid`` so the tiny validation set keeps
    some positive-with-collision videos.
    """
    rng = np.random.RandomState(seed)
    split = pd.Series("train", index=df.index)
    for _, idx in df.groupby(df["collision_valid"].astype(int)).groups.items():
        idx = list(idx)
        rng.shuffle(idx)
        n_val = max(1, round(len(idx) * val_frac)) if len(idx) >= 3 else 0
        for i in idx[:n_val]:
            split[i] = "validation"
    return split


class _FrameSet(Dataset):
    def __init__(self, frames, transform):
        self.frames, self.transform = frames, transform

    def __len__(self):
        return len(self.frames)

    def __getitem__(self, index):
        return self.transform(Image.fromarray(self.frames[index]))


def decode_frames(path: Path):
    cap = cv2.VideoCapture(str(path))
    frames = []
    while True:
        ok, bgr = cap.read()
        if not ok:
            break
        frames.append(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    cap.release()
    return frames


def extract(video_path, backbone, transform, device, batch_size, workers):
    frames = decode_frames(video_path)
    if not frames:
        raise ValueError(f"cannot decode {video_path.name}")
    loader = DataLoader(
        _FrameSet(frames, transform), batch_size=batch_size, shuffle=False,
        num_workers=workers, pin_memory=(device.type == "cuda"),
    )
    feats = []
    with torch.inference_mode():
        for images in loader:
            with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=(device.type == "cuda")):
                out = backbone(images.to(device, non_blocking=True))
            feats.append(out.float().cpu())
    return torch.cat(feats).to(torch.float16).numpy(), len(frames)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


LABEL_COLS = [
    "video_id", "source_path", "source_label", "decoded_frames", "fps",
    "label_source", "actual_contact", "lane_entry_suitable",
    "collision_frame", "entry_frame", "evasion_space", "entry_side",
    "collision_valid", "entry_valid", "evasion_valid", "side_valid",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--labels",
        default="data/derived/releases/s2-labels-v6-20260925/stage2_merged_v6.csv",
    )
    ap.add_argument("--out-dir", default="data/derived/s2_feat_cache_v1")
    ap.add_argument("--batch-size", type=int, default=256)
    ap.add_argument("--num-workers", type=int, default=4)
    ap.add_argument("--val-frac", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--limit", type=int, default=0, help="cache only N videos (smoke)")
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    df = pd.read_csv(ROOT / args.labels, dtype={"video_id": str})
    df = df.reset_index(drop=True)
    df["split"] = assign_splits(df, args.val_frac, args.seed)
    if args.limit:
        df = df.head(args.limit).copy()

    out_dir = ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # ResNet18 IMAGENET1K_V1 weights: same object the submission loads.
    from torchvision.models import ResNet18_Weights

    weights = ResNet18_Weights.IMAGENET1K_V1
    backbone = build_stage2_backbone()
    backbone.load_state_dict(weights.get_state_dict(progress=False), strict=False)
    backbone.to(device).eval()
    models_dir = ROOT / "models" / "stage2"
    models_dir.mkdir(parents=True, exist_ok=True)
    weight_path = models_dir / "resnet18-f37072fd.pth"
    if not weight_path.exists():
        torch.save(weights.get_state_dict(progress=False), weight_path)

    transform = stage2_transform()
    manifest = {
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "labels": args.labels,
        "backbone": "resnet18 IMAGENET1K_V1 (fc=Identity)",
        "resnet18_sha256": sha256(weight_path),
        "note": "per-frame ResNet18 features; row i == frame index i; proxy agent labels, not official GT",
        "videos": [],
    }
    n_ok, mismatches = 0, []
    for _, row in df.iterrows():
        vid = row["video_id"]
        src = ROOT / row["source_path"]
        feats, n_dec = extract(src, backbone, transform, device, args.batch_size, args.num_workers)
        npy = out_dir / f"{vid}.npy"
        np.save(npy, feats)
        recorded = int(float(row["decoded_frames"]))
        if n_dec != recorded:
            mismatches.append({"video_id": vid, "decoded_now": n_dec, "recorded": recorded})
        entry = {c: (None if pd.isna(row[c]) else row[c]) for c in LABEL_COLS}
        entry.update({
            "split": row["split"],
            "cached_frames": int(feats.shape[0]),
            "feat_dim": int(feats.shape[1]),
            "sha256": sha256(npy),
        })
        manifest["videos"].append(entry)
        n_ok += 1
        print(f"  {vid}: {feats.shape} split={row['split']} (decoded {n_dec}, recorded {recorded})", flush=True)

    manifest["n_videos"] = n_ok
    manifest["n_train"] = int((df["split"] == "train").sum())
    manifest["n_validation"] = int((df["split"] == "validation").sum())
    manifest["decode_mismatches"] = mismatches
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(
        f"cached {n_ok} videos -> {out_dir} "
        f"(train={manifest['n_train']} val={manifest['n_validation']} mismatches={len(mismatches)})",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
