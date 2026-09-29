"""S23 real-recapture QA (Pro, read-only on data/captures/s23).

usage: s23_qa.py [--captures data/captures/s23] [--table .../s23_capture_ready.csv] [--out work/s23_qa]

Per file: name -> capture-table row (SRC0xx_Cn_takeNN.(mp4|mov)), size <= 512MiB, sha256,
ffprobe (codec, WxH, fps, duration, rotation), full decode frame count, dark/blown ratio,
and source match: per-frame mean-luma time series of the capture vs its playback clip
(resampled to the capture fps), best lag by normalized cross-correlation over the whole
recording. Also checks the correlation against every other source to catch mis-named files.
Writes report.json + manifest.csv + one contact sheet per file (<=640px) under --out.
"""
import argparse
import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path

import cv2
import numpy as np

NAME_RE = re.compile(r"^(SRC\d{3})_(C[1-4])_take(\d{2})\.(mp4|mov)$", re.IGNORECASE)
MAX_BYTES = 512 * 1024 * 1024


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=codec_name,codec_tag_string,width,height,avg_frame_rate,r_frame_rate,nb_frames,duration:stream_side_data=rotation:stream_tags=rotate",
                          "-of", "json", str(path)], capture_output=True, text=True)
    if out.returncode:
        return {"error": out.stderr.strip()[:300]}
    s = (json.loads(out.stdout).get("streams") or [{}])[0]
    num, den = (s.get("avg_frame_rate") or "0/1").split("/")
    s["fps"] = float(num) / float(den) if float(den) else None
    rot = s.get("tags", {}).get("rotate")
    for sd in s.get("side_data_list", []) or []:
        rot = sd.get("rotation", rot)
    s["rotation"] = rot
    return s


