"""Synthetic screen re-capture (S1) from comma s1_playback clips. CPU only, OpenCV only.

For each source clip (20 fps, 1280 wide) this writes:
  <SRC>_ORIG.mp4          original, same final pipeline (resize, 20->30 fps nearest-frame, same writer)
  <SRC>_SYN<k>.mp4        k-th synthetic re-capture with seeded random parameters
Re-capture model per variant (seeded by source id and k):
  display: frame scaled into a panel with a subpixel RGB stripe mask (period px) and a dark bezel
  camera:  perspective warp (corner jitter), zoom (bezel visible or cropped), hand jitter per frame,
           temporal sampling at 30 fps with blending across 20 fps display frames (exposure overlap),
           rolling-refresh brightness bands, defocus blur, gamma, white balance, black-level lift,
           vignetting, soft reflection blob, sensor noise, JPEG round trip (phone encode)
  final:   resize to OUT_W x OUT_H and the same mp4v writer as the original
Every output of a source keeps the source split (s23_capture_ready.csv confirmed_split).
A manifest CSV with parameters and SHA-256 is written next to the videos. All outputs are "synthetic".

--profile v1s (decision 9f59432f, HF direction gate): same seed stream as v1, but blur_sigma is mapped into
[0, 0.6] and contrast into [0.95, 1.0], and one texture pass is added after the final resize at the model's
224 input scale (per-frame sensor noise + a slowly drifting moire beat, both drawn on a 224x224 grid and
upsampled), so that the re-capture keeps more high frequency than the original at 224, as S23 captures do.
"""
import argparse
import csv
import hashlib
import json
import math
import random
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PLAN_REL = "data/derived/comma_subset_v1/s23_capture_ready.csv"
OUT_W, OUT_H, OUT_FPS = 960, 540, 30.0
CANVAS_W, CANVAS_H = 1280, 720  # camera sensor canvas before final resize


def read_frames(path):
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 20.0
    frames = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
    cap.release()
    return frames, fps


def writer(path):
    return cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), OUT_FPS, (OUT_W, OUT_H))


def final(img):
    return cv2.resize(img, (OUT_W, OUT_H), interpolation=cv2.INTER_AREA)


def sample_params(rng):
    return {
        "stripe_period_px": rng.choice([3, 3, 4, 5]),
        "stripe_strength": round(rng.uniform(0.15, 0.45), 3),
        "panel_scale": round(rng.uniform(0.95, 1.25), 3),   # >1 crops bezel away, <1 shows bezel
        "corner_jitter": round(rng.uniform(0.0, 0.06), 4),
        "rotation_deg": round(rng.uniform(-3, 3), 2),
        "hand_jitter_px": round(rng.uniform(0.0, 3.0), 2),
        "blend_exposure": round(rng.uniform(0.3, 1.0), 3),   # fraction of a display frame the exposure spans
        "band_amp": round(rng.uniform(0.0, 0.06), 4),
        "band_period_px": rng.randint(60, 300),
        "blur_sigma": round(rng.uniform(0.0, 1.6), 3),
        "gamma": round(rng.uniform(0.8, 1.25), 3),
        "wb": [round(rng.uniform(0.88, 1.12), 3), 1.0, round(rng.uniform(0.88, 1.12), 3)],  # B, G, R gains
        "black_lift": round(rng.uniform(3, 22), 1),
        "contrast": round(rng.uniform(0.8, 1.0), 3),
        "vignette": round(rng.uniform(0.05, 0.35), 3),
        "reflection_alpha": round(rng.uniform(0.0, 0.12), 3),
        "reflection_center": [round(rng.uniform(0.1, 0.9), 3), round(rng.uniform(0.1, 0.9), 3)],
        "reflection_radius": round(rng.uniform(0.15, 0.5), 3),
        "noise_sigma": round(rng.uniform(1.0, 5.0), 2),
        "jpeg_quality": rng.randint(55, 90),
    }


