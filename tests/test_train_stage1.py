"""Tests for the Stage 1 recapture discriminator trainer data path (CPU-fast).

Guards what would silently corrupt Stage 1 training/eval: (1) the release manifest
must map labels to the same class convention the submission thresholds
(original->0 ORIGINAL, recapture_synthetic->1 RERECORDED) and the frozen split must
be leak-free by source, (2) the dataset must expose every (video, slot) clip, and
(3) evaluate() must aggregate per-clip probs to a per-video mean == inference and
score it, with records aligned to the video order.
"""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

# GitHub CI (.github/workflows/contracts.yml) installs only psutil; the ML stack is tested on Ultra's venv.
ML_MISSING = [m for m in ("numpy", "pandas", "torch", "torchvision", "cv2") if importlib.util.find_spec(m) is None]
if ML_MISSING:
    raise unittest.SkipTest("ML stack not installed: " + ", ".join(ML_MISSING))

import numpy as np
import pandas as pd
import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TR = _load("afda_train_stage1", "scripts/train_stage1.py")
RELEASE = ROOT / "data/derived/releases/s1-synth-v1-20260925/manifest.csv"


class ReadSplitTest(unittest.TestCase):
    def test_label_mapping_and_missing_files_skipped(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "A_ORIG.mp4").write_bytes(b"x")
        (tmp / "A_SYN0.mp4").write_bytes(b"x")
        # B_ORIG.mp4 intentionally NOT created -> must be skipped
        csv = tmp / "manifest.csv"
        pd.DataFrame(
            {
                "file": ["A_ORIG.mp4", "A_SYN0.mp4", "B_ORIG.mp4"],
                "source_id": ["A", "A", "B"],
                "split": ["train", "train", "train"],
                "label": ["original", "recapture_synthetic", "original"],
            }
        ).to_csv(csv, index=False)
        rows = TR.read_split(csv, tmp, "train")
        self.assertEqual(len(rows), 2)  # missing B skipped
        by_file = {r["file"]: r for r in rows}
        self.assertEqual(by_file["A_ORIG.mp4"]["label"], 0)  # ORIGINAL == 0
        self.assertEqual(by_file["A_SYN0.mp4"]["label"], 1)  # RERECORDED == 1

    def test_unknown_label_raises(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "x.mp4").write_bytes(b"x")
        csv = tmp / "m.csv"
        pd.DataFrame(
            {"file": ["x.mp4"], "source_id": ["x"], "split": ["train"], "label": ["bogus"]}
        ).to_csv(csv, index=False)
        with self.assertRaises(ValueError):
            TR.read_split(csv, tmp, "train")


class ReleaseSplitTest(unittest.TestCase):
    def test_frozen_split_is_disjoint_by_source(self):
        if not RELEASE.exists():
            self.skipTest("s1-synth release not present")
        df = pd.read_csv(RELEASE)
        # a source_id must live in exactly one split (no original/recapture leak)
        per_source_splits = df.groupby("source_id")["split"].nunique()
        self.assertTrue((per_source_splits == 1).all())
        self.assertEqual(set(df["label"].unique()) - set(TR.LABEL_TO_CLASS), set())


class DatasetItemsTest(unittest.TestCase):
    def test_every_video_gets_slots_items(self):
        rows = [
            {"file": "a.mp4", "source_id": "a", "path": Path("a.mp4"), "label": 0},
            {"file": "b.mp4", "source_id": "b", "path": Path("b.mp4"), "label": 1},
        ]
        ds = TR.S1ClipDataset(rows, size=224, frames=16, slots=3)
        self.assertEqual(len(ds), 6)  # 2 videos x 3 slots
        from collections import Counter

        counts = Counter(vi for vi, _slot in ds.items)
        self.assertEqual(counts, Counter({0: 3, 1: 3}))
        self.assertEqual(sorted(slot for _vi, slot in ds.items if _vi == 0), [0, 1, 2])


class EvaluateTest(unittest.TestCase):
    def test_per_video_mean_and_records_alignment(self):
        rows = [
            {"file": "orig.mp4", "source_id": "s0", "path": Path("orig.mp4"), "label": 0},
            {"file": "syn.mp4", "source_id": "s1", "path": Path("syn.mp4"), "label": 1},
        ]

        class Stub(nn.Module):  # clips already ARE the logits it returns
            def forward(self, x):
                return x

        # video 0: two clips, softmax[:,1] < 0.5 -> ORIGINAL; video 1: -> RERECORDED
        loader = [
            (torch.tensor([[3.0, 0.0], [2.0, 0.0]]), torch.tensor([0, 0]), torch.tensor([0, 0])),
            (torch.tensor([[0.0, 4.0]]), torch.tensor([1]), torch.tensor([1])),
        ]
        metrics, records = TR.evaluate(Stub(), loader, torch.device("cpu"), amp=False, rows=rows)
        self.assertEqual(metrics["n_videos"], 2)
        self.assertEqual(metrics["macro_f1"], 1.0)  # both videos correct
        self.assertEqual(metrics["acc"], 1.0)
        self.assertEqual(list(records["file"]), ["orig.mp4", "syn.mp4"])
        self.assertEqual(list(records["pred"]), ["ORIGINAL", "RERECORDED"])
        self.assertLess(records["prob_rerecorded"].iloc[0], 0.5)

    def test_class_weights_favor_minority(self):
        w = TR.class_weights([0] * 24 + [1] * 96, 2)
        self.assertGreater(float(w[0]), float(w[1]))  # rarer ORIGINAL upweighted


if __name__ == "__main__":
    unittest.main()
