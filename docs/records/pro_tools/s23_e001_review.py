"""Pro review of Ultra result 8a06d93a (S23 codec-aligned S1 eval, model e001).

Ultra's csv has one ORIGINAL row per capture window (original named by the capture file + kind=original).
Adapter renames originals to <SRC>_ORIGINAL_for_<cap>.mp4 so s23_eval_review.review_split can check
integrity/all_rows/unique_orig; then adds separability diagnostics Ultra asked for:
  * AUROC of prob_rerecorded (capture=positive) per split, Mann-Whitney with ties = 0.5
  * paired win rate: capture prob > its own aligned original window prob, and mean paired diff
  * train-fitted threshold (max Macro-F1 on S23 train) applied to validation/test (diagnostic only)
usage: s23_e001_review.py --pred <csv> --out <dir>
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from official_metrics import s1_score  # noqa: E402
from s23_eval_review import ALIGN, ALIGN_SHA, load_pred, review_split  # noqa: E402


def auroc(pos, neg):
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    if not len(pos) or not len(neg):
        return None
    gt = (pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()
    return float(gt / (len(pos) * len(neg)))


def f1_at(df, thr):
    pred = np.where(df.prob_rerecorded >= thr, "RERECORDED", "ORIGINAL")
    return float(s1_score(df["true"].tolist(), pred.tolist())["S1"])


def best_thr(df):
    ps = np.sort(df.prob_rerecorded.unique())
    cands = np.concatenate([[ps[0] - 1e-6], (ps[:-1] + ps[1:]) / 2, [ps[-1] + 1e-6]])
    scores = [(f1_at(df, t), t) for t in cands]
    return max(scores)


def diag(df):
    cap, org = df[df.kind == "capture"], df[df.kind == "original"]
    m = cap.merge(org, on=["source_id", "condition", "split", "file"], suffixes=("_cap", "_org"))
    d = m.prob_rerecorded_cap - m.prob_rerecorded_org
    return {
        "n_capture": len(cap), "n_original": len(org),
        "macro_f1_as_submitted": float(s1_score(df["true"].tolist(), df["pred"].tolist())["S1"]),
        "accuracy": float((df["true"] == df["pred"]).mean()),
        "auroc_capture_vs_original": auroc(cap.prob_rerecorded, org.prob_rerecorded),
        "paired_n": len(m),
        "paired_win_rate": float(((d > 0) + 0.5 * (d == 0)).mean()) if len(m) else None,
        "paired_diff_mean": float(d.mean()) if len(m) else None,
        "paired_diff_median": float(d.median()) if len(m) else None,
        "prob_capture": {"mean": float(cap.prob_rerecorded.mean()), "min": float(cap.prob_rerecorded.min()),
                         "max": float(cap.prob_rerecorded.max())},
        "prob_original": {"mean": float(org.prob_rerecorded.mean()), "min": float(org.prob_rerecorded.min()),
                          "max": float(org.prob_rerecorded.max())},
        "per_condition": {c: {"n_pairs": int(len(g)),
                              "auroc": auroc(g.prob_rerecorded_cap, g.prob_rerecorded_org),
                              "paired_win_rate": float((g.prob_rerecorded_cap > g.prob_rerecorded_org).mean())}
                          for c, g in m.groupby("condition")},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    raw = pd.read_csv(a.pred)
    align = pd.read_csv(ALIGN)
    sha = hashlib.sha256(Path(ALIGN).read_bytes()).hexdigest()

    # consistency with the frozen alignment table
    amap = align.set_index("file")
    chk = {
        "rows": len(raw),
        "dup_file_kind": int(raw.duplicated(["file", "kind"]).sum()),
        "files_not_in_release": sorted(set(raw.file) - set(align.file)),
        "release_files_missing": sorted(set(align.file) - set(raw.file)),
        "split_mismatch": int((raw.split != raw.file.map(amap.split)).sum()),
        "source_mismatch": int((raw.source_id != raw.file.map(amap.source_id)).sum()),
        "true_label_mismatch": int((raw["true"] != raw.kind.map({"capture": "RERECORDED",
                                                                  "original": "ORIGINAL"})).sum()),
        "pred_vs_prob_at_0.5_mismatch": int((raw.pred != np.where(raw.prob_rerecorded >= 0.5, "RERECORDED",
                                                                   "ORIGINAL")).sum()),
        "correct_col_mismatch": int((raw.correct != (raw["true"] == raw.pred).astype(int)).sum()),
    }
    chk["pass"] = (chk["dup_file_kind"] == 0 and not chk["files_not_in_release"] and not chk["release_files_missing"]
                   and chk["split_mismatch"] == 0 and chk["source_mismatch"] == 0 and chk["true_label_mismatch"] == 0)

    # pass through the prepared S23 review tool (renamed originals)
    ad = raw.copy()
    ad["file"] = np.where(ad.kind == "original",
                          ad.source_id + "_ORIGINAL_for_" + ad.file.str.replace(".mp4", "", regex=False) + ".mp4",
                          ad.file)
    ad = ad.rename(columns={"prob_rerecorded": "prob"})[["file", "pred", "prob"]]
    ad_path = out / "pred_adapted.csv"
    ad.to_csv(ad_path, index=False)
    pred = load_pred(ad_path)
    tool = {s: review_split(pred, align, s) for s in ("validation", "test")}

    per_split = {s: diag(raw[raw.split == s]) for s in ("train", "validation", "test")}
    per_split["overall"] = diag(raw)
    f_tr, t_tr = best_thr(raw[raw.split == "train"])
    thr = {"note": "diagnostic only: threshold fitted on S23 train split, applied unchanged to val/test",
           "threshold": float(t_tr), "train_macro_f1": f_tr,
           "validation_macro_f1": f1_at(raw[raw.split == "validation"], t_tr),
           "test_macro_f1": f1_at(raw[raw.split == "test"], t_tr)}
    rep = {"packet": "8a06d93a698b488ea0d714994a6112d4", "release_id": "s1-s23-real-v1-20260926",
           "align_sha256": sha, "align_sha_matches_release": sha == ALIGN_SHA,
           "label_source": "real_capture (not synthetic)", "consistency": chk,
           "s23_eval_review": tool, "diagnostics": per_split, "train_threshold_transfer": thr}
    (out / "report.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    brief = {"consistency_pass": chk["pass"],
             **{s: {k: per_split[s][k] for k in ("macro_f1_as_submitted", "auroc_capture_vs_original",
                                                 "paired_win_rate", "paired_diff_mean")} for s in per_split},
             "tool_val": {k: tool["validation"][k] for k in ("s1_all_rows", "s1_unique_orig")},
             "tool_test": {k: tool["test"][k] for k in ("s1_all_rows", "s1_unique_orig")},
             "tool_integrity": [tool[s]["integrity"]["pass"] for s in tool], "thr": thr}
    print(json.dumps(brief, indent=1, default=str))


if __name__ == "__main__":
    main()
