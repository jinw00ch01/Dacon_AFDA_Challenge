"""Tests for the Stage 2 feature cache + trainer data path (CPU-fast).

Guards what silently corrupts Stage 2 training: (1) the per-video split must be
deterministic and leak-free, (2) cached targets must map to the right frame
position / class (collision_frame, entry_frame, evasion_space, entry_side with
RIGHT==1), and (3) the training loss must actually flow gradients through the
real Stage2Temporal head the submission loads.
"""
import importlib.util
import json
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


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CACHE = _load("afda_cache_stage2", "scripts/cache_s2_features.py")
TR = _load("afda_train_stage2", "scripts/train_stage2.py")


def _write_cache(tmp, videos):
    """videos: list of dicts with video_id, split, feats(T,512), and label fields."""
    manifest = {"videos": []}
    for v in videos:
        np.save(tmp / f"{v['video_id']}.npy", v["feats"].astype(np.float16))
        entry = {k: v.get(k) for k in (
            "video_id", "split", "fps", "collision_frame", "entry_frame",
            "evasion_space", "entry_side", "collision_valid", "entry_valid",
            "evasion_valid", "side_valid")}
        manifest["videos"].append(entry)
    (tmp / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


class AssignSplitTest(unittest.TestCase):
    def test_deterministic_disjoint_and_stratified(self):
        df = pd.DataFrame({
            "video_id": [f"{i:05d}" for i in range(20)],
            "collision_valid": [1] * 10 + [0] * 10,
        })
        a = CACHE.assign_splits(df, val_frac=0.2, seed=0)
        b = CACHE.assign_splits(df, val_frac=0.2, seed=0)
        self.assertTrue((a.values == b.values).all())  # deterministic
        self.assertEqual(set(a.unique()) - {"train", "validation"}, set())
        # both strata contribute at least one validation video (no leakage of a
        # whole stratum into train only)
        val_has_pos = ((a == "validation") & (df["collision_valid"] == 1)).any()
        val_has_neg = ((a == "validation") & (df["collision_valid"] == 0)).any()
        self.assertTrue(val_has_pos and val_has_neg)


class LoadCacheTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        T = 100
        rng = np.random.default_rng(0)
        _write_cache(self.tmp, [
            {"video_id": "A", "split": "train", "fps": 30.0,
             "feats": rng.random((T, 512)),
             "collision_frame": 40, "entry_frame": 20,
             "evasion_space": 1, "entry_side": "RIGHT",
             "collision_valid": 1, "entry_valid": 1, "evasion_valid": 1, "side_valid": 1},
            {"video_id": "B", "split": "validation", "fps": 30.0,
             "feats": rng.random((T, 512)),
             "collision_frame": None, "entry_frame": None,
             "evasion_space": None, "entry_side": None,
             "collision_valid": 0, "entry_valid": 0, "evasion_valid": 0, "side_valid": 0},
            {"video_id": "C", "split": "train", "fps": 30.0,
             "feats": rng.random((5, 512)),  # short clip -> position must clip
             "collision_frame": 999, "entry_frame": 3,
             "evasion_space": 0, "entry_side": "LEFT",
             "collision_valid": 1, "entry_valid": 1, "evasion_valid": 1, "side_valid": 1},
        ])

    def test_targets_and_side_mapping(self):
        train = {it["video_id"]: it for it in TR.load_cache(self.tmp, "train")}
        self.assertEqual(train["A"]["collision"], 40)
        self.assertEqual(train["A"]["entry"], 20)
        self.assertEqual(train["A"]["evasion"], 1)
        self.assertEqual(train["A"]["side"], 1)  # RIGHT == 1
        self.assertEqual(train["C"]["side"], 0)  # LEFT == 0
        self.assertEqual(train["C"]["collision"], 4)  # clipped to T-1

    def test_invalid_targets_are_none(self):
        val = TR.load_cache(self.tmp, "validation")
        self.assertEqual(len(val), 1)
        b = val[0]
        self.assertIsNone(b["collision"])
        self.assertIsNone(b["entry"])
        self.assertIsNone(b["evasion"])
        self.assertIsNone(b["side"])


class TrainingPathTest(unittest.TestCase):
    def test_loss_backward_flows_gradients(self):
        from afda.models import Stage2Temporal

        torch.manual_seed(0)
        model = Stage2Temporal()
        x = torch.randn(1, 60, 512)
        h, cl, el = TR._logits(model, x)
        self.assertEqual(tuple(cl.shape), (1, 60))
        self.assertEqual(tuple(el.shape), (1, 60))
        scene = TR._scene(model, h, 30, 10)
        self.assertEqual(tuple(scene.shape), (1, 4))
        loss = (torch.nn.functional.cross_entropy(cl, torch.tensor([30]))
                + torch.nn.functional.cross_entropy(scene[:, 2:], torch.tensor([1])))
        loss.backward()
        grads = [p.grad for p in model.parameters() if p.grad is not None]
        self.assertTrue(grads and all(torch.isfinite(g).all() for g in grads))

    def test_evaluate_reports_seconds(self):
        from afda.models import Stage2Temporal

        tmp = Path(tempfile.mkdtemp())
        rng = np.random.default_rng(1)
        _write_cache(tmp, [
            {"video_id": "V", "split": "validation", "fps": 30.0,
             "feats": rng.random((50, 512)),
             "collision_frame": 25, "entry_frame": 10,
             "evasion_space": 1, "entry_side": "LEFT",
             "collision_valid": 1, "entry_valid": 1, "evasion_valid": 1, "side_valid": 1},
        ])
        items = TR.load_cache(tmp, "validation")
        model = Stage2Temporal()
        m = TR.evaluate(model, items, torch.device("cpu"), amp=False)
        self.assertEqual(m["n_collision"], 1)
        self.assertEqual(m["n_entry"], 1)
        self.assertGreaterEqual(m["time_mae_s"], 0.0)
        self.assertIn(m["evasion_acc"], (0.0, 1.0))
        self.assertIn(m["side_acc"], (0.0, 1.0))


class RandomTimeCropTest(unittest.TestCase):
    def test_noop_when_disabled_or_too_short(self):
        feats = np.zeros((100, 512), np.float32)
        rng = np.random.RandomState(0)
        # crop disabled
        f, c, e = TR.random_time_crop(feats, 40, 20, None, rng)
        self.assertEqual(f.shape[0], 100)
        self.assertEqual((c, e), (40, 20))
        # T <= crop_frames -> unchanged
        f, c, e = TR.random_time_crop(feats, 40, 20, 100, rng)
        self.assertEqual(f.shape[0], 100)
        self.assertEqual((c, e), (40, 20))

    def test_anchor_stays_inside_and_targets_remap(self):
        feats = np.arange(1000, dtype=np.float32).reshape(1000, 1) * np.ones((1, 512), np.float32)
        for seed in range(50):
            rng = np.random.RandomState(seed)
            f, c, e = TR.random_time_crop(feats, 600, 610, 256, rng)
            self.assertEqual(f.shape[0], 256)
            # at least one target survives (the anchor), and survivors are in-range
            self.assertTrue(c is not None or e is not None)
            for q, orig in ((c, 600), (e, 610)):
                if q is not None:
                    self.assertTrue(0 <= q < 256)
                    # window-relative index maps back to the same original feature row
                    np.testing.assert_array_equal(f[q], feats[orig])

    def test_deterministic_with_seed(self):
        feats = np.random.default_rng(0).random((900, 512)).astype(np.float32)
        a = TR.random_time_crop(feats, 500, None, 256, np.random.RandomState(7))
        b = TR.random_time_crop(feats, 500, None, 256, np.random.RandomState(7))
        np.testing.assert_array_equal(a[0], b[0])
        self.assertEqual((a[1], a[2]), (b[1], b[2]))

    def test_target_outside_window_dropped(self):
        feats = np.zeros((1000, 512), np.float32)
        # gap is 800 > window 256: exactly one target (the anchor) can survive
        for seed in range(30):
            rng = np.random.RandomState(seed)
            _, c, e = TR.random_time_crop(feats, 100, 900, 256, rng)
            survivors = [x for x in (c, e) if x is not None]
            self.assertEqual(len(survivors), 1)  # anchor kept, the other dropped


class ConstBaselineTest(unittest.TestCase):
    def test_uses_train_median_and_reports_seconds(self):
        train = [
            {"feats": np.zeros((100, 1), np.float32), "fps": 10.0, "collision": 40, "entry": 20},
            {"feats": np.zeros((100, 1), np.float32), "fps": 10.0, "collision": 60, "entry": 30},
        ]
        val = [
            {"feats": np.zeros((100, 1), np.float32), "fps": 10.0, "collision": 50, "entry": None},
        ]
        b = TR.const_baseline(train, val)
        self.assertEqual(b["collision_frame"], 50)  # median(40,60)
        self.assertEqual(b["entry_frame"], 25)       # median(20,30) rounds to 25
        self.assertAlmostEqual(b["collision_mae_s"], 0.0)  # |50-50|/10
        self.assertIsNone(b["entry_mae_s"])          # no val entry labels
        self.assertAlmostEqual(b["time_mae_s"], 0.0)


class ResampleHzTest(unittest.TestCase):
    def test_resample_length_and_index_map(self):
        # 120 frames @ 30fps -> 40 frames @ 10Hz (indices 0,3,6,...,117)
        feats = np.arange(120, dtype=np.float32)[:, None]
        out = TR.resample_to_hz(feats, fps=30.0, hz=10)
        self.assertEqual(out.shape[0], 40)
        self.assertEqual(int(out[0, 0]), 0)
        self.assertEqual(int(out[1, 0]), 3)   # round(1*30/10)
        self.assertEqual(int(out[-1, 0]), 117)  # round(39*30/10)

    def test_resample_noop_when_hz_falsy(self):
        feats = np.zeros((50, 1), np.float32)
        self.assertIs(TR.resample_to_hz(feats, 30.0, None), feats)

    def test_remap_pos_to_hz(self):
        # collision at frame 597 @30fps -> round(597*10/30)=199 @10Hz
        self.assertEqual(TR.remap_pos_to_hz(597, 30.0, 10, new_len=402), 199)
        self.assertIsNone(TR.remap_pos_to_hz(None, 30.0, 10, 402))
        # clipped into range
        self.assertEqual(TR.remap_pos_to_hz(10_000, 30.0, 10, new_len=402), 401)

    def test_apply_resample_updates_fps_and_targets(self):
        items = [{"feats": np.arange(120, dtype=np.float32)[:, None], "fps": 30.0,
                  "collision": 60, "entry": None, "evasion": None, "side": None}]
        TR.apply_resample(items, 10)
        self.assertEqual(items[0]["fps"], 10.0)
        self.assertEqual(items[0]["feats"].shape[0], 40)
        self.assertEqual(items[0]["collision"], 20)  # round(60*10/30)
        self.assertIsNone(items[0]["entry"])


class EvaluateWindowsTest(unittest.TestCase):
    def _model(self):
        torch.manual_seed(0)
        return TR.Stage2Temporal()

    def test_windowed_eval_reports_seconds_and_center(self):
        # single val video, 40 frames @10Hz, collision at 20; window 50 > len -> full clip
        val = [{"feats": np.random.RandomState(0).randn(40, 512).astype(np.float32),
                "fps": 10.0, "collision": 20, "entry": None, "evasion": None, "side": None}]
        m = self._model()
        out = TR.evaluate_windows(m, val, window=50, n_windows=3, seed=123,
                                  device=torch.device("cpu"), amp=False)
        self.assertEqual(out["n_collision"], 3)  # 3 windows, collision present in each
        self.assertIsNotNone(out["collision_mae_s"])
        # center baseline: window<=len -> center=min(25,39)=25, |25-20|/10 = 0.5
        self.assertAlmostEqual(out["collision_center_mae_s"], 0.5, places=6)

    def test_window_contains_collision_and_remaps(self):
        # long clip: 400 frames, collision at 199, window 50 -> each window includes 199
        rng = np.random.RandomState(1)
        starts = TR._window_starts(400, anchor=199, window=50, n=20, rng=rng)
        for s in starts:
            self.assertTrue(s <= 199 < s + 50)
            self.assertTrue(0 <= s <= 350)


if __name__ == "__main__":
    unittest.main()
