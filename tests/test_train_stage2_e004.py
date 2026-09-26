"""Tests for the Stage 2 e004 official-layout changes (CPU-fast).

e004 adds three config-gated changes to scripts/train_stage2.py, all default-off so
e001/e002/e003 stay byte-identical: (1) biased window placement so the collision
anchor lands at the official window position 30-41, (2) a per-position log-prior added
to the collision/entry logits, and (3) checkpoint selection by the official S2 score.

These tests exercise the pure helpers (biased_window_start, position_log_prior), the
official-S2 metrics wiring via src/afda/metrics.py, evaluate_windows' new keys with a
tiny real Stage2Temporal model on CPU, and the no-bias equivalence guarantee.
"""
import importlib.util
import sys
import unittest
from pathlib import Path

# GitHub CI (.github/workflows/contracts.yml) installs only psutil; the ML stack is tested on Ultra's venv.
ML_MISSING = [m for m in ("numpy", "torch") if importlib.util.find_spec(m) is None]
if ML_MISSING:
    raise unittest.SkipTest("ML stack not installed: " + ", ".join(ML_MISSING))

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TR = _load("afda_train_stage2_e004", "scripts/train_stage2.py")
from afda import metrics  # noqa: E402
from afda.models import Stage2Temporal  # noqa: E402


class BiasedWindowStartTests(unittest.TestCase):
    def test_anchor_position_within_bias(self):
        """Across many draws, anchor - start stays in [lo,hi] when the window fits."""
        rng = np.random.RandomState(0)
        t_len, window, lo, hi, anchor = 200, 50, 25, 41, 120
        for _ in range(500):
            start = TR.biased_window_start(t_len, anchor, window, [lo, hi], rng)
            pos = anchor - start
            self.assertGreaterEqual(pos, lo)
            self.assertLessEqual(pos, hi)
            self.assertGreaterEqual(start, 0)
            self.assertLessEqual(start + window, t_len)

    def test_clamps_at_left_boundary(self):
        """Anchor near the start: window cannot extend below 0, start clamps to 0."""
        rng = np.random.RandomState(1)
        t_len, window, anchor = 60, 50, 5  # needs pos<=5 to fit at start 0
        for _ in range(200):
            start = TR.biased_window_start(t_len, anchor, window, [25, 41], rng)
            self.assertGreaterEqual(start, 0)
            self.assertLessEqual(start + window, t_len)

    def test_clamps_at_right_boundary(self):
        """Anchor near the end: window cannot extend past t_len."""
        rng = np.random.RandomState(2)
        t_len, window, anchor = 60, 50, 55
        for _ in range(200):
            start = TR.biased_window_start(t_len, anchor, window, [25, 41], rng)
            self.assertGreaterEqual(start, 0)
            self.assertLessEqual(start + window, t_len)

    def test_short_sequence_returns_zero(self):
        rng = np.random.RandomState(3)
        self.assertEqual(TR.biased_window_start(30, 10, 50, [25, 41], rng), 0)

    def test_no_bias_matches_uniform_placement(self):
        """bias=None reproduces the pre-e004 anchor-containing uniform placement."""
        t_len, window, anchor = 200, 50, 120
        rng_a = np.random.RandomState(7)
        rng_b = np.random.RandomState(7)
        for _ in range(100):
            got = TR.biased_window_start(t_len, anchor, window, None, rng_a)
            lo = max(0, anchor - window + 1)
            hi = min(anchor, t_len - window)
            exp = int(rng_b.randint(lo, hi + 1)) if hi >= lo else max(0, min(anchor, t_len - window))
            self.assertEqual(got, exp)


class PositionLogPriorTests(unittest.TestCase):
    def _items(self, n=30, collision=32, entry=24, t_len=200):
        rng = np.random.RandomState(0)
        items = []
        for i in range(n):
            items.append({
                "video_id": f"v{i}",
                "feats": rng.randn(t_len, 512).astype(np.float32),
                "fps": 10.0,
                "collision": collision,
                "entry": entry,
                "evasion": 0,
                "side": 1,
            })
        return items

    def test_length_and_finite(self):
        prior = TR.position_log_prior(self._items(), 50, "collision", bias=[25, 41], seed=0)
        self.assertEqual(prior.shape, (50,))
        self.assertEqual(prior.dtype, np.float32)
        self.assertTrue(np.all(np.isfinite(prior)))

    def test_higher_mass_in_bias_region(self):
        """Collision at frame 32 -> mass concentrates in the biased [25,41] band."""
        prior = TR.position_log_prior(self._items(collision=32), 50, "collision",
                                      bias=[25, 41], seed=0)
        band = prior[25:42]
        outside = np.concatenate([prior[:25], prior[42:]])
        self.assertGreater(band.mean(), outside.mean())
        # the modal position should sit inside the biased band
        self.assertTrue(25 <= int(prior.argmax()) <= 41)

    def test_uniform_when_key_absent(self):
        items = self._items()
        for it in items:
            it["entry"] = None
        prior = TR.position_log_prior(items, 50, "entry", bias=[25, 41], seed=0)
        self.assertEqual(prior.shape, (50,))
        self.assertTrue(np.allclose(prior, prior[0]))  # uniform


