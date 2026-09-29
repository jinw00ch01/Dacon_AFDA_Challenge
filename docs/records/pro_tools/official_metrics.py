"""Pro-side independent implementation of the official AFDA scoring (CLAUDE.md decision 10).

Do not import Ultra's src/afda/metrics.py; this is the cross-check.
  total = 0.2*S1 + 0.4*S2 + 0.4*S3
  S1 = Macro-F1(ORIGINAL/RERECORDED)
  S2 = 0.35*Acc@0.3s(collision) + 0.35*Acc@0.3s(entry) + 0.15*MacroF1(entry_side) + 0.15*MacroF1(evasion)
  S3 = 0.7*MacroF1(accel) + 0.3*MacroF1(steer, rows with GT accel STOPPED excluded)
Frames -> seconds via per-video fps (official S2: 10 fps). ``tol_mode``: "float" (|dt|<=0.3 in IEEE float),
"frames" (|df| <= round(0.3*fps), float-safe). Rows whose GT is -1/None are skipped for that sub-metric
(documented choice; the official handling of -1 is unknown) and counted in the returned ``n`` fields.
Macro-F1 label set = union of GT and predicted labels (sklearn default); S1 uses the fixed two labels.
"""


def macro_f1(gt, pred, labels=None):
    labels = sorted(set(gt) | set(pred)) if labels is None else labels
    f1s = []
    for c in labels:
        tp = sum(1 for g, p in zip(gt, pred) if g == c and p == c)
        fp = sum(1 for g, p in zip(gt, pred) if g != c and p == c)
        fn = sum(1 for g, p in zip(gt, pred) if g == c and p != c)
        f1s.append(0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn))
    return sum(f1s) / len(f1s) if f1s else None


def _missing(v):
    return v is None or v == "" or str(v) == "-1"


def acc_at(gt_frames, pred_frames, fps, tol=0.3, tol_mode="float"):
    hits = n = 0
    for g, p, f in zip(gt_frames, pred_frames, fps):
        if _missing(g):
            continue
        n += 1
        if _missing(p):
            continue
        g, p, f = int(g), int(p), float(f)
        ok = abs(p / f - g / f) <= tol if tol_mode == "float" else abs(p - g) <= round(tol * f)
        hits += ok
    return (hits / n if n else None), n


def s2_score(rows, tol_mode="float"):
    """rows: dicts with fps, gt_collision, pred_collision, gt_entry, pred_entry, gt_side, pred_side,
    gt_evasion, pred_evasion. Returns dict with components and S2 (None components count as 0)."""
    fps = [r.get("fps", 10) for r in rows]
    c, nc = acc_at([r["gt_collision"] for r in rows], [r["pred_collision"] for r in rows], fps, tol_mode=tol_mode)
    e, ne = acc_at([r["gt_entry"] for r in rows], [r["pred_entry"] for r in rows], fps, tol_mode=tol_mode)
    side = [(str(r["gt_side"]), str(r["pred_side"])) for r in rows if not _missing(r["gt_side"])]
    eva = [(str(r["gt_evasion"]), str(r["pred_evasion"])) for r in rows if not _missing(r["gt_evasion"])]
    fs = macro_f1([g for g, _ in side], [p for _, p in side]) if side else None
    fe = macro_f1([g for g, _ in eva], [p for _, p in eva]) if eva else None
    s2 = 0.35 * (c or 0) + 0.35 * (e or 0) + 0.15 * (fs or 0) + 0.15 * (fe or 0)
    return {"collision_acc03": c, "n_collision": nc, "entry_acc03": e, "n_entry": ne, "side_f1": fs,
            "n_side": len(side), "evasion_f1": fe, "n_evasion": len(eva), "S2": s2}


def s3_score(gt_accel, pred_accel, gt_steer, pred_steer, stopped="STOPPED"):
    fa = macro_f1(gt_accel, pred_accel)
    keep = [i for i, g in enumerate(gt_accel) if g != stopped]
    gs, ps = [gt_steer[i] for i in keep], [pred_steer[i] for i in keep]
    fs = macro_f1(gs, ps) if keep else None
    return {"accel_f1": fa, "steer_f1": fs, "n": len(gt_accel), "n_steer": len(keep),
            "S3": 0.7 * (fa or 0) + 0.3 * (fs or 0)}


def s1_score(gt, pred):
    return {"S1": macro_f1(gt, pred, ["ORIGINAL", "RERECORDED"]), "n": len(gt)}


def total(s1, s2, s3):
    return 0.2 * s1 + 0.4 * s2 + 0.4 * s3


if __name__ == "__main__":
    # self-test
    assert abs(macro_f1(["A", "A", "B", "B"], ["A", "A", "A", "A"], ["A", "B"]) - (2 / 3) / 2) < 1e-9
    assert s1_score(["ORIGINAL", "RERECORDED"], ["RERECORDED", "RERECORDED"])["S1"] == (0 + 2 / 3) / 2
    a, n = acc_at([30, 30, 30, -1], [33, 32, 34, 5], [10] * 4)
    assert n == 3 and abs(a - 2 / 3) < 1e-9
    a2, _ = acc_at([30, 1], [33, 4], [10, 10])  # 3.3-3.0 passes; 0.4-0.1 = 0.30000000000000004 fails
    assert a2 == 0.5, a2
    a3, _ = acc_at([30, 1], [33, 4], [10, 10], tol_mode="frames")
    assert a3 == 1.0
    r = s3_score(["STOPPED", "ACCEL", "DECEL"], ["STOPPED", "ACCEL", "ACCEL"], ["STRAIGHT", "LEFT", "RIGHT"],
                 ["LEFT", "LEFT", "LEFT"])
    assert r["n_steer"] == 2 and abs(r["steer_f1"] - 1 / 3) < 1e-9
    off = [32, 30, 31, 41, 30]
    rows = [dict(fps=10, gt_collision=g, pred_collision=30, gt_entry=-1, pred_entry=22, gt_side=-1,
                 pred_side="LEFT", gt_evasion=-1, pred_evasion=1) for g in off]
    print("official 5 examples, const 30:", s2_score(rows))
    print("self-test ok")
