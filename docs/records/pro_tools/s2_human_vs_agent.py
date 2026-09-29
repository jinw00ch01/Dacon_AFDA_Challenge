"""Compare human `reviewed` S2 rows against the latest agent label per video (read-only).

Usage: s2_human_vs_agent.py <out_dir>
Writes diff.csv (one row per reviewed video) and report.json (agreement counts, frame errors).
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HUMAN = ROOT / "data/derived/nexar_subset_v1/stage2_review_with_metadata.csv"
AGENT = ROOT / "data/derived/labels/agent/stage2_agent_labels.csv"
FIELDS = ["actual_contact", "lane_entry_suitable", "collision_frame", "entry_frame", "evasion_space", "entry_side"]


def rows(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    human = {r["video_id"].zfill(5): r for r in rows(HUMAN) if r["review_status"] == "reviewed"}
    agent = {}
    for r in rows(AGENT):
        agent[r["video_id"].zfill(5)] = r
    diffs, rep = [], {"n_reviewed": len(human), "missing_agent": [], "fields": {}}
    col_err, ent_err = [], []
    for f in FIELDS:
        rep["fields"][f] = {"same": 0, "diff": 0, "pairs": {}}
    for vid, h in sorted(human.items()):
        a = agent.get(vid)
        if a is None:
            rep["missing_agent"].append(vid)
            continue
        row = {"video_id": vid, "agent_confidence": a.get("confidence", ""), "human_notes": h.get("notes", "")}
        for f in FIELDS:
            hv, av = (h.get(f) or "").strip(), (a.get(f) or "").strip()
            if f in ("collision_frame", "entry_frame", "evasion_space"):
                hn, an = num(hv), num(av)
                same = hn == an
            else:
                same = hv.lower() == av.lower()
            rep["fields"][f]["same" if same else "diff"] += 1
            key = f"{av or '-'}->{hv or '-'}" if f not in ("collision_frame", "entry_frame") else None
            if key:
                rep["fields"][f]["pairs"][key] = rep["fields"][f]["pairs"].get(key, 0) + 1
            row[f"agent_{f}"], row[f"human_{f}"] = av, hv
        fps = num(h.get("fps")) or 30.0
        hc, ac = num(h["collision_frame"]), num(a["collision_frame"])
        if hc is not None and ac is not None:
            col_err.append({"video_id": vid, "frames": ac - hc, "sec": (ac - hc) / fps})
        he, ae = num(h["entry_frame"]), num(a["entry_frame"])
        if he is not None and ae is not None:
            ent_err.append({"video_id": vid, "frames": ae - he, "sec": (ae - he) / fps})
        row["collision_err_frames"] = "" if hc is None or ac is None else ac - hc
        row["entry_err_frames"] = "" if he is None or ae is None else ae - he
        diffs.append(row)

    def summ(errs):
        if not errs:
            return {"n": 0}
        s = sorted(abs(e["sec"]) for e in errs)
        return {"n": len(s), "median_abs_sec": s[len(s) // 2] if len(s) % 2 else (s[len(s) // 2 - 1] + s[len(s) // 2]) / 2,
                "max_abs_sec": s[-1], "within_0p3s": sum(x <= 0.3 + 1e-9 for x in s),
                "within_1s": sum(x <= 1.0 + 1e-9 for x in s), "items": errs}
    rep["collision_err"] = summ(col_err)
    rep["entry_err"] = summ(ent_err)
    # decision 8 check: nexar time_of_event x fps vs human collision frame (contact=yes only)
    tev = []
    for vid, h in sorted(human.items()):
        hc, t, fps = num(h["collision_frame"]), num(h.get("source_time_of_event_seconds")), num(h.get("fps"))
        if h["actual_contact"] == "yes" and hc is not None and t is not None and fps:
            ev = round(t * fps)
            tev.append({"video_id": vid, "frames": ev - hc, "sec": (ev - hc) / fps})
    rep["nexar_event_vs_human"] = summ(tev)
    # contact changes that move a video into/out of collision supervision
    rep["contact_flip"] = [d["video_id"] + f": {d['agent_actual_contact']}->{d['human_actual_contact']}"
                           for d in diffs if d["agent_actual_contact"] != d["human_actual_contact"]]
    with open(out / "diff.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(diffs[0].keys()))
        w.writeheader()
        w.writerows(diffs)
    (out / "report.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in rep.items() if k not in ("collision_err", "entry_err")}, ensure_ascii=False))
    print("collision", {k: v for k, v in rep["collision_err"].items() if k != "items"}, rep["collision_err"].get("items"))
    print("entry", {k: v for k, v in rep["entry_err"].items() if k != "items"}, rep["entry_err"].get("items"))
    print("nexar_event", {k: v for k, v in rep["nexar_event_vs_human"].items() if k != "items"},
          [(e["video_id"], e["frames"]) for e in rep["nexar_event_vs_human"].get("items", [])])


if __name__ == "__main__":
    main(sys.argv[1])
