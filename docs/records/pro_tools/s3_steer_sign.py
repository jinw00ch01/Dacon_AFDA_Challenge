"""Check the sign convention of steering_angle_deg in s3_auxiliary_10hz.csv against the comma video.

For every source, decode video.hevc (grayscale, downsampled), measure the horizontal image shift of the
horizon band between frames f-2 and f+2 (0.2 s) with phase correlation, and correlate it with the CAN
steering angle at rows with speed > 3 m/s. A yaw to the LEFT moves distant scenery to the RIGHT in the image.
Also writes contact sheets (<=640 px wide) of the strongest positive / negative steering events.

usage: s3_steer_sign.py <out_dir> [SRC001,SRC002,...]
"""
import csv
import glob
import json
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
CSV = ROOT / "data/derived/comma_subset_v1/s3_auxiliary_10hz.csv"
SEG = ROOT / "data/external/comma2k19_subset_v1/segments"
out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)

rows = defaultdict(list)
for r in csv.DictReader(CSV.open(encoding="utf-8-sig")):
    rows[r["source_id"]].append(r)


def decode(path, scale=0.25):
    cap = cv2.VideoCapture(str(path))
    small, full = [], []
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        small.append(cv2.resize(g, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA).astype(np.float32))
        full.append(cv2.resize(fr, (213, 160), interpolation=cv2.INTER_AREA))
    cap.release()
    return small, full


def shift(a, b):
    h = a.shape[0]
    band = slice(int(h * 0.30), int(h * 0.55))
    win = cv2.createHanningWindow(a[band].shape[::-1], cv2.CV_32F)
    (dx, dy), resp = cv2.phaseCorrelate(a[band], b[band], win)
    return dx, resp


report = {"method": __doc__.strip().splitlines()[0], "sources": {}}
all_s, all_dx = [], []
events = []
only = set(sys.argv[2].split(",")) if len(sys.argv) > 2 else None
for sid, rs in sorted(rows.items()):
    if only and sid not in only:
        continue
    segs = glob.glob(str(SEG / rs[0]["origin_group"].replace("|", "_") / "*" / "video.hevc"))
    if len(segs) != 1:
        report["sources"][sid] = {"error": f"segment match count {len(segs)}"}
        continue
    small, full = decode(segs[0])
    st, dxs = [], []
    for r in rs:
        f = int(r["source_frame_index"])
        if f - 2 < 0 or f + 2 >= len(small) or float(r["speed_mps"]) <= 3.0:
            continue
        dx, resp = shift(small[f - 2], small[f + 2])
        if resp < 0.05:
            continue
        st.append(float(r["steering_angle_deg"]))
        dxs.append(dx)
        events.append((float(r["steering_angle_deg"]), sid, f, r["split"]))
    st, dxs = np.array(st), np.array(dxs)
    big = np.abs(st) > 20
    report["sources"][sid] = {
        "split": rs[0]["split"], "n": int(len(st)),
        "steer_range": [round(float(st.min()), 1), round(float(st.max()), 1)] if len(st) else None,
        "pearson_steer_vs_dx": round(float(np.corrcoef(st, dxs)[0, 1]), 3) if len(st) > 5 and st.std() > 0 else None,
        "n_abs_steer_gt20": int(big.sum()),
        "sign_agree_pos_steer_pos_dx": round(float(np.mean(np.sign(st[big]) == np.sign(dxs[big]))), 3) if big.any() else None,
    }
    all_s.extend(st.tolist())
    all_dx.extend(dxs.tolist())
    # keep frames only for this source's extreme events
    for sign in (1, -1):
        cand = [e for e in events if e[1] == sid and sign * e[0] > 20]
        if cand:
            e = max(cand, key=lambda e: sign * e[0])
            idx = [max(0, e[2] - 20), e[2], min(len(full) - 1, e[2] + 20)]
            strip = np.hstack([full[i] for i in idx])
            cv2.putText(strip, f"{sid} steer {e[0]:+.1f}deg f{e[2]} (-1s,0,+1s)", (4, 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
            cv2.imwrite(str(out / f"{sid}_{'pos' if sign > 0 else 'neg'}.jpg"), strip)
    print(sid, report["sources"][sid], flush=True)

s, d = np.array(all_s), np.array(all_dx)
big = np.abs(s) > 20
report["overall"] = {
    "n": int(len(s)),
    "pearson_steer_vs_dx": round(float(np.corrcoef(s, d)[0, 1]), 3),
    "n_abs_steer_gt20": int(big.sum()),
    "sign_agree_pos_steer_pos_dx": round(float(np.mean(np.sign(s[big]) == np.sign(d[big]))), 3),
    "mean_dx_steer_gt20": round(float(d[s > 20].mean()), 3) if (s > 20).any() else None,
    "mean_dx_steer_lt_minus20": round(float(d[s < -20].mean()), 3) if (s < -20).any() else None,
}
(out / f"steer_sign_report{'_' + sys.argv[2].replace(',', '_') if only else ''}.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
print("OVERALL", report["overall"])
