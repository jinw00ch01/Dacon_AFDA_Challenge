"""S1 official-format pairs from Nexar (CLAUDE.md decision 13, 9/28 20:55).

The official S1/S2 examples are ~2012 low-quality dashcam clips: 1280x720 frames holding a 4:3
picture (960x720) between black pillar bars, a date/time caption at the top, 10 fps, 50 frames,
originals MPEG-4 (OpenCV mp4v), re-records x264. This tool turns Nexar clips into that format
(watermark, logo and the blurred bottom band are cropped away), then applies the v1c digital
re-record recipe of scripts/s1_synth_digital.py to the formatted original:

  NXF<vid>_W0_ORIG.mp4    formatted original, OpenCV mp4v (like the official originals)
  NXF<vid>_W0_DIG0.mp4    v1c grain/tone, libx264 CRF 23, grain calibrated to a HF-ratio target
  NXF<vid>_W0_ORIGX.mp4   ORIG decoded -> libx264 at DIG0's bytes           (x264/x264 pair)
  NXF<vid>_W0_DIGM0.mp4   DIG0 recipe -> mpeg4/mp4v at ORIG's bytes          (mp4v/mp4v pair)

pairs.csv lists the four (original, re-record) pairs per window; 2 of 4 are codec-matched.
Positives: the 50-frame window puts the Nexar event at a random index 28-42 (the official
examples hold the collision at 30-41). Negatives: a random window. Split by a hash of the video id
(train 70 / val 15 / test 15); every file of a video keeps that split. All outputs are synthetic.
"""
import argparse
import csv
import datetime as dt
import glob
import hashlib
import json
import os
import random
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import s1_synth_digital as sd  # noqa: E402

W, H, FPS, CLIP = sd.W, sd.H, sd.FPS, sd.CLIP
PIC_W = 960  # 4:3 picture inside the 1280x720 frame
BAR = (W - PIC_W) // 2
# Nexar layout (fractions of the frame): logo top-left x<0.18, GETNEXAR.COM box top-right x>0.80,
# blurred band y>0.815. A 4:3 crop from y 0.06-0.80 spans x 0.222-0.778 and keeps clear of all three.
CROP_Y0, CROP_Y1 = 0.06, 0.80


def split_of(vid):
    h = int(hashlib.sha256(f"s1nxf|{vid}".encode()).hexdigest(), 16) % 100
    return "train" if h < 70 else "val" if h < 85 else "test"


def crop_box(h, w):
    y0, y1 = int(round(CROP_Y0 * h)), int(round(CROP_Y1 * h))
    cw = int(round((y1 - y0) * 4 / 3))
    x0 = (w - cw) // 2
    return y0, y1, x0, x0 + cw


def sample_fmt(rng):
    """Per-clip look: low source resolution, caption date/time/colour/position, mild tone."""
    lo_h = rng.choice([240, 240, 288, 300, 360])
    colors = [(90, 205, 80), (80, 220, 110), (120, 200, 60), (235, 235, 235), (60, 210, 230)]
    start = dt.datetime(2010, 1, 1) + dt.timedelta(seconds=rng.randint(0, 4 * 365 * 86400))
    return {
        "lo_w": int(round(lo_h * 4 / 3)), "lo_h": lo_h,
        "blur": round(rng.uniform(0.0, 0.8), 2),
        "caption_start": start.strftime("%Y-%m-%d %H:%M:%S"),
        "caption_fmt": rng.choice(["%d. %m. %Y  %H:%M:%S", "%d.%m.%Y %H:%M:%S", "%Y/%m/%d %H:%M:%S"]),
        "caption_color": list(rng.choice(colors[:3] if rng.random() < 0.7 else colors[3:])),
        "caption_scale": round(rng.uniform(0.50, 0.62) * lo_h / 240, 3),
        "caption_x": round(rng.uniform(0.12, 0.30), 3),
        "caption_y": round(rng.uniform(0.07, 0.10), 3),
        "sat": round(rng.uniform(0.75, 1.0), 2),
        "gamma": round(rng.uniform(0.9, 1.1), 2),
        "first_sub": rng.randint(0, 9),  # tenth-of-second phase of the caption clock
    }


def format_frame(src, i, f):
    y0, y1, x0, x1 = crop_box(*src.shape[:2])
    pic = cv2.resize(src[y0:y1, x0:x1], (f["lo_w"], f["lo_h"]), interpolation=cv2.INTER_AREA)
    if f["sat"] < 1.0 or f["gamma"] != 1.0:
        hsv = cv2.cvtColor(pic, cv2.COLOR_BGR2HSV).astype(np.float32)
        hsv[..., 1] *= f["sat"]
        hsv[..., 2] = 255.0 * (hsv[..., 2] / 255.0) ** f["gamma"]
        pic = cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR)
    t = dt.datetime.strptime(f["caption_start"], "%Y-%m-%d %H:%M:%S") + dt.timedelta(
        seconds=(f["first_sub"] + i) // 10)
    text = t.strftime(f["caption_fmt"])
    org = (int(f["caption_x"] * f["lo_w"]), int(f["caption_y"] * f["lo_h"] + 14 * f["caption_scale"]))
    cv2.putText(pic, text, org, cv2.FONT_HERSHEY_SIMPLEX, f["caption_scale"], tuple(f["caption_color"]),
                max(1, int(round(2 * f["caption_scale"]))), cv2.LINE_AA)
    if f["blur"] > 0:
        pic = cv2.GaussianBlur(pic, (0, 0), f["blur"])
    out = np.zeros((H, W, 3), np.uint8)
    out[:, BAR:BAR + PIC_W] = cv2.resize(pic, (PIC_W, H), interpolation=cv2.INTER_LINEAR)
    return out


def read_ids(path, ids):
    cap = cv2.VideoCapture(str(path))
    want, got, k = set(ids), {}, 0
    while k <= max(ids):
        ok, fr = cap.read()
        if not ok:
            break
        if k in want:
            got[k] = fr
        k += 1
    cap.release()
    return [got[i] for i in ids if i in got]


def sources(root):
    rows = []
    with open(root / "work/nexar_v2/meta.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append({"vid": r["video_id"], "path": r["source_path"], "label": "positive",
                         "n": int(r["decoded_frames"]), "fps": float(r["fps"]),
                         "event": int(r["nexar_event_frame"])})
    for p in sorted(glob.glob(str(root / "data/external/nexar_subset_v1/train/negative/*.mp4"))):
        cap = cv2.VideoCapture(p)
        n, fps = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), cap.get(cv2.CAP_PROP_FPS) or 30.0
        cap.release()
        rows.append({"vid": Path(p).stem, "path": os.path.relpath(p, root).replace("\\", "/"),
                     "label": "negative", "n": n, "fps": fps, "event": None})
    return rows


