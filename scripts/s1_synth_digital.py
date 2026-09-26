"""S1 synthetic v1c: 'digital re-record' pairs matched to the official Baseline stage1 examples.

The five Baseline pairs (Baseline/data/stage1/{original,rerecorded}/00000k.mp4) are pixel-aligned
(phase shift < 0.05 px), PSNR 30.6-31.8 dB, 1280x720, 10 fps, 50 frames. Originals are MPEG-4
Simple Profile (OpenCV mp4v style, GOP 12); re-records are libx264 High with B-frames, about 2.1x
the bitrate, with more fine-grain high frequency (x1.07-1.44) and slightly stronger contrast.
No perspective, bezel, blur or desaturation. This generator mirrors that pipeline:

  <SRC>_W<w>_ORIG.mp4       window w of the playback clip, 16:9 centre crop, 1280x720, 10 fps,
                            50 frames, OpenCV mp4v writer (like the Baseline originals)
  <SRC>_W<w>_DIG<k>.mp4     decode the ORIG file -> luma grain + contrast/black tone -> ffmpeg libx264
                            (default preset, CRF 23). Grain sigma is calibrated per clip (up to
                            MAX_ATTEMPTS re-encodes, secant inside a bracket) so the fine-detail
                            HF ratio vs ORIG is within HF_TOL of a seeded target in 1.1-1.45, the
                            range of the Baseline pairs; params record calib_attempts/calib_ok.

Every output of a source keeps the source split (s23_capture_ready.csv confirmed_split). A manifest
with parameters and SHA-256 is written next to the videos. All outputs are "synthetic".
"""
import argparse
import csv
import hashlib
import json
import random
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np

W, H, FPS, CLIP = 1280, 720, 10.0, 50


def sample_params(rng):
    return {
        "target_hf_ratio": round(rng.uniform(1.1, 1.45), 3),  # Baseline pairs: 1.07-1.44
        "grain_sigma": 3.0,  # first guess; calibrated per clip toward target_hf_ratio
        "contrast": round(rng.uniform(1.0, 1.05), 3),
        "black": round(rng.uniform(0.0, 3.0), 2),
        "crf": 23,  # libx264 default, as tagged in the Baseline re-records
    }


def hf_std(bgr):
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    return float((g - cv2.GaussianBlur(g, (0, 0), 1.0)).std())


def hf_ratio(orig_frames, rec_frames):
    idx = np.linspace(3, len(orig_frames) - 4, 3).astype(int)
    return float(np.mean([hf_std(rec_frames[i]) / hf_std(orig_frames[i]) for i in idx]))


SIGMA_MIN, SIGMA_MAX = 0.8, 12.0
HF_TOL = 0.04  # accept |measured - target| <= HF_TOL
MAX_ATTEMPTS = 8


def next_sigma(sigma, measured, target):
    """Grain adds HF variance ~ sigma^2: rescale sigma so measured^2-1 hits target^2-1."""
    scale = ((target ** 2 - 1) / max(measured ** 2 - 1, 0.01)) ** 0.5
    return float(min(SIGMA_MAX, max(SIGMA_MIN, sigma * scale)))


def calib_step(tried, target):
    """Next grain sigma from all (sigma, measured) tries. x264 CRF quantises weak grain away, so the
    response is thresholded and one rescale step is not enough: once the target is bracketed, take
    the secant between the closest tries on each side, kept to the middle 35-65% of the bracket
    (a steep, convex response makes plain regula falsi stall on one side), else rescale."""
    below = [t for t in tried if t[1] < target]
    above = [t for t in tried if t[1] >= target]
    if below and above:
        (s0, m0), (s1, m1) = max(below, key=lambda t: t[1]), min(above, key=lambda t: t[1])
        frac = (target - m0) / max(m1 - m0, 1e-6)
        return float(s0 + min(0.65, max(0.35, frac)) * (s1 - s0))
    s, m = tried[-1]
    return next_sigma(s, m, target)


def hf_close(tried, target):
    return min(tried, key=lambda t: abs(t[1] - target))


def crop_16x9(h, w):
    """Centre crop box (y0, y1, x0, x1) with 16:9 aspect."""
    if w * 9 >= h * 16:
        cw = h * 16 // 9
        x0 = (w - cw) // 2
        return 0, h, x0, x0 + cw
    ch = w * 9 // 16
    y0 = (h - ch) // 2
    return y0, y0 + ch, 0, w


def window_ids(n_src, src_fps, n_windows):
    """Source frame indices for each 50-frame 10 fps window (nearest frame)."""
    step = src_fps / FPS
    out = []
    for w in range(n_windows):
        ids = [int(round((w * CLIP + i) * step)) for i in range(CLIP)]
        if ids[-1] >= n_src:
            break
        out.append(ids)
    return out


def tone(frame, rng, p):
    img = frame.astype(np.float32)
    img += rng.normal(0, p["grain_sigma"], img.shape[:2]).astype(np.float32)[..., None]
    img = (img - 128.0) * p["contrast"] + 128.0 - p["black"]
    return np.clip(img, 0, 255).astype(np.uint8)


def read_frames(path):
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 20.0
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(f)
    cap.release()
    return frames, fps


def write_mp4v(path, frames):
    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    for f in frames:
        w.write(f)
    w.release()


