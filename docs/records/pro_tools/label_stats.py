"""Summarize a merged Stage 2 CSV: contact / confidence distribution for agent rows, by source_label."""
import csv
import json
import sys
from collections import Counter

rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8")))
out = {}
for lab in ("positive", "negative"):
    sub = [r for r in rows if r["source_label"] == lab and r["label_source"] != "none" and r["confidence"]]
    out[lab] = {
        "labeled": len(sub),
        "actual_contact": dict(Counter(r["actual_contact"] for r in sub)),
        "confidence": dict(sorted(Counter(r["confidence"] for r in sub).items())),
        "valid": {k: sum(int(r[k] or 0) for r in sub) for k in ("collision_valid", "entry_valid", "evasion_valid", "side_valid")},
        "lane_entry_suitable": dict(Counter(r["lane_entry_suitable"] for r in sub)),
    }
out["label_source"] = dict(Counter(r["label_source"] for r in rows))
pos_all = [r["video_id"] for r in rows if r["source_label"] == "positive"]
done = {r["video_id"] for r in rows if r["source_label"] == "positive" and r["confidence"]}
out["positive_unlabeled"] = sorted(v for v in pos_all if v not in done)
print(json.dumps(out, ensure_ascii=False, indent=1))
