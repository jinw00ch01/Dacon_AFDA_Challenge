"""Measure Stage 2 checkpoints on the OFFICIAL Baseline/data/stage2 examples.

The Pro review (packet f62cad3f) showed the decisive gap: the S2 model is
trained on 30fps ~1,200-frame Nexar clips, but the official evaluation format is
10fps / 50-frame clips (Baseline/data/stage2, t_collision 30-41). The v001 S2
model has never been measured on that format. This harness closes that gap: it
decodes the five official 50-frame examples exactly as the submission would
(reusing scripts.preflight_e2e.prepare_stage2 + submission.inference.predict_stage2),
so the collision predictions are byte-identical to what the real submission emits.

Metric: collision MAE in SECONDS = mean(|pred_frame - gt_frame| / fps) over the
examples that have a labelled collision (t_collision >= 0). fps is read per video
via cv2 (falls back to 10.0). entry/evasion/side are all -1 in the official
examples, so only collision is scored. Constant-predictor baselines defined ONLY
from Nexar train priors (no leakage from the 5 examples) are reported alongside.

Usage:
  python scripts/eval_stage2_official.py \
      --model-root models/stage2 --model-root models/stage2_e002 \
      --out work/s2_official_eval/report.json
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from preflight_e2e import _force_rmtree, _load_submission, prepare_stage2  # noqa: E402

BASELINE_DATA = ROOT / "Baseline" / "data"
BASELINE_STAGE2 = BASELINE_DATA / "stage2"


def _read_labels():
    """stem (000001..) -> gt collision frame (int), only labelled (>=0)."""
    labels = {}
    with (BASELINE_STAGE2 / "labels.csv").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            stem = Path(row["path"]).stem
            tc = int(row["t_collision"])
            if tc >= 0:
                labels[stem] = tc
    return labels


def _fps_by_stem():
    fps = {}
    for mp4 in sorted((BASELINE_STAGE2 / "videos").glob("*.mp4")):
        cap = cv2.VideoCapture(str(mp4))
        v = cap.get(cv2.CAP_PROP_FPS)
        cap.release()
        fps[mp4.stem] = float(v) if v and v > 0 else 10.0
    return fps


def _mae_seconds(pred_frame_by_stem, labels, fps):
    errs = {}
    for stem, gt in labels.items():
        if stem not in pred_frame_by_stem:
            continue
        errs[stem] = abs(int(pred_frame_by_stem[stem]) - gt) / fps[stem]
    mae = (sum(errs.values()) / len(errs)) if errs else None
    return mae, errs


def _const_baselines(labels, fps, n_frames_by_stem):
    """Constant-frame predictors whose value is fixed OUTSIDE the 5 examples."""
    # Nexar-train priors carried from the review (const_baseline / recompute):
    #   abs frame 597 (train-median absolute collision frame), clipped per video.
    #   fraction 0.491 (train-median collision fraction) -> round(0.491 * (T-1)).
    #   fraction 0.5 (window centre) as a neutral position-free reference.
    out = {}
    for name, fn in (
        ("abs_frame_597_clipped", lambda t: min(597, t - 1)),
        ("fraction_0.491", lambda t: round(0.491 * (t - 1))),
        ("center_0.5", lambda t: round(0.5 * (t - 1))),
    ):
        preds = {stem: fn(n_frames_by_stem[stem]) for stem in labels}
        mae, _ = _mae_seconds(preds, labels, fps)
        out[name] = {"mae_s": mae, "pred_frame_example": preds}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-root", action="append", required=True,
                    help="dir with best.pt + resnet18-*.pth (repeatable)")
    ap.add_argument("--out", type=Path, default=ROOT / "work" / "s2_official_eval" / "report.json")
    ap.add_argument("--work", type=Path, default=ROOT / "work" / "s2_official_eval" / "prepared")
    ap.add_argument("--resnet-root", type=Path, default=ROOT / "models" / "stage2",
                    help="dir holding resnet18-f37072fd.pth, used when a model-root lacks it")
    args = ap.parse_args()

    resnet_name = "resnet18-f37072fd.pth"
    resnet_src = args.resnet_root / resnet_name

    inference = _load_submission()
    labels = _read_labels()
    fps = _fps_by_stem()

    work = args.work
    if work.exists():
        _force_rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    stage2_dir, expected = prepare_stage2(BASELINE_DATA, work)
    n_frames_by_stem = {stem: len(frames) for stem, frames in expected.items()}
    print(f"decoded {len(expected)} official S2 examples: "
          f"{ {k: n_frames_by_stem[k] for k in sorted(n_frames_by_stem)} }", flush=True)

    report = {
        "baseline_stage2_examples": {
            "n_labelled_collision": len(labels),
            "n_frames": n_frames_by_stem,
            "fps": fps,
            "t_collision_gt": labels,
        },
        "const_baselines": _const_baselines(labels, fps, n_frames_by_stem),
        "models": {},
        "caveat": "Only collision is labelled in the official examples (entry/evasion/side=-1). "
                  "5 examples only; a gate reference, not official score. Const baselines fixed "
                  "from Nexar train priors, no leakage.",
    }

    for root in args.model_root:
        root_path = Path(root)
        # predict_stage2 loads resnet18 from the same dir as best.pt; if this
        # checkpoint dir lacks it (e.g. models/stage2_e002), stage a temp dir
        # with both files so we never mutate the checkpoint dir.
        if not (root_path / resnet_name).exists():
            staged = work / f"model_{root_path.name}"
            staged.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root_path / "best.pt", staged / "best.pt")
            shutil.copy2(resnet_src, staged / resnet_name)
            root_path = staged
        preds_df = inference.predict_stage2(stage2_dir, root_path)
        pred_frame_by_stem = {str(r["ID"]): int(r["collision_frame"]) for _, r in preds_df.iterrows()}
        mae, errs = _mae_seconds(pred_frame_by_stem, labels, fps)
        report["models"][str(root)] = {
            "collision_mae_s": mae,
            "pred_frame": pred_frame_by_stem,
            "per_example_err_s": errs,
        }
        print(f"{root}: collision_mae_s={mae}  preds={pred_frame_by_stem}", flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
