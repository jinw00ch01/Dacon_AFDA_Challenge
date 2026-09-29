"""Pro review of Ultra S1 e001: recompute metrics from val_predictions.csv,
check integrity against the synthetic manifest, and test whether the synthetic
val is saturated by trivial 1-feature rules and whether those rules transfer to
the 10 real Baseline stage1 examples (5 ORIGINAL / 5 RERECORDED).

usage: s1_review.py --pred <val_predictions.csv> --manifest <manifest.csv>
                    --video-root <dir> --baseline <Baseline/data/stage1> --out <dir>
"""
import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
N_SAMPLE = 12


def f1_score(y_true, y_pred, average="macro"):
    t, p = np.asarray(y_true), np.asarray(y_pred)
    scores = []
    for c in np.unique(np.concatenate([t, p])):
        tp = ((t == c) & (p == c)).sum()
        fp = ((t != c) & (p == c)).sum()
        fn = ((t == c) & (p != c)).sum()
        scores.append(2 * tp / (2 * tp + fp + fn) if tp + fp + fn else 0.0)
    return float(np.mean(scores))


def video_features(path):
    cap = cv2.VideoCapture(str(path))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    idx = set(np.linspace(0, max(n - 1, 0), N_SAMPLE).astype(int).tolist())
    lap, hf, sat, blk, contrast, dark = [], [], [], [], [], []
    prev_small, motion = None, []
    i = 0
    while True:
        ok, bgr = cap.read()
        if not ok:
            break
        if i in idx:
            g = cv2.cvtColor(cv2.resize(bgr, (640, 360), interpolation=cv2.INTER_AREA),
                             cv2.COLOR_BGR2GRAY).astype(np.float32)
            lap.append(cv2.Laplacian(g, cv2.CV_32F).var())
            f = np.abs(np.fft.fftshift(np.fft.fft2(g - g.mean())))
            cy, cx = np.array(f.shape) // 2
            yy, xx = np.ogrid[:f.shape[0], :f.shape[1]]
            r = np.hypot((yy - cy) / cy, (xx - cx) / cx)
            hf.append(float(f[r > 0.5].sum() / (f.sum() + 1e-9)))
            hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
            sat.append(float(hsv[..., 1].mean()))
            d = np.abs(np.diff(g, axis=1))
            blk.append(float(d[:, 7::8].mean() / (d.mean() + 1e-9)))
            contrast.append(float(g.std()))
            dark.append(float(np.percentile(g, 1)))
            small = cv2.resize(g, (160, 90))
            if prev_small is not None:
                motion.append(float(np.abs(small - prev_small).mean()))
            prev_small = small
        i += 1
    cap.release()
    return {"decoded_frames": i, "meta_frames": n, "fps": fps, "width": w, "height": h,
            "bytes_per_px_frame": Path(path).stat().st_size / max(i * w * h, 1),
            "lap_var": float(np.mean(lap)), "hf_ratio": float(np.mean(hf)),
            "saturation": float(np.mean(sat)), "blockiness": float(np.mean(blk)),
            "contrast": float(np.mean(contrast)), "black_p1": float(np.mean(dark)),
            "sampled_motion": float(np.mean(motion)) if motion else None}


FEATS = ["bytes_per_px_frame", "lap_var", "hf_ratio", "saturation", "blockiness",
         "contrast", "black_p1"]


def stump(train, feat):
    """Best single threshold on train (either direction); returns (thr, sign, acc)."""
    x, y = train[feat].values, train["y"].values
    best = (None, 1, -1.0)
    for thr in np.unique(x):
        for sign in (1, -1):
            p = (sign * (x - thr) >= 0).astype(int)
            acc = (p == y).mean()
            if acc > best[2]:
                best = (float(thr), sign, float(acc))
    return best


