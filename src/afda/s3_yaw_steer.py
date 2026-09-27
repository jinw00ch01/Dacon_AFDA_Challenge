"""Stage 3 steering class from the image yaw proxy (Pro qa, follow-up to decision 1a07c3d2 / CLAUDE.md 12-D).

Per 10 Hz step k (frame k-1 -> k) the frames are resized to 160x120 gray and Farneback flow is computed with the
same parameters as scripts/pro_s3_motion/s3_motion_features.py. yaw_far = median horizontal flow in the far band
y in [0.25H, 0.47H) (horizon region, dominated by ego rotation). When the car turns LEFT the scene moves RIGHT
on screen, so yaw_far > 0 = LEFT, matching stage3_labels.POSITIVE_STEER_IS_LEFT (checked on 23 comma sources).
Step 0 copies step 1. The series is smoothed with a centred rolling mean of SMOOTH_W steps (offline, whole clip).
LEFT if > T_HI, RIGHT if < T_LO, else STRAIGHT. SMOOTH_W / T_LO / T_HI were chosen on the comma TRAIN split only
(work/s3_yaw_steer_r1, labels: stage3_labels default rule v1b).
Thresholds are in pixels at 160 px width, i.e. relative to the horizontal field of view of the clip.
"""
import cv2
import numpy as np

W, H = 160, 120
SMOOTH_W = 9
T_LO = -0.3031277992659145
T_HI = 0.19773931497501007
_FAR = slice(int(np.ceil(0.25 * H)), int(np.ceil(0.47 * H)))


def to_gray(frames):
    """frames: iterable of BGR uint8 images (any size) -> (N, 120, 160) uint8."""
    return np.stack([cv2.resize(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), (W, H), interpolation=cv2.INTER_AREA)
                     for f in frames])


def yaw_series(gray):
    """gray: (N, 120, 160) uint8 at 10 Hz -> (N,) float yaw_far; index 0 copies index 1."""
    n = len(gray)
    out = np.zeros(n, np.float64)
    for k in range(1, n):
        fl = cv2.calcOpticalFlowFarneback(gray[k - 1], gray[k], None, 0.5, 4, 15, 3, 5, 1.1, 0)
        out[k] = float(np.median(fl[_FAR, :, 0]))
    if n > 1:
        out[0] = out[1]
    return out


def smooth(x, w=SMOOTH_W):
    """centred rolling mean with shrinking edges (pandas rolling(w, center=True, min_periods=1))."""
    x = np.asarray(x, np.float64)
    h = w // 2
    return np.array([x[max(0, i - h):i + h + 1].mean() for i in range(len(x))])


def classify(yaw):
    s = smooth(yaw)
    return np.where(s > T_HI, "LEFT", np.where(s < T_LO, "RIGHT", "STRAIGHT"))


def predict_steer(frames, gray=False):
    """10 Hz clip frames (BGR list, or gray array if gray=True) -> array of LEFT/STRAIGHT/RIGHT per frame."""
    g = np.asarray(frames) if gray else to_gray(frames)
    if len(g) < 2:
        return np.array(["STRAIGHT"] * len(g))
    return classify(yaw_series(g))
