"""Tests for the shared src/afda modules and the self-contained submission inference.

Focus: (1) submission/inference.py satisfies the harness source contract,
(2) its inlined preprocessing stays equivalent to src/afda.preprocess so training
and submission cannot silently drift, (3) model heads have the contract shapes,
(4) predict outputs validate against harness contracts. Heavy MViT forward passes
are intentionally avoided so the suite stays CPU-fast.
"""
import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
SUBMISSION = ROOT / "submission" / "inference.py"
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from harness.__main__ import check_source
from harness.contracts import SCHEMAS, validate
from afda import preprocess, models


def _load_submission():
    spec = importlib.util.spec_from_file_location("afda_submission_inference", SUBMISSION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SubmissionContractTests(unittest.TestCase):
    def test_source_signatures(self):
        # Same gate harness package/validate_zip applies to the shipped file.
        check_source(SUBMISSION.read_text(encoding="utf-8-sig"))

    def test_predict_signatures_present(self):
        module = _load_submission()
        for name in ("predict_stage1", "predict_stage2", "predict_stage3"):
            self.assertTrue(callable(getattr(module, name)))


class PreprocessEquivalenceTests(unittest.TestCase):
    def setUp(self):
        self.sub = _load_submission()

    def test_constants_match(self):
        for name in ("ACCEL", "STEER", "VIDEO_EXT", "IMAGE_EXT"):
            self.assertEqual(getattr(preprocess, name), getattr(self.sub, name), name)
        for name in ("S1_MEAN", "S1_STD", "S3_MEAN", "S3_STD"):
            self.assertTrue(torch.equal(getattr(preprocess, name), getattr(self.sub, name)), name)

    def test_stage1_normalization_matches(self):
        rng = np.random.default_rng(0)
        clip = [rng.integers(0, 256, (8, 8, 3), dtype=np.uint8) for _ in range(4)]
        expected = preprocess.normalize_stage1_clip(clip)
        actual = self.sub._normalize_stage1_clip(clip)
        self.assertEqual(tuple(expected.shape), (3, 4, 8, 8))
        self.assertTrue(torch.equal(expected, actual))

    def test_stage3_normalization_matches(self):
        rng = np.random.default_rng(1)
        frames = torch.from_numpy(rng.integers(0, 256, (20, 3, 224, 224), dtype=np.uint8))
        indices = preprocess.stage3_clip_indices(20, 0)
        expected = preprocess.normalize_stage3_clip(frames, indices)
        # Reproduce the submission's inline stage-3 clip math on the same inputs.
        clips = frames[torch.from_numpy(indices)].permute(0, 2, 1, 3, 4).float() / 255.0
        actual = (clips - self.sub.S3_MEAN[None, :, None, :, :]) / self.sub.S3_STD[None, :, None, :, :]
        self.assertEqual(expected.shape[1:], (3, 16, 224, 224))
        self.assertTrue(torch.equal(expected, actual))

    def test_frame_number_parsing(self):
        for stem, want in (("frame_000042", 42), ("000007", 7), ("noindex", 0)):
            self.assertEqual(preprocess.frame_number(Path(stem + ".jpg")), want)
            self.assertEqual(self.sub._frame_number(Path(stem + ".jpg")), want)


class ModelShapeTests(unittest.TestCase):
    def test_stage1_head_is_two_class(self):
        model = models.build_stage1_model()
        self.assertEqual(model.head[1].out_features, 2)

    def test_stage3_head_shapes(self):
        model = models.Stage3MViT()
        self.assertEqual(model.accel.out_features, 4)
        self.assertEqual(model.steer.out_features, 3)

    def test_stage2_temporal_forward(self):
        model = models.Stage2Temporal().eval()
        with torch.inference_mode():
            collision_idx, entry_idx, scene = model(torch.zeros(1, 5, 512))
        self.assertEqual(collision_idx.shape, (1,))
        self.assertEqual(entry_idx.shape, (1,))
        self.assertEqual(scene.shape, (1, 4))
        # Predicted frame indices must land inside the sequence.
        self.assertTrue(0 <= int(collision_idx) < 5 and 0 <= int(entry_idx) < 5)

    def test_submission_and_shared_architectures_align(self):
        sub = _load_submission()
        self.assertEqual(sub._Stage3MViT().accel.out_features, models.Stage3MViT().accel.out_features)
        shared_keys = set(models.Stage2Temporal().state_dict().keys())
        self.assertEqual(shared_keys, set(sub._Stage2Temporal().state_dict().keys()))


class PredictOutputValidatesTests(unittest.TestCase):
    """A checkpoint-free sanity check that our output rows satisfy harness contracts."""

    def test_synthetic_rows_validate(self):
        s1 = [{"ID": "v1", "answer": "ORIGINAL"}, {"ID": "v2", "answer": "RERECORDED"}]
        validate("stage1", SCHEMAS["stage1"], s1, {"v1": None, "v2": None})

        s2 = [{"ID": "c1", "collision_frame": 10, "entry_frame": 20, "evasion_space": 1, "entry_side": "LEFT"}]
        validate("stage2", SCHEMAS["stage2"], s2, {"c1": [10, 20, 30]})

        s3 = [{"ID": "vid", "sample_index": i, "accel_label": "CONSTANT", "steer_label": "STRAIGHT"} for i in range(3)]
        validate("stage3", SCHEMAS["stage3"], s3, {"vid": 3})


if __name__ == "__main__":
    unittest.main()