def write_x264(ffmpeg, path, frames, crf):
    cmd = [ffmpeg, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
           "-r", str(int(FPS)), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", str(crf),
           str(path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in frames:
        proc.stdin.write(np.ascontiguousarray(f).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed: {path.name}")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def process_source(row, root, out_dir, ffmpeg, windows, variants, seed):
    src = row["planned_source_id"]
    frames, fps = read_frames(root / row["source_path"])
    y0, y1, x0, x1 = crop_16x9(*frames[0].shape[:2])
    records = []
    for w, ids in enumerate(window_ids(len(frames), fps, windows)):
        clip = [cv2.resize(frames[i][y0:y1, x0:x1], (W, H), interpolation=cv2.INTER_AREA) for i in ids]
        orig = out_dir / f"{src}_W{w}_ORIG.mp4"
        write_mp4v(orig, clip)
        records.append({"file": orig.name, "window": w, "variant": "ORIG", "label": "original",
                        "src_frames": [ids[0], ids[-1]], "params": {}})
        decoded, _ = read_frames(orig)  # re-record starts from the delivered original file
        for k in range(variants):
            rng = random.Random(f"{seed}|{src}|{w}|{k}")
            p = sample_params(rng)
            noise_seed = rng.randint(0, 2**31)
            path = out_dir / f"{src}_W{w}_DIG{k}.mp4"
            tried = []
            while True:  # re-encode until the HF ratio is within HF_TOL of the target
                nrng = np.random.default_rng(noise_seed)
                write_x264(ffmpeg, path, [tone(f, nrng, p) for f in decoded], p["crf"])
                p["measured_hf_ratio"] = round(hf_ratio(decoded, read_frames(path)[0]), 3)
                tried.append((p["grain_sigma"], p["measured_hf_ratio"]))
                if abs(p["measured_hf_ratio"] - p["target_hf_ratio"]) <= HF_TOL or len(tried) >= MAX_ATTEMPTS:
                    break
                sigma = round(calib_step(tried, p["target_hf_ratio"]), 2)
                if any(abs(sigma - s) < 0.01 for s, _ in tried):  # clamped or converged
                    break
                p["grain_sigma"] = sigma
            best_sigma, _ = hf_close(tried, p["target_hf_ratio"])
            if best_sigma != p["grain_sigma"]:  # last try was not the closest: rebuild the closest
                p["grain_sigma"] = best_sigma
                nrng = np.random.default_rng(noise_seed)
                write_x264(ffmpeg, path, [tone(f, nrng, p) for f in decoded], p["crf"])
                p["measured_hf_ratio"] = round(hf_ratio(decoded, read_frames(path)[0]), 3)
            p["calib_attempts"] = len(tried)
            p["calib_ok"] = abs(p["measured_hf_ratio"] - p["target_hf_ratio"]) <= HF_TOL
            records.append({"file": path.name, "window": w, "variant": f"DIG{k}", "label": "recapture_synthetic",
                            "src_frames": [ids[0], ids[-1]], "params": p})
    out = []
    for r in records:
        fpath = out_dir / r["file"]
        cap = cv2.VideoCapture(str(fpath))
        n = 0
        while cap.grab():
            n += 1
        cap.release()
        out.append({"file": r["file"], "source_id": src, "origin_group": row["origin_group"],
                    "split": row["confirmed_split"], "label": r["label"], "synthetic": 1,
                    "variant": r["variant"], "window": r["window"],
                    "src_frame_range": f"{r['src_frames'][0]}-{r['src_frames'][1]}",
                    "frames": n, "fps": FPS, "width": W, "height": H,
                    "codec": "mpeg4" if r["variant"] == "ORIG" else "h264",
                    "bytes": fpath.stat().st_size, "sha256": sha256(fpath),
                    "source_playback": row["source_path"],
                    "params": json.dumps(r["params"], separators=(",", ":"))})
    return out


def find_ffmpeg(arg):
    if arg:
        return arg
    found = shutil.which("ffmpeg")
    if found:
        return found
    hits = sorted(Path.home().glob("AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg*/ffmpeg-*/bin/ffmpeg.exe"))
    if not hits:
        raise SystemExit("ffmpeg with libx264 not found; pass --ffmpeg")
    return str(hits[-1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1],
                    help="checkout holding data/derived/comma_subset_v1")
    ap.add_argument("--windows", type=int, default=2)
    ap.add_argument("--variants", type=int, default=1)
    ap.add_argument("--seed", default="s1synth_v1c")
    ap.add_argument("--sources", nargs="*", help="limit to these source ids")
    ap.add_argument("--ffmpeg")
    args = ap.parse_args()
    root = args.root.resolve()
    ffmpeg = find_ffmpeg(args.ffmpeg)
    out_dir = args.out if args.out.is_absolute() else root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    plan_path = root / "data/derived/comma_subset_v1/s23_capture_ready.csv"
    with plan_path.open(encoding="utf-8-sig", newline="") as f:
        plan = {}
        for r in csv.DictReader(f):
            plan.setdefault(r["planned_source_id"], r)
    ids = args.sources or sorted(plan)
    manifest = out_dir / "manifest.csv"
    new = not manifest.exists()
    with manifest.open("a", encoding="utf-8", newline="") as mf:
        wr = None
        for sid in ids:
            rows = process_source(plan[sid], root, out_dir, ffmpeg, args.windows, args.variants, args.seed)
            if wr is None:
                wr = csv.DictWriter(mf, list(rows[0]))
                if new:
                    wr.writeheader()
            wr.writerows(rows)
            mf.flush()
            print(json.dumps({"source": sid, "outputs": len(rows), "bytes": sum(r["bytes"] for r in rows)}),
                  flush=True)


if __name__ == "__main__":
    main()
