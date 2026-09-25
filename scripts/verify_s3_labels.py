"""Verify src/afda/stage3_labels reproduces the released s3 v1b class counts.

Reads the frozen release CSV + rule JSON, applies the label rule, and compares
per-split accel counts and moving (non-STOPPED) steer counts against
recommended_by_split in the rule file. Exits non-zero on any mismatch.
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from afda import stage3_labels  # noqa: E402

RELEASE = ROOT / "data/derived/releases/s3-aux-rules-v1b-20260925"
CSV = RELEASE / "s3_auxiliary_10hz.csv"
RULE = RELEASE / "s3_class_rules_v1b_a02_s45.json"


def main() -> int:
    rule_doc = json.loads(RULE.read_text(encoding="utf-8"))
    rule = rule_doc["recommended"]
    excluded = set(rule_doc.get("excluded", []))
    targets = rule_doc["recommended_by_split"]

    df = pd.read_csv(CSV, encoding="utf-8-sig")
    df = df[~df["source_id"].isin(excluded)].reset_index(drop=True)
    labeled = stage3_labels.add_labels(df, rule)

    mismatches = []
    report = {}
    for split, target in targets.items():
        part = labeled[labeled["split"] == split]
        accel_counts = part["accel_label"].value_counts().to_dict()
        moving = part[part["accel_label"] != "STOPPED"]
        steer_counts = moving["steer_label"].value_counts().to_dict()
        report[split] = {"n": len(part), "accel": accel_counts, "steer_moving": steer_counts}

        for cls in stage3_labels.ACCEL_CLASSES:
            got, want = accel_counts.get(cls, 0), target["accel"].get(cls, 0)
            if got != want:
                mismatches.append(f"{split} accel {cls}: got {got} want {want}")
        for cls in stage3_labels.STEER_CLASSES:
            got, want = steer_counts.get(cls, 0), target["steer_moving"].get(cls, 0)
            if got != want:
                mismatches.append(f"{split} steer {cls}: got {got} want {want}")

    print(json.dumps(report, indent=2, ensure_ascii=False))
    if mismatches:
        print("\nMISMATCHES:")
        for m in mismatches:
            print(" -", m)
        return 1
    print("\nAll per-split accel + moving-steer counts match the released v1b rule.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