def apply(df, feat, thr, sign):
    return (sign * (df[feat].values - thr) >= 0).astype(int)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--video-root", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pred-sha256")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rep = {}

    raw = Path(a.pred).read_bytes()
    rep["pred_sha256"] = hashlib.sha256(raw).hexdigest()
    rep["pred_sha256_match"] = (a.pred_sha256 == rep["pred_sha256"]) if a.pred_sha256 else None
    pred = pd.read_csv(a.pred)
    man = pd.read_csv(a.manifest)
    man["true"] = np.where(man["label"] == "original", "ORIGINAL", "RERECORDED")
    j = pred.merge(man[["file", "source_id", "origin_group", "split", "true"]],
                   on="file", how="left", suffixes=("", "_man"))
    val_man = man[man["split"] == "validation"]
    rep["integrity"] = {
        "pred_rows": len(pred), "dup_files": int(pred["file"].duplicated().sum()),
        "missing_in_manifest": int(j["split_man"].isna().sum()),
        "val_files_missing_from_pred": sorted(set(val_man["file"]) - set(pred["file"])),
        "split_mismatch": int((j["split"] != j["split_man"]).sum()),
        "source_mismatch": int((j["source_id"] != j["source_id_man"]).sum()),
        "label_mismatch": int((j["true"] != j["true_man"]).sum()),
        "pred_prob_threshold_mismatch": int(((j["prob_rerecorded"] >= 0.5)
                                             != (j["pred"] == "RERECORDED")).sum()),
        "origin_group_overlap_val_train": sorted(
            set(man.loc[man.split == "validation", "origin_group"])
            & set(man.loc[man.split == "train", "origin_group"])),
        "origin_group_overlap_test_train": sorted(
            set(man.loc[man.split == "test", "origin_group"])
            & set(man.loc[man.split == "train", "origin_group"])),
    }
    rep["recomputed"] = {
        "macro_f1": float(f1_score(pred["true"], pred["pred"], average="macro")),
        "acc": float((pred["true"] == pred["pred"]).mean()),
        "n": len(pred), "n_original": int((pred["true"] == "ORIGINAL").sum()),
        "prob_range_original": [float(pred.loc[pred.true == "ORIGINAL", "prob_rerecorded"].min()),
                                float(pred.loc[pred.true == "ORIGINAL", "prob_rerecorded"].max())],
        "prob_range_rerecorded": [float(pred.loc[pred.true == "RERECORDED", "prob_rerecorded"].min()),
                                  float(pred.loc[pred.true == "RERECORDED", "prob_rerecorded"].max())],
    }

    rows = []
    for _, r in man.iterrows():
        f = video_features(Path(a.video_root) / r["file"])
        rows.append({"file": r["file"], "set": "synthetic_" + r["split"],
                     "y": int(r["label"] != "original"), **f})
    base = Path(a.baseline)
    lab = pd.read_csv(base / "labels.csv")
    for _, r in lab.iterrows():
        f = video_features(base / r["path"])
        rows.append({"file": r["ID"], "set": "baseline_real",
                     "y": int(r["label"] == "RERECORDED"), **f})
    feat = pd.DataFrame(rows)
    feat.to_csv(out / "features.csv", index=False)

    train = feat[feat.set == "synthetic_train"]
    stumps = {}
    for fname in FEATS:
        thr, sign, tr_acc = stump(train, fname)
        res = {"thr": thr, "sign": sign, "train_acc": tr_acc}
        for s in ("synthetic_validation", "synthetic_test", "baseline_real"):
            d = feat[feat.set == s]
            p = apply(d, fname, thr, sign)
            res[s + "_acc"] = float((p == d["y"].values).mean())
            res[s + "_macro_f1"] = float(f1_score(d["y"], p, average="macro"))
        stumps[fname] = res
    rep["one_feature_stumps_fit_on_synthetic_train"] = stumps
    rep["feature_means"] = (feat.groupby(["set", "y"])[FEATS + ["fps", "width", "height",
                                                                 "decoded_frames"]]
                            .mean().round(4).reset_index().to_dict("records"))
    rep["baseline_real_per_video"] = feat[feat.set == "baseline_real"][
        ["file", "y", "fps", "width", "height", "decoded_frames"] + FEATS
    ].round(4).to_dict("records")
    (out / "report.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False),
                                     encoding="utf-8")
    print(json.dumps({k: rep[k] for k in ("pred_sha256_match", "integrity", "recomputed")},
                     indent=1))
    print(pd.DataFrame(stumps).T.round(3).to_string())


if __name__ == "__main__":
    main()
