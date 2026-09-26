"""Tests for scripts/train_stage3.py data path (no MViT forward, CPU-fast).

Guards the two things that silently corrupt training: (1) the 16-frame window
must be built exactly as submission/inference.py builds it, and (2) proxy labels
must align to cache row positions. MViT forward/accuracy is out of scope here.
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

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def _load_trainer():
    spec = importlib.util.spec_from_file_location("afda_train_stage3", ROOT / "scripts" / "train_stage3.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TR = _load_trainer()


def _aux_rows(source_id, split, n, speed, steer):
    return pd.DataFrame(
        {
            "source_id": [source_id] * n,
            "split": [split] * n,
            "sample_index": list(range(n)),
            "speed_mps": [speed] * n,
            "steering_angle_deg": [steer] * n,
            "acceleration_mps2_proxy": [1.0] * n,
        }
    )


class TrainStage3DataTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.T = 6
        rng = np.random.default_rng(0)
        # Two sources: STOPPED+STRAIGHT (train) and moving+LEFT (validation).
        self.train_arr = rng.integers(0, 256, size=(self.T, 3, 4, 4), dtype=np.uint8)
        (self.tmp / "train").mkdir()
        (self.tmp / "validation").mkdir()
        np.save(self.tmp / "train" / "SRC_A.npy", self.train_arr)
        np.save(self.tmp / "validation" / "SRC_B.npy", rng.integers(0, 256, (self.T, 3, 4, 4), dtype=np.uint8))
        self.aux = pd.concat(
            [
                _aux_rows("SRC_A", "train", self.T, speed=0.1, steer=0.0),      # STOPPED -> STRAIGHT
                _aux_rows("SRC_B", "validation", self.T, speed=20.0, steer=30.0),  # ACCEL + LEFT
            ],
            ignore_index=True,
        )
        self.rule = TR.stage3_labels.DEFAULT_RULE

    def test_length_and_stride(self):
        ds = TR.S3ClipDataset(self.tmp, self.aux, "train", self.rule, window=16, stride=2)
        self.assertEqual(len(ds), len(range(0, self.T, 2)))  # 3 samples

    def test_window_matches_inference(self):
        ds = TR.S3ClipDataset(self.tmp, self.aux, "train", self.rule, window=16, stride=1)
        for pos in range(self.T):
            clip, _, _, _ = ds[pos]
            self.assertEqual(tuple(clip.shape), (3, 16, 4, 4))
            idx = np.clip(pos - 8 + np.arange(16), 0, self.T - 1)  # same formula as inference
            expected = torch.from_numpy(self.train_arr[idx].astype(np.float32)).permute(1, 0, 2, 3) / 255.0
            expected = (expected - TR.MEAN) / TR.STD
            self.assertTrue(torch.allclose(clip, expected, atol=1e-5))

    def test_label_alignment(self):
        train = TR.S3ClipDataset(self.tmp, self.aux, "train", self.rule, window=16, stride=1)
        # STOPPED == accel index 3, STRAIGHT == steer index 1.
        self.assertEqual(set(train.accel), {TR.ACCEL.index("STOPPED")})
        self.assertEqual(set(train.steer), {TR.STEER.index("STRAIGHT")})
        val = TR.S3ClipDataset(self.tmp, self.aux, "validation", self.rule, window=16, stride=1)
        self.assertEqual(set(val.accel), {TR.ACCEL.index("ACCELERATING")})
        self.assertEqual(set(val.steer), {TR.STEER.index("LEFT")})

    def test_misalignment_guard(self):
        bad = self.aux[self.aux["source_id"] == "SRC_A"].iloc[:-1]  # one fewer row than cache
        with self.assertRaises(ValueError):
            TR.S3ClipDataset(self.tmp, bad, "train", self.rule, window=16, stride=1)

    def test_metric_helpers(self):
        w = TR.class_weights([0, 0, 0, 1], 4)  # class 3 absent -> finite weight, no div0
        self.assertTrue(torch.isfinite(w).all())
        self.assertAlmostEqual(TR.macro_f1([0, 1, 2], [0, 1, 2], 3), 1.0)

    def test_steer_metrics_excludes_stopped(self):
        stopped = TR.ACCEL.index("STOPPED")
        moving = TR.ACCEL.index("ACCELERATING")
        left, straight, right = (TR.STEER.index(x) for x in ("LEFT", "STRAIGHT", "RIGHT"))
        a_true = [stopped, moving, moving]
        s_true = [straight, left, right]
        s_pred = [left, left, right]  # wrong only on the STOPPED row
        official, incl, n_stopped = TR.steer_metrics(a_true, s_true, s_pred)
        self.assertEqual(n_stopped, 1)
        # Dropping the STOPPED row makes the remaining two perfectly classified.
        self.assertGreater(official, incl)
        self.assertAlmostEqual(official, TR.macro_f1([left, right], [left, right], len(TR.STEER)))

    def test_evaluate_records_alignment(self):
        class _Dummy(torch.nn.Module):
            def forward(self, clips):
                b = clips.shape[0]
                return torch.zeros(b, len(TR.ACCEL)), torch.zeros(b, len(TR.STEER))

        val = TR.S3ClipDataset(self.tmp, self.aux, "validation", self.rule, window=16, stride=1)
        loader = torch.utils.data.DataLoader(val, batch_size=2, shuffle=False)
        ids = list(val.samples)
        metrics, records = TR.evaluate(_Dummy(), loader, torch.device("cpu"), amp=False, identities=ids)
        self.assertEqual(len(records), len(ids))
        self.assertEqual(list(records["source_id"]), [sid for sid, _ in ids])
        self.assertEqual(list(records["sample_index"]), [pos for _, pos in ids])
        self.assertEqual(set(records.columns) >= {"accel_pred", "steer_pred", "split"}, True)
        self.assertIn("steer_macro_f1_incl_stopped", metrics)
        # decision 10: best.pt selection metric is official S3 = 0.7*accel + 0.3*steer.
        self.assertAlmostEqual(
            metrics["official_s3"],
            0.7 * metrics["accel_macro_f1"] + 0.3 * metrics["steer_macro_f1"],
        )
        with self.assertRaises(ValueError):
            TR.evaluate(_Dummy(), loader, torch.device("cpu"), amp=False, identities=ids[:-1])

    def test_dataset_exposes_speed_target(self):
        # e002 regression head needs the raw speed_mps per sample, aligned to accel/steer.
        val = TR.S3ClipDataset(self.tmp, self.aux, "validation", self.rule, window=16, stride=1)
        self.assertEqual(len(val.speed), len(val.accel))
        self.assertTrue(all(abs(s - 20.0) < 1e-9 for s in val.speed))  # SRC_B speed=20
        _clip, accel_idx, steer_idx, speed = val[0]
        self.assertEqual(accel_idx, TR.ACCEL.index("ACCELERATING"))
        self.assertAlmostEqual(float(speed), 20.0)

    def test_evaluate_speed_mode_derives_accel(self):
        # A monotonically rising predicted speed must derive to ACCELERATING and the
        # speed path must emit official_s3 plus a speed_pred column in the records.
        class _SpeedModel(torch.nn.Module):
            def __init__(self, base):
                super().__init__()
                self.base = float(base)
                self._t = 0.0

            def forward(self, clips):
                b = clips.shape[0]
                # rising ramp across the (shuffle=False) val sequence
                speeds = self.base + self._t + torch.arange(b, dtype=torch.float32)
                self._t += b
                return speeds[:, None], torch.zeros(b, len(TR.STEER))

        val = TR.S3ClipDataset(self.tmp, self.aux, "validation", self.rule, window=16, stride=1)
        loader = torch.utils.data.DataLoader(val, batch_size=2, shuffle=False)
        ids = list(val.samples)
        metrics, records = TR.evaluate(
            _SpeedModel(5.0), loader, torch.device("cpu"), amp=False,
            identities=ids, predict_speed=True, rule=self.rule,
        )
        self.assertIn("official_s3", metrics)
        self.assertIn("speed_pred", records.columns)
        self.assertEqual(set(records["accel_pred"]), {"ACCELERATING"})
        # speed mode without identities cannot order per-source speeds -> guard raises
        with self.assertRaises(ValueError):
            TR.evaluate(_SpeedModel(5.0), loader, torch.device("cpu"), amp=False,
                        identities=None, predict_speed=True, rule=self.rule)


    def test_evaluate_stopped_head_overrides_accel(self):
        # e004: a 3-tuple model (speed, steer, stopped_logit). Where the STOPPED head
        # fires (prob >= threshold) the derived accel class must become STOPPED, and
        # the records must carry a stopped_prob column.
        class _SpeedStoppedModel(torch.nn.Module):
            def forward(self, clips):
                b = clips.shape[0]
                speeds = torch.full((b,), 20.0)  # high speed -> derive never STOPPED
                stopped_logit = torch.full((b,), 10.0)  # sigmoid ~1 -> always fires
                return speeds[:, None], torch.zeros(b, len(TR.STEER)), stopped_logit[:, None]

        val = TR.S3ClipDataset(self.tmp, self.aux, "validation", self.rule, window=16, stride=1)
        loader = torch.utils.data.DataLoader(val, batch_size=2, shuffle=False)
        ids = list(val.samples)
        metrics, records = TR.evaluate(
            _SpeedStoppedModel(), loader, torch.device("cpu"), amp=False,
            identities=ids, predict_speed=True, rule=self.rule,
            predict_stopped=True, stopped_threshold=0.5,
        )
        self.assertIn("stopped_prob", records.columns)
        self.assertEqual(set(records["accel_pred"]), {"STOPPED"})
        # accel_pred_raw carries the pre-override class (Pro gate request 918be48a):
        # speed 20 -> derive is never STOPPED, so raw != override.
        self.assertIn("accel_pred_raw", records.columns)
        self.assertNotIn("STOPPED", set(records["accel_pred_raw"]))

    def test_evaluate_stopped_head_below_threshold_keeps_accel(self):
        # A STOPPED head that never fires (prob < threshold) leaves the derived class.
        class _NeverStopped(torch.nn.Module):
            def forward(self, clips):
                b = clips.shape[0]
                return torch.full((b, 1), 20.0), torch.zeros(b, len(TR.STEER)), torch.full((b, 1), -10.0)

        val = TR.S3ClipDataset(self.tmp, self.aux, "validation", self.rule, window=16, stride=1)
        loader = torch.utils.data.DataLoader(val, batch_size=2, shuffle=False)
        ids = list(val.samples)
        _metrics, records = TR.evaluate(
            _NeverStopped(), loader, torch.device("cpu"), amp=False,
            identities=ids, predict_speed=True, rule=self.rule,
            predict_stopped=True, stopped_threshold=0.5,
        )
        self.assertNotIn("STOPPED", set(records["accel_pred"]))


if __name__ == "__main__":
    unittest.main()
