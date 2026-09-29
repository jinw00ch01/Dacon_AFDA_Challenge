"""Compare the paired Baseline stage1 examples (original/00000k vs rerecorded/00000k):
alignment, PSNR, fine-detail ratio, bitrate. Read-only on Baseline; writes to --out."""
import argparse
import json
import os
from pathlib import Path

import cv2
import numpy as np


def frames(p):
    cap = cv2.VideoCapture(str(p))
    out = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        out.append(f)
    cap.release()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    base, out = Path(a.baseline), Path(a.out)
    (out / "frames").mkdir(parents=True, exist_ok=True)
    res = []
    for k in range(1, 6):
        po, pr = base / "original" / f"00000{k}.mp4", base / "rerecorded" / f"00000{k}.mp4"
        O, R = frames(po), frames(pr)
        ps, sh, hfr = [], [], []
        for i in (5, 25, 45):
            ga = cv2.cvtColor(O[i], cv2.COLOR_BGR2GRAY).astype(np.float32)
            gb = cv2.cvtColor(R[i], cv2.COLOR_BGR2GRAY).astype(np.float32)
            ps.append(round(float(cv2.PSNR(O[i], R[i])), 1))
            (dx, dy), _ = cv2.phaseCorrelate(ga, gb)
            sh.append([round(dx, 2), round(dy, 2)])
            ha = ga - cv2.GaussianBlur(ga, (0, 0), 1.0)
            hb = gb - cv2.GaussianBlur(gb, (0, 0), 1.0)
            hfr.append(round(float(hb.std() / ha.std()), 3))
        res.append({"k": k, "frames_O": len(O), "frames_R": len(R), "psnr_db": ps,
                    "phase_shift_px": sh, "hf_std_ratio_R_over_O": hfr,
                    "bytes_O": os.path.getsize(po), "bytes_R": os.path.getsize(pr)})
        if k == 3:
            crop = np.hstack([O[25][200:520, 400:880], R[25][200:520, 400:880]])
            cv2.imwrite(str(out / "frames" / "crop_3.jpg"), cv2.resize(crop, (640, 213)))
    (out / "baseline_pairs.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    for r in res:
        print(r)


if __name__ == "__main__":
    main()
