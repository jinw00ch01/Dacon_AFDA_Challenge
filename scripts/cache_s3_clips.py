"""Cache 10Hz frame sequences for Stage 3 training from comma segment video.hevc.

Why this exists (see docs/STATUS.md): the eval server feeds Stage 3 a *10Hz* video and
asks for a class per 0.1s sample_index. The S1 playback clips (10s / 200 frames @ 20fps)
are for Stage 1 and are the wrong temporal rate for S3. To keep training and eval identical
we decode each source's full comma segment ``video.hevc`` with the SAME decoder the eval uses
(``src.afda.preprocess.decode_stage3_frames`` -> cv2.VideoCapture, 256 short-side, center-crop
224), then decimate to 10Hz by selecting the ``source_frame_index`` rows from the frozen
auxiliary CSV. The result per source is a (n_rows, 3, 224, 224) uint8 tensor that is exactly
what ``decode_stage3_frames`` would return for a real 10Hz eval video -- so training can build
16-frame windows with ``stage3_clip_indices`` the same way inference does.

This script produces frame caches only. Class targets are NOT written here: they are computed
at train time from ``src.afda.stage3_labels`` (proxy rule v1b) so the label rule stays the
single source of truth. SRC014 is excluded from S3 (frame-time offset > 30ms; see report.json).

Output: <out>/<split>/<source_id>.npy (uint8) + <out>/manifest.json.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from afda.preprocess import decode_stage3_frames  # noqa: E402

SEGMENTS = ROOT / "data" / "external" / "comma2k19_subset_v1" / "segments"
DEFAULT_AUX = ROOT / "data" / "derived" / "releases" / "s3-aux-rules-v1b-20260925" / "s3_auxiliary_10hz.csv"
FALLBACK_AUX = ROOT / "data" / "derived" / "comma_subset_v1" / "s3_auxiliary_10hz.csv"
EXCLUDED = {"SRC014"}


def resolve_hevc(origin_group: str) -> Path:
    """origin_group 'hash|date' -> the unique video.hevc under segments/hash_date/<seg>/."""
    dir_name = origin_group.replace("|", "_")
    matches = glob.glob(str(SEGMENTS / dir_name / "*" / "video.hevc"))
    if len(matches) != 1:
        raise ValueError(f"{origin_group}: expected 1 video.hevc, found {len(matches)}")
    return Path(matches[0])


def sha256_bytes(arr: np.ndarray) -> str:
    return hashlib.sha256(arr.tobytes()).hexdigest()


def rel(path: Path) -> str:
    """Repo-relative string when possible, else absolute (e.g. smoke dirs outside ROOT)."""
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aux", type=Path, default=None, help="auxiliary 10Hz CSV (default: frozen v1b release)")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "derived" / "s3_clip_cache_v1")
    ap.add_argument("--sources", nargs="*", default=None, help="only these source_ids (smoke)")
    args = ap.parse_args()

    aux_path = args.aux or (DEFAULT_AUX if DEFAULT_AUX.exists() else FALLBACK_AUX)
    aux = pd.read_csv(aux_path)
    args.out.mkdir(parents=True, exist_ok=True)

    manifest = {
        "aux_csv": rel(aux_path),
        "decoder": "src.afda.preprocess.decode_stage3_frames (cv2, 256 short-side, center-crop 224)",
        "rate": "10Hz, decimated by source_frame_index",
        "excluded_source_ids": sorted(EXCLUDED),
        "note": "frames only; labels computed at train time from stage3_labels v1b; not official GT",
        "sources": [],
    }

    src_ids = args.sources or [s for s in sorted(aux["source_id"].unique()) if s not in EXCLUDED]
    for sid in src_ids:
        if sid in EXCLUDED:
            print(f"{sid}: excluded, skipping")
            continue
        rows = aux[aux["source_id"] == sid].sort_values("sample_index")
        origin = rows["origin_group"].iloc[0]
        split = rows["split"].iloc[0]
        idx = rows["source_frame_index"].to_numpy().astype(np.int64)
        hevc = resolve_hevc(origin)

        frames = decode_stage3_frames(hevc).numpy()  # (T,3,224,224) uint8
        total = frames.shape[0]
        if idx.max() >= total:
            raise ValueError(f"{sid}: source_frame_index max {idx.max()} >= decoded frames {total}")
        seq = frames[idx]  # (n_rows,3,224,224) uint8, 10Hz

        split_dir = args.out / split
        split_dir.mkdir(parents=True, exist_ok=True)
        out_path = split_dir / f"{sid}.npy"
        np.save(out_path, seq)
        entry = {
            "source_id": sid,
            "origin_group": origin,
            "split": split,
            "hevc": rel(hevc),
            "decoded_frames": int(total),
            "cached_rows": int(seq.shape[0]),
            "aux_rows": int(len(rows)),
            "source_frame_index_min": int(idx.min()),
            "source_frame_index_max": int(idx.max()),
            "npy": rel(out_path),
            "sha256": sha256_bytes(seq),
        }
        manifest["sources"].append(entry)
        print(f"{sid}: {split} {seq.shape} from {hevc.name} (decoded {total})")

    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote {len(manifest['sources'])} sources -> {args.out / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
