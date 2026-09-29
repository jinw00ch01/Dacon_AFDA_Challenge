"""QA for the S1 v1c codec-matched set (ORIGX + DIGM0 per window) against its r2 base.

Usage: s1_qa_cm.py <cm_dir> <base_dir> <report.json>
Checks: manifest vs disk, sha/size, decode 50 frames 1280x720 + fourcc, split/group/range equal to the
base window, DIGM0 calib_ok, pairs.csv coverage (4 per window) and codec_matched share, label x codec
balance and per-codec byte medians by label (no codec/bitrate shortcut at file level).
"""
import argparse
import csv
import hashlib
import json
import statistics
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
FOURCC = {"mpeg4": "mp4v", "h264": "avc1"}


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cm_dir", type=Path)
    ap.add_argument("base_dir", type=Path)
    ap.add_argument("report", type=Path)
    args = ap.parse_args()
    cm_dir = args.cm_dir if args.cm_dir.is_absolute() else ROOT / args.cm_dir
    base_dir = args.base_dir if args.base_dir.is_absolute() else ROOT / args.base_dir
    rows = read_csv(cm_dir / "manifest.csv")
    base = read_csv(base_dir / "manifest.csv")
    base_win = defaultdict(dict)
    for r in base:
        base_win[(r["source_id"], r["window"])][r["variant"]] = r

    problems = []
    dup = [k for k, n in Counter(r["file"] for r in rows).items() if n > 1]
    if dup:
        problems.append(f"duplicate manifest rows: {dup}")
    listed = {r["file"] for r in rows}
    on_disk = {p.name for p in cm_dir.glob("*.mp4")}
    if on_disk ^ listed:
        problems.append(f"disk/manifest mismatch: {sorted(on_disk ^ listed)}")

    cm_win = defaultdict(dict)
    calib, hf_m, byte_ratio = [], [], []
    for r in rows:
        cm_win[(r["source_id"], r["window"])][r["variant"]] = r
        path = cm_dir / r["file"]
        if not path.exists():
            continue
        if str(path.stat().st_size) != r["bytes"] or sha256(path) != r["sha256"]:
            problems.append(f"{r['file']} size/sha mismatch")
        cap = cv2.VideoCapture(str(path))
        n = 0
        while cap.grab():
            n += 1
        w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        if n != int(r["frames"]) or n != 50 or (w, h) != (1280, 720):
            problems.append(f"{r['file']} decoded {n} {w}x{h} vs manifest {r['frames']}")
        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                "stream=codec_name,codec_tag_string", "-of", "csv=p=0", str(path)],
                               capture_output=True, text=True).stdout.strip().split(",")
        if probe != [r["codec"], FOURCC[r["codec"]]]:
            problems.append(f"{r['file']} ffprobe {probe} != {r['codec']}")
        p = json.loads(r["params"] or "{}")
        if r["variant"] == "DIGM0":
            calib.append(bool(p.get("calib_ok")))
            if "measured_hf_ratio" in p:
                hf_m.append(p["measured_hf_ratio"])

    for key, v in sorted(cm_win.items()):
        if sorted(v) != ["DIGM0", "ORIGX"]:
            problems.append(f"{key} variants {sorted(v)}")
        b = base_win.get(key)
        if not b:
            problems.append(f"{key} not in base")
            continue
        for r in v.values():
            for k in ("split", "origin_group", "src_frame_range"):
                if r[k] != b["ORIG"][k]:
                    problems.append(f"{r['file']} {k} {r[k]} != base {b['ORIG'][k]}")
        if "ORIGX" in v:
            byte_ratio.append(int(v["ORIGX"]["bytes"]) / int(b["DIG0"]["bytes"]))
        if "DIGM0" in v:
            byte_ratio.append(int(v["DIGM0"]["bytes"]) / int(b["ORIG"]["bytes"]))
    missing = sorted(set(base_win) - set(cm_win))
    if missing:
        problems.append(f"base windows without cm output: {missing}")

    pairs = read_csv(cm_dir / "pairs.csv")
    per_win = Counter((p["source_id"], p["window"]) for p in pairs)
    bad = {k: n for k, n in per_win.items() if n != 4}
    if bad or set(per_win) != set(base_win):
        problems.append(f"pairs per window != 4 or windows differ: {bad}")
    matched = sum(int(p["codec_matched"]) for p in pairs)
    matched_ratio = [float(p["bytes_ratio"]) for p in pairs if p["codec_matched"] == "1"]

    allrows = base + rows
    label_codec = Counter(f'{r["label"]}:{r["codec"]}' for r in allrows)
    bytes_by = defaultdict(list)
    for r in allrows:
        bytes_by[f'{r["codec"]}:{r["label"]}'].append(int(r["bytes"]))
    report = {
        "cm_dir": str(cm_dir.relative_to(ROOT)), "base_dir": str(base_dir.relative_to(ROOT)),
        "cm_files": len(rows), "windows": len(cm_win), "base_windows": len(base_win),
        "files_per_split": dict(Counter(r["split"] for r in rows)),
        "cm_total_bytes": sum(int(r["bytes"]) for r in rows),
        "digm0_calib_ok": f"{sum(calib)}/{len(calib)}",
        "digm0_hf": ({"min": min(hf_m), "max": max(hf_m), "median": statistics.median(hf_m)} if hf_m else None),
        "cm_bytes_vs_target": ({"min": round(min(byte_ratio), 3), "max": round(max(byte_ratio), 3)}
                               if byte_ratio else None),
        "pairs": len(pairs), "codec_matched_pairs": matched,
        "codec_matched_share": round(matched / len(pairs), 3) if pairs else None,
        "codec_matched_bytes_ratio": ({"min": min(matched_ratio), "max": max(matched_ratio),
                                       "median": statistics.median(matched_ratio)} if matched_ratio else None),
        "label_x_codec_all": dict(label_codec),
        "median_bytes_codec_label": {k: int(statistics.median(v)) for k, v in sorted(bytes_by.items())},
        "pass": not problems, "problems": problems,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "problems"} | {"n_problems": len(problems)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
