"""Compare v1c trial pairs (ORIG vs DIG) with the Baseline stage1 pair statistics."""
import csv
import json
import sys
from pathlib import Path

import cv2
import numpy as np


def frames(path):
    cap = cv2.VideoCapture(str(path))
    out = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        out.append(f)
    cap.release()
    return out


def psnr(a, b):
    mse = np.mean((a.astype(np.float32) - b.astype(np.float32)) ** 2)
    return 10 * np.log10(255 ** 2 / max(mse, 1e-9))


def hf(bgr):
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    return float((g - cv2.GaussianBlur(g, (0, 0), 1.0)).std())


def main():
    d = Path(sys.argv[1])
    rows = list(csv.DictReader((d / "manifest.csv").open(encoding="utf-8")))
    by = {r["file"]: r for r in rows}
    out = []
    for r in rows:
        if r["variant"] == "ORIG":
            continue
        o = by[r["file"].rsplit("_", 1)[0] + "_ORIG.mp4"]
        fo, fr = frames(d / o["file"]), frames(d / r["file"])
        idx = np.linspace(3, len(fo) - 4, 3).astype(int)
        out.append({
            "file": r["file"], "frames": [len(fo), len(fr)],
            "psnr_db": [round(psnr(fo[i], fr[i]), 1) for i in idx],
            "hf_ratio": round(float(np.mean([hf(fr[i]) / hf(fo[i]) for i in idx])), 3),
            "bytes_ratio": round(int(r["bytes"]) / int(o["bytes"]), 2),
            "p1_dark": [round(float(np.percentile(fo[idx[1]], 1)), 1), round(float(np.percentile(fr[idx[1]], 1)), 1)],
        })
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