def luma_series(path, keep_frames=0):
    cap = cv2.VideoCapture(str(path))
    series, frames, n = [], [], 0
    dark = blown = 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(cv2.resize(fr, (160, 90), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        series.append(float(g.mean()))
        dark += float((g < 16).mean())
        blown += float((g > 245).mean())
        if keep_frames:
            frames.append(fr)
        n += 1
    cap.release()
    return np.asarray(series), n, (dark / n if n else None), (blown / n if n else None), frames


def resample(series, src_fps, dst_fps):
    if len(series) < 2:
        return series
    t_src = np.arange(len(series)) / src_fps
    t_dst = np.arange(0, t_src[-1], 1.0 / dst_fps)
    return np.interp(t_dst, t_src, series)


def best_ncc(cap_s, src_s):
    """Slide the (shorter) source series over the capture; return (max ncc, lag in capture frames)."""
    d_cap = np.diff(cap_s)
    d_src = np.diff(src_s)
    if len(d_src) < 10 or len(d_cap) < len(d_src) // 2:
        return None, None
    d_src = (d_src - d_src.mean()) / (d_src.std() + 1e-9)
    best, lag = -2.0, None
    m = len(d_src)
    for k in range(-m // 2, max(1, len(d_cap) - m // 2)):
        a0, a1 = max(0, k), min(len(d_cap), k + m)
        b0 = a0 - k
        seg = d_cap[a0:a1]
        if len(seg) < m // 2:
            continue
        ref = d_src[b0:b0 + len(seg)]
        seg = (seg - seg.mean()) / (seg.std() + 1e-9)
        r = float((seg * ref).mean())
        if r > best:
            best, lag = r, k
    return best, lag


def sheet(frames, path, n=8):
    if not frames:
        return
    idx = np.linspace(0, len(frames) - 1, n).astype(int)
    tiles = []
    for i in idx:
        t = cv2.resize(frames[i], (320, 180), interpolation=cv2.INTER_AREA)
        cv2.putText(t, str(i), (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        tiles.append(t)
    rows = [np.hstack(tiles[i:i + 2]) for i in range(0, n, 2)]
    cv2.imwrite(str(path), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 85])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--captures", default="data/captures/s23")
    ap.add_argument("--table", default="data/derived/comma_subset_v1/s23_capture_ready.csv")
    ap.add_argument("--out", default="work/s23_qa")
    ap.add_argument("--min-ncc", type=float, default=0.5)
    args = ap.parse_args()
    out = Path(args.out)
    (out / "sheets").mkdir(parents=True, exist_ok=True)
    with open(args.table, encoding="utf-8-sig", newline="") as f:
        table = list(csv.DictReader(f))
    by_name = {r["output_filename"].lower(): r for r in table}
    playback = {r["planned_source_id"]: r["source_path"] for r in table}
    src_cache = {}

    def src_series(sid):
        if sid not in src_cache:
            p = playback[sid]
            s, n, *_ = luma_series(p)
            src_cache[sid] = (s, probe(p).get("fps") or 20.0)
        return src_cache[sid]

    files = sorted(p for p in Path(args.captures).iterdir() if p.is_file())
    rows, problems = [], []
    for p in files:
        rec = {"file": p.name, "bytes": p.stat().st_size, "problems": []}
        m = NAME_RE.match(p.name)
        base = None
        if not m:
            rec["problems"].append("name_pattern")
        else:
            sid, cond, take = m.group(1).upper(), m.group(2).upper(), m.group(3)
            rec.update(source_id=sid, condition=cond, take=take)
            base = by_name.get(f"{sid}_{cond}_take01.mp4".lower())
            if base is None:
                rec["problems"].append("not_in_capture_table")
            else:
                rec.update(split=base["confirmed_split"], origin_group=base["origin_group"],
                           display_role=base["display_role"])
        if rec["bytes"] > MAX_BYTES:
            rec["problems"].append("over_512MiB")
        rec["sha256"] = sha256(p)
        pr = probe(p)
        rec["probe"] = pr
        if "error" in pr:
            rec["problems"].append("ffprobe_error")
        s, n, dark, blown, frames = luma_series(p, keep_frames=1)
        rec.update(decoded_frames=n, dark_ratio=dark, blown_ratio=blown)
        if n == 0:
            rec["problems"].append("decode_zero_frames")
        elif pr.get("nb_frames") and abs(int(pr["nb_frames"]) - n) > 1:
            rec["problems"].append(f"frame_count_mismatch probe={pr['nb_frames']} decoded={n}")
        fps = pr.get("fps") or 30.0
        rec["duration_s"] = n / fps if n else None
        if rec["duration_s"] is not None and rec["duration_s"] < 10.0:
            rec["problems"].append("shorter_than_clip_10s")
        if blown is not None and blown > 0.05:
            rec["problems"].append("blown_highlights>5%")
        sheet(frames, out / "sheets" / f"{p.stem}.jpg")
        del frames
        if base is not None and n:
            src_s, src_fps = src_series(rec["source_id"])
            ncc, lag = best_ncc(s, resample(src_s, src_fps, fps))
            rec.update(match_ncc=ncc, match_lag_frames=lag,
                       match_start_s=(lag / fps if lag is not None else None))
            others = {}
            for sid in sorted(playback):
                if sid == rec["source_id"]:
                    continue
                o_s, o_fps = src_series(sid)
                others[sid] = best_ncc(s, resample(o_s, o_fps, fps))[0]
            best_other = max(others, key=lambda k: others[k] if others[k] is not None else -9)
            rec.update(best_other_source=best_other, best_other_ncc=others[best_other])
            if ncc is None or ncc < args.min_ncc:
                rec["problems"].append("weak_source_match")
            if ncc is not None and others[best_other] is not None and others[best_other] > ncc:
                rec["problems"].append(f"better_match_{best_other}")
        rows.append(rec)
        problems += [f"{p.name}: {x}" for x in rec["problems"]]

    with open(out / "manifest.csv", "w", encoding="utf-8", newline="") as f:
        cols = ["file", "source_id", "condition", "take", "split", "origin_group", "display_role", "bytes",
                "sha256", "decoded_frames", "duration_s", "match_ncc", "match_start_s", "best_other_source",
                "best_other_ncc", "dark_ratio", "blown_ratio", "problems"]
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**r, "problems": ";".join(r["problems"])})
    split_counts = {}
    for r in rows:
        split_counts[r.get("split")] = split_counts.get(r.get("split"), 0) + 1
    report = {"n_files": len(rows), "n_ok": sum(not r["problems"] for r in rows), "split_counts": split_counts,
              "problems": problems, "files": rows}
    (out / "report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("n_files", "n_ok", "split_counts", "problems")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
