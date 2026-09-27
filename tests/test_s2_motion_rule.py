"""Stage 2 motion collision rule (decision 12-A)."""
import importlib.util
import sys
import unittest
from pathlib import Path

ML_MISSING = [m for m in ("numpy", "cv2") if importlib.util.find_spec(m) is None]
if ML_MISSING:
    raise unittest.SkipTest("ML stack not installed: " + ", ".join(ML_MISSING))

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from afda import s2_motion_rule as rule  # noqa: E402


def textured(seed=0, h=180, w=320):
    rng = np.random.RandomState(seed)
    base = rng.randint(0, 255, (h // 6, w // 6), np.uint8)
    import cv2
    return cv2.GaussianBlur(cv2.resize(base, (w, h), interpolation=cv2.INTER_CUBIC), (5, 5), 0)


def zoom(img, s):
    import cv2
    h, w = img.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), 0, s)
    return cv2.warpAffine(img, m, (w, h), borderMode=cv2.BORDER_REFLECT)


class MotionRuleTest(unittest.TestCase):
    def test_sudden_stop_with_jolt(self):
        # forward motion (steady zoom) until frame 30, then stop and a vertical jolt at 30..31
        img = textured()
        frames, s = [], 1.0
        for k in range(50):
            if k < 30:
                s *= 1.02
            g = zoom(img, s)
            if k in (30, 31):
                g = np.roll(g, 6 if k == 30 else -6, axis=0)
            frames.append(np.dstack([g] * 3))
        pred = rule.predict_collision(frames)
        self.assertLessEqual(abs(pred - 30), 3)
        self.assertEqual(rule.predict_entry(pred), max(0, pred - rule.ENTRY_K))

    def test_output_in_range_and_short_input(self):
        g = np.zeros((50, 90, 160), np.uint8)
        p = rule.predict_collision(g, gray=True)
        self.assertTrue(0 <= p < 50)
        self.assertEqual(rule.predict_collision(g[:2], gray=True), 0)


if __name__ == "__main__":
    unittest.main()
