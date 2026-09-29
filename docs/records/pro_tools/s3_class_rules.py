"""S3 proxy class-rule candidates from s3_auxiliary_10hz.csv (train split only, SRC014 excluded).

Rules (all per source, centered rolling mean of `window` samples, 10 Hz):
  STOPPED       smoothed speed < v_stop
  ACCELERATING  smoothed accel >  a_db   (else if not STOPPED)
  DECELERATING  smoothed accel < -a_db
  CONSTANT      otherwise
  steer: centered = smoothed steering - bias (bias = train median while moving and |steer|<10 deg)
         LEFT if centered > s_th, RIGHT if < -s_th (comma convention: positive angle = left), else STRAIGHT
Writes JSON summary to --out.
"""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[2]
CSV = ROOT / "data/derived/comma_subset_v1/s3_auxiliary_10hz.csv"


def smooth(values, window):
    half = window // 2
    out = []
    for i in range(len(values)):
        seg = values[max(0, i - half):i + half + 1]
        out.append(sum(seg) / len(seg))
    return out


def load():
    by_src = defaultdict(list)
    with CSV.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            by_src[row["source_id"]].append(row)
    for rows in by_src.values():
        rows.sort(key=lambda r: int(r["sample_index"]))
    return by_src


def classify(rows, window, v_stop, a_db, s_th, bias):
    speed = smooth([float(r["speed_mps"]) for r in rows], window)
    accel = smooth([float(r["acceleration_mps2_proxy"]) for r in rows], window)
    steer = smooth([float(r["steering_angle_deg"]) for r in rows], window)
    out = []
    for v, a, s in zip(speed, accel, steer):
        acc = "STOPPED" if v < v_stop else "ACCELERATING" if a > a_db else "DECELERATING" if a < -a_db else "CONSTANT"
        c = s - bias
        st = "LEFT" if c > s_th else "RIGHT" if c < -s_th else "STRAIGHT"
        out.append((acc, st))
    return out


def dist(labels):
    acc = Counter(a for a, _ in labels)
    steer_moving = Counter(s for a, s in labels if a != "STOPPED")
    n, m = len(labels), sum(steer_moving.values())
    return {"n": n, "accel": {k: acc.get(k, 0) for k in ("ACCELERATING", "DECELERATING", "CONSTANT", "STOPPED")},
            "accel_pct": {k: round(100 * acc.get(k, 0) / n, 1) for k in ("ACCELERATING", "DECELERATING", "CONSTANT", "STOPPED")},
            "steer_moving": {k: steer_moving.get(k, 0) for k in ("LEFT", "STRAIGHT", "RIGHT")},
            "steer_moving_pct": {k: round(100 * steer_moving.get(k, 0) / max(m, 1), 1) for k in ("LEFT", "STRAIGHT", "RIGHT")}}


def quantile(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(0, round(q * (len(xs) - 1))))]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--window", type=int, default=5)
    p.add_argument("--v-stop", type=float, default=0.5)
    p.add_argument("--a-db", type=float, default=0.3)
    p.add_argument("--s-th", type=float, default=5.0)
    args = p.parse_args()
    by_src = load()
    splits = {s: rows[0]["split"] for s, rows in by_src.items()}
    included = {s: r for s, r in by_src.items() if s != "SRC014"}
    train = {s: r for s, r in included.items() if splits[s] == "train"}
    report = {"csv": str(CSV.relative_to(ROOT)), "excluded": ["SRC014"],
              "sources_by_split": {k: sorted(s for s in included if splits[s] == k) for k in sorted(set(splits.values()))},
              "rows_by_split": dict(Counter(splits[s] for s, r in included.items() for _ in r))}
    # raw train statistics
    speeds = [float(x["speed_mps"]) for r in train.values() for x in r]
    moving_steer = [float(x["steering_angle_deg"]) for r in train.values() for x in r
                    if float(x["speed_mps"]) > 2 and abs(float(x["steering_angle_deg"])) < 10]
    bias = median(moving_steer)
    report["train_raw"] = {"speed_quantiles": {q: round(quantile(speeds, q), 3) for q in (0.01, 0.05, 0.1, 0.5, 0.9)},
                           "frac_speed_below_0.5": round(sum(v < 0.5 for v in speeds) / len(speeds), 4),
                           "frac_speed_below_1.0": round(sum(v < 1.0 for v in speeds) / len(speeds), 4),
                           "steer_bias_median_deg": round(bias, 3)}
    for w in (1, 5, 11):
        acc_all, steer_all = [], []
        for r in train.values():
            a = smooth([float(x["acceleration_mps2_proxy"]) for x in r], w)
            s = smooth([float(x["steering_angle_deg"]) for x in r], w)
            v = smooth([float(x["speed_mps"]) for x in r], w)
            acc_all += [ai for ai, vi in zip(a, v) if vi >= 0.5]
            steer_all += [abs(si - bias) for si, vi in zip(s, v) if vi >= 0.5]
        report[f"train_quantiles_w{w}"] = {
            "abs_accel": {q: round(quantile([abs(x) for x in acc_all], q), 3) for q in (0.5, 0.6, 0.7, 0.8, 0.9)},
            "abs_steer_centered": {q: round(quantile(steer_all, q), 3) for q in (0.5, 0.7, 0.8, 0.9, 0.95)}}
    grid = []
    for w in (5, 11):
        for v_stop in (0.5, 1.0):
            for a_db in (0.2, 0.3, 0.5):
                for s_th in (2.0, 5.0, 10.0):
                    labels = [l for r in train.values() for l in classify(r, w, v_stop, a_db, s_th, bias)]
                    grid.append({"window": w, "v_stop": v_stop, "a_db": a_db, "s_th": s_th, **dist(labels)})
    report["train_grid"] = grid
    rec = {"window": args.window, "v_stop": args.v_stop, "a_db": args.a_db, "s_th": args.s_th, "bias": round(bias, 3)}
    report["recommended"] = rec
    report["recommended_by_split"] = {}
    for split in report["sources_by_split"]:
        labels = [l for s, r in included.items() if splits[s] == split
                  for l in classify(r, rec["window"], rec["v_stop"], rec["a_db"], rec["s_th"], bias)]
        report["recommended_by_split"][split] = dist(labels)
    report["recommended_by_source"] = {s: dist(classify(r, rec["window"], rec["v_stop"], rec["a_db"], rec["s_th"], bias))
                                       for s, r in sorted(included.items())}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("rows_by_split", "train_raw", "train_quantiles_w5", "recommended_by_split")}, indent=1))


if __name__ == "__main__":
    main()
