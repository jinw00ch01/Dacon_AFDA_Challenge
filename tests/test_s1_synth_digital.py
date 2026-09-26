"""Pure helpers of scripts/s1_synth_digital.py (v1c digital re-record generator)."""
import importlib.util
import random
import sys
import unittest
from pathlib import Path

# GitHub CI (.github/workflows/contracts.yml) installs only psutil.
ML_MISSING = [m for m in ("numpy", "cv2") if importlib.util.find_spec(m) is None]
if ML_MISSING:
    raise unittest.SkipTest("ML stack not installed: " + ", ".join(ML_MISSING))

import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import s1_synth_digital as sd  # noqa: E402


class S1SynthDigitalTest(unittest.TestCase):
    def test_params_seeded_and_in_range(self):
        a = sd.sample_params(random.Random("s|SRC001|0|0"))
        b = sd.sample_params(random.Random("s|SRC001|0|0"))
        self.assertEqual(a, b)
        for k in range(50):
            p = sd.sample_params(random.Random(k))
            self.assertTrue(1.1 <= p["target_hf_ratio"] <= 1.45)
            self.assertTrue(1.0 <= p["contrast"] <= 1.05)
            self.assertTrue(0.0 <= p["black"] <= 3.0)
            self.assertEqual(p["crf"], 23)

    def test_next_sigma_moves_toward_target_and_clamps(self):
        self.assertLess(sd.next_sigma(3.0, 1.9, 1.3), 3.0)
        self.assertGreater(sd.next_sigma(3.0, 1.1, 1.3), 3.0)
        self.assertAlmostEqual(sd.next_sigma(3.0, 1.3, 1.3), 3.0, places=6)
        self.assertEqual(sd.next_sigma(3.0, 1.0, 1.45), 6.0)
        self.assertEqual(sd.next_sigma(3.0, 5.0, 1.1), 0.8)

    def test_crop_16x9(self):
        self.assertEqual(sd.crop_16x9(962, 1280), (121, 841, 0, 1280))
        self.assertEqual(sd.crop_16x9(720, 1280), (0, 720, 0, 1280))
        y0, y1, x0, x1 = sd.crop_16x9(1080, 2400)
        self.assertEqual((y1 - y0, x1 - x0), (1080, 1920))

    def test_window_ids_fit_and_stop(self):
        wins = sd.window_ids(200, 20.0, 2)
        self.assertEqual(len(wins), 2)
        self.assertEqual([len(w) for w in wins], [50, 50])
        self.assertEqual(wins[0][:3], [0, 2, 4])
        self.assertEqual(wins[1][0], 100)
        self.assertEqual(wins[1][-1], 198)
        self.assertEqual(len(sd.window_ids(150, 20.0, 2)), 1)  # second window would overrun

    def test_tone_keeps_alignment_and_dtype(self):
        f = np.full((8, 8, 3), 100, np.uint8)
        out = sd.tone(f, np.random.default_rng(0), {"grain_sigma": 0.0, "contrast": 1.0, "black": 0.0})
        self.assertEqual(out.dtype, np.uint8)
        np.testing.assert_array_equal(out, f)
        out = sd.tone(f, np.random.default_rng(0), {"grain_sigma": 3.0, "contrast": 1.04, "black": 2.0})
        self.assertAlmostEqual(float(out.mean()), (100 - 128) * 1.04 + 128 - 2, delta=1.5)


if __name__ == "__main__":
    unittest.main()