def v1s_params(p, seed, src, k):
    """Map v1 parameters into the v1s range and draw the 224-scale texture from a separate stream,
    so every other parameter of a v1s variant equals the v1 variant with the same seed."""
    q = dict(p)
    q["blur_sigma"] = round(p["blur_sigma"] * 0.6 / 1.6, 3)
    q["contrast"] = round(0.95 + (p["contrast"] - 0.8) * 0.25, 3)
    r = random.Random(f"{seed}|{src}|{k}|v1s")
    q["tex_noise_sigma"] = round(r.uniform(*V1S_NOISE), 2)
    q["moire_amp"] = round(r.uniform(*V1S_MOIRE), 4)
    q["moire_period_224"] = round(r.uniform(2.2, 4.0), 3)
    q["moire_beat_224"] = round(r.uniform(12.0, 40.0), 2)
    q["moire_angle_deg"] = round(r.uniform(-12, 12), 2)
    q["tex_seed"] = r.randint(0, 2**31)
    return q


V1S_NOISE = (4.0, 9.0)
V1S_MOIRE = (0.03, 0.08)
TEX = 224


def build_texture(p):
    yy, xx = np.mgrid[0:TEX, 0:TEX].astype(np.float32)
    a = math.radians(p["moire_angle_deg"])
    u = xx * math.cos(a) + yy * math.sin(a)
    v = -xx * math.sin(a) + yy * math.cos(a)
    return {"u": u, "v": v, "nrng": np.random.default_rng(p["tex_seed"])}


def texture_frame(img, tx, p, t):
    """One pass at the 224 input scale: multiplicative moire beat (drifting phase) + additive sensor noise."""
    ph = 2 * np.pi * 0.35 * t
    m = np.cos(2 * np.pi * tx["u"] / p["moire_period_224"] + ph) * (0.5 + 0.5 * np.cos(2 * np.pi * tx["v"] / p["moire_beat_224"] + 0.3 * ph))
    n = tx["nrng"].normal(0, p["tex_noise_sigma"], (TEX, TEX, 3)).astype(np.float32)
    n += tx["nrng"].normal(0, p["tex_noise_sigma"] * 0.5, (TEX, TEX, 1)).astype(np.float32)  # luma-correlated part
    h, w = img.shape[:2]
    m = cv2.resize(m, (w, h), interpolation=cv2.INTER_LINEAR)[..., None]
    n = cv2.resize(n, (w, h), interpolation=cv2.INTER_LINEAR)
    out = img.astype(np.float32) * (1.0 + p["moire_amp"] * m) + n
    return np.clip(out, 0, 255).astype(np.uint8)