def window(src, rng):
    step = src["fps"] / FPS
    n10 = int((src["n"] - 1) / step) + 1
    if src["event"] is not None:
        pos = rng.randint(28, 42)
        start = int(round(src["event"] / step)) - pos
    else:
        pos = None
        start = rng.randint(0, max(0, n10 - CLIP))
    start = max(0, min(start, n10 - CLIP))
    ids = [min(src["n"] - 1, int(round((start + i) * step))) for i in range(CLIP)]
    return ids, pos, start


def process(src, root, out_dir, ffmpeg, seed):
    rng = random.Random(f"{seed}|{src['vid']}")
    ids, pos, start = window(src, rng)
    frames = read_ids(root / src["path"], ids)
    if len(frames) != CLIP:
        return {"vid": src["vid"], "error": f"decoded {len(frames)} of {CLIP}"}
    f = sample_fmt(rng)
    clip = [format_frame(fr, i, f) for i, fr in enumerate(frames)]
    stem = f"NXF{src['vid']}_W0"
    sid, og, split = f"NXF{src['vid']}", f"nexar|{src['vid']}", split_of(src["vid"])
    orig = out_dir / f"{stem}_ORIG.mp4"
    sd.write_mp4v(orig, clip)
    decoded, _ = sd.read_frames(orig)
    p = sd.sample_params(rng)
    noise_seed = rng.randint(0, 2**31)
    dig = out_dir / f"{stem}_DIG0.mp4"
    sd.calibrate_grain(decoded, p, noise_seed, lambda fr: sd.write_x264(ffmpeg, dig, fr, p["crf"]), dig)
    common = {"source_id": sid, "origin_group": og, "split": split, "window": 0,
              "src_frame_range": f"{ids[0]}-{ids[-1]}", "source_playback": src["path"]}
    fmt = {"fmt": f, "nexar_label": src["label"], "event_pos_10hz": pos, "start_10hz": start}
    rows = []
    for path, variant, label, codec, params in [
            (orig, "ORIG", "original", "mpeg4", fmt), (dig, "DIG0", "recapture_synthetic", "h264", p)]:
        rows.append({**common, "file": path.name, "label": label, "synthetic": 1, "variant": variant,
                     "frames": sd.count_frames(path), "fps": FPS, "width": W, "height": H, "codec": codec,
                     "bytes": path.stat().st_size, "sha256": sd.sha256(path),
                     "params": json.dumps(params, separators=(",", ":"))})
    rows += sd.codec_matched_window(rows[0], rows[1], out_dir, out_dir, ffmpeg, seed)
    return {"vid": src["vid"], "rows": rows}


COLS = ["file", "source_id", "origin_group", "split", "label", "synthetic", "variant", "window",
        "src_frame_range", "frames", "fps", "width", "height", "codec", "bytes", "sha256",
        "source_playback", "params"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "data/derived/s1_nexar_fmt_v1")
    ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--seed", default="s1nxf_v1")
    ap.add_argument("--ffmpeg")
    args = ap.parse_args()
    out = args.out if args.out.is_absolute() else ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    ffmpeg = sd.find_ffmpeg(args.ffmpeg)
    srcs = sources(ROOT)
    rng = random.Random(args.seed)
    rng.shuffle(srcs)  # a partial run still mixes positives and negatives
    if args.limit:
        srcs = srcs[:args.limit]
    manifest = out / "manifest.csv"
    done = set()
    if manifest.exists():
        with manifest.open(encoding="utf-8", newline="") as fh:
            done = {r["source_id"] for r in csv.DictReader(fh) if r["variant"] == "DIGM0"}
    todo = [s for s in srcs if f"NXF{s['vid']}" not in done]
    new = not manifest.exists()
    with manifest.open("a", encoding="utf-8", newline="") as mf:
        wr = csv.DictWriter(mf, COLS)
        if new:
            wr.writeheader()
        with ProcessPoolExecutor(args.procs) as ex:
            futs = [ex.submit(process, s, ROOT, out, ffmpeg, args.seed) for s in todo]
            for fu in as_completed(futs):
                res = fu.result()
                if "error" in res:
                    print(json.dumps(res), flush=True)
                    continue
                wr.writerows([{k: r[k] for k in COLS} for r in res["rows"]])
                mf.flush()
                print(json.dumps({"vid": res["vid"], "bytes": sum(int(r["bytes"]) for r in res["rows"])}),
                      flush=True)
    with manifest.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    pairs = sd.build_pairs(rows)
    with (out / "pairs.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, list(pairs[0]))
        w.writeheader()
        w.writerows(pairs)


if __name__ == "__main__":
    main()
