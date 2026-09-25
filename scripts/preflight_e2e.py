"""End-to-end safety-net preflight on the supplied Baseline examples.

Milestone A gate: prove submission/inference.py runs offline on GPU over the
Baseline example videos and emits contract-valid Stage 1/2/3 CSVs. It does NOT
claim any score — the Baseline examples are a format/plumbing check, not a
validation benchmark (harness/contracts.py docstring).

The Baseline layout differs from the evaluation-server layout the submission
expects, so this driver first materializes the eval layout under an output dir:
  Stage 1: <out>/stage1/videos/<uniqueID>.mp4   (original/ + rerecorded/ merged)
  Stage 2: <out>/stage2/images/<ID>/<frame>.jpg (each video decoded to frames)
  Stage 3: <out>/stage3/videos/<ID>.mp4         (copied as-is)
then calls predict_stage{1,2,3}, writes predictions + expected manifests, and
validates each CSV with harness.contracts.validate so the job fails loudly on
any contract break.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.contracts import validate  # noqa: E402


def _force_rmtree(path: Path) -> None:
    """rmtree that tolerates read-only files on Windows.

    prepare_stage1/3 copy2 the Baseline mp4s, which are read-only; copy2
    preserves the read-only bit, so a plain rmtree on the next run raises
    PermissionError [WinError 5]. Clear the write bit on every entry first.
    """
    if not path.exists():
        return
    for child in path.rglob("*"):
        try:
            os.chmod(child, stat.S_IWRITE)
        except OSError:
            pass
    shutil.rmtree(path)


def _load_submission():
    # Import by a stable module name on sys.path (not importlib-from-path) so
    # DataLoader workers spawned on Windows can re-import the Dataset classes;
    # multiprocessing propagates sys.path to children. On the Linux eval server
    # the module is imported the same way.
    sub_dir = str(ROOT / "submission")
    if sub_dir not in sys.path:
        sys.path.insert(0, sub_dir)
    import inference  # noqa: E402  (submission/inference.py)

    return inference


def _decode_count(path: Path) -> int:
    """Frames decoded by a read-until-fail loop (matches _stage3_frames)."""
    cap = cv2.VideoCapture(str(path))
    count = 0
    while True:
        ok, _ = cap.read()
        if not ok:
            break
        count += 1
    cap.release()
    return count


def prepare_stage1(baseline: Path, out: Path):
    videos = out / "stage1" / "videos"
    videos.mkdir(parents=True, exist_ok=True)
    expected = {}
    for sub in ("original", "rerecorded"):
        for mp4 in sorted((baseline / "stage1" / sub).glob("*.mp4")):
            ident = f"{sub[:4]}_{mp4.stem}"
            shutil.copy2(mp4, videos / f"{ident}.mp4")
            expected[ident] = None  # S1 expected value is unused by validate()
    return out / "stage1", expected


def prepare_stage2(baseline: Path, out: Path):
    image_root = out / "stage2" / "images"
    expected = {}
    for mp4 in sorted((baseline / "stage2" / "videos").glob("*.mp4")):
        ident = mp4.stem
        folder = image_root / ident
        folder.mkdir(parents=True, exist_ok=True)
        cap = cv2.VideoCapture(str(mp4))
        index = 0
        while True:
            ok, bgr = cap.read()
            if not ok:
                break
            cv2.imwrite(str(folder / f"{index:06d}.jpg"), bgr)
            index += 1
        cap.release()
        if index == 0:
            raise RuntimeError(f"stage2 decode produced 0 frames: {mp4.name}")
        expected[ident] = list(range(index))
    return out / "stage2", expected


def prepare_stage3(baseline: Path, out: Path):
    videos = out / "stage3" / "videos"
    videos.mkdir(parents=True, exist_ok=True)
    expected = {}
    for mp4 in sorted((baseline / "stage3" / "videos").glob("*.mp4")):
        ident = mp4.stem
        shutil.copy2(mp4, videos / mp4.name)
        expected[ident] = _decode_count(mp4)
        if expected[ident] == 0:
            raise RuntimeError(f"stage3 decode produced 0 frames: {mp4.name}")
    return out / "stage3", expected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, default=ROOT / "Baseline" / "data")
    parser.add_argument("--model-root", type=Path, default=ROOT / "models")
    parser.add_argument("--out", type=Path, default=ROOT / "work" / "preflight_e2e")
    args = parser.parse_args()

    inference = _load_submission()
    out = args.out
    _force_rmtree(out)
    out.mkdir(parents=True)

    summary = {}
    stages = [
        ("stage1", prepare_stage1, inference.predict_stage1, args.model_root / "stage1"),
        ("stage2", prepare_stage2, inference.predict_stage2, args.model_root / "stage2"),
        ("stage3", prepare_stage3, inference.predict_stage3, args.model_root / "stage3"),
    ]
    for stage, prepare, predict, model_dir in stages:
        data_dir, expected = prepare(args.baseline, out)
        (out / f"{stage}_expected.json").write_text(
            json.dumps(expected), encoding="utf-8"
        )
        frame = predict(str(data_dir), str(model_dir))
        csv_path = out / f"{stage}_pred.csv"
        frame.to_csv(csv_path, index=False, encoding="utf-8")
        rows = frame.to_dict("records")
        result = validate(stage, list(frame.columns), [
            {k: str(v) for k, v in row.items()} for row in rows
        ], expected)
        summary[stage] = {
            "csv": str(csv_path),
            "expected": str(out / f"{stage}_expected.json"),
            "n_ids": len(expected),
            "n_rows": len(rows),
            "validate": result,
        }
        print(f"[{stage}] ok rows={len(rows)} ids={len(expected)}", flush=True)

    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
