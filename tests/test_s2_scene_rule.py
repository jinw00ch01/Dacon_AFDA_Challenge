"""Stage 2 motion side / evasion rules (decision 12-C)."""
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
from afda import s2_scene_rule as rule  # noqa: E402


def textured(seed, h, w, cell=4):
    rng = np.random.RandomState(seed)
    base = rng.randint(0, 255, (h // cell, w // cell), np.uint8)
    return cv2.GaussianBlur(cv2.resize(base, (w, h), interpolation=cv2.INTER_CUBIC), (3, 3), 0)


def moving_block(step, n=30):
    """static background, a textured block crossing the lower centre by `step` px per frame."""
    bg, obj = textured(0, 90, 160), textured(1, 30, 40)
    out = []
    for k in range(n):
        f = bg.copy()
        x = int(60 + step * (k - n // 2))
        x0, x1 = max(0, x), min(160, x + 40)
        if x1 > x0:
            f[50:80, x0:x1] = obj[:, x0 - x:x1 - x]
        out.append(f)
    return np.stack(out)


class SceneRuleTest(unittest.TestCase):
    def test_side_from_horizontal_motion(self):
        self.assertEqual(rule.predict_side(moving_block(+2), 20), "LEFT")
        self.assertEqual(rule.predict_side(moving_block(-2), 20), "RIGHT")

    def test_evasion_from_ego_speed(self):
        bg = textured(2, 90, 400)
        slow = np.stack([bg[:, 100:260]] * 30)
        fast = np.stack([bg[:, 20 + 4 * k:180 + 4 * k] for k in range(30)])
        self.assertEqual(rule.predict_evasion(slow, 20), 1)
        self.assertEqual(rule.predict_evasion(fast, 20), 0)

    def test_fallback_without_context(self):
        g = moving_block(+2)
        self.assertEqual(rule.predict_side(g, 0), rule.SIDE_FALLBACK)
        self.assertEqual(rule.predict_evasion(g, 0), rule.EVASION_FALLBACK)
        self.assertEqual(rule.predict_evasion(g, 1), rule.EVASION_FALLBACK)


if __name__ == "__main__":
    unittest.main()