class OfficialS2WiringTests(unittest.TestCase):
    def test_stage2_score_formula(self):
        """Confirm the weighted-sum formula used for checkpoint selection."""
        s2 = metrics.stage2_score(0.8, 0.6, 0.5, 0.4)
        self.assertAlmostEqual(s2, 0.35 * 0.8 + 0.35 * 0.6 + 0.15 * 0.5 + 0.15 * 0.4)

    def test_accuracy_within_frames_tol(self):
        # 10Hz, tol 0.3s == +/-3 frames.
        self.assertEqual(metrics.accuracy_within_frames([30, 30], [33, 34], fps=10, tol=0.3), 0.5)

    def test_const_predictor_hits_official_layout(self):
        """Constant frame-30 collision beats a scattered predictor when GT is at 30-41."""
        gt = [30, 33, 38, 41, 36]
        const_pred = [30] * 5
        scattered = [5, 10, 45, 2, 48]
        ca_const = metrics.accuracy_within_frames(const_pred, gt, fps=10, tol=0.3)
        ca_scat = metrics.accuracy_within_frames(scattered, gt, fps=10, tol=0.3)
        self.assertGreater(ca_const, ca_scat)


class EvaluateWindowsKeysTests(unittest.TestCase):
    def _items(self, n=6, t_len=120):
        rng = np.random.RandomState(0)
        items = []
        for i in range(n):
            items.append({
                "video_id": f"v{i}",
                "feats": rng.randn(t_len, 512).astype(np.float32),
                "fps": 10.0,
                "collision": 32 + (i % 3),
                "entry": 24 + (i % 3),
                "evasion": i % 2,
                "side": (i + 1) % 2,
            })
        return items

    def test_returns_official_keys(self):
        torch.manual_seed(0)
        model = Stage2Temporal()
        device = torch.device("cpu")
        m = TR.evaluate_windows(model, self._items(), window=50, n_windows=3,
                                seed=12345, device=device, amp=False, bias=[25, 41])
        for key in ("official_s2", "collision_acc03", "entry_acc03", "dir_f1",
                    "evasion_f1", "const_official_s2", "const_collision_acc03",
                    "const_entry_acc03"):
            self.assertIn(key, m)
        # official_s2 recomputes exactly from its components via stage2_score
        recomputed = metrics.stage2_score(
            m["collision_acc03"] or 0.0, m["entry_acc03"] or 0.0,
            m["dir_f1"] or 0.0, m["evasion_f1"] or 0.0)
        self.assertAlmostEqual(m["official_s2"], recomputed, places=6)
        # const uses zero direction/evasion F1 (no scene model)
        const_recomputed = metrics.stage2_score(
            m["const_collision_acc03"] or 0.0, m["const_entry_acc03"] or 0.0, 0.0, 0.0)
        self.assertAlmostEqual(m["const_official_s2"], const_recomputed, places=6)
        self.assertGreaterEqual(m["official_s2"], 0.0)
        self.assertLessEqual(m["official_s2"], 1.0)

    def test_prior_added_without_error(self):
        torch.manual_seed(0)
        model = Stage2Temporal()
        device = torch.device("cpu")
        items = self._items()
        pc = TR.position_log_prior(items, 50, "collision", bias=[25, 41], seed=0)
        pe = TR.position_log_prior(items, 50, "entry", bias=[25, 41], seed=1)
        m = TR.evaluate_windows(model, items, window=50, n_windows=2, seed=12345,
                                device=device, amp=False, bias=[25, 41],
                                prior_collision=pc, prior_entry=pe)
        self.assertIn("official_s2", m)


class NoBiasEquivalenceTests(unittest.TestCase):
    """e001/e002/e003 guarantee: without bias, crop/window logic is unchanged."""

    def test_random_time_crop_no_bias_identity(self):
        rng = np.random.RandomState(11)
        feats = rng.randn(200, 512).astype(np.float32)
        # default call (no bias kwarg) must equal explicit bias=None
        r1 = np.random.RandomState(5)
        r2 = np.random.RandomState(5)
        for _ in range(50):
            a = TR.random_time_crop(feats, 120, 90, 50, r1)
            b = TR.random_time_crop(feats, 120, 90, 50, r2, bias=None)
            self.assertEqual(a[1], b[1])
            self.assertEqual(a[2], b[2])
            self.assertTrue(np.array_equal(a[0], b[0]))

    def test_window_starts_no_bias_identity(self):
        r1 = np.random.RandomState(9)
        r2 = np.random.RandomState(9)
        a = TR._window_starts(200, 120, 50, 5, r1)
        b = TR._window_starts(200, 120, 50, 5, r2, bias=None)
        self.assertEqual(a, b)

    def test_window_starts_bias_changes_placement(self):
        r = np.random.RandomState(9)
        biased = TR._window_starts(200, 120, 50, 200, r, bias=[25, 41])
        for start in biased:
            pos = 120 - start
            self.assertGreaterEqual(pos, 25)
            self.assertLessEqual(pos, 41)


if __name__ == "__main__":
    unittest.main()
