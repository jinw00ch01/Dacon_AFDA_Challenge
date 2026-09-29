"""v1c calibration with the official example pipeline: ORIG = OpenCV mp4v (MPEG-4 Simple,
GOP 12, 10 fps, 1280x720, like Baseline originals), SYN = decode ORIG -> grain/tone -> ffmpeg
libx264 default (High, B-frames, like Baseline rerecorded). Prints PSNR / HF ratio / bytes ratio
to compare with Baseline pairs (PSNR 30.6-31.8, HF 1.07-1.44, bytes ~2.1)."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from s1_v1c_calib import read, stats, write, W, H, FPS  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "work" / "s1_v1c_calib"
FFMPEG = shutil.which("ffmpeg") or str(next(Path.home().glob(
    "AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg*/ffmpeg-*/bin/ffmpeg.exe")))


def x264(path, frames, crf=None):
    cmd = [FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
           "-r", str(int(FPS)), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p"]
    if crf is not None:
        cmd += ["-crf", str(crf)]
    p = subprocess.Popen(cmd + [str(path)], stdin=subprocess.PIPE)
    for f in frames:
        p.stdin.write(np.ascontiguousarray(f).tobytes())
    p.stdin.close()
    assert p.wait() == 0


def tone(f, rng, sigma, contrast, black):
    img = f.astype(np.float32)
    if sigma > 0:
        img += rng.normal(0, sigma, img.shape[:2]).astype(np.float32)[..., None]
    img = (img - 128) * contrast + 128 - black
    return np.clip(img, 0, 255).astype(np.uint8)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    srcs = sys.argv[1:] or ["SRC001_ORIGINAL.mp4", "SRC010_ORIGINAL.mp4"]
    res = {}
    for s in srcs:
        src = ROOT / "data/derived/comma_subset_v1/s1_playback" / s
        frames = [cv2.resize(f, (W, H), interpolation=cv2.INTER_AREA) for f in read(src, 100)[::2]][:50]
        po = OUT / f"{s[:6]}_ORIG_mp4v.mp4"
        write(po, frames)
        dec = read(po)
        rng = np.random.default_rng(0)
        for sigma in (0, 2, 3, 4):
            for contrast, black in ((1.0, 0), (1.04, 2)):
                for crf in (None, 18):
                    name = f"{s[:6]}_s{sigma}_c{contrast}_b{black}_crf{crf or 23}"
                    pr = OUT / f"{name}.mp4"
                    x264(pr, [tone(f, rng, sigma, contrast, black) for f in dec], crf)
                    res[name] = stats(po, pr)
                    print(name, res[name], flush=True)
    (OUT / "calib2.json").write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
