"""Decision 12-C: gate for fixed (a-priori) rules on features.csv. Side: obj_u_L{L} > 0 -> LEFT (victim moves right on
screen), L chosen by FIT AUROC. Evasion: pre_mag_L5 <= FIT threshold (from s2_scene_rule report) -> 1.
Usage: s2_scene_rule_fixed.py <rule_dir> <merged.csv>"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from s2_scene_rule import gate, apply, macro_f1
d = Path(sys.argv[1]); F = pd.read_csv(d / "features.csv", dtype={"video_id": str})
lab = pd.read_csv(sys.argv[2], dtype={"video_id": str}).set_index("video_id")
rep = json.load(open(d / "report.json", encoding="utf-8"))
out = {}
for head, vcol, col, enc, rules in (
        ("side", "side_valid", "entry_side", lambda v: int(v == "LEFT"),
         [(f"obj_u_L{L}", 1, 0.0) for L in (5, 10, 20)]),
        ("evasion", "evasion_valid", "evasion_space", lambda v: int(float(v)),
         [("pre_mag_L5", -1, rep["heads"]["evasion"]["pred"]["rule"]["threshold"])])):
    valid = lab.index[lab[vcol] == 1]
    for anchor in ("pred", "gt"):
        D = F[(F.anchor == anchor) & F.video_id.isin(valid)].copy()
        D["y"] = [enc(lab.loc[v, col]) for v in D.video_id]
        fb = int(D[D.group == "FIT"].y.mean() >= 0.5)
        for f, direc, thr in rules:
            r = {}
            for g, x in D.groupby("group"):
                p = np.array([apply(v, direc, thr, fb) for v in x[f].values.astype(float)])
                r[g] = gate(x, p)
                hu = (x.label_source == "human").values
                r[g + "_human"] = {"n_videos": int(x[hu].video_id.nunique()),
                                   "accuracy": round(float((x.y.values[hu] == p[hu]).mean()), 4)}
                ag = ~hu
                r[g + "_agent"] = {"n_videos": int(x[ag].video_id.nunique()), "macro_f1": round(macro_f1(x.y.values[ag], p[ag]), 4)}
                if g == "HELD":
                    w0 = (x.win == 0).values
                    r["HELD_win0"] = gate(x[w0], p[w0])
            out[f"{head}/{anchor}/{f}/dir{direc}/thr{thr:.3f}"] = r
            print(head, anchor, f, "FIT", r["FIT"]["macro_f1"], "HELD", json.dumps(r["HELD"]), "human", r["HELD_human"], "agent", r["HELD_agent"], "win0", r["HELD_win0"]["macro_f1"], r["HELD_win0"]["perm_p"])
json.dump(out, open(d / "fixed_rules.json", "w"), indent=1)
