"""S23 capture <-> playback-original alignment table + visual check sheets (Pro, read-only inputs).

match_start_s in work/s23_qa_b1/manifest.csv is lag/cap_fps where lag = capture frame index at which
original frame 0 would sit. It is <= 0 for every file: the recording starts AFTER the original starts.
So the original window that the capture shows is [orig_start_s, orig_start_s + overlap_s] with
orig_start_s = -match_start_s, and the capture window is [cap_start_s = max(0, match_start_s), ...].

usage: s23_align.py [--manifest work/s23_qa_b1/manifest.csv] [--out work/s23_align_b1] [--splits validation,test]
Writes pairs.csv (all rows) and one sheet per selected file: 4 aligned instants, capture (top) vs original (bottom).
"""
import argparse
import csv
from pathlib import Path

import cv2
import numpy as np


def frame_at(path, t):
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 20.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    idx = min(max(0, int(round(t * fps))), max(0, n - 1))
    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
    ok, fr = cap.read()
    cap.release()
    return fr if ok else None


def info(path):
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 20.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    return fps, n


def tile(fr, w=320):
    if fr is None:
        return np.zeros((180, w, 3), np.uint8)
    h = int(fr.shape[0] * w / fr.shape[1])
    return cv2.resize(fr, (w, h), interpolation=cv2.INTER_AREA)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="work/s23_qa_b1/manifest.csv")
    ap.add_argument("--table", default="data/derived/comma_subset_v1/s23_capture_ready.csv")
    ap.add_argument("--captures", default="data/captures/s23")
    ap.add_argument("--out", default="work/s23_align_b1")
    ap.add_argument("--splits", default="validation,test")
    a = ap.parse_args()
    out = Path(a.out)
    (out / "sheets").mkdir(parents=True, exist_ok=True)
    with open(a.table, encoding="utf-8-sig", newline="") as f:
        playback = {r["planned_source_id"]: r["source_path"] for r in csv.DictReader(f)}
    with open(a.manifest, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    sel = set(a.splits.split(","))
    res = []
    for r in rows:
        ms = float(r["match_start_s"])
        orig = playback[r["source_id"]]
        o_fps, o_n = info(orig)
        o_dur = o_n / o_fps
        cap_start = max(0.0, ms)
        orig_start = max(0.0, -ms)
        overlap = min(float(r["duration_s"]) - cap_start, o_dur - orig_start)
        rec = dict(file=r["file"], source_id=r["source_id"], condition=r["condition"], split=r["split"],
                   origin_group=r["origin_group"], original_path=orig, match_start_s=round(ms, 4),
                   cap_start_s=round(cap_start, 4), orig_start_s=round(orig_start, 4),
                   overlap_s=round(overlap, 4), orig_duration_s=round(o_dur, 4),
                   frames_10hz=int(np.floor(overlap * 10 + 1e-6)), match_ncc=round(float(r["match_ncc"]), 4),
                   enough_for_50f_10hz=overlap >= 4.9)
        res.append(rec)
        if r["split"] in sel:
            cap_path = Path(a.captures) / r["file"]
            ts = np.linspace(0.3, max(0.3, overlap - 0.3), 4)
            top = np.hstack([tile(frame_at(cap_path, cap_start + t)) for t in ts])
            bot = np.hstack([tile(frame_at(orig, orig_start + t)) for t in ts])
            w = min(top.shape[1], bot.shape[1])
            sheet = np.vstack([top[:, :w], bot[:, :w]])
            cv2.putText(sheet, f"{r['file']} orig_start={orig_start:.2f}s ncc={rec['match_ncc']}", (5, 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            cv2.imwrite(str(out / "sheets" / f"{Path(r['file']).stem}.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 80])
    with open(out / "pairs.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(res[0]))
        w.writeheader()
        w.writerows(res)
    print(f"{len(res)} rows; short(<4.9s)={sum(not x['enough_for_50f_10hz'] for x in res)}")
    for x in res:
        if x["split"] in sel:
            print(x["file"], x["orig_start_s"], x["overlap_s"], x["match_ncc"])


if __name__ == "__main__":
    main()
