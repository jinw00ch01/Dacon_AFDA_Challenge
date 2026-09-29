"""Write a JSON list of actual_contact=no decisions for the Nexar negatives (source_label=negative)."""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
rows = csv.DictReader((ROOT / "data/derived/nexar_subset_v1/stage2_review_with_metadata.csv").open(encoding="utf-8-sig"))
out = [{"video_id": r["video_id"], "actual_contact": "no", "lane_entry_suitable": "no", "confidence": 0.6,
        "notes": "Nexar source_label=negative (the dataset annotates no collision/near-miss event). Recorded from the source label only; "
                 "frames were NOT visually inspected by the agent. No collision/entry frames are defined for negatives."}
       for r in rows if r["source_label"] == "negative"]
Path(sys.argv[1]).write_text(json.dumps(out, indent=1), encoding="utf-8")
print(len(out))
