"""Collect attachments for the S23 batch-1 and S2 labels v7 qa packets and print summaries."""
import collections
import csv
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OB = ROOT / "work/agent/outbox"

s23 = OB / "s23_real_b1_files"
(s23 / "identity").mkdir(parents=True, exist_ok=True)
for n in ("manifest.csv", "report.json"):
    shutil.copy2(ROOT / "work/s23_qa_b1" / n, s23 / n)
for j in (ROOT / "work/s23_qa_b1/identity").glob("*.jpg"):
    shutil.copy2(j, s23 / "identity" / j.name)

s2 = OB / "stage2_labels_v7_files"
shutil.copy2(ROOT / "work/s2_human_vs_agent/diff.csv", s2 / "human_vs_agent_diff.csv")
shutil.copy2(ROOT / "work/s2_human_vs_agent/report.json", s2 / "human_vs_agent_report.json")
shutil.copy2(ROOT / "data/derived/labels/agent/stage2_agent_labels.csv", s2 / "stage2_agent_labels_raw.csv")

for d in (s23, s2):
    print(d.name, sum(p.stat().st_size for p in d.rglob("*") if p.is_file()) / 1e6, "MB")
r = list(csv.DictReader(open(s2 / "stage2_merged_v7.csv", encoding="utf-8-sig")))
print(collections.Counter(x["label_source"] for x in r))
h = [x for x in r if x["label_source"] == "human"]
print(collections.Counter((x["actual_contact"], x["collision_valid"], x["entry_valid"], x["evasion_valid"], x["side_valid"]) for x in h))
print(collections.Counter(x["collision_frame_source"] for x in r))
pos = [x for x in r if x["source_label"] == "positive"]
print("positive contact", collections.Counter(x["actual_contact"] for x in pos))
