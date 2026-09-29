"""Correlate integrated pitch signals (high-passed) with the accel proxy, per source. Usage: s3_pitch_eval.py <pitch.csv>"""
import sys
import numpy as np, pandas as pd
d = pd.read_csv(sys.argv[1]).sort_values(["source_id", "sample_index"])
res = []
for s, g in d.groupby("source_id"):
    acc = g.acceleration_mps2_proxy.rolling(5, center=True, min_periods=1).mean()
    r = {"src": s, "split": g.split.iloc[0], "acc_sd": round(acc.std(), 2)}
    for c in ["pitch_v_hb", "pitch_v_far", "prof_shift"]:
        p = g[c].cumsum()
        for hp in (30, 100):
            x = p - p.rolling(hp, center=True, min_periods=1).mean()
            x = x.rolling(5, center=True, min_periods=1).mean()
            r[f"{c[:9]}_{hp}"] = round(np.corrcoef(x, acc)[0, 1], 2)
    res.append(r)
print(pd.DataFrame(res).to_string())
