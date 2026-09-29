"""Pro review of an Ultra S1 result trained on v1 (optical) + v1c (digital) synthetic recapture.

Decision 9/10 checks, all with the official S1 = Macro-F1(ORIGINAL/RERECORDED):
  * integrity: join predictions to the three manifests by file name; missing / duplicate / unknown rows,
    rows outside the requested split, origin_group leak between train and the evaluated split.
  * per-family scores: v1, v1c (r2 + codec-matched release), min(v1, v1c) (decision 9 selection rule).
  * codec shortcut: v1c scored inside each codec separately (h264-only files, mpeg4-only files). A pure
    codec classifier is constant there (S1 0.333; a coin flip ~0.5); gate fails at <= 0.6.
    Over all v1c the codec-only reference scores 0.5 because half the pairs are codec-matched. Also P(pred=RR | codec) per true label, and a codec-only reference.
  * pairwise ranking (needs a probability column): share of pairs where p(RR) of the recapture > original,
    split into codec-matched and codec-mismatched pairs (threshold-free).

usage: s1_mixed_review.py --pred <csv> --out <dir> [--split validation] [--selftest]
pred csv: a file-name column (file|sample_id|video|path|filename) and a label column
(pred|pred_label|prediction|label_pred, ORIGINAL/RERECORDED or 0/1), optional prob column
(prob_rerecorded|p_rerecorded|prob|score|p1).
"""
import argparse
import json
import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from official_metrics import s1_score  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "data" / "derived"
MANIFESTS = {
    "v1": D / "s1_synthetic_v1" / "manifest.csv",
    "v1c_r2": D / "s1_synthetic_v1c_r2" / "manifest.csv",
    "v1c_cm": D / "s1_synthetic_v1c_cm" / "manifest.csv",
}
PAIRS_CM = D / "s1_synthetic_v1c_cm" / "pairs.csv"
FILE_COLS = ["file", "sample_id", "video", "path", "filename", "video_name"]
PRED_COLS = ["pred", "pred_label", "prediction", "label_pred", "pred_class"]
PROB_COLS = ["prob_rerecorded", "p_rerecorded", "prob", "score", "p1", "prob_rr"]


def norm_label(v):
    s = str(v).strip().upper()
    if s in ("1", "RERECORDED", "RECAPTURE_SYNTHETIC", "RECAPTURE", "RR"):
        return "RERECORDED"
    if s in ("0", "ORIGINAL", "ORIG"):
        return "ORIGINAL"
    raise ValueError(f"unknown label {v!r}")


def load_gt():
    frames = []
    for fam, p in MANIFESTS.items():
        m = pd.read_csv(p)
        if "codec" not in m.columns:
            m["codec"] = "mjpeg_or_h264_v1"  # v1: single final encode for both classes
        m["family"] = "v1" if fam == "v1" else "v1c"
        m["manifest"] = fam
        frames.append(m[["file", "source_id", "origin_group", "split", "label", "variant", "codec",
                         "family", "manifest"]])
    gt = pd.concat(frames, ignore_index=True)
    # r2 and cm share ORIG/DIG0 file names only if identical; keep first and flag conflicts
    dup = gt[gt.duplicated("file", keep=False)]
    conflicts = dup.groupby("file")["label"].nunique()
    gt = gt.drop_duplicates("file", keep="first").copy()
    gt["y"] = gt["label"].map(norm_label)
    return gt, int((conflicts > 1).sum())


def pick(cols, names):
    low = {c.lower(): c for c in cols}
    for n in names:
        if n in low:
            return low[n]
    return None


def f1(df):
    if len(df) == 0:
        return None
    return s1_score(df["y"].tolist(), df["pred"].tolist())["S1"]


def binom_p_two_sided(k, n):
    """exact two-sided binomial test vs p=0.5"""
    if n == 0:
        return None
    pk = [math.comb(n, i) / 2 ** n for i in range(n + 1)]
    return float(min(1.0, sum(q for q in pk if q <= pk[k] + 1e-15)))


