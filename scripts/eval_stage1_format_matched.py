"""Stage 1 evaluation on the format-matched S23 clips (Pro qa 3ab82c / review d999b155).

Unlike ``eval_stage1_s23.py`` (which crops real-time windows out of the raw release
pairs, leaving the HEVC-vs-h264 codec difference in place), this harness scores the
PRE-CUT ``s1_s23_format_matched_v1`` clips where BOTH members of every pair share the
same codec/resolution/fps/length inside a track (mp4v track: FMP4/FMP4; x264 track:
libx264/libx264). Any remaining separability therefore cannot come from a codec or
geometry shortcut. Per decision 8111e544 the x264 track is the primary criterion
(its residual file-size cue is weaker: val size-AUROC 0.5 vs mp4v 0.672).

Each clip is already exactly the aligned 5 s window at 50 frames / 10 fps. We sample
the model's own ``frames`` count evenly across the clip and push the pixels through
submission.inference._decode_stage1_clip so they are byte-identical to submission time.

Verdict (review d999b155 / qa 3ab82c): per-track overall AUROC >= 0.7 => the original
proxy 0.333 was a format-drift artefact (add ORIGINAL resolution/fps/codec augmentation
to S1 training); AUROC ~0.5 => e001 does not see a real re-recording cue (v1c mixing +
full-resolution patch input needed). A model AUROC near the track's size-cue AUROC is
NOT proof of discriminability. Proxy caveat: val/test are 8 pairs per track.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
from torch import nn
from torchvision.models.video import mvit_v2_s

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "submission"))

from submission.inference import _decode_stage1_clip  # noqa: E402
from src.afda import metrics as M  # noqa: E402


def _frame_ids(n_frames: int, total: int):
    """n_frames evenly spaced indices across the whole clip [0, total)."""
    ids = np.round((np.arange(n_frames) + 0.5) / n_frames * total).astype(int)
    return np.clip(ids, 0, total - 1)


def _total_frames(path: Path) -> int:
    cap = cv2.VideoCapture(str(path))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    return max(1, total)


def _auroc(pos: np.ndarray, neg: np.ndarray) -> float:
    """AUROC of P(capture prob > original prob) via rank statistic (ties=0.5)."""
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    wins = 0.0
    for p in pos:
        wins += float((neg < p).sum()) + 0.5 * float((neg == p).sum())
    return wins / (len(pos) * len(neg))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", default="models/stage1")
    ap.add_argument("--tag", default="e001")
    ap.add_argument(
        "--clips-dir",
        default="data/derived/experiment_packets/inbox/3ab82c653e484e59963e3f91f58f8aeb/files",
        help="dir holding the 192 mp4 clips and manifest.csv",
    )
    ap.add_argument("--manifest", default=None, help="defaults to <clips-dir>/manifest.csv")
    ap.add_argument("--out-dir", default="work/agent/outbox/s1_s23_fmt_eval")
    args = ap.parse_args()

    clips_dir = ROOT / args.clips_dir
    manifest_path = Path(args.manifest) if args.manifest else clips_dir / "manifest.csv"
    df = pd.read_csv(manifest_path, dtype={"source_id": str})

    ckpt = torch.load(Path(args.model_dir) / "best.pt", map_location="cpu", weights_only=False)
    size, frames = int(ckpt["size"]), int(ckpt["frames"])
    model = mvit_v2_s(weights=None)
    model.head[1] = nn.Linear(model.head[1].in_features, 2)
    model.load_state_dict(ckpt["model"])
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device).eval()

    rows = []
    for _, r in df.iterrows():
        path = clips_dir / r["file"]
        total = _total_frames(path)
        ids = _frame_ids(frames, total)
        clip = _decode_stage1_clip(path, size, ids)  # (3, frames, size, size)
        batch = clip.unsqueeze(0).to(device)
        with torch.inference_mode():
            if device.type == "cuda":
                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    p = torch.softmax(model(batch), 1)[0, 1]
            else:
                p = torch.softmax(model(batch), 1)[0, 1]
        p = float(p.float().cpu())
        pred = "RERECORDED" if p >= 0.5 else "ORIGINAL"
        rows.append({
            "file": r["file"], "pair_id": r["pair_id"], "source_id": r["source_id"],
            "split": r["split"], "codec": r["codec"], "kind": r["kind"],
            "label": r["label"], "prob_rerecorded": round(p, 6), "pred": pred,
            "correct": int(pred == r["label"]),
        })

    out = pd.DataFrame(rows)
    out_dir = ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    pred_csv = out_dir / f"s1_s23_fmt_predictions_{args.tag}.csv"
    out.to_csv(pred_csv, index=False)

    def _metrics(sub: pd.DataFrame) -> dict:
        yt, yp = sub["label"].tolist(), sub["pred"].tolist()
        cap = sub[sub.kind == "capture"].sort_values("pair_id")
        org = sub[sub.kind == "original"].sort_values("pair_id")
        merged = cap.merge(org, on="pair_id", suffixes=("_cap", "_org"))
        win = (merged["prob_rerecorded_cap"] > merged["prob_rerecorded_org"]).mean() \
            if len(merged) else float("nan")
        return {
            "n_clips": int(len(sub)), "n_pairs": int(len(sub) // 2),
            "macro_f1": round(M.stage1_score(yt, yp), 6),
            "accuracy": round(float(sub["correct"].mean()), 6),
            "orig_recall": round(float(sub[sub.label == "ORIGINAL"]["correct"].mean()), 6),
            "rerec_recall": round(float(sub[sub.label == "RERECORDED"]["correct"].mean()), 6),
            "auroc_capture_vs_original": round(_auroc(
                cap["prob_rerecorded"].to_numpy(), org["prob_rerecorded"].to_numpy()), 6),
            "paired_win_rate": round(float(win), 6),
        }

    result = {"model_dir": args.model_dir, "tag": args.tag, "size": size,
              "frames": frames, "manifest": str(manifest_path), "by_track": {}}
    for codec in ["x264", "mp4v"]:  # x264 first: primary criterion (decision 8111e544)
        tk = out[out.codec == codec]
        if not len(tk):
            continue
        entry = {"overall": _metrics(tk), "by_split": {}}
        for sp in ["validation", "test", "train"]:
            sub = tk[tk.split == sp]
            if len(sub):
                entry["by_split"][sp] = _metrics(sub)
        # val+test only (train may be used for future S1 training; decision 8111e544)
        vt = tk[tk.split.isin(["validation", "test"])]
        if len(vt):
            entry["val_test"] = _metrics(vt)
        result["by_track"][codec] = entry

    metrics_json = out_dir / f"s1_s23_fmt_metrics_{args.tag}.json"
    metrics_json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"\nwrote {pred_csv}\nwrote {metrics_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
