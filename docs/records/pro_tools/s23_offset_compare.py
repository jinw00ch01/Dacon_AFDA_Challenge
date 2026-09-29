"""Compare capture frames with original at several candidate offsets. usage: s23_offset_compare.py FILE OUT.jpg OFF1 OFF2 ..."""
import csv, sys
import cv2, numpy as np
sys.path.insert(0, "work/pro_tools")
from s23_align import frame_at, tile
play = {r["planned_source_id"]: r["source_path"] for r in csv.DictReader(open("data/derived/comma_subset_v1/s23_capture_ready.csv", encoding="utf-8-sig"))}
fn, out, offs = sys.argv[1], sys.argv[2], [float(x) for x in sys.argv[3:]]
ts = [0.5, 2.0, 3.5, 5.0]
rows = [np.hstack([tile(frame_at(f"data/captures/s23/{fn}", t), 256) for t in ts])]
for o in offs:
    r = np.hstack([tile(frame_at(play[fn[:6]], t + o), 256) for t in ts])
    cv2.putText(r, f"orig_start={o}", (5, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2); rows.append(r[:, :rows[0].shape[1]])
cv2.imwrite(out, np.vstack(rows))
