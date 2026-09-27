"""Stage 2 collision-time rule from global camera motion (CLAUDE.md decision 12-A, Pro qa).

Input: the 10 Hz window frames of one Stage 2 video (official format: 50 frames). Each frame is resized to
160x90 grayscale (INTER_AREA). For each step k (frame k-1 -> k) Farneback optical flow gives
  div_k    mean radial expansion (u*rx + v*ry) / (rx^2 + ry^2 + 1) around the image centre
  dy_k     median vertical flow
Score (per window, each series 3-tap smoothed and z-scored):
  z(div_drop) + z(jerk_y),  div_drop_k = div_{k-1} - div_k,  jerk_y_k = |dy_k - dy_{k-1}|
Collision frame = argmax(score) + LAG (clipped to the window). Entry candidate (decision 12-B, not yet
adopted) = collision - ENTRY_K.

Parameters were chosen only on the FIT split (82 videos, agent labels) in Pro's evaluation
(work/s2_motion_rule_r1, random collision position U{0..49}); the rule sees only the window frames and uses
no statistics across evaluation files.
"""
import cv2
import numpy as np

SIZE = (160, 90)
LAG = -2
ENTRY_K = 8
SCORES = ("div_drop", "jerk_y")


def to_gray(frames):
    """frames: iterable of BGR uint8 images (any size) -> (N, 90, 160) uint8."""
    return np.stack([cv2.cvtColor(cv2.resize(f, SIZE, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
                     for f in frames])


def motion_series(gray):
    """gray: (N, H, W) uint8 -> dict of (N,) float32 arrays for div and dy; index 0 copies index 1."""
    n, h, w = gray.shape
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    rx, ry = xs - w / 2, ys - h / 2
    r2 = rx ** 2 + ry ** 2 + 1.0
    div, dy = np.zeros(n, np.float32), np.zeros(n, np.float32)
    for k in range(1, n):
        fl = cv2.calcOpticalFlowFarneback(gray[k - 1], gray[k], None, 0.5, 3, 13, 3, 5, 1.1, 0)
        u, v = fl[..., 0], fl[..., 1]
        dy[k] = float(np.median(v))
        div[k] = float(np.mean((u * rx + v * ry) / r2))
    if n > 1:
        div[0], dy[0] = div[1], dy[1]
    return {"div": div, "dy": dy}


def _smooth3(x):
    return np.convolve(np.pad(x, 1, mode="edge"), np.ones(3) / 3, mode="valid")


def _z(x):
    return (x - x.mean()) / (x.std() + 1e-6)


def collision_score(series):
    div, dy = series["div"], series["dy"]
    div_drop = -np.diff(div, prepend=div[0])
    jerk_y = np.abs(np.diff(dy, prepend=dy[0]))
    return _z(_smooth3(div_drop)) + _z(_smooth3(jerk_y))


def predict_collision(frames, gray=False):
    """Window-relative collision frame index for one video (frames: BGR list, or gray array if gray=True)."""
    g = np.asarray(frames) if gray else to_gray(frames)
    if len(g) < 3:
        return 0
    return int(np.clip(int(np.argmax(collision_score(motion_series(g)))) + LAG, 0, len(g) - 1))


def predict_entry(collision_idx):
    """Decision 12-B candidate: collision minus the FIT-median lead; per-video because collision is."""
    return int(max(0, collision_idx - ENTRY_K))
