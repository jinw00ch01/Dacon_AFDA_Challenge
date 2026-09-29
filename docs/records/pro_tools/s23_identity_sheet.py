"""Visual identity check for S23 captures flagged by s23_qa.py (weak/better match).

Usage: s23_identity_sheet.py <qa_report.json> <out_dir> [--all]
Per file one 640px sheet: row 1 capture, row 2 claimed source (aligned by match_start_s),
row 3 best other source (same source times). Labels are drawn on each tile.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
TW, TH = 213, 120


def grab(path, t):
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 20.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    i = int(min(max(0, round(t * fps)), max(0, n - 1)))
    cap.set(cv2.CAP_PROP_POS_FRAMES, i)
    ok, fr = cap.read()
    cap.release()
    if not ok:
        fr = np.zeros((TH, TW, 3), np.uint8)
    t = cv2.resize(fr, (TW, TH), interpolation=cv2.INTER_AREA)
    return t


def label(tile, text):
    cv2.putText(tile, text, (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
    return tile


def main(report, out, all_files=False):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rep = json.loads(Path(report).read_text(encoding="utf-8"))
    files = [v for v in rep.values() if isinstance(v, list) and v and isinstance(v[0], dict)][0]
    src = lambda sid: ROOT / f"data/derived/comma_subset_v1/s1_playback/{sid}_ORIGINAL.mp4"
    cap_dir = ROOT / "data/captures/s23"
    for f in files:
        flagged = [p for p in f["problems"] if p != "shorter_than_clip_10s"]
        if not flagged and not all_files:
            continue
        off = -(f.get("match_start_s") or 0.0)
        ts = [1.0, 4.0, 7.0]
        rows = [np.hstack([label(grab(cap_dir / f["file"], t), f"cap {t:.0f}s") for t in ts]),
                np.hstack([label(grab(src(f["source_id"]), t + off), f"{f['source_id']} {t + off:.1f}s") for t in ts]),
                np.hstack([label(grab(src(f["best_other_source"]), t + off), f"{f['best_other_source']} {t + off:.1f}s") for t in ts])]
        cv2.imwrite(str(out / (Path(f["file"]).stem + ".jpg")), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 85])
        print(f["file"], flagged)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], "--all" in sys.argv)
