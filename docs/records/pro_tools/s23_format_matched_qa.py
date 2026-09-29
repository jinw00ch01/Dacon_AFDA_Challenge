"""QA for data/derived/s1_s23_format_matched_v1: manifest vs files, decoded frames/size/fps/fourcc,
per-track class balance, per-track size cue (AUROC of bytes), and a pair contact sheet.
usage: s23_format_matched_qa.py --dir <dir> --out <dir> [--sheet PAIR_ID ...]
"""
import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pandas as pd


def auroc(pos, neg):
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    if len(pos) == 0 or len(neg) == 0:
        return None
    gt = (pos[:, None] > neg[None, :]).mean()
    eq = (pos[:, None] == neg[None, :]).mean()
    return float(gt + 0.5 * eq)


def probe(p):
    cap = cv2.VideoCapture(str(p))
    fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
    fcc = "".join(chr((fourcc >> 8 * i) & 0xFF) for i in range(4))
    meta_n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    n, shp, first, mid = 0, None, None, None
    while True:
        ok, f = cap.read()
        if not ok:
            break
        if n == 0:
            first, shp = f, f.shape
        if n == 25:
            mid = f
        n += 1
    cap.release()
    return dict(decoded=n, meta_frames=meta_n, fps=fps, fourcc=fcc, shape=shp), first, mid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sheet", nargs="*", default=[])
    a = ap.parse_args()
    d, out = Path(a.dir), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    m = pd.read_csv(d / "manifest.csv")
    issues = []
    files = {p.name for p in d.glob("*.mp4")}
    if set(m.file) != files:
        issues.append({"manifest_vs_files": sorted(set(m.file) ^ files)})
    if m.file.duplicated().any():
        issues.append({"dup_files": m.file[m.file.duplicated()].tolist()})
    rows, thumbs = [], {}
    for r in m.itertuples():
        p = d / r.file
        info, first, mid = probe(p)
        sha_ok = hashlib.sha256(p.read_bytes()).hexdigest() == r.sha256
        bad = []
        if info["decoded"] != 50 or r.frames != 50:
            bad.append("frames")
        if info["meta_frames"] != info["decoded"]:
            bad.append("meta_frames")
        if info["shape"] is None or info["shape"][:2] != (720, 1280):
            bad.append("shape")
        if abs(info["fps"] - 10.0) > 0.01:
            bad.append("fps")
        if not sha_ok:
            bad.append("sha")
        if p.stat().st_size != r.bytes:
            bad.append("bytes")
        rows.append(dict(file=r.file, pair_id=r.pair_id, codec=r.codec, kind=r.kind, split=r.split,
                         bytes=r.bytes, **{k: v for k, v in info.items() if k != "shape"}, bad=";".join(bad)))
        if r.pair_id in a.sheet:
            thumbs[(r.pair_id, r.codec, r.kind)] = (first, mid)
        if bad:
            issues.append({r.file: bad})
    q = pd.DataFrame(rows)
    q.to_csv(out / "probe.csv", index=False)
    per_pair = m.groupby("pair_id").agg(n=("file", "size"), splits=("split", "nunique"),
                                        groups=("origin_group", "nunique"))
    bad_pairs = per_pair[(per_pair.n != 4) | (per_pair.splits != 1) | (per_pair.groups != 1)]
    if len(bad_pairs):
        issues.append({"bad_pairs": bad_pairs.index.tolist()})
    # origin_group must not straddle splits
    g = m.groupby("origin_group").split.nunique()
    if (g > 1).any():
        issues.append({"group_split_leak": g[g > 1].index.tolist()})
    tracks = {}
    for codec, t in m.groupby("codec"):
        cap = t[t.kind == "capture"].set_index("pair_id").bytes
        org = t[t.kind == "original"].set_index("pair_id").bytes
        ratio = (cap / org).dropna()
        tracks[codec] = dict(
            n_capture=int(len(cap)), n_original=int(len(org)),
            fourcc=sorted(q[q.codec == codec].fourcc.unique().tolist()),
            bytes_median_capture=float(cap.median()), bytes_median_original=float(org.median()),
            capture_over_original_ratio_median=float(ratio.median()),
            ratio_range=[float(ratio.min()), float(ratio.max())],
            pair_win_capture_bigger=float((ratio > 1).mean()),
            size_auroc_capture_vs_original=auroc(cap.values, org.values),
            by_split={s: dict(size_auroc=auroc(t[(t.kind == "capture") & (t.split == s)].bytes,
                                               t[(t.kind == "original") & (t.split == s)].bytes))
                      for s in sorted(t.split.unique())})
    report = dict(dir=str(d), rows=int(len(m)), pairs=int(m.pair_id.nunique()),
                  sources=int(m.source_id.nunique()), split_pairs=m.drop_duplicates("pair_id").split.value_counts().to_dict(),
                  labels=m.label.value_counts().to_dict(), label_source=m.label_source.unique().tolist(),
                  decoded_frames=q.decoded.value_counts().to_dict(), total_bytes=int(m.bytes.sum()),
                  tracks=tracks, issues=issues, pass_=not issues)
    (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    for pid in a.sheet:
        tiles = []
        for codec in ("mp4v", "x264"):
            row = []
            for kind in ("original", "capture"):
                f0, f1 = thumbs.get((pid, codec, kind), (None, None))
                for f in (f0, f1):
                    f = cv2.resize(f, (320, 180)) if f is not None else np.zeros((180, 320, 3), np.uint8)
                    cv2.putText(f, f"{codec} {kind}", (5, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
                    row.append(f)
            tiles.append(np.hstack(row))
        cv2.imwrite(str(out / f"sheet_{pid}.jpg"), np.vstack(tiles))
    print(json.dumps({k: report[k] for k in ("rows", "pairs", "decoded_frames", "pass_")}, default=str))
    print(json.dumps(tracks, indent=1))
    print("issues", issues[:10])


if __name__ == "__main__":
    main()
