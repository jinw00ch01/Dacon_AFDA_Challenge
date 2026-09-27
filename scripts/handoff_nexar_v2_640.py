"""Build 640px handoff copies of the Nexar v2 subset for Pro's S2 labeling.

CLAUDE.md decision 8 (S2 expansion): send Pro ~300 more Nexar positives as 640px
copies whose DECODED frame count equals the original, so Pro can label contact /
lane-entry / direction / evasion. The collision timing comes from the Nexar
`time_of_event` (seconds) -> collision_frame = round(time_of_event * fps), tagged
`label_source=nexar_event` and `contact_unverified` until Pro confirms contact.

ffmpeg is not installed on this PC, so downscaling uses OpenCV frame-by-frame:
we decode every frame, resize (longest side -> <=640, even dims), and write it, so
the output frame count equals the number of successfully decoded input frames BY
CONSTRUCTION. We then re-decode the output and assert its count matches, giving a
verified frame-parity guarantee (decision 8 requires "원본과 디코드 프레임 수가 같은 640px 사본").

Outputs (git-ignored, under data/derived/):
  data/derived/handoff/nexar_v2_640/videos/<stem>.mp4   -- the 640px copies
  data/derived/handoff/nexar_v2_640/nexar_ext_meta.csv  -- per-video meta + parity
  data/derived/handoff/nexar_v2_640/summary.json        -- run summary + batching

Usage (smoke a few first, then full via a queued CPU job):
  python scripts/handoff_nexar_v2_640.py --limit 3
  python scripts/handoff_nexar_v2_640.py            # all 300
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/external/nexar_subset_v2"
OUT = ROOT / "data/derived/handoff/nexar_v2_640"
MAX_SIDE = 640
BATCH_BYTES = int(3.5 * 1024**3)  # keep each request packet well under the 4 GiB cap


def _even(x: int) -> int:
    return x - (x % 2)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_time_of_event() -> dict:
    """stem -> time_of_event seconds (float), from the positive metadata.csv."""
    toe = {}
    meta = SRC / "train/positive/metadata.csv"
    with meta.open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            stem = Path(row["file_name"]).stem
            v = row.get("time_of_event")
            try:
                toe[stem] = float(v) if v not in (None, "") else None
            except ValueError:
                toe[stem] = None
    return toe


def _downscale(src: Path, dst: Path):
    """Decode every frame, resize longest side to <=MAX_SIDE, write. Returns dict."""
    cap = cv2.VideoCapture(str(src))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open {src}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    w0 = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h0 = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    scale = min(1.0, MAX_SIDE / max(w0, h0))
    ow, oh = (_even(max(2, round(w0 * scale))), _even(max(2, round(h0 * scale))))

    dst.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out_fps = fps if fps and fps > 0 else 30.0
    writer = cv2.VideoWriter(str(dst), fourcc, out_fps, (ow, oh))
    if not writer.isOpened():
        cap.release()
        raise RuntimeError(f"cannot open writer {dst}")

    in_frames = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        in_frames += 1
        writer.write(cv2.resize(frame, (ow, oh), interpolation=cv2.INTER_AREA))
    cap.release()
    writer.release()

    # Re-decode the output and count -> verified parity.
    cap2 = cv2.VideoCapture(str(dst))
    out_frames = 0
    while True:
        ok, _ = cap2.read()
        if not ok:
            break
        out_frames += 1
    cap2.release()

    return {
        "orig_w": w0, "orig_h": h0, "out_w": ow, "out_h": oh,
        "fps": round(float(out_fps), 4),
        "orig_decoded_frames": in_frames, "out_decoded_frames": out_frames,
        "parity_ok": bool(in_frames == out_frames and in_frames > 0),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="process only first N (smoke)")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    out = args.out
    vids = sorted((SRC / "train/positive").glob("*.mp4"))
    if args.limit:
        vids = vids[: args.limit]
    toe = _load_time_of_event()
    (out / "videos").mkdir(parents=True, exist_ok=True)

    rows = []
    n_bad = 0
    for i, src in enumerate(vids, 1):
        stem = src.stem
        dst = out / "videos" / f"{stem}.mp4"
        info = _downscale(src, dst)
        t = toe.get(stem)
        cframe = int(round(t * info["fps"])) if t is not None else None
        row = {
            "video_id": stem,
            "out_path": f"videos/{stem}.mp4",
            "orig_res": f"{info['orig_w']}x{info['orig_h']}",
            "out_res": f"{info['out_w']}x{info['out_h']}",
            "fps": info["fps"],
            "orig_decoded_frames": info["orig_decoded_frames"],
            "out_decoded_frames": info["out_decoded_frames"],
            "parity_ok": int(info["parity_ok"]),
            "time_of_event_s": t if t is not None else "",
            "collision_frame_nexar": cframe if cframe is not None else "",
            "label_source": "nexar_event",
            "contact_status": "contact_unverified",
            "out_bytes": dst.stat().st_size,
            "out_sha256": _sha256(dst),
        }
        rows.append(row)
        if not info["parity_ok"]:
            n_bad += 1
            print(f"  PARITY FAIL {stem}: in={info['orig_decoded_frames']} out={info['out_decoded_frames']}",
                  flush=True)
        if i % 25 == 0 or i == len(vids):
            print(f"{i}/{len(vids)} done (parity_fail so far={n_bad})", flush=True)

    # Greedy batch assignment (<= BATCH_BYTES per request packet).
    batch, acc, bidx = [], 0, 1
    for r in rows:
        if acc + r["out_bytes"] > BATCH_BYTES and batch:
            bidx += 1
            acc = 0
        r["batch"] = bidx
        acc += r["out_bytes"]

    fields = ["video_id", "out_path", "orig_res", "out_res", "fps",
              "orig_decoded_frames", "out_decoded_frames", "parity_ok",
              "time_of_event_s", "collision_frame_nexar", "label_source",
              "contact_status", "out_bytes", "out_sha256", "batch"]
    with (out / "nexar_ext_meta.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    total_bytes = sum(r["out_bytes"] for r in rows)
    summary = {
        "source_subset": str(SRC.relative_to(ROOT)),
        "source_revision": "260710de7e076bc3f5259071421a77dd76d36ac3",
        "n_videos": len(rows),
        "n_parity_fail": n_bad,
        "max_side": MAX_SIDE,
        "total_out_bytes": total_bytes,
        "total_out_gib": round(total_bytes / 1024**3, 3),
        "n_batches": bidx,
        "batch_bytes_cap": BATCH_BYTES,
        "label_note": "collision_frame_nexar = round(time_of_event * fps); label_source=nexar_event; contact_unverified (Pro confirms contact + labels entry/direction/evasion). NOT DACON GT.",
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"summary: {json.dumps(summary)}", flush=True)
    if n_bad:
        print(f"WARNING: {n_bad} videos failed frame parity — do NOT hand off those.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
