"""v1s 렌더 병렬 드라이버: source를 N개 프로세스로 나눠 같은 out 폴더에 렌더하고 manifest를 source 순으로 합친다."""
import argparse, csv, subprocess, sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--procs", type=int, default=3)
    ap.add_argument("--variants", type=int, default=4)
    a = ap.parse_args()
    plan = Path(a.data_root) / "data/derived/comma_subset_v1/s23_capture_ready.csv"
    ids = sorted({r["planned_source_id"] for r in csv.DictReader(plan.open(encoding="utf-8-sig"))})
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    procs = []
    for i in range(a.procs):
        part = ids[i::a.procs]
        cmd = [sys.executable, a.script, "--profile", "v1s", "--seed", "s1synth_v1", "--data-root", a.data_root, "--out", str(out),
               "--variants", str(a.variants), "--preview", "--manifest", f"manifest_part{i}.csv", "--sources", *part]
        procs.append(subprocess.Popen(cmd))
    rc = [p.wait() for p in procs]
    print({"returncodes": rc, "sources": len(ids)}, flush=True)
    if any(rc):
        sys.exit(1)
    rows, header = [], None
    for i in range(a.procs):
        with (out / f"manifest_part{i}.csv").open(encoding="utf-8", newline="") as f:
            rd = csv.DictReader(f)
            header = rd.fieldnames
            rows += list(rd)
    rows.sort(key=lambda r: (r["source_id"], r["variant"] != "ORIG", r["variant"]))
    with (out / "manifest.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, header)
        w.writeheader()
        w.writerows(rows)
    for i in range(a.procs):
        (out / f"manifest_part{i}.csv").unlink()
    print({"manifest_rows": len(rows)}, flush=True)


if __name__ == "__main__":
    main()
