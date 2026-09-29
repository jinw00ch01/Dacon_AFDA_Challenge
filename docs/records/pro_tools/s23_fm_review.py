"""Review an S1 prediction CSV on the format-matched S23 pairs (data/derived/s1_s23_format_matched_v1).
Joins on file basename to the manifest; per track (mp4v/x264) x split: official S1 Macro-F1, AUROC,
paired win rate, and the file-size baseline AUROC plus prob~bytes rank correlation (compression shortcut check).
usage: s23_fm_review.py --pred <csv> --out <dir> [--exclude-train] | --selftest <dir>
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from official_metrics import s1_score  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data" / "derived" / "s1_s23_format_matched_v1" / "manifest.csv"
PROB_COLS = ("prob_rerecorded", "prob_rr", "p_rerecorded", "prob")
FILE_COLS = ("file", "video", "path", "filename")


def auroc(pos, neg):
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    if len(pos) == 0 or len(neg) == 0:
        return None
    return float((pos[:, None] > neg[None, :]).mean() + 0.5 * (pos[:, None] == neg[None, :]).mean())


def spearman(x, y):
    if len(x) < 3:
        return None
    rx, ry = pd.Series(x).rank().values, pd.Series(y).rank().values
    if rx.std() == 0 or ry.std() == 0:
        return None
    c = np.corrcoef(rx, ry)[0, 1]
    return None if np.isnan(c) else float(c)


def block(t):
    cap, org = t[t.label == "RERECORDED"], t[t.label == "ORIGINAL"]
    pw = cap.set_index("pair_id").prob.sub(org.set_index("pair_id").prob).dropna()
    return dict(
        n=int(len(t)), n_pairs=int(t.pair_id.nunique()),
        macro_f1=round(s1_score(t.label.tolist(), t.pred.tolist())["S1"], 4),
        accuracy=round(float((t.label == t.pred).mean()), 4),
        pred_counts=t.pred.value_counts().to_dict(),
        auroc=auroc(cap.prob, org.prob),
        paired_win_rate=None if pw.empty else float((pw > 0).mean() + 0.5 * (pw == 0).mean()),
        size_baseline_auroc=auroc(cap.bytes, org.bytes),
        prob_bytes_spearman_within_class={
            "RERECORDED": spearman(cap.prob, cap.bytes), "ORIGINAL": spearman(org.prob, org.bytes)})


def review(pred_df, man, exclude_train=False):
    fcol = next((c for c in FILE_COLS if c in pred_df.columns), None)
    pcol = next((c for c in PROB_COLS if c in pred_df.columns), None)
    if fcol is None or pcol is None:
        raise SystemExit(f"need one of {FILE_COLS} and {PROB_COLS}; got {list(pred_df.columns)}")
    p = pred_df.copy()
    p["file"] = p[fcol].astype(str).map(lambda s: Path(s.replace("\\", "/")).name)
    p["prob"] = p[pcol].astype(float)
    if "pred" not in p.columns:
        p["pred"] = np.where(p.prob >= 0.5, "RERECORDED", "ORIGINAL")
    integ = {"dup_rows": int(p.file.duplicated().sum()),
             "unknown_files": sorted(set(p.file) - set(man.file))[:10]}
    m = man if not exclude_train else man[man.split != "train"]
    integ["missing_files"] = sorted(set(m.file) - set(p.file))[:10]
    integ["n_missing"] = int(len(set(m.file) - set(p.file)))
    extra = p.drop(columns=[c for c in ("label", "split", "codec", "pair_id", "bytes") if c in p.columns])
    d = m.merge(extra[["file", "prob", "pred"]].drop_duplicates("file"), on="file", how="inner")
    for c in ("label", "split", "codec"):
        if c in pred_df.columns:
            chk = p.set_index("file")[c].reindex(d.file).astype(str).str.lower().values
            integ[f"{c}_mismatch"] = int((chk != d[c].astype(str).str.lower().values).sum())
    if exclude_train and "train" in set(man.loc[man.file.isin(p.file), "split"]):
        integ["note"] = "train rows present in pred; excluded from scoring"
    integ["pass"] = (integ["dup_rows"] == 0 and not integ["unknown_files"] and integ["n_missing"] == 0
                     and all(v == 0 for k, v in integ.items() if k.endswith("_mismatch")))
    out = {"integrity": integ, "tracks": {}}
    for codec, t in d.groupby("codec"):
        tr = {"all": block(t)}
        for s, ts in t.groupby("split"):
            tr[s] = block(ts)
        if not exclude_train and (t.split != "train").any():
            tr["val+test"] = block(t[t.split != "train"])
        out["tracks"][codec] = tr
    out["tracks_pooled"] = block(d)
    for codec, tr in out["tracks"].items():
        a, sb = tr["all"]["auroc"], tr["all"]["size_baseline_auroc"]
        tr["verdict"] = ("no_signal" if a is None or a < 0.6 else
                         "at_or_below_size_baseline" if sb is not None and a <= sb + 0.05 else "signal_beyond_size")
    return out


def selftest(outdir):
    man = pd.read_csv(MANIFEST)
    rng = np.random.default_rng(0)
    y = (man.label == "RERECORDED").astype(float).values
    cases = {
        "oracle": y * 0.9 + 0.05,
        "all_rr": np.full(len(man), 0.98),
        "size_proxy": man.bytes.rank(pct=True).values,
        "random": rng.random(len(man)),
    }
    res = {}
    for k, pr in cases.items():
        r = review(pd.DataFrame({"file": man.file, "prob_rerecorded": pr, "label": man.label}), man)
        res[k] = {c: {"f1": v["all"]["macro_f1"], "auroc": v["all"]["auroc"], "verdict": v["verdict"]}
                  for c, v in r["tracks"].items()} | {"integrity": r["integrity"]["pass"]}
    broken = pd.DataFrame({"file": list(man.file[:-3]) + [man.file[0]], "prob": 0.5})
    res["broken_integrity"] = review(broken, man)["integrity"]["pass"]
    ok = (res["oracle"]["x264"]["f1"] == 1.0 and res["all_rr"]["x264"]["f1"] == 0.3333
          and res["size_proxy"]["mp4v"]["verdict"] == "at_or_below_size_baseline" and res["broken_integrity"] is False)
    res["pass"] = bool(ok)
    Path(outdir).mkdir(parents=True, exist_ok=True)
    (Path(outdir) / "selftest.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred")
    ap.add_argument("--out")
    ap.add_argument("--exclude-train", action="store_true")
    ap.add_argument("--selftest")
    a = ap.parse_args()
    if a.selftest:
        return selftest(a.selftest)
    r = review(pd.read_csv(a.pred), pd.read_csv(MANIFEST), a.exclude_train)
    Path(a.out).mkdir(parents=True, exist_ok=True)
    (Path(a.out) / "report.json").write_text(json.dumps(r, indent=2, default=str), encoding="utf-8")
    print(json.dumps(r, indent=1, default=str))


if __name__ == "__main__":
    main()
