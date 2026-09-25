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
from afda import preprocess, models, stage3_labels


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


class Stage3LabelRuleTests(unittest.TestCase):
    """Data-free checks of the S3 proxy label logic (full-count reproduction lives
    in scripts/verify_s3_labels.py which needs the frozen release CSV)."""

    R = stage3_labels.DEFAULT_RULE

    def test_accel_thresholds(self):
        a = lambda s, ac: stage3_labels.classify_accel(s, ac, self.R["v_stop"], self.R["a_db"])
        self.assertEqual(a(0.2, 5.0), "STOPPED")       # below v_stop wins over accel
        self.assertEqual(a(10.0, 0.5), "ACCELERATING")
        self.assertEqual(a(10.0, -0.5), "DECELERATING")
        self.assertEqual(a(10.0, 0.1), "CONSTANT")     # inside +-a_db deadband
        self.assertEqual(a(10.0, 0.2), "CONSTANT")     # boundary is not strictly greater

    def test_steer_sign_and_mask(self):
        s = lambda st, stopped: stage3_labels.classify_steer(st, self.R["bias"], self.R["s_th"], stopped)
        # bias -0.3: centered = angle + 0.3. Positive centered => LEFT.
        self.assertEqual(s(10.0, False), "LEFT")
        self.assertEqual(s(-10.0, False), "RIGHT")
        self.assertEqual(s(0.0, False), "STRAIGHT")
        self.assertEqual(s(10.0, True), "STRAIGHT")    # STOPPED masks steering
        self.assertTrue(stage3_labels.POSITIVE_STEER_IS_LEFT)

    def test_add_labels_grouping(self):
        # Uniform values per source so the centered moving average is a no-op.
        pd = __import__("pandas")
        df = pd.DataFrame(
            {
                "source_id": ["A", "A", "B", "B"],
                "speed_mps": [0.1, 0.1, 20.0, 20.0],
                "steering_angle_deg": [20.0, 20.0, -20.0, -20.0],
                "acceleration_mps2_proxy": [1.0, 1.0, 1.0, 1.0],
            }
        )
        out = stage3_labels.add_labels(df)
        # Source A is below v_stop -> STOPPED and steer-masked to STRAIGHT.
        self.assertEqual(list(out["accel_label"]), ["STOPPED", "STOPPED", "ACCELERATING", "ACCELERATING"])
        self.assertEqual(list(out["steer_label"]), ["STRAIGHT", "STRAIGHT", "RIGHT", "RIGHT"])

    def test_accel_from_speed_series_ramp(self):
        # +1 m/s per 0.1s step => ~+10 m/s^2 accel -> ACCELERATING once above v_stop.
        speed = [i * 1.0 for i in range(8)]
        labels = stage3_labels.accel_from_speed_series(speed)  # default 10Hz spacing
        self.assertTrue(all(x == "ACCELERATING" for x in labels))  # rising speed, +accel throughout
        # A rise that starts from rest: the first samples are STOPPED (speed_ma < v_stop).
        slow_start = stage3_labels.accel_from_speed_series([0.0, 0.0, 0.0, 1.0, 2.0, 3.0])
        self.assertEqual(slow_start[0], "STOPPED")
        # A flat sequence sits in the deadband -> CONSTANT (and STOPPED when slow).
        self.assertEqual(stage3_labels.accel_from_speed_series([20.0] * 6), ["CONSTANT"] * 6)
        self.assertEqual(stage3_labels.accel_from_speed_series([0.1] * 6), ["STOPPED"] * 6)


class Stage3SpeedPostProcessTests(unittest.TestCase):
    """The e002 accel-from-speed post-processing (Pro packet 824b3122). Feeding the
    *oracle* true speed through derive_accel_column must reproduce add_labels' accel
    labels exactly, which pins the gradient/smoothing order the trained head relies on."""

    RELEASE_CSV = ROOT / "data" / "derived" / "releases" / "s3-aux-rules-v1b-20260925" / "s3_auxiliary_10hz.csv"

    def test_grouping_does_not_span_sources(self):
        pd = __import__("pandas")
        # B is flat-but-fast; if A's speeds leaked into B's gradient window the last
        # A row / first B row would misclassify. Per-source grouping prevents that.
        df = pd.DataFrame(
            {
                "source_id": ["A", "A", "A", "B", "B", "B"],
                "sample_index": [0, 1, 2, 0, 1, 2],
                "speed_pred": [0.0, 5.0, 10.0, 20.0, 20.0, 20.0],
            }
        )
        labels = stage3_labels.derive_accel_column(df, "speed_pred")
        self.assertEqual(list(labels[df["source_id"] == "B"]), ["CONSTANT", "CONSTANT", "CONSTANT"])

    def test_oracle_true_speed_reproduces_add_labels(self):
        pd = __import__("pandas")
        if not self.RELEASE_CSV.exists():
            self.skipTest("frozen release CSV not present")
        df = pd.read_csv(self.RELEASE_CSV)
        df = df[df["source_id"] != "SRC014"].reset_index(drop=True)  # excluded from GT
        ref = stage3_labels.add_labels(df)["accel_label"].to_numpy()
        oracle = df.copy()
        oracle["speed_pred"] = oracle["speed_mps"]
        derived = stage3_labels.derive_accel_column(oracle, "speed_pred").to_numpy()
        for split in ("train", "validation", "test"):
            mask = (df["split"] == split).to_numpy()
            acc = float((ref[mask] == derived[mask]).mean())
            self.assertEqual(acc, 1.0, f"{split} oracle reproduction {acc} != 1.0")


if __name__ == "__main__":
    unittest.main()
