"""Calibrate a 'digital re-record' S1 variant (v1c) against the official Baseline pairs.
Target stats (work/s1_review_e001/baseline_pairs.json): aligned, PSNR 30.6-31.8 dB,
native HF-residual ratio 1.07-1.44, bytes ratio ~2.1, slightly darker blacks.
Writes a few trial clips to work/s1_v1c_calib/ and prints the same stats.
"""
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "work" / "s1_v1c_calib"
W, H, FPS = 1280, 720, 10.0


def codec_info(p):
    cap = cv2.VideoCapture(str(p))
    four = int(cap.get(cv2.CAP_PROP_FOURCC))
    cap.release()
    return "".join(chr((four >> 8 * i) & 0xFF) for i in range(4))


def read(p, n=None):
    cap = cv2.VideoCapture(str(p))
    fr = []
    while True:
        ok, f = cap.read()
        if not ok or (n and len(fr) >= n):
            break
        fr.append(f)
    cap.release()
    return fr


def hf(g, sigma=1.0):
    g = g.astype(np.float32)
    return float((g - cv2.GaussianBlur(g, (0, 0), sigma)).std())


def write(path, frames):
    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    for f in frames:
        w.write(f)
    w.release()


def degrade(f, rng, sigma, grain_blur, contrast, black):
    img = f.astype(np.float32)
    n = rng.normal(0, sigma, img.shape[:2]).astype(np.float32)
    if grain_blur > 0:
        n = cv2.GaussianBlur(n, (0, 0), grain_blur) * (1 + grain_blur)
    img = img + n[..., None]
    img = (img - 128) * contrast + 128 - black
    return np.clip(img, 0, 255).astype(np.uint8)


def stats(po, pr):
    O, R = read(po), read(pr)
    ps, hr = [], []
    for i in np.linspace(3, len(O) - 3, 3).astype(int):
        ps.append(cv2.PSNR(O[i], R[i]))
        hr.append(hf(cv2.cvtColor(R[i], cv2.COLOR_BGR2GRAY)) / hf(cv2.cvtColor(O[i], cv2.COLOR_BGR2GRAY)))
    return {"psnr": round(float(np.mean(ps)), 2), "hf_ratio": round(float(np.mean(hr)), 3),
            "bytes_ratio": round(os.path.getsize(pr) / os.path.getsize(po), 2)}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    base = ROOT / "Baseline/data/stage1"
    print("baseline codec", codec_info(base / "original/000001.mp4"), codec_info(base / "rerecorded/000001.mp4"))
    src = ROOT / "data/derived/comma_subset_v1/s1_playback" / (sys.argv[1] if len(sys.argv) > 1 else "SRC001_ORIGINAL.mp4")
    frames = [cv2.resize(f, (W, H), interpolation=cv2.INTER_AREA) for f in read(src, 100)[::2]][:50]
    po = OUT / "ORIG.mp4"
    write(po, frames)
    rng = np.random.default_rng(0)
    res = {}
    for sigma in (3, 5, 8):
        for gb in (0.0, 0.6):
            for contrast, black in ((1.0, 0), (1.04, 2)):
                name = f"s{sigma}_g{gb}_c{contrast}_b{black}"
                pr = OUT / f"{name}.mp4"
                write(pr, [degrade(f, rng, sigma, gb, contrast, black) for f in frames])
                res[name] = stats(po, pr)
                print(name, res[name], flush=True)
    (OUT / "calib.json").write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
