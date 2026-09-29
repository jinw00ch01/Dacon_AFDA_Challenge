"""How much of the Baseline rerecord cue (fine-grain noise) survives the S1 model
input (_center_crop_resize to 224, INTER_AREA)? Compares HF residual std of the
aligned pairs at native resolution vs at 224, and the mean abs pixel diff at 224."""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, "src")


def center_crop_resize(rgb, size):  # verbatim copy of afda.preprocess._center_crop_resize
    h, w = rgb.shape[:2]
    scale = size / min(h, w)
    nh, nw = max(size, round(h * scale)), max(size, round(w * scale))
    rgb = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_AREA)
    y, x = (nh - size) // 2, (nw - size) // 2
    return rgb[y: y + size, x: x + size]


def hf(g, sigma=1.0):
    g = g.astype(np.float32)
    return float((g - cv2.GaussianBlur(g, (0, 0), sigma)).std())


def frame(p, i):
    cap = cv2.VideoCapture(str(p))
    cap.set(cv2.CAP_PROP_POS_FRAMES, i)
    ok, f = cap.read()
    cap.release()
    return cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)


def pair_stats(po, pr, idxs):
    nat, s224, diff224 = [], [], []
    for i in idxs:
        a, b = frame(po, i), frame(pr, i)
        nat.append(hf(b) / hf(a))
        a2, b2 = center_crop_resize(a, 224), center_crop_resize(b, 224)
        s224.append(hf(b2) / hf(a2))
        diff224.append(float(np.abs(a2.astype(np.float32) - b2.astype(np.float32)).mean()))
    return {"hf_ratio_native": round(float(np.mean(nat)), 3),
            "hf_ratio_224": round(float(np.mean(s224)), 3),
            "mean_abs_diff_224": round(float(np.mean(diff224)), 2)}


def main():
    base = Path(sys.argv[1])
    syn = Path(sys.argv[2])
    out = Path(sys.argv[3])
    rep = {"baseline_real": {}, "synthetic_val": {}}
    for k in range(1, 6):
        rep["baseline_real"][k] = pair_stats(base / "original" / f"00000{k}.mp4",
                                             base / "rerecorded" / f"00000{k}.mp4", (5, 25, 45))
    for s in ("SRC017", "SRC018", "SRC019", "SRC020"):
        for v in range(4):
            rep["synthetic_val"][f"{s}_SYN{v}"] = pair_stats(
                syn / f"{s}_ORIG.mp4", syn / f"{s}_SYN{v}.mp4", (30, 150, 270))
    (out / "hf_at_224.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    for grp, d in rep.items():
        arr = {k: np.mean([x[k] for x in d.values()]) for k in next(iter(d.values()))}
        print(grp, {k: round(float(v), 3) for k, v in arr.items()})
        for name, x in d.items():
            print("  ", name, x)


if __name__ == "__main__":
    main()
