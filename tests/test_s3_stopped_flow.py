"""Stage 3 STOPPED-from-motion rule (Pro qa, decision 12-D follow-up)."""
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
from afda import s3_stopped_flow as sf  # noqa: E402
from afda import s3_yaw_steer as ys  # noqa: E402


def texture():
    rng = np.random.RandomState(0)
    base = rng.randint(0, 255, (90, 120), np.uint8)
    return cv2.GaussianBlur(cv2.resize(base, (480, 360), interpolation=cv2.INTER_CUBIC), (3, 3), 0)


def zooming(rate, n=24):
    """textured scene expanding about the assumed FOE by `rate` per frame (forward motion) at 160x120."""
    big = texture()
    out = []
    for k in range(n):
        s = 1.0 + rate * k
        m = cv2.getRotationMatrix2D((240.0, 0.47 * 360), 0.0, s)
        out.append(cv2.resize(cv2.warpAffine(big, m, (480, 360)), (160, 120), interpolation=cv2.INTER_AREA))
    return np.stack(out)


class StoppedFlowTest(unittest.TestCase):
    def test_static_is_stopped_and_forward_is_not(self):
        still = np.stack([cv2.resize(texture(), (160, 120), interpolation=cv2.INTER_AREA)] * 20)
        self.assertTrue(np.all(sf.predict_stopped(still)))
        self.assertFalse(np.any(sf.predict_stopped(zooming(0.03))))

    def test_shared_flow_matches_yaw_rule(self):
        g = zooming(0.02, 12)
        self.assertTrue(np.allclose(sf.motion_series(g)[:, 0], ys.yaw_series(g)))

    def test_short_clips(self):
        self.assertEqual(list(sf.predict_stopped(zooming(0.02, 1))), [False])
        self.assertEqual(len(sf.predict_stopped(zooming(0.02, 5))), 5)


if __name__ == "__main__":
    unittest.main()
