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

Codec-matched mode (--codec-matched-from <dir of the ORIG/DIG0 set>, CLAUDE.md decision 9) blocks the
codec shortcut (ORIG = MPEG-4, DIG = x264) with two more files per window, so each codec holds both
classes at a matched bitrate:

  <SRC>_W<w>_ORIGX.mp4      the decoded ORIG re-encoded with libx264 at the byte size of DIG0
                            (label original; pairs with DIG0 as an x264/x264 pair)
  <SRC>_W<w>_DIGM0.mp4      DIG0's tone/grain recipe written with ffmpeg mpeg4 (mp4v tag, GOP 12,
                            no B-frames, like the ORIG writer) at the byte size of ORIG, grain
                            re-calibrated to DIG0's HF target (pairs with ORIG as an mp4v/mp4v pair)

pairs.csv lists the four (original, re-record) pairs of every window with codec_matched 0/1; half
of them are codec-matched, and per-file codec and bitrate carry no label information.

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


def calibrate_grain(decoded, p, noise_seed, encode, path):
    """Re-encode (encode(frames) writes path) until the HF ratio of path vs decoded is within
    HF_TOL of p["target_hf_ratio"]; updates p with grain_sigma, measured_hf_ratio, calib_*."""
    tried = []
    while True:
        nrng = np.random.default_rng(noise_seed)
        encode([tone(f, nrng, p) for f in decoded])
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
        encode([tone(f, nrng, p) for f in decoded])
        p["measured_hf_ratio"] = round(hf_ratio(decoded, read_frames(path)[0]), 3)
    p["calib_attempts"] = len(tried)
    p["calib_ok"] = abs(p["measured_hf_ratio"] - p["target_hf_ratio"]) <= HF_TOL


BYTES_TOL = 0.10  # codec-matched files: accept |bytes / target - 1| <= BYTES_TOL
RATE_TRIES = 4


def next_kbps(kbps, actual_bytes, target_bytes):
    """ABR over 50 frames misses its target (x264 overshoots ~1.5x): rescale by the byte error."""
    return max(50, int(round(kbps * target_bytes / max(actual_bytes, 1))))


