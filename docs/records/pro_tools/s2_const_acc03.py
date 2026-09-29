"""S2 constant-position baseline under the official Acc@0.3s metric (CLAUDE.md decision 10, Pro 1-1).

Independent of Ultra modules. Official S2 format: 10 fps, 50 frames. For every window-cutting hypothesis
we convert labels to window-relative 10 Hz frame indices and search the constant frame c in 0..49 that
maximises the share of videos with |c/10 - gt/10| <= 0.3 s (float, like a straightforward scorer), and
also report exact +-3 / +-2 frame hit rates (float 0.3 edge: some 3-frame gaps compute to 0.30000000000000004).

Usage: s2_const_acc03.py <out.json>
"""
import csv
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HZ, T = 10.0, 50
OFFICIAL = ROOT / "Baseline/data/stage2/labels.csv"
AGENT = ROOT / "data/derived/labels/agent/stage2_agent_labels.csv"
META = ROOT / "data/derived/nexar_subset_v1/stage2_review_with_metadata.csv"


def hit(c, g, rule):
    if rule == "float03":
        return abs(c / HZ - g / HZ) <= 0.3
    return abs(c - g) <= {"pm3": 3, "pm2": 2}[rule]


def best_const(gts, rule="float03"):
    """gts: list of window-relative 10Hz frames (None = not in window, counts as a miss)."""
    n = len(gts)
    if not n:
        return None
    scores = [(sum(1 for g in gts if g is not None and hit(c, g, rule)) / n, c) for c in range(T)]
    top = max(s for s, _ in scores)
    best = [c for s, c in scores if s == top]
    return {"acc": round(top, 4), "best_frames": best, "n": n,
            "acc_at": {str(c): round(s, 4) for s, c in scores if c in (25, 30, 31, 32, 33, 35)}}


def summarize(gts, extra=None):
    inside = [g for g in gts if g is not None]
    out = {"n": len(gts), "n_in_window": len(inside),
           "pos_stats": ({"min": min(inside), "median": statistics.median(inside), "max": max(inside),
                          "hist": dict(sorted(Counter(inside).items()))} if inside else None)}
    for rule in ("float03", "pm3", "pm2"):
        out[rule] = best_const(gts, rule)
    if extra:
        out.update(extra)
    return out


def float_edge():
    """Which exact 3-frame gaps fail |a/10-b/10|<=0.3 in IEEE float (for c,g in 0..49)."""
    fails = [(c, c + 3) for c in range(T - 3) if abs(c / HZ - (c + 3) / HZ) > 0.3]
    return {"n_3frame_pairs": T - 3, "n_fail_float": len(fails), "examples": fails[:8]}


def load_rows():
    meta = {r["video_id"]: r for r in csv.DictReader(META.open(encoding="utf-8-sig"))}
    rows = []
    for r in csv.DictReader(AGENT.open(encoding="utf-8-sig")):
        m = meta.get(r["video_id"])
        if m is None:
            continue
        fps = float(m["decoded_frames"]) / float(m["duration_seconds"]) if m["duration_seconds"] else float(m["fps"])
        rows.append({"vid": r["video_id"], "contact": r["actual_contact"], "fps": fps,
                     "dur": float(m["duration_seconds"]),
                     "toe": float(m["source_time_of_event_seconds"]) if m["source_time_of_event_seconds"] else None,
                     "col": int(r["collision_frame"]) if r["collision_frame"] else None,
                     "ent": int(r["entry_frame"]) if r["entry_frame"] else None,
                     "lane_entry": r["lane_entry_suitable"], "evasion": r["evasion_space"],
                     "side": r["entry_side"], "conf": float(r["confidence"] or 0)})
    return rows


def rel(t, start):
    """seconds -> window-relative 10Hz index, None if outside [0, T-1]."""
    if t is None:
        return None
    q = int(round((t - start) * HZ))
    return q if 0 <= q < T else None