def review(pred_df, split, gt, n_conflicts):
    fcol, pcol = pick(pred_df.columns, FILE_COLS), pick(pred_df.columns, PRED_COLS)
    qcol = pick(pred_df.columns, PROB_COLS)
    if fcol is None or pcol is None:
        raise SystemExit(f"cannot find file/pred columns in {list(pred_df.columns)}")
    p = pd.DataFrame({"file": pred_df[fcol].map(lambda s: Path(str(s)).name),
                      "pred": pred_df[pcol].map(norm_label)})
    if qcol:
        p["prob"] = pd.to_numeric(pred_df[qcol], errors="coerce")
    integ = {"n_pred_rows": int(len(p)), "file_col": fcol, "pred_col": pcol, "prob_col": qcol,
             "duplicate_files": int(p["file"].duplicated().sum()),
             "manifest_label_conflicts": n_conflicts}
    j = p.drop_duplicates("file").merge(gt, on="file", how="left", indicator=True)
    integ["unknown_files"] = sorted(j.loc[j["_merge"] == "left_only", "file"].tolist())[:20]
    integ["n_unknown"] = int((j["_merge"] == "left_only").sum())
    j = j[j["_merge"] == "both"].drop(columns="_merge")
    integ["rows_outside_split"] = int((j["split"] != split).sum())
    want = gt[gt["split"] == split]
    integ["missing_from_split"] = int(len(set(want["file"]) - set(j["file"])))
    tr_groups = set(gt.loc[gt["split"] == "train", "origin_group"])
    integ["origin_group_leak"] = sorted(set(want["origin_group"]) & tr_groups)
    j = j[j["split"] == split]
    integ["pass"] = (integ["duplicate_files"] == 0 and integ["n_unknown"] == 0
                     and integ["rows_outside_split"] == 0 and integ["missing_from_split"] == 0
                     and not integ["origin_group_leak"] and n_conflicts == 0)

    fam = {}
    for name, sub in [("all", j), ("v1", j[j.family == "v1"]), ("v1c", j[j.family == "v1c"])]:
        fam[name] = {"S1": f1(sub), "n": int(len(sub)),
                     "n_rr": int((sub.y == "RERECORDED").sum())}
    v1s, v1cs = fam["v1"]["S1"], fam["v1c"]["S1"]
    fam["min_v1_v1c"] = None if v1s is None or v1cs is None else min(v1s, v1cs)

    c = j[j.family == "v1c"]
    codec = {}
    for cd, sub in c.groupby("codec"):
        k = int((sub.y == sub.pred).sum())
        codec[cd] = {"S1": f1(sub), "n": int(len(sub)), "acc": k / len(sub),
                     "binom_p_vs_chance": binom_p_two_sided(k, len(sub)),
                     "p_pred_rr_given_gt": {g: float((s.pred == "RERECORDED").mean())
                                            for g, s in sub.groupby("y")}}
    within = [v["S1"] for v in codec.values() if v["S1"] is not None]
    codec["min_within_codec_S1"] = min(within) if within else None
    ref = c.assign(pred=c["codec"].map(lambda x: "RERECORDED" if x == "h264" else "ORIGINAL"))
    codec["reference_codec_only_classifier_S1_on_v1c"] = f1(ref)
    codec["chance_gate"] = ("FAIL: within-codec S1 <= 0.6 (codec shortcut suspected)"
                            if within and min(within) <= 0.6 else "ok" if within else None)

    pairs = None
    if qcol and PAIRS_CM.exists():
        pr = pd.read_csv(PAIRS_CM)
        pr = pr[pr["split"] == split]
        pm = dict(zip(j["file"], j["prob"]))
        pr = pr.assign(po=pr.original_file.map(pm), pr_=pr.recapture_file.map(pm)).dropna(subset=["po", "pr_"])
        pairs = {}
        for cm, sub in pr.groupby("codec_matched"):
            wins = float(((sub.pr_ > sub.po) + 0.5 * (sub.pr_ == sub.po)).mean())
            pairs["codec_matched" if cm == 1 else "codec_mismatched"] = {"n_pairs": int(len(sub)),
                                                                          "rank_acc": wins}
    per_source = (j.assign(ok=(j.y == j.pred)).groupby(["family", "source_id"])["ok"].mean()
                  .round(3).reset_index().to_dict("records"))
    return {"split": split, "integrity": integ, "family": fam, "codec": codec,
            "pairwise": pairs, "per_source_acc": per_source,
            "notes": ["S1 = official Macro-F1 (work/pro_tools/official_metrics.py, independent of src/afda/metrics.py)",
                      "all scores are synthetic (decision 3); Baseline 10 examples are reference only (decision 10)"]}


def selftest(gt, split):
    v = gt[gt.split == split]
    out = {}
    oracle = pd.DataFrame({"file": v.file, "pred": v.y, "prob": (v.y == "RERECORDED").astype(float)})
    codec_only = pd.DataFrame({"file": v.file,
                               "pred": [("RERECORDED" if (f == "v1c" and cd == "h264") or (f == "v1" and g == "RERECORDED")
                                         else "ORIGINAL") for f, cd, g in zip(v.family, v.codec, v.y)]})
    codec_only["prob"] = (codec_only.pred == "RERECORDED").astype(float)
    for name, df in [("oracle", oracle), ("v1_perfect_v1c_codec_only", codec_only)]:
        r = review(df, split, gt, 0)
        out[name] = {"integrity_pass": r["integrity"]["pass"], "family": r["family"],
                     "min_within_codec_S1": r["codec"]["min_within_codec_S1"],
                     "chance_gate": r["codec"]["chance_gate"], "pairwise": r["pairwise"]}
    broken = pd.concat([oracle.iloc[1:], oracle.iloc[:1], oracle.iloc[:1]])
    out["broken_missing_dup"] = {"integrity_pass": review(broken.iloc[1:], split, gt, 0)["integrity"]["pass"]}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred")
    ap.add_argument("--out", required=True)
    ap.add_argument("--split", default="validation")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    gt, nc = load_gt()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rep = selftest(gt, a.split) if a.selftest else review(pd.read_csv(a.pred), a.split, gt, nc)
    rep_counts = gt.groupby(["family", "split", "codec", "y"]).size().reset_index(name="n").to_dict("records")
    if a.selftest:
        rep = {"selftest": rep, "gt_counts": rep_counts}
    (out / "report.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(rep, indent=1, ensure_ascii=False)[:6000])


if __name__ == "__main__":
    main()