def stripe_mask(h, w, period, strength):
    """Subpixel RGB stripes: each column lights mostly one channel (BGR order in OpenCV)."""
    cols = np.arange(w) % period
    mask = np.full((h, w, 3), 1.0 - strength, dtype=np.float32)
    for ch, c in zip((2, 1, 0), range(3)):  # R, G, B stripes left to right
        on = (cols * 3 // period) == c
        mask[:, on, ch] = 1.0
    mask[np.arange(h) % period == period - 1] *= (1.0 - strength / 2)  # row gap between pixel rows
    return mask / mask.mean()


def build_static(p, rng, src_h, src_w):
    # panel image size on the camera canvas (before warp), fitted to canvas and scaled by panel_scale
    fit = min(CANVAS_W / src_w, CANVAS_H / src_h)
    pw, ph = int(src_w * fit * p["panel_scale"]), int(src_h * fit * p["panel_scale"])
    mask = stripe_mask(ph, pw, p["stripe_period_px"], p["stripe_strength"])
    cx, cy = CANVAS_W / 2, CANVAS_H / 2
    src_pts = np.float32([[0, 0], [pw, 0], [pw, ph], [0, ph]])
    dst = []
    a = math.radians(p["rotation_deg"])
    for x, y in src_pts:
        dx, dy = x - pw / 2, y - ph / 2
        rx, ry = dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a)
        jx, jy = (rng.uniform(-1, 1) * p["corner_jitter"] * CANVAS_W, rng.uniform(-1, 1) * p["corner_jitter"] * CANVAS_H)
        dst.append([cx + rx + jx, cy + ry + jy])
    H = cv2.getPerspectiveTransform(src_pts, np.float32(dst))
    yy, xx = np.mgrid[0:CANVAS_H, 0:CANVAS_W].astype(np.float32)
    r = np.sqrt(((xx - cx) / cx) ** 2 + ((yy - cy) / cy) ** 2) / math.sqrt(2)
    vign = (1.0 - p["vignette"] * r ** 2)[..., None]
    rcx, rcy = p["reflection_center"][0] * CANVAS_W, p["reflection_center"][1] * CANVAS_H
    rr = p["reflection_radius"] * CANVAS_W
    refl = (np.exp(-(((xx - rcx) ** 2 + (yy - rcy) ** 2) / (2 * rr ** 2))) * 255 * p["reflection_alpha"])[..., None]
    band = (np.sin(2 * np.pi * yy[:, :1] / p["band_period_px"]))[..., None].astype(np.float32)
    lut = np.clip(((np.arange(256) / 255.0) ** p["gamma"]) * 255, 0, 255).astype(np.uint8)
    nrng = np.random.default_rng(rng.randint(0, 2**31))
    noise = [nrng.normal(0, p["noise_sigma"], (CANVAS_H, CANVAS_W, 3)).astype(np.float32) for _ in range(4)]
    return {"pw": pw, "ph": ph, "mask": mask, "H": H, "vign": vign.astype(np.float32), "refl": refl.astype(np.float32),
            "band": band, "lut": lut, "noise": noise}


