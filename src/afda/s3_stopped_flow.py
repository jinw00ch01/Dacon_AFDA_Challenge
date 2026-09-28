"""Stage 3 STOPPED from image motion (Pro qa, decision 12-D follow-up). OR-override on the accel head.

Same 160x120 gray and Farneback call as src/afda/s3_yaw_steer.py, so the submission can take all three per-step
values (yaw_far, div_far, mag_all) from ONE flow field per 10 Hz step (no extra flow cost).
  div_far = mean radial divergence (u*rx + v*ry) / (rx^2 + ry^2 + 1) * W in y in [0.30H, 0.50H)
            (FOE assumed at (0.5W, 0.47H)); ~0 when the car does not move forward.
  mag_all = median |flow| above the hood (y < 0.74H); guards against high-speed flow failure, where div_far also
            collapses to ~0 on fast textureless highway (seen on comma test SRC021 at ~31 m/s).
Step 0 copies step 1. div_far is smoothed with a centred rolling mean of 15 steps, mag_all with 5 steps.
STOPPED if div_far_s15 <= A_DIVFAR and mag_all_s5 <= B_MAGALL. A/B were chosen on the comma TRAIN split only
(max STOPPED F1, work/s3_stopped_flow_r3; labels: stage3_labels default rule v1b).
"""
import cv2
import numpy as np

W, H = 160, 120
A_DIVFAR = 0.18678625586132247
B_MAGALL = 0.11957117766141878
SMOOTH_DIVFAR = 15
SMOOTH_MAGALL = 5
_FAR = slice(int(np.ceil(0.25 * H)), int(np.ceil(0.47 * H)))
_yy, _xx = np.mgrid[0:H, 0:W].astype(np.float32)
_rx, _ry = _xx - W / 2, _yy - 0.47 * H
_r2 = _rx ** 2 + _ry ** 2 + 1.0
_FARB = (_yy >= 0.30 * H) & (_yy < 0.50 * H)
_ABOVE_HOOD = _yy < 0.74 * H


def step_values(flow):
    """Farneback flow (120, 160, 2) of one 10 Hz step -> (yaw_far, div_far, mag_all)."""
    u, v = flow[..., 0], flow[..., 1]
    return (float(np.median(u[_FAR])),
            float(np.mean(((u * _rx + v * _ry) / _r2)[_FARB]) * W),
            float(np.median(np.hypot(u, v)[_ABOVE_HOOD])))


def motion_series(gray):
    """gray: (N, 120, 160) uint8 at 10 Hz -> (N, 3) float [yaw_far, div_far, mag_all]; row 0 copies row 1."""
    n = len(gray)
    out = np.zeros((n, 3), np.float64)
    for k in range(1, n):
        fl = cv2.calcOpticalFlowFarneback(gray[k - 1], gray[k], None, 0.5, 4, 15, 3, 5, 1.1, 0)
        out[k] = step_values(fl)
    if n > 1:
        out[0] = out[1]
    return out


def smooth(x, w):
    """centred rolling mean with shrinking edges (pandas rolling(w, center=True, min_periods=1))."""
    x = np.asarray(x, np.float64)
    h = w // 2
    return np.array([x[max(0, i - h):i + h + 1].mean() for i in range(len(x))])


def stopped_mask(div_far, mag_all):
    return (smooth(div_far, SMOOTH_DIVFAR) <= A_DIVFAR) & (smooth(mag_all, SMOOTH_MAGALL) <= B_MAGALL)


def predict_stopped(gray):
    """10 Hz gray clip -> bool array, True = STOPPED (override the accel class)."""
    g = np.asarray(gray)
    if len(g) < 2:
        return np.zeros(len(g), bool)
    m = motion_series(g)
    return stopped_mask(m[:, 1], m[:, 2])
