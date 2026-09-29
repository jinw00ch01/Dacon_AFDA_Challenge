"""Review result 27809272 (S1 e003): rescore the format-matched S23 predictions for e001/e002/e003
with the independent s23_fm_review tool (val+test only), and check source leakage between the
S23 val/test sources and the synthetic (v1s/v1c) train splits.
usage: s1_e003_review.py --pkt <inbox packet dir> --out <dir>
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s23_fm_review import MANIFEST, review  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pkt", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    files = Path(a.pkt) / "files"
    man = pd.read_csv(MANIFEST)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    summary = {}
    for e in ("e001", "e002", "e003"):
        pred = pd.read_csv(files / f"s1_s23_fmt_predictions_{e}.csv")
        r = review(pred, man, exclude_train=True)
        # also score all rows (incl. train) for reference
        r_all = review(pred, man, exclude_train=False)
        (out / f"report_{e}.json").write_text(json.dumps({"val_test": r, "all": r_all}, indent=2, default=str),
                                              encoding="utf-8")
        s = {"integrity": r["integrity"]["pass"], "n_missing": r["integrity"]["n_missing"],
             "mismatch": {k: v for k, v in r["integrity"].items() if k.endswith("_mismatch")}}
        for c, tr in r["tracks"].items():
            for sp in ("validation", "test", "all"):
                if sp in tr:
                    b = tr[sp]
                    s[f"{c}.{sp}"] = {k: b[k] for k in ("n", "macro_f1", "auroc", "paired_win_rate",
                                                         "size_baseline_auroc", "pred_counts")}
            s[f"{c}.verdict"] = tr["verdict"]
        if "train" in r_all["tracks"].get("x264", {}):
            s["x264.train"] = {k: r_all["tracks"]["x264"]["train"][k] for k in ("n", "macro_f1", "auroc")}
        summary[e] = s
    # leakage: S23 source ids by split vs synthetic manifests' splits
    s23_src = man.groupby("split").source_id.unique()
    s23_og = man.groupby("split").origin_group.unique()
    leak = {"s23_sources_by_split": {k: sorted(v.tolist()) for k, v in s23_src.items()},
            "s23_train_valtest_origin_overlap": sorted(set(s23_og.get("train", [])) & (
                set(s23_og.get("validation", [])) | set(s23_og.get("test", []))))}
    synth = {}
    for mp in sorted((ROOT / "data" / "derived").glob("s1_synth*/manifest.csv")):
        m = pd.read_csv(mp)
        if "split" not in m.columns:
            continue
        rec = {"columns_used": []}
        for col, ref in (("origin_group", s23_og), ("source_id", s23_src)):
            if col in m.columns:
                rec["columns_used"].append(col)
                tr = set(m.loc[m.split == "train", col].astype(str))
                for sp in ("validation", "test"):
                    rec[f"{col}.{sp}_in_train"] = sorted(set(map(str, ref.get(sp, []))) & tr)
        rec["splits"] = m.split.value_counts().to_dict()
        synth[mp.parent.name] = rec
    leak["s23_valtest_sources_in_synth_train"] = synth
    summary["leakage"] = leak
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=1, default=str))


if __name__ == "__main__":
    main()
