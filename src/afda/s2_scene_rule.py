"""Stage 2 entry-side and evasion-space rules from motion (CLAUDE.md decision 12-C, Pro qa).

Input: the 10 Hz window frames of one Stage 2 video as 160x90 grayscale (afda.s2_motion_rule.to_gray) and the
window-relative collision index c (afda.s2_motion_rule.predict_collision). Farneback flow between consecutive
frames (same parameters as the collision rule) is average-pooled 10x10 to a 9x16 grid. Per step a global affine
model u = a + b*rx + c*ry, v = d + e*rx + f*ry (one refit on the 80 % smallest residuals) is removed; the
residual (ru, rv) is object motion relative to the ego-motion field.

Side (fixed a priori, no fitted threshold): over window frames [c-L, c] (L = 10 steps, chosen by FIT AUROC), the residual-energy-
weighted mean of ru in the lower-centre block (grid rows 3..8, cols 3..12). Positive = the object moves right
on screen = it came in from the LEFT (frame-labeler definition: judged on the dashcam screen).
Evasion: pre_mag = mean pooled flow magnitude over grid rows 4..8, frames [c-5, c-1] (ego speed proxy).
evasion_space = 1 if pre_mag <= EVASION_THR else 0. EVASION_THR was chosen on the FIT split only.
If there is no pre-collision context (c too small) the fallback is LEFT / evasion 1 (FIT majority classes).

Evaluation: work/s2_scene_rule_r1 (Pro); the rules use only the window frames of one video.
"""
import cv2
import numpy as np

GH, GW, POOL = 9, 16, 10
SIDE_L = 10
EVASION_L = 5
EVASION_THR = 1.721142750989563
SIDE_FALLBACK, EVASION_FALLBACK = "LEFT", 1

_RX = np.tile((np.arange(GW) + 0.5) / GW - 0.5, (GH, 1))
_RY = np.tile(((np.arange(GH) + 0.5) / GH - 0.5)[:, None], (1, GW))
_A = np.c_[np.ones(GH * GW), _RX.ravel(), _RY.ravel()]


def _pool(x):
    h, w = x.shape
    return x.reshape(h // POOL, POOL, w // POOL, POOL).mean((1, 3))


def _affine_resid(x):
    y = x.ravel()
    coef = np.linalg.lstsq(_A, y, rcond=None)[0]
    r = y - _A @ coef
    keep = np.abs(r) <= np.quantile(np.abs(r), 0.8)
    coef = np.linalg.lstsq(_A[keep], y[keep], rcond=None)[0]
    return (y - _A @ coef).reshape(GH, GW)


def _flow(gray, k):
    """pooled (u, v) of the flow into window frame k (k >= 1)."""
    fl = cv2.calcOpticalFlowFarneback(gray[k - 1], gray[k], None, 0.5, 3, 13, 3, 5, 1.1, 0)
    return _pool(fl[..., 0]).astype(np.float16).astype(np.float64), _pool(fl[..., 1]).astype(np.float16).astype(np.float64)


def _frames(c, lo, hi, n):
    return list(range(max(1, c + lo), min(n - 1, c + hi) + 1))


def side_feature(gray, c):
    ks = _frames(c, -SIDE_L, 0, len(gray))
    if not ks:
        return None
    num = den = 0.0
    for k in ks:
        u, v = _flow(gray, k)
        ru, rv = _affine_resid(u), _affine_resid(v)
        e = (ru ** 2 + rv ** 2)[3:, 3:13]
        num += float((ru[3:, 3:13] * e).sum())
        den += float(e.sum())
    return num / (den + 1e-9)


def evasion_feature(gray, c):
    ks = _frames(c, -EVASION_L, -1, len(gray))
    if not ks:
        return None
    mags = []
    for k in ks:
        u, v = _flow(gray, k)
        mags.append(float(np.mean(np.hypot(u[4:], v[4:]))))
    return float(np.mean(mags))


def predict_side(gray, collision_idx):
    x = side_feature(np.asarray(gray), int(collision_idx))
    return SIDE_FALLBACK if x is None else ("LEFT" if x > 0.0 else "RIGHT")


def predict_evasion(gray, collision_idx):
    x = evasion_feature(np.asarray(gray), int(collision_idx))
    return EVASION_FALLBACK if x is None else int(x <= EVASION_THR)
