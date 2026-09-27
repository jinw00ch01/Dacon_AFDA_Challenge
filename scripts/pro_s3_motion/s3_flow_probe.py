"""Probe flow settings for a monotone speed proxy at 10 Hz (decision 12-D). usage: s3_flow_probe.py SRC..."""
import sys, glob, json
from pathlib import Path
import cv2, numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from s3_motion_features import AUX, SEGMENTS
CFG = {"w160_l4_w15": (160, 120, 4, 15), "w160_l5_w25": (160, 120, 5, 25), "w320_l5_w25": (320, 240, 5, 25), "w96_l3_w11": (96, 72, 3, 11)}
aux = pd.read_csv(AUX, encoding="utf-8-sig")
res = {}
for sid in sys.argv[1:]:
    g = aux[aux.source_id == sid].sort_values("sample_index")
    hv = glob.glob(str(SEGMENTS / g.origin_group.iloc[0].replace("|", "_") / "*" / "video.hevc"))[0]
    idx = g.source_frame_index.to_numpy().astype(int)[::1]
    want = set(idx.tolist()); fr = {}; cap = cv2.VideoCapture(hv); i = 0
    while i <= idx.max():
        ok, b = cap.read()
        if not ok: break
        if i in want: fr[i] = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
        i += 1
    sp = g.speed_mps.to_numpy()
    res[sid] = {}
    for name, (W, H, L, WS) in CFG.items():
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); rx, ry = xx - W / 2, yy - 0.47 * H; r2 = rx**2 + ry**2 + 1
        bands = {"far": (yy >= .30*H) & (yy < .50*H), "mid": (yy >= .50*H) & (yy < .62*H), "near": (yy >= .62*H) & (yy < .74*H), "all": yy < .74*H}
        vals = {b: [] for b in bands}
        small = {k: cv2.resize(v, (W, H), interpolation=cv2.INTER_AREA) for k, v in fr.items()}
        for k in range(1, len(idx), 2):  # every other row for speed
            f = cv2.calcOpticalFlowFarneback(small[idx[k-1]], small[idx[k]], None, 0.5, L, WS, 3, 5, 1.1, 0)
            dv = (f[..., 0] * rx + f[..., 1] * ry) / r2
            for b, m in bands.items(): vals[b].append(float(np.mean(dv[m])) * W)  # scale-invariant
        s = sp[1::2][:len(vals["all"])]
        res[sid][name] = {b: round(float(np.corrcoef(pd.Series(v).rolling(5, center=True, min_periods=1).median(), s)[0, 1]), 3) for b, v in vals.items()}
    print(sid, json.dumps(res[sid]), flush=True)
Path("work/s3_flow_probe.json").write_text(json.dumps(res, indent=1))
