"""Append-only Stage 2 agent labels, kept separate from the human review CSV.

  add    validate one labeling decision and append it (latest row per video wins)
  latest print the current agent label per video
  merge  write a merged candidate: human `reviewed` rows always override agent rows

Agent rows are `agent_labeled`, never `reviewed`. The human CSV is only read.

Expansion videos (decision 8, Nexar positives beyond the human CSV) come in through `--meta <csv>`
(repeatable; columns video_id, source_path, source_label, decoded_frames, fps and optional
nexar_event_frame = time_of_event x fps). In `merge`, an expansion video without an agent row becomes
label_source=nexar_event with actual_contact=contact_unverified (collision_valid stays 0); an agent row
with actual_contact=yes but no collision_frame takes nexar_event_frame. `collision_frame_source` records
which of human / agent / nexar_event supplied the frame.
"""
import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HUMAN = ROOT / "data/derived/nexar_subset_v1/stage2_review_with_metadata.csv"
AGENT = ROOT / "data/derived/labels/agent/stage2_agent_labels.csv"
FIELDS = ["video_id", "labeled_utc", "labeler", "model", "guideline_version", "actual_contact", "lane_entry_suitable",
          "collision_frame", "entry_frame", "evasion_space", "entry_side", "confidence", "evidence", "notes"]
LABEL_FIELDS = ["actual_contact", "lane_entry_suitable", "collision_frame", "entry_frame", "evasion_space", "entry_side"]


def rows(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def latest():
    result = {}
    for row in rows(AGENT):
        result[row["video_id"]] = row
    return result


def load_meta(extra=()):
    """Human CSV rows first, then expansion metadata rows keyed by video_id."""
    meta = {r["video_id"]: r for r in rows(HUMAN)}
    for path in extra or ():
        for row in rows(Path(path)):
            vid = row["video_id"]
            if vid in meta and int(float(meta[vid]["decoded_frames"])) != int(float(row["decoded_frames"])):
                raise SystemExit(f"{vid}: decoded_frames differs between metadata files")
            meta.setdefault(vid, row)
    return meta


def add(args):
    meta = load_meta(args.meta)
    if args.video_id not in meta:
        raise SystemExit(f"Unknown video_id {args.video_id!r} (keep leading zeros)")
    frames = int(float(meta[args.video_id]["decoded_frames"]))
    for name in ("collision_frame", "entry_frame"):
        value = getattr(args, name)
        if value is not None and not 0 <= value < frames:
            raise SystemExit(f"{name}={value} outside 0..{frames - 1}")
    if args.actual_contact != "yes" and args.collision_frame is not None:
        raise SystemExit("collision_frame requires actual_contact=yes")
    if args.entry_frame is not None and args.collision_frame is not None and args.entry_frame > args.collision_frame:
        raise SystemExit("entry_frame after collision_frame: re-check, or record only the confident one")
    if not 0 <= args.confidence <= 1:
        raise SystemExit("confidence must be within 0..1")
    row = {"video_id": args.video_id, "labeled_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "labeler": "agent_labeled", "model": args.model or os.environ.get("AFDA_MODEL", "claude"),
           "guideline_version": args.guideline, "actual_contact": args.actual_contact,
           "lane_entry_suitable": args.lane_entry_suitable,
           "collision_frame": "" if args.collision_frame is None else args.collision_frame,
           "entry_frame": "" if args.entry_frame is None else args.entry_frame,
           "evasion_space": "" if args.evasion_space is None else args.evasion_space,
           "entry_side": args.entry_side or "", "confidence": args.confidence,
           "evidence": ";".join(args.evidence), "notes": args.notes}
    AGENT.parent.mkdir(parents=True, exist_ok=True)
    new = not AGENT.exists()
    with AGENT.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, FIELDS)
        if new:
            writer.writeheader()
        writer.writerow(row)
    print(json.dumps(row, ensure_ascii=False))


def merge(args):
    agent = latest()
    merged = []
    for meta in load_meta(args.meta).values():
        vid = meta["video_id"]
        human = meta.get("review_status") == "reviewed"
        source = meta if human else agent.get(vid)
        event = (meta.get("nexar_event_frame") or "").strip()
        event = str(int(float(event))) if event else ""
        label_source = "human" if human else ("agent" if source else ("nexar_event" if event else "none"))
        out = {"video_id": vid, "source_path": meta["source_path"], "source_label": meta["source_label"],
               "decoded_frames": meta["decoded_frames"], "fps": meta["fps"],
               "label_source": label_source,
               "confidence": "1.0" if human else (source or {}).get("confidence", "")}
        for name in LABEL_FIELDS:
            out[name] = (source or {}).get(name, "")
        frame_source = label_source if out["collision_frame"] != "" else ""
        if label_source == "nexar_event":
            out["actual_contact"], out["collision_frame"], frame_source = "contact_unverified", event, "nexar_event"
        elif out["actual_contact"] == "yes" and out["collision_frame"] == "" and event:
            out["collision_frame"], frame_source = event, "nexar_event"
        out["collision_valid"] = int(out["actual_contact"] == "yes" and out["collision_frame"] != "")
        out["entry_valid"] = int(out["lane_entry_suitable"] == "yes" and out["entry_frame"] != "")
        out["evasion_valid"] = int(out["evasion_space"] in {"0", "1"})
        out["side_valid"] = int(out["entry_side"] in {"LEFT", "RIGHT"})
        out["collision_frame_source"] = frame_source
        out["nexar_event_frame"] = event
        merged.append(out)
    target = args.out or ROOT / "data/derived/labels" / f"stage2_merged_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, list(merged[0]))
        writer.writeheader()
        writer.writerows(merged)
    counts = {k: sum(r[k] for r in merged) for k in ("collision_valid", "entry_valid", "evasion_valid", "side_valid")}
    sources = {k: sum(r["label_source"] == k for r in merged) for k in ("human", "agent", "nexar_event", "none")}
    print(json.dumps({"file": str(target), "videos": len(merged), **sources, "valid_counts": counts}))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    a = sub.add_parser("add")
    a.add_argument("--video-id", required=True)
    a.add_argument("--actual-contact", required=True, choices=["yes", "no", "uncertain"])
    a.add_argument("--lane-entry-suitable", required=True, choices=["yes", "no", "uncertain"])
    a.add_argument("--collision-frame", type=int)
    a.add_argument("--entry-frame", type=int)
    a.add_argument("--evasion-space", type=int, choices=[0, 1])
    a.add_argument("--entry-side", choices=["LEFT", "RIGHT"])
    a.add_argument("--confidence", type=float, required=True)
    a.add_argument("--evidence", nargs="*", default=[])
    a.add_argument("--notes", default="")
    a.add_argument("--model")
    a.add_argument("--guideline", default="DATA_PREPARATION_SPEC.md#5@2026-09-25")
    a.add_argument("--meta", action="append", default=[], help="expansion metadata CSV (repeatable)")
    sub.add_parser("latest")
    m = sub.add_parser("merge")
    m.add_argument("--out", type=Path)
    m.add_argument("--meta", action="append", default=[], help="expansion metadata CSV (repeatable)")
    args = parser.parse_args()
    if args.command == "add":
        add(args)
    elif args.command == "latest":
        print(json.dumps(latest(), ensure_ascii=False, indent=2))
    else:
        merge(args)


if __name__ == "__main__":
    main()