def main():
    out_path = Path(sys.argv[1])
    res = {"metric": "Acc@0.3s at 10Hz/50 frames; best constant over 0..49", "float_edge": float_edge()}

    off = [int(r["t_collision"]) for r in csv.DictReader(OFFICIAL.open(encoding="utf-8-sig"))]
    res["official_examples"] = summarize(off, {"t_collision": off, "entry": "all -1 (entry unscored/undefined here)"})

    rows = load_rows()
    col = [r for r in rows if r["contact"] == "yes" and r["col"] is not None]
    evt = [r for r in col if r["toe"] is not None]
    res["labels"] = {"source": "agent_labeled only (human reviewed rows: 0)", "rows": len(rows),
                     "contact_yes_with_collision": len(col), "with_nexar_toe": len(evt),
                     "with_entry_frame": sum(1 for r in col if r["ent"] is not None)}
    dt = [r["col"] / r["fps"] - r["toe"] for r in evt]
    res["labels"]["collision_minus_toe_s"] = {"median": round(statistics.median(dt), 3),
                                             "abs_le_0.3": sum(abs(x) <= 0.3 for x in dt),
                                             "abs_le_0.5": sum(abs(x) <= 0.5 for x in dt), "n": len(dt)}

    hyp = {}
    # H1: window anchored on the dataset event time with a fixed pre-roll (official 30/30/31/32/41 suggests ~3 s).
    for pre in (2.5, 3.0, 3.5):
        starts = {r["vid"]: r["toe"] - pre for r in evt}
        c = [rel(r["col"] / r["fps"], starts[r["vid"]]) for r in evt]
        ent_rows = [r for r in evt if r["ent"] is not None]
        e = [rel(r["ent"] / r["fps"], starts[r["vid"]]) for r in ent_rows]
        hyp[f"event_anchor_pre{pre}"] = {"collision": summarize(c), "entry": summarize(e) if e else None,
                                         "entry_before_window": sum(1 for r in ent_rows
                                                                    if r["ent"] / r["fps"] < starts[r["vid"]])}
    # H2: window anchored on the true contact with the official-observed offset spread (uniform 30..41).
    spread = list(range(30, 42))
    hyp["contact_anchor_uniform_30_41"] = {"collision": summarize(spread),
                                           "note": "each offset 30..41 equally likely; analytic"}
    # H3: last 5 s of each clip.
    c = [rel(r["col"] / r["fps"], r["dur"] - T / HZ) for r in col]
    hyp["clip_tail_5s"] = {"collision": summarize(c)}
    # H4: any 50-frame window containing the collision, uniformly (position carries no information).
    hyp["uniform_any_window"] = {"collision": summarize(list(range(T))), "note": "analytic lower bound"}
    # Entry relative to collision on the 10 Hz grid (sign: entry before collision is negative).
    ent = [r for r in col if r["ent"] is not None]
    lead = [round((r["ent"] / r["fps"] - r["col"] / r["fps"]) * HZ) for r in ent]
    if lead:
        res["entry_minus_collision_10hz"] = {"n": len(lead), "min": min(lead), "median": statistics.median(lead),
                                            "max": max(lead), "hist": dict(sorted(Counter(lead).items()))}
        # Rule entry = collision - k (given the true collision frame, placed at 30 so float rounding matches).
        rule = {}
        for rname in ("float03", "pm3", "pm2"):
            sc = [(sum(hit(30 - k, 30 + d, rname) for d in lead) / len(lead), k) for k in range(1, 20)]
            top = max(s for s, _ in sc)
            rule[rname] = {"acc": round(top, 4), "best_k": [k for s, k in sc if s == top]}
        res["entry_rule_collision_minus_k"] = rule
        # Entry under the official-like collision placement: collision at each of 30..41, entry = col + lead.
        e = [c0 + d if 0 <= c0 + d < T else None for c0 in spread for d in lead]
        hyp["contact_anchor_uniform_30_41"]["entry"] = summarize(e)
    res["hypotheses"] = hyp

    for key in ("evasion", "side"):
        vals = [r[key] for r in ent if r[key] not in ("", None)]
        res[f"{key}_dist_entry_cases"] = dict(Counter(vals))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("official_examples", "labels", "float_edge")}, ensure_ascii=False)[:3000])
    for k, v in hyp.items():
        print(k, "collision", v["collision"]["float03"], "| entry",
              (v.get("entry") or {}).get("float03"))


if __name__ == "__main__":
    main()
