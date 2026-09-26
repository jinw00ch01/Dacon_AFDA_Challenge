"""Human review of Stage 2 labels without hand-editing the human CSV.

  sheet  write work/s2_human_review/s2_review_sheet.csv for the given video ids (default: the
         uncertain cases the Pro agent listed) with the agent's proposal next to empty human
         columns, plus one frame-number contact sheet per video around the event
  apply  validate the filled sheet and write the rows into the human CSV with
         review_status=reviewed, in one atomic write (so the exchange worker and the Pro agent
         see a single change). A backup of the human CSV is kept under work/.

Run by a person on Pro. Agents never run `apply`: the human CSV is theirs to read only.
Excel may drop the leading zeros of video_id or save as CP949; `apply` accepts both.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
HUMAN = ROOT / "data/derived/nexar_subset_v1/stage2_review_with_metadata.csv"
AGENT = ROOT / "data/derived/labels/agent/stage2_agent_labels.csv"
WORK = ROOT / "work/s2_human_review"
SHEET = WORK / "s2_review_sheet.csv"
DEFAULT_IDS = ("00082 00282 00291 00295 00527 00566 00600 00660 00692 00723 00849 00860 00867 00887 "
               "00947 00989 00996 01028 01037 00861 00902 00064").split()
LABEL_FIELDS = ["actual_contact", "lane_entry_suitable", "collision_frame", "entry_frame", "evasion_space", "entry_side"]
HUMAN_COLUMNS = LABEL_FIELDS + ["human_notes"]


def read_rows(path):
    for encoding in ("utf-8-sig", "cp949"):
        try:
            with Path(path).open(encoding=encoding, newline="") as handle:
                return list(csv.DictReader(handle))
        except UnicodeDecodeError:
            continue
    raise SystemExit(f"Cannot read {path} as UTF-8 or CP949")


def video_key(value):
    value = str(value).strip().lstrip("=").strip('"').strip()
    return value.zfill(5) if value.isdigit() else value


def latest_agent(path=AGENT):
    latest = {}
    if Path(path).exists():
        for row in read_rows(path):
            latest[video_key(row["video_id"])] = row
    return latest


def sheet(ids, human=HUMAN, agent=AGENT, out=SHEET, images=True, force=False):
    if out.exists() and not force:
        raise SystemExit(f"{out} already exists; it may hold your review. Use --force to rebuild it.")
    meta = {video_key(r["video_id"]): r for r in read_rows(human)}
    proposals = latest_agent(agent)
    rows = []
    for vid in ids:
        vid = video_key(vid)
        if vid not in meta:
            raise SystemExit(f"Unknown video_id {vid}")
        m, a = meta[vid], proposals.get(vid, {})
        fps, frames = float(m["fps"]), int(float(m["decoded_frames"]))
        event = round(float(m["source_time_of_event_seconds"]) * fps) if m.get("source_time_of_event_seconds") else ""
        centre = next((int(float(v)) for v in (a.get("collision_frame"), event, a.get("entry_frame")) if v not in (None, "")), frames // 2)
        reviewed = m.get("review_status") == "reviewed"
        row = {"video_id": vid, "video_path": str((ROOT / m["source_path"]).resolve()), "fps": m["fps"],
               "decoded_frames": frames, "nexar_event_frame": event, "sheet_image": f"sheets/{vid}_event.jpg",
               **{"agent_" + k: a.get(k, "") for k in LABEL_FIELDS + ["confidence"]},
               "agent_notes": (a.get("notes") or "")[:300]}
        row.update({k: (m.get(k, "") if reviewed else "") for k in LABEL_FIELDS})
        row["human_notes"] = ""
        rows.append((row, centre, frames))
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, list(rows[0][0]))
        writer.writeheader()
        writer.writerows(r for r, _, _ in rows)
    if images:
        for row, centre, frames in rows:
            target = out.parent / row["sheet_image"]
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run([sys.executable, str(ROOT / "scripts/frame_sheet.py"), "--video", row["video_path"],
                            "--start", str(max(0, centre - 45)), "--end", str(min(frames, centre + 46)), "--step", "3",
                            "--width", "320", "--out", str(target)], check=True, capture_output=True)
    print(f"wrote {out} ({len(rows)} videos)" + (f" and contact sheets in {out.parent / 'sheets'}" if images else ""))


def _int_or_blank(value):
    value = str(value).strip()
    return "" if value == "" else str(int(float(value)))


def validate(row, meta):
    """Return (clean values, errors) for one filled sheet row."""
    errors, clean = [], {}
    frames = int(float(meta["decoded_frames"]))
    contact = str(row.get("actual_contact", "")).strip().lower()
    clean["actual_contact"] = contact
    if contact not in {"yes", "no", "uncertain"}:
        errors.append(f"actual_contact={contact!r} must be yes/no/uncertain")
    suitable = str(row.get("lane_entry_suitable", "")).strip().lower()
    clean["lane_entry_suitable"] = suitable
    if suitable not in {"", "yes", "no", "uncertain"}:
        errors.append(f"lane_entry_suitable={suitable!r} must be yes/no/uncertain or blank")
    for name in ("collision_frame", "entry_frame"):
        try:
            clean[name] = _int_or_blank(row.get(name, ""))
        except ValueError:
            errors.append(f"{name}={row.get(name)!r} is not a frame number")
            clean[name] = ""
            continue
        if clean[name] and not 0 <= int(clean[name]) < frames:
            errors.append(f"{name}={clean[name]} outside 0..{frames - 1}")
    if clean.get("collision_frame") and contact != "yes":
        errors.append("collision_frame only with actual_contact=yes")
    if clean.get("collision_frame") and clean.get("entry_frame") and int(clean["entry_frame"]) > int(clean["collision_frame"]):
        errors.append("entry_frame is after collision_frame")
    try:
        clean["evasion_space"] = _int_or_blank(row.get("evasion_space", ""))
    except ValueError:
        clean["evasion_space"] = "invalid"
    if clean["evasion_space"] not in {"", "0", "1"}:
        errors.append(f"evasion_space={row.get('evasion_space')!r} must be 0, 1 or blank")
    side = str(row.get("entry_side", "")).strip().upper()
    clean["entry_side"] = {"L": "LEFT", "R": "RIGHT"}.get(side, side)
    if clean["entry_side"] not in {"", "LEFT", "RIGHT"}:
        errors.append(f"entry_side={row.get('entry_side')!r} must be LEFT/RIGHT or blank")
    return clean, errors


def apply(sheet_path=SHEET, human=HUMAN, dry_run=False, backup_dir=WORK / "backup", today=None):
    if hasattr(sys.stdout, "reconfigure"):  # Korean notes must not crash a cp1252 stdout (English Windows, CI)
        sys.stdout.reconfigure(encoding="utf-8")
    human = Path(human)
    with human.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields, rows = reader.fieldnames, list(reader)
    by_id = {video_key(r["video_id"]): r for r in rows}
    today = today or datetime.now().strftime("%Y-%m-%d")
    updates, problems = [], []
    for filled in read_rows(sheet_path):
        vid = video_key(filled.get("video_id", ""))
        if not str(filled.get("actual_contact", "")).strip():
            continue  # not reviewed yet: leave the human CSV untouched for this video
        if vid not in by_id:
            problems.append(f"{vid}: unknown video_id")
            continue
        clean, errors = validate(filled, by_id[vid])
        problems += [f"{vid}: {e}" for e in errors]
        updates.append((vid, clean, str(filled.get("human_notes", "")).strip()))
    if problems:
        print("Nothing written. Fix these rows in the sheet and run apply again:")
        print("\n".join("  - " + p for p in problems))
        return 1
    if not updates:
        print("No filled rows (actual_contact is empty everywhere). Nothing to apply.")
        return 0
    for vid, clean, note in updates:
        before = {k: by_id[vid].get(k, "") for k in LABEL_FIELDS}
        print(f"{vid}: {before} -> {clean}" + (f" | note: {note}" if note else ""))
    if dry_run:
        print(f"dry run: {len(updates)} rows would be marked reviewed")
        return 0
    for vid, clean, note in updates:
        row = by_id[vid]
        row.update(clean)
        row["review_status"] = "reviewed"
        stamp = f"human review {today}" + (f": {note}" if note else "")
        row["notes"] = (row.get("notes", "") + " | " if row.get("notes") else "") + stamp
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"{human.stem}_{datetime.now():%Y%m%d_%H%M%S}.csv"
    shutil.copyfile(human, backup)
    temp = human.with_name(human.name + ".partial")
    with temp.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    try:
        os.replace(temp, human)
    except PermissionError:
        temp.unlink(missing_ok=True)
        print(f"{human.name} is open in another program (Excel?). Close it and run apply again.")
        return 1
    print(f"marked {len(updates)} rows reviewed in {human} (backup: {backup})")
    print("The Pro agent picks this up within a minute or two; the exchange sends the CSV to Ultra.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    make = sub.add_parser("sheet")
    make.add_argument("--ids", nargs="*", default=DEFAULT_IDS)
    make.add_argument("--no-images", action="store_true")
    make.add_argument("--force", action="store_true", help="rebuild an existing sheet (loses what you typed)")
    run = sub.add_parser("apply")
    run.add_argument("--sheet", type=Path, default=SHEET)
    run.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.command == "sheet":
        sheet(args.ids, images=not args.no_images, force=args.force)
        return 0
    return apply(args.sheet, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