def write_abr(ffmpeg, path, frames, codec, kbps):
    """ffmpeg at an average bitrate. codec 'h264' = libx264 defaults; 'mpeg4' = the OpenCV mp4v
    writer's stream shape (MPEG-4 Simple, mp4v tag, GOP 12, no B-frames)."""
    enc = (["-c:v", "libx264"] if codec == "h264"
           else ["-c:v", "mpeg4", "-tag:v", "mp4v", "-g", "12", "-bf", "0"])
    cmd = [ffmpeg, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
           "-r", str(int(FPS)), "-i", "-", *enc, "-pix_fmt", "yuv420p", "-b:v", f"{kbps}k", str(path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in frames:
        proc.stdin.write(np.ascontiguousarray(f).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed: {path.name}")


class RateMatcher:
    """Encoder callable for calibrate_grain: hits target_bytes, carrying the rate correction."""

    def __init__(self, ffmpeg, path, codec, target_bytes):
        self.ffmpeg, self.path, self.codec, self.target = ffmpeg, path, codec, target_bytes
        self.kbps = max(50, int(target_bytes * 8 / (CLIP / FPS) / 1000))
        self.tries = 0

    def __call__(self, frames):
        for _ in range(RATE_TRIES):
            write_abr(self.ffmpeg, self.path, frames, self.codec, self.kbps)
            self.tries += 1
            actual = self.path.stat().st_size
            if abs(actual / self.target - 1) <= BYTES_TOL:
                return
            self.kbps = next_kbps(self.kbps, actual, self.target)

    def params(self):
        actual = self.path.stat().st_size
        return {"target_bytes": self.target, "kbps": self.kbps, "rate_encodes": self.tries,
                "bytes_ratio": round(actual / self.target, 3),
                "rate_ok": abs(actual / self.target - 1) <= BYTES_TOL}


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
            calibrate_grain(decoded, p, noise_seed, lambda frames: write_x264(ffmpeg, path, frames, p["crf"]), path)
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


def count_frames(path):
    cap = cv2.VideoCapture(str(path))
    n = 0
    while cap.grab():
        n += 1
    cap.release()
    return n


def codec_matched_window(orig_row, dig_row, src_dir, out_dir, ffmpeg, seed):
    """ORIGX (x264 original at DIG0's bytes) and DIGM0 (mp4v re-record at ORIG's bytes) for one window."""
    stem = orig_row["file"][: -len("_ORIG.mp4")]
    decoded, _ = read_frames(src_dir / orig_row["file"])
    made = []
    origx = out_dir / f"{stem}_ORIGX.mp4"
    rm = RateMatcher(ffmpeg, origx, "h264", int(dig_row["bytes"]))
    rm(decoded)
    px = {"from": orig_row["file"], "bytes_like": dig_row["file"], **rm.params(),
          "measured_hf_ratio": round(hf_ratio(decoded, read_frames(origx)[0]), 3)}
    made.append((origx, "ORIGX", "original", "h264", px))
    dig_p = json.loads(dig_row["params"])
    p = {k: dig_p[k] for k in ("target_hf_ratio", "grain_sigma", "contrast", "black")}
    digm = out_dir / f"{stem}_DIGM0.mp4"
    rm = RateMatcher(ffmpeg, digm, "mpeg4", int(orig_row["bytes"]))
    calibrate_grain(decoded, p, random.Random(f"{seed}|{stem}|M0").randint(0, 2**31), rm, digm)
    made.append((digm, "DIGM0", "recapture_synthetic", "mpeg4",
                 {"from": orig_row["file"], "recipe_of": dig_row["file"], **p, **rm.params()}))
    rows = []
    for path, variant, label, codec, params in made:
        rows.append({**{k: orig_row[k] for k in ("source_id", "origin_group", "split", "window",
                                                 "src_frame_range", "source_playback")},
                     "file": path.name, "label": label, "synthetic": 1, "variant": variant,
                     "frames": count_frames(path), "fps": FPS, "width": W, "height": H, "codec": codec,
                     "bytes": path.stat().st_size, "sha256": sha256(path),
                     "params": json.dumps(params, separators=(",", ":"))})
    return rows


def build_pairs(rows):
    """All (original, re-record) pairs inside each (source, window) with codec_matched 0/1."""
    by_win = {}
    for r in rows:
        by_win.setdefault((r["source_id"], str(r["window"])), []).append(r)
    pairs = []
    for (src, w), group in sorted(by_win.items()):
        origs = sorted((r for r in group if r["label"] == "original"), key=lambda r: r["file"])
        recs = sorted((r for r in group if r["label"] != "original"), key=lambda r: r["file"])
        for o in origs:
            for r in recs:
                pairs.append({"source_id": src, "window": w, "split": o["split"],
                              "original_file": o["file"], "recapture_file": r["file"],
                              "original_codec": o["codec"], "recapture_codec": r["codec"],
                              "codec_matched": int(o["codec"] == r["codec"]),
                              "bytes_ratio": round(int(r["bytes"]) / int(o["bytes"]), 3)})
    return pairs


def run_codec_matched(src_dir, out_dir, ffmpeg, seed, sources):
    with (src_dir / "manifest.csv").open(encoding="utf-8", newline="") as f:
        base = list(csv.DictReader(f))
    cols = list(base[0])
    wins = {}
    for r in base:
        wins.setdefault((r["source_id"], r["window"]), {})[r["variant"]] = r
    manifest = out_dir / "manifest.csv"
    new = not manifest.exists()
    done = set()
    if not new:  # resume: skip windows already written
        with manifest.open(encoding="utf-8", newline="") as f:
            done = {r["file"] for r in csv.DictReader(f)}
    with manifest.open("a", encoding="utf-8", newline="") as mf:
        wr = csv.DictWriter(mf, cols)
        if new:
            wr.writeheader()
        for (sid, w), v in sorted(wins.items()):
            stem = v["ORIG"]["file"][: -len("_ORIG.mp4")]
            if (sources and sid not in sources) or f"{stem}_DIGM0.mp4" in done:
                continue
            rows = codec_matched_window(v["ORIG"], v["DIG0"], src_dir, out_dir, ffmpeg, seed)
            wr.writerows([{k: r[k] for k in cols} for r in rows])
            mf.flush()
            print(json.dumps({"window": stem, "outputs": [(r["file"], r["bytes"]) for r in rows]}), flush=True)
    with manifest.open(encoding="utf-8", newline="") as f:
        cm_rows = list(csv.DictReader(f))
    pairs = build_pairs([r for r in base if not sources or r["source_id"] in sources] + cm_rows)
    with (out_dir / "pairs.csv").open("w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, list(pairs[0]))
        wr.writeheader()
        wr.writerows(pairs)


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
    ap.add_argument("--codec-matched-from", type=Path,
                    help="ORIG/DIG0 set (with manifest.csv) to extend with ORIGX/DIGM0 codec-matched files")
    args = ap.parse_args()
    root = args.root.resolve()
    ffmpeg = find_ffmpeg(args.ffmpeg)
    out_dir = args.out if args.out.is_absolute() else root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.codec_matched_from:
        src_dir = args.codec_matched_from
        src_dir = src_dir if src_dir.is_absolute() else root / src_dir
        run_codec_matched(src_dir, out_dir, ffmpeg, args.seed, set(args.sources or []))
        return
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
