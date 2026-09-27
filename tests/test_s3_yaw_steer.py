"""Stage 3 yaw-proxy steering rule (Pro qa, decision 12-D follow-up)."""
import importlib.util
import sys
import unittest
from pathlib import Path

ML_MISSING = [m for m in ("numpy", "cv2") if importlib.util.find_spec(m) is None]
if ML_MISSING:
    raise unittest.SkipTest("ML stack not installed: " + ", ".join(ML_MISSING))

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from afda import s3_yaw_steer as ys  # noqa: E402


def panning(step, n=20):
    """textured scene shifted horizontally by `step` px per frame at 160x120 (step > 0 = scene moves right)."""
    rng = np.random.RandomState(0)
    base = rng.randint(0, 255, (60, 200), np.uint8)
    big = cv2.GaussianBlur(cv2.resize(base, (800, 120), interpolation=cv2.INTER_CUBIC), (3, 3), 0)
    return np.stack([big[:, 300 - int(round(step * k)):460 - int(round(step * k))] for k in range(n)])


class YawSteerTest(unittest.TestCase):
    def test_sign_convention(self):
        self.assertTrue(np.all(ys.predict_steer(panning(2.0), gray=True)[2:] == "LEFT"))
        self.assertTrue(np.all(ys.predict_steer(panning(-2.0), gray=True)[2:] == "RIGHT"))
        self.assertTrue(np.all(ys.predict_steer(panning(0.0), gray=True) == "STRAIGHT"))

    def test_shapes_and_short_clips(self):
        self.assertEqual(len(ys.predict_steer(panning(1.0, 7), gray=True)), 7)
        self.assertEqual(list(ys.predict_steer(panning(1.0, 1), gray=True)), ["STRAIGHT"])
        bgr = [cv2.cvtColor(np.zeros((360, 640), np.uint8), cv2.COLOR_GRAY2BGR)] * 3
        self.assertEqual(list(ys.predict_steer(bgr)), ["STRAIGHT"] * 3)

    def test_smooth_matches_centered_rolling_mean(self):
        x = np.arange(12, dtype=float) ** 2
        exp = [x[max(0, i - 4):i + 5].mean() for i in range(12)]
        self.assertTrue(np.allclose(ys.smooth(x), exp))


if __name__ == "__main__":
    unittest.main()
