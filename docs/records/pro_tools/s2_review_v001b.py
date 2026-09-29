"""Independent review of v001b (result 4f4c9dfc): const collision=30 / entry=22 on 50-frame 10Hz clips.

Recomputes Acc@0.3s on the 5 official examples with a Pro-side implementation (not src/afda/metrics.py),
checks the fallback positions for other clip lengths, and writes an interpretation table for the
leaderboard S2 delta (evasion/side unchanged -> dS2 = 0.35*dCol + 0.35*dEntry).
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "work/s2_review_v001b"
FPS = 10.0
TOL = 0.3


def hit(pred, gt):
    # official: frame -> seconds via per-video map (10Hz: idx/10), |dt| <= 0.3
    return abs(pred / FPS - gt / FPS) <= TOL + 1e-9


def hit_raw(pred, gt):
    return abs(pred / FPS - gt / FPS) <= TOL


def const_positions(n):
    # re-implemented from the result description, not imported
    if n == 50:
        c, e = 30, 22
    else:
        c, e = round(0.6 * (n - 1)), round(0.44 * (n - 1))
    c = min(max(c, 0), n - 1)
    e = min(max(e, 0), c)
    return c, e


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(open(ROOT / "Baseline/data/stage2/labels.csv", encoding="utf-8")))
    gt = [int(r["t_collision"]) for r in rows]
    entry_gt = [int(r["t_entry"]) for r in rows]
    pred_c, pred_e = const_positions(50)
    col_eps = sum(hit(pred_c, g) for g in gt) / len(gt)
    col_raw = sum(hit_raw(pred_c, g) for g in gt) / len(gt)
    v001_col_pred = None  # v001 per-example preds live on Ultra; e001 Acc from review 61eea74c = 0.0
    fallback = {n: const_positions(n) for n in (1, 2, 10, 30, 49, 50, 51, 60, 100, 150, 300, 1200)}
    ratio_check = {n: [round(c / max(n - 1, 1), 3), round(e / max(n - 1, 1), 3)] for n, (c, e) in fallback.items()}
    base = 0.2060
    table = []
    for dc in (0.0, 0.4, 0.8):
        for de in (0.0, 0.2, 0.45):
            table.append({"col_acc": dc, "entry_acc": de, "pred_S2_if_v001_col_entry_were_0": round(base + 0.35 * dc + 0.35 * de, 4)})
    rep = {
        "official5": {
            "t_collision": gt,
            "t_entry": entry_gt,
            "pred_collision": pred_c,
            "pred_entry": pred_e,
            "abs_diff_frames": [abs(pred_c - g) for g in gt],
            "collision_acc03_eps": col_eps,
            "collision_acc03_raw_float": col_raw,
            "entry_acc03": None,
            "entry_note": "t_entry all -1 in official examples: entry accuracy not measurable",
        },
        "fallback_positions": {str(k): v for k, v in fallback.items()},
        "fallback_ratio": {str(k): v for k, v in ratio_check.items()},
        "v001_e001_collision_acc03_official5": 0.0,
        "delta_table": table,
        "delta_identity": "evasion_space/entry_side unchanged -> dS2 = 0.35*dCollisionAcc + 0.35*dEntryAcc",
    }
    (OUT / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(rep["official5"], ensure_ascii=False))
    print(json.dumps(rep["fallback_positions"]))


if __name__ == "__main__":
    main()
