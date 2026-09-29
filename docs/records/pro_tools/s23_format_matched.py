"""Format-matched S23 pairs: both classes in the official S1 clip shape, same encoder per track.

For each row of the frozen alignment table (release s1-s23-real-v1-20260926, sha 3764c0f7...):
  capture  window [0, 5s)                              of data/captures/s23/<file>
  original window [orig_start_s_final, +5s)            of the comma s1_playback original
Both: 10 fps nearest-frame sampling (50 frames), 16:9 centre crop, resize 1280x720 (INTER_AREA), then
  track 'mp4v' : both written by the OpenCV mp4v writer (Baseline original style)
  track 'x264' : both written by ffmpeg libx264 crf 23 yuv420p (Baseline re-record style)
So codec, resolution, fps, length and aspect carry no label information inside a track.
Outputs + manifest (split, origin_group, codec, frames, bytes, sha256) under --out. Label source: real capture.
usage: s23_format_matched.py --out <dir> [--limit N]
"""
import argparse
import csv
import hashlib
import sys
from pathlib import Path

import cv2
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import s1_synth_digital as sd  # noqa: E402

ALIGN = ROOT / "work" / "agent" / "outbox" / "s23_align_b1_files" / "s23_pairs_aligned.csv"
ALIGN_SHA = "3764c0f712a7ab812edbdca397a5f35c1f63024cee729224b0dde62a4c594311"
CAP_DIR = ROOT / "data" / "captures" / "s23"
W, H, FPS, N = 1280, 720, 10.0, 50
sd.W, sd.H, sd.FPS = W, H, FPS


def window(path, start_s):
    frames, fps = sd.read_frames(path)
    ids = [int(round((start_s + i / FPS) * fps)) for i in range(N)]
    if ids[-1] >= len(frames):
        raise RuntimeError(f"{path.name}: window {start_s}+5s beyond {len(frames)} frames")
    out = []
    for i in ids:
        f = frames[i]
        y0, y1, x0, x1 = sd.crop_16x9(*f.shape[:2])
        out.append(cv2.resize(f[y0:y1, x0:x1], (W, H), interpolation=cv2.INTER_AREA))
    return out, fps, len(frames)


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--ffmpeg")
    a = ap.parse_args()
    if sha256(ALIGN) != ALIGN_SHA:
        raise SystemExit("alignment table sha differs from the frozen release")
    ffmpeg = sd.find_ffmpeg(a.ffmpeg)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    align = pd.read_csv(ALIGN)
    if a.limit:
        align = align.head(a.limit)
    rows = []
    for r in align.itertuples():
        stem = r.file.replace(".mp4", "")
        cap, cap_fps, cap_n = window(CAP_DIR / r.file, 0.0)
        org, org_fps, org_n = window(ROOT / r.original_path, float(r.orig_start_s_final))
        for kind, frames, src_fps, src_n, start in (("capture", cap, cap_fps, cap_n, 0.0),
                                                     ("original", org, org_fps, org_n, r.orig_start_s_final)):
            label = "RERECORDED" if kind == "capture" else "ORIGINAL"
            for codec in ("mp4v", "x264"):
                p = out / f"{stem}_{kind.upper()}_{codec}.mp4"
                if codec == "mp4v":
                    sd.write_mp4v(p, frames)
                else:
                    sd.write_x264(ffmpeg, p, frames, 23)
                c = cv2.VideoCapture(str(p))
                n = 0
                while c.read()[0]:
                    n += 1
                c.release()
                rows.append({"file": p.name, "pair_id": stem, "source_id": r.source_id, "condition": r.condition,
                             "split": r.split, "origin_group": r.origin_group, "kind": kind, "label": label,
                             "codec": codec, "frames": n, "fps": FPS, "width": W, "height": H,
                             "src_fps": round(src_fps, 3), "src_frames": src_n, "start_s": float(start),
                             "bytes": p.stat().st_size, "sha256": sha256(p), "label_source": "real_capture"})
        print(stem, "ok", flush=True)
    with open(out / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)
    bad = [x["file"] for x in rows if x["frames"] != N]
    print({"clips": len(rows), "bad_frames": bad, "bytes": sum(x["bytes"] for x in rows)})


if __name__ == "__main__":
    main()
