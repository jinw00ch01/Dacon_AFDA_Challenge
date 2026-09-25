"""Render a contact sheet of decoded frames with their 0-based decode index burned in.

Used by the frame-labeler agent to find collision/entry frames coarse-to-fine:
  python scripts/frame_sheet.py --video data/external/nexar_subset_v1/train/positive/00004.mp4 --start 0 --end 1200 --step 40
  python scripts/frame_sheet.py --video ... --start 880 --end 920 --step 2
Frames are decoded sequentially (no seeking) so the index equals the decode order.
Output images are downscaled (default 320 px per tile) and written under work/frames/.
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=-1, help="exclusive; -1 = until the last frame")
    parser.add_argument("--step", type=int, default=30)
    parser.add_argument("--cols", type=int, default=5)
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--max-tiles", type=int, default=30)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    video = args.video if args.video.is_absolute() else ROOT / args.video
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS)
    wanted = None if args.end < 0 else set(range(args.start, args.end, max(1, args.step)))
    tiles, index, total = [], 0, 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        total = index + 1
        take = (index >= args.start and (index - args.start) % max(1, args.step) == 0) if wanted is None else index in wanted
        if take and len(tiles) < args.max_tiles:
            height = round(frame.shape[0] * args.width / frame.shape[1])
            tile = cv2.resize(frame, (args.width, height), interpolation=cv2.INTER_AREA)
            label = f"#{index}  {index / fps:.2f}s" if fps else f"#{index}"
            cv2.rectangle(tile, (0, 0), (args.width, 22), (0, 0, 0), -1)
            cv2.putText(tile, label, (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1, cv2.LINE_AA)
            tiles.append((index, tile))
        if args.end >= 0 and index >= args.end - 1:
            break
        index += 1
    cap.release()
    if not tiles:
        raise SystemExit(json.dumps({"error": "no frames in range", "decoded_until": total}))
    h, w = tiles[0][1].shape[:2]
    rows = (len(tiles) + args.cols - 1) // args.cols
    sheet = np.zeros((rows * h, args.cols * w, 3), dtype=np.uint8)
    for i, (_, tile) in enumerate(tiles):
        r, c = divmod(i, args.cols)
        sheet[r * h:(r + 1) * h, c * w:(c + 1) * w] = tile[:h, :w]
    out = args.out or ROOT / "work/frames" / f"{video.stem}_{args.start}_{args.end}_s{args.step}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), sheet, [cv2.IMWRITE_JPEG_QUALITY, 85])
    print(json.dumps({"sheet": str(out), "frames": [i for i, _ in tiles], "fps": fps,
                      "decoded_frames_seen": total, "tile_width": args.width}))


if __name__ == "__main__":
    main()
