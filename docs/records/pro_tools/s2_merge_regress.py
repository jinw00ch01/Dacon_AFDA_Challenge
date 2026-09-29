"""Regression: new stage2_agent_label.merge (staging copy) on real data vs existing v6 merged CSV."""
import argparse
import csv
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("s2l", ROOT / "work/pro_tools/staging/stage2_agent_label.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.HUMAN = ROOT / "data/derived/nexar_subset_v1/stage2_review_with_metadata.csv"
mod.AGENT = ROOT / "data/derived/labels/agent/stage2_agent_labels.csv"

out = ROOT / "work/s2_merge_regress/merged_new.csv"
out.parent.mkdir(parents=True, exist_ok=True)
if out.exists():
    out.unlink()
mod.merge(argparse.Namespace(out=out, meta=[]))
ref_path = ROOT / "work/agent/stage2_merged_latest.csv"
read = lambda p: {r["video_id"]: r for r in csv.DictReader(p.open(encoding="utf-8-sig", newline=""))}
new, ref = read(out), read(ref_path)
cols = [c for c in next(iter(ref.values())) if c != "confidence"]
diffs = [(v, c, ref[v][c], new[v].get(c)) for v in ref for c in cols if ref[v][c] != new.get(v, {}).get(c)]
report = {"ref": str(ref_path), "rows_ref": len(ref), "rows_new": len(new), "compared_cols": cols,
          "diff_count": len(diffs), "diffs": diffs[:20],
          "new_cols": [c for c in next(iter(new.values())) if c not in ref[next(iter(ref))]],
          "frame_source_counts": {s: sum(r["collision_frame_source"] == s for r in new.values())
                                  for s in ("human", "agent", "nexar_event", "")}}
(out.parent / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({k: v for k, v in report.items() if k != "compared_cols"}))