def recapture_frame(disp, st, p, rng, t):
    panel = cv2.resize(disp, (st["pw"], st["ph"]), interpolation=cv2.INTER_LINEAR).astype(np.float32)
    panel = panel * st["mask"]
    jitter = np.float32([[1, 0, rng.gauss(0, p["hand_jitter_px"])], [0, 1, rng.gauss(0, p["hand_jitter_px"])], [0, 0, 1]])
    img = cv2.warpPerspective(panel, jitter @ st["H"], (CANVAS_W, CANVAS_H), flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_CONSTANT, borderValue=(12, 12, 14))  # dark bezel/room
    if p["band_amp"] > 0:
        shift = int(t * 37) % CANVAS_H
        img *= 1.0 + p["band_amp"] * np.roll(st["band"], shift, axis=0)
    if p["blur_sigma"] > 0.05:
        img = cv2.GaussianBlur(img, (0, 0), p["blur_sigma"])
    img = img * np.float32(p["wb"]) * st["vign"]
    img = img * p["contrast"] + p["black_lift"] + st["refl"]
    # noise bank: random frame from 4, rolled by a random offset so no pattern repeats frame to frame
    img += np.roll(st["noise"][rng.randrange(4)], (rng.randrange(CANVAS_H), rng.randrange(CANVAS_W)), axis=(0, 1))
    img = cv2.LUT(np.clip(img, 0, 255).astype(np.uint8), st["lut"])
    ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, p["jpeg_quality"]])
    return cv2.imdecode(enc, cv2.IMREAD_COLOR)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def process_source(row, out_dir, variants, seed, data_root, profile="v1"):
    src = row["planned_source_id"]
    frames, fps = read_frames(data_root / row["source_path"])
    n_out = int(round(len(frames) / fps * OUT_FPS))
    records = []
    # original pair: nearest display frame, same final resize and writer
    path = out_dir / f"{src}_ORIG.mp4"
    w = writer(path)
    for i in range(n_out):
        w.write(final(frames[min(len(frames) - 1, int(i * fps / OUT_FPS))]))
    w.release()
    records.append({"file": path.name, "variant": "ORIG", "label": "original", "params": {}})
    for k in range(variants):
        rng = random.Random(f"{seed}|{src}|{k}")
        p = sample_params(rng)
        if profile == "v1s":
            p = v1s_params(p, seed, src, k)
            tx = build_texture(p)
        st = build_static(p, rng, frames[0].shape[0], frames[0].shape[1])
        path = out_dir / f"{src}_SYN{k}.mp4"
        w = writer(path)
        phase = rng.random()
        for i in range(n_out):
            t = i / OUT_FPS
            pos = t * fps + phase
            a = int(pos)
            frac = pos - a
            f0 = frames[min(len(frames) - 1, a)]
            # exposure straddles the next display frame when frac > 1 - blend_exposure
            wgt = max(0.0, (frac - (1 - p["blend_exposure"])) / max(p["blend_exposure"], 1e-6))
            disp = f0 if wgt <= 0 or a + 1 >= len(frames) else cv2.addWeighted(f0, 1 - wgt, frames[a + 1], wgt, 0)
            out = final(recapture_frame(disp, st, p, rng, t))
            if profile == "v1s":
                out = texture_frame(out, tx, p, t)
            w.write(out)
        w.release()
        records.append({"file": path.name, "variant": f"SYN{k}", "label": "recapture_synthetic", "params": p})
    out = []
    for r in records:
        fpath = out_dir / r["file"]
        out.append({"file": r["file"], "profile": profile, "source_id": src, "origin_group": row["origin_group"], "split": row["confirmed_split"],
                    "label": r["label"], "synthetic": 1, "variant": r["variant"], "frames": n_out, "fps": OUT_FPS,
                    "width": OUT_W, "height": OUT_H, "bytes": fpath.stat().st_size, "sha256": sha256(fpath),
                    "source_playback": row["source_path"], "params": json.dumps(r["params"], separators=(",", ":"))})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--variants", type=int, default=4)
    ap.add_argument("--seed", default="s1synth_v1")
    ap.add_argument("--sources", nargs="*", help="limit to these source ids")
    ap.add_argument("--preview", action="store_true", help="also write a PNG of frame 45 for each output")
    ap.add_argument("--profile", choices=["v1", "v1s"], default="v1")
    ap.add_argument("--manifest", default="manifest.csv", help="manifest file name (parallel parts write separate files)")
    ap.add_argument("--data-root", type=Path, default=ROOT, help="checkout holding data/derived (for worktrees)")
    args = ap.parse_args()
    out_dir = args.out if args.out.is_absolute() else ROOT / args.out
    PLAN = args.data_root / PLAN_REL
    out_dir.mkdir(parents=True, exist_ok=True)
    with PLAN.open(encoding="utf-8-sig", newline="") as f:
        plan = {}
        for r in csv.DictReader(f):
            plan.setdefault(r["planned_source_id"], r)
    ids = args.sources or sorted(plan)
    manifest = out_dir / args.manifest
    new = not manifest.exists()
    with manifest.open("a", encoding="utf-8", newline="") as mf:
        wr = None
        for sid in ids:
            rows = process_source(plan[sid], out_dir, args.variants, args.seed, args.data_root, args.profile)
            if wr is None:
                wr = csv.DictWriter(mf, list(rows[0]))
                if new:
                    wr.writeheader()
            wr.writerows(rows)
            mf.flush()
            if args.preview:
                for r in rows:
                    cap = cv2.VideoCapture(str(out_dir / r["file"]))
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 45)
                    ok, fr = cap.read()
                    cap.release()
                    if ok:
                        cv2.imwrite(str(out_dir / (Path(r["file"]).stem + "_f45.jpg")), cv2.resize(fr, (480, 270)))
            print(json.dumps({"source": sid, "outputs": len(rows), "bytes": sum(r["bytes"] for r in rows)}), flush=True)


if __name__ == "__main__":
    main()
