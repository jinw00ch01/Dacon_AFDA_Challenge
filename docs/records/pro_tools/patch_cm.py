"""One-off: add the codec-matched mode to scripts/s1_synth_digital.py in the given checkout."""
import sys
from pathlib import Path

p = Path(sys.argv[1]) / "scripts/s1_synth_digital.py"
s = p.read_text(encoding="utf-8")

s = s.replace('''Every output of a source keeps the source split''', '''Codec-matched mode (--codec-matched-from <dir of the ORIG/DIG0 set>, CLAUDE.md decision 9) blocks the
codec shortcut (ORIG = MPEG-4, DIG = x264) with two more files per window, so each codec holds both
classes at a matched bitrate:

  <SRC>_W<w>_ORIGX.mp4      the decoded ORIG re-encoded with libx264 at the byte size of DIG0
                            (label original; pairs with DIG0 as an x264/x264 pair)
  <SRC>_W<w>_DIGM0.mp4      DIG0's tone/grain recipe written with ffmpeg mpeg4 (mp4v tag, GOP 12,
                            no B-frames, like the ORIG writer) at the byte size of ORIG, grain
                            re-calibrated to DIG0's HF target (pairs with ORIG as an mp4v/mp4v pair)

pairs.csv lists the four (original, re-record) pairs of every window with codec_matched 0/1; half
of them are codec-matched, and per-file codec and bitrate carry no label information.

Every output of a source keeps the source split''')

old_loop = '''            path = out_dir / f"{src}_W{w}_DIG{k}.mp4"
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
'''
new_loop = '''            path = out_dir / f"{src}_W{w}_DIG{k}.mp4"
            calibrate_grain(decoded, p, noise_seed, lambda frames: write_x264(ffmpeg, path, frames, p["crf"]), path)
'''
assert old_loop in s
s = s.replace(old_loop, new_loop)

helper = '''def calibrate_grain(decoded, p, noise_seed, encode, path):
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


'''
s = s.replace("def crop_16x9(h, w):", helper + "def crop_16x9(h, w):", 1)

cm = '''def count_frames(path):
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


def find_ffmpeg(arg):'''
s = s.replace("def find_ffmpeg(arg):", cm, 1)

old_main = '''    ap.add_argument("--ffmpeg")
    args = ap.parse_args()
    root = args.root.resolve()
    ffmpeg = find_ffmpeg(args.ffmpeg)
    out_dir = args.out if args.out.is_absolute() else root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
'''
assert old_main in s
s = s.replace(old_main, '''    ap.add_argument("--ffmpeg")
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
''')
p.write_text(s, encoding="utf-8")
print("ok")
