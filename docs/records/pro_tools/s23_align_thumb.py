"""Cross-check S23 lag with 10Hz grayscale thumbnails (edge-based) instead of mean luma. usage: s23_align_thumb.py FILE..."""
import csv, sys
import cv2, numpy as np
play = {r["planned_source_id"]: r["source_path"] for r in csv.DictReader(open("data/derived/comma_subset_v1/s23_capture_ready.csv", encoding="utf-8-sig"))}
def thumbs(p, hz=10):
    cap = cv2.VideoCapture(p); fps = cap.get(cv2.CAP_PROP_FPS); out = []; i = 0; nxt = 0.0
    while True:
        ok, f = cap.read()
        if not ok: break
        if i / fps >= nxt - 1e-6:
            g = cv2.cvtColor(cv2.resize(f, (64, 36), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.float32)
            g = cv2.Laplacian(cv2.GaussianBlur(g, (3, 3), 0), cv2.CV_32F)
            out.append(((g - g.mean()) / (g.std() + 1e-6)).ravel()); nxt += 1 / hz
        i += 1
    return np.array(out)
for fn in sys.argv[1:]:
    sid = fn[:6]; c = thumbs(f"data/captures/s23/{fn}"); o = thumbs(play[sid])
    best = []
    for s in range(0, len(o) - 30):
        m = min(len(c), len(o) - s)
        best.append((float((c[:m] * o[s:s + m]).mean()), s / 10))
    best.sort(reverse=True)
    print(fn, "top3 orig_start:", [(round(b[1], 1), round(b[0], 3)) for b in best[:3]])
