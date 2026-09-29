"""Pro review of an Ultra S1 result scored on the S23 real re-capture release (s1-s23-real-v1-20260926).

Official S1 = Macro-F1(ORIGINAL/RERECORDED), via official_metrics.s1_score (Pro's own implementation).
  * integrity: every S23 capture of the split present once; no train capture; originals map to the
    split's sources; alignment CSV sha matches the frozen release (3764c0f7...).
  * two scorings (decision c85dd4a7 caveat): 'all_rows' as submitted (an original repeated per capture
    window counts each time), and 'unique_orig' where repeated originals of one source collapse to one
    row (mean prob, else majority label). Both are reported; neither hides the duplication.
  * per-condition recall (C1..C4), pairwise ranking p(RR) capture > original of same source, and the
    one-error swing (how much Macro-F1 moves if a single prediction flips).

usage: s23_eval_review.py --pred <csv> --out <dir> [--split validation|test|both] [--selftest]
pred csv: file column (file|sample_id|video|path|filename), label column (pred|pred_label|prediction),
optional prob column (prob_rerecorded|p_rerecorded|prob|score|p1). Original rows are recognised by
'ORIGINAL' in the file name, captures by the release file names (SRCxxx_Cy_takeNN.mp4).
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from official_metrics import s1_score  # noqa: E402
from s1_mixed_review import FILE_COLS, PRED_COLS, PROB_COLS, norm_label  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
ALIGN = ROOT / "work" / "agent" / "outbox" / "s23_align_b1_files" / "s23_pairs_aligned.csv"
ALIGN_SHA = "3764c0f712a7ab812edbdca397a5f35c1f63024cee729224b0dde62a4c594311"
SRC_RE = re.compile(r"(SRC\d{3})")
CAP_RE = re.compile(r"(SRC\d{3}_C\d_take\d{2})")


def pick(df, cols, required=True):
    for c in cols:
        if c in df.columns:
            return c
    if required:
        raise SystemExit(f"none of {cols} in {list(df.columns)}")
    return None


def load_pred(path):
    p = pd.read_csv(path)
    fc, lc, pc = pick(p, FILE_COLS), pick(p, PRED_COLS), pick(p, PROB_COLS, required=False)
    out = pd.DataFrame({"raw": p[fc].astype(str).map(lambda s: Path(s).name)})
    out["pred"] = p[lc].map(norm_label)
    out["prob"] = p[pc].astype(float) if pc else float("nan")
    out["is_orig"] = out["raw"].str.upper().str.contains("ORIGINAL")
    out["source_id"] = out["raw"].map(lambda s: (SRC_RE.search(s) or [None])[0] if SRC_RE.search(s) else None)
    out["cap_key"] = out["raw"].map(lambda s: CAP_RE.search(s).group(1) if CAP_RE.search(s) else None)
    out["label"] = out["is_orig"].map({True: "ORIGINAL", False: "RERECORDED"})
    return out


def score_block(df):
    if df.empty or df["label"].nunique() < 2:
        return None
    return float(s1_score(df["label"].tolist(), df["pred"].tolist())["S1"])


def one_error_swing(df):
    base = score_block(df)
    if base is None:
        return None
    flip = {"ORIGINAL": "RERECORDED", "RERECORDED": "ORIGINAL"}
    deltas = []
    for i in df.index:
        d = df.copy()
        d.loc[i, "pred"] = flip[d.loc[i, "pred"]]
        deltas.append(abs(score_block(d) - base))
    return {"max": max(deltas), "median": float(pd.Series(deltas).median())}


def collapse_orig(df):
    orig, caps = df[df.is_orig], df[~df.is_orig]
    rows = []
    for src, g in orig.groupby("source_id"):
        if g["prob"].notna().all():
            pr = float(g["prob"].mean())
            pred = "RERECORDED" if pr >= 0.5 else "ORIGINAL"
        else:
            pr = float("nan")
            vc = g["pred"].value_counts()
            pred = vc.index[0] if len(vc) == 1 or vc.iloc[0] != vc.iloc[1] else "ORIGINAL"
        rows.append({"raw": f"{src}_ORIGINAL", "pred": pred, "prob": pr, "is_orig": True,
                     "source_id": src, "cap_key": None, "label": "ORIGINAL", "n_dup": len(g)})
    return pd.concat([caps, pd.DataFrame(rows)], ignore_index=True)


def review_split(pred, align, split):
    a = align[align.split == split]
    exp_caps = set(a["file"].str.replace(".mp4", "", regex=False))
    exp_srcs = set(a["source_id"])
    caps, orig = pred[~pred.is_orig], pred[pred.is_orig]
    caps_s = caps[caps.cap_key.isin(exp_caps)]
    orig_s = orig[orig.source_id.isin(exp_srcs)]
    all_caps = set(align["file"].str.replace(".mp4", "", regex=False))
    train_caps = set(align.loc[align.split == "train", "file"].str.replace(".mp4", "", regex=False))
    integ = {
        "captures_expected": len(exp_caps),
        "captures_found": int(caps_s.cap_key.nunique()),
        "captures_missing": sorted(exp_caps - set(caps_s.cap_key)),
        "capture_duplicates": sorted(caps_s.cap_key[caps_s.cap_key.duplicated()].unique().tolist()),
        "train_captures_in_pred": sorted(set(caps.cap_key.dropna()) & train_caps),
        "unknown_capture_rows": sorted(caps.loc[~caps.cap_key.isin(all_caps), "raw"].tolist()),
        "orig_sources_expected": len(exp_srcs),
        "orig_sources_found": int(orig_s.source_id.nunique()),
        "orig_rows": int(len(orig_s)),
        "orig_sources_missing": sorted(exp_srcs - set(orig_s.source_id)),
    }
    integ["pass"] = (not integ["captures_missing"] and not integ["capture_duplicates"]
                     and not integ["train_captures_in_pred"] and not integ["orig_sources_missing"])
    block = pd.concat([caps_s, orig_s], ignore_index=True)
    cond = caps_s.assign(condition=caps_s.cap_key.str.extract(r"_(C\d)_")[0])
    per_cond = {c: {"n": len(g), "recall_rr": float((g.pred == "RERECORDED").mean())}
                for c, g in cond.groupby("condition")}
    rank = None
    if block["prob"].notna().all() and len(orig_s):
        om = orig_s.groupby("source_id")["prob"].mean()
        wins = [(r.prob > om[r.source_id]) + 0.5 * (r.prob == om[r.source_id])
                for r in caps_s.itertuples() if r.source_id in om.index]
        rank = {"n_pairs": len(wins), "acc": float(sum(wins) / len(wins)) if wins else None}
    uniq = collapse_orig(block)
    return {
        "integrity": integ,
        "n_all_rows": {"ORIGINAL": int((block.label == "ORIGINAL").sum()),
                       "RERECORDED": int((block.label == "RERECORDED").sum())},
        "s1_all_rows": score_block(block),
        "s1_unique_orig": score_block(uniq),
        "n_unique_orig": int(uniq.is_orig.sum()),
        "orig_pred_rr_rate": float((orig_s.pred == "RERECORDED").mean()) if len(orig_s) else None,
        "capture_pred_rr_rate": float((caps_s.pred == "RERECORDED").mean()) if len(caps_s) else None,
        "per_condition": per_cond,
        "pair_rank": rank,
        "one_error_swing": one_error_swing(block),
    }


def selftest(align, out):
    rows = []
    for split in ("validation", "test"):
        a = align[align.split == split]
        for r in a.itertuples():
            rows.append({"file": r.file, "pred": "RERECORDED", "prob": 0.9})
            rows.append({"file": f"{r.source_id}_ORIGINAL_for_{r.condition}.mp4", "pred": "ORIGINAL", "prob": 0.1})
    oracle = pd.DataFrame(rows)
    const = oracle.assign(pred="RERECORDED", prob=0.5)
    broken = oracle.iloc[2:].copy()
    broken = pd.concat([broken, broken.iloc[:1]])
    res = {}
    for name, df in (("oracle", oracle), ("const_rr", const), ("broken", broken)):
        p = out / f"selftest_{name}.csv"
        df.to_csv(p, index=False)
        res[name] = {s: review_split(load_pred(p), align, s) for s in ("validation", "test")}
    ok = (res["oracle"]["validation"]["s1_all_rows"] == 1.0 and res["oracle"]["test"]["s1_unique_orig"] == 1.0
          and res["oracle"]["validation"]["pair_rank"]["acc"] == 1.0
          and res["const_rr"]["validation"]["s1_all_rows"] <= 0.5
          and not res["broken"]["validation"]["integrity"]["pass"]
          and res["oracle"]["validation"]["integrity"]["pass"])
    return {"pass": bool(ok), "results": res}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred")
    ap.add_argument("--out", required=True)
    ap.add_argument("--split", default="both")
    ap.add_argument("--align", default=str(ALIGN))
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256(Path(a.align).read_bytes()).hexdigest()
    align = pd.read_csv(a.align)
    rep = {"align_csv": a.align, "align_sha256": sha, "align_sha_matches_release": sha == ALIGN_SHA,
           "release_id": "s1-s23-real-v1-20260926", "label_source": "real_capture (not synthetic)"}
    if a.selftest:
        rep["selftest"] = selftest(align, out)
    else:
        pred = load_pred(a.pred)
        splits = ["validation", "test"] if a.split == "both" else [a.split]
        rep["pred"] = a.pred
        rep["splits"] = {s: review_split(pred, align, s) for s in splits}
    (out / "report.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps(rep.get("selftest", {}).get("pass", rep.get("splits")), default=str)[:3000])


if __name__ == "__main__":
    main()
