"""Official AFDA competition scoring (user decision 10, sample_02~04.png).

Single source of truth for validation, checkpoint selection, and reporting
(CLAUDE.md decision 10). Legacy MAE / simple-mean numbers are auxiliary only.

    overall = 0.2 * S1 + 0.4 * S2 + 0.4 * S3

    S1 = macro-F1 over {ORIGINAL, RERECORDED}.

    S2 = 0.35 * collision Acc@0.3s
       + 0.35 * entry    Acc@0.3s
       + 0.15 * entry-direction macro-F1
       + 0.15 * evasion-space   macro-F1
      Acc@0.3s: share of videos whose predicted event time is within 0.3s of the
      ground-truth time. Frames are mapped to seconds per video (frame / fps);
      at 10fps this is +/-3 frames. This is a HIT-RATE, not MAE.

    S3 = 0.7 * accel macro-F1 + 0.3 * steer macro-F1.
      The steer term drops rows whose TRUE accel label is STOPPED (evaluation.md).

Implemented in pure Python (no numpy) so the module and its tests run under the
GitHub CI contract job (which installs only psutil). The macro-F1 convention
(denominator 2*tp+fp+fn, F1=0 when the denominator is 0, unweighted mean over a
FIXED label set) matches scripts/train_stage3.py:macro_f1 exactly.
"""
from __future__ import annotations

from typing import Optional, Sequence, Union

# Fixed label sets. Mirror scripts/afda/stage3_labels.py; kept local so this
# module has no heavy imports and stays CI-safe.
S1_CLASSES = ("ORIGINAL", "RERECORDED")
ACCEL_CLASSES = ("ACCELERATING", "DECELERATING", "CONSTANT", "STOPPED")
STEER_CLASSES = ("LEFT", "STRAIGHT", "RIGHT")
STOPPED_LABEL = "STOPPED"

# Official scoring constants.
TOL_SECONDS = 0.3
W_S1, W_S2, W_S3 = 0.2, 0.4, 0.4
S2_W_COLLISION, S2_W_ENTRY, S2_W_DIR, S2_W_EVASION = 0.35, 0.35, 0.15, 0.15
S3_W_ACCEL, S3_W_STEER = 0.7, 0.3

Number = Union[int, float]


def macro_f1(y_true: Sequence, y_pred: Sequence, labels: Sequence) -> float:
    """Unweighted mean of per-class F1 over ``labels`` (a fixed set).

    F1 for a class = 2*tp / (2*tp + fp + fn), and 0.0 when that denominator is 0
    (matches scripts/train_stage3.py). ``labels`` is fixed so absent classes
    still count as 0 and never inflate the mean.
    """
    y_true = list(y_true)
    y_pred = list(y_pred)
    if len(y_true) != len(y_pred):
        raise ValueError(f"length mismatch: {len(y_true)} true vs {len(y_pred)} pred")
    if not labels:
        raise ValueError("labels must be non-empty")
    f1s = []
    for c in labels:
        tp = fp = fn = 0
        for t, p in zip(y_true, y_pred):
            if p == c and t == c:
                tp += 1
            elif p == c and t != c:
                fp += 1
            elif p != c and t == c:
                fn += 1
        denom = 2 * tp + fp + fn
        f1s.append(0.0 if denom == 0 else 2 * tp / denom)
    return sum(f1s) / len(f1s)


def stage1_score(y_true: Sequence, y_pred: Sequence,
                 labels: Sequence = S1_CLASSES) -> float:
    """S1 = macro-F1 over {ORIGINAL, RERECORDED}."""
    return macro_f1(y_true, y_pred, labels)


def frame_to_seconds(frame: Number, fps: Number) -> float:
    """Map a frame index to seconds. fps must be > 0."""
    if fps is None or fps <= 0:
        raise ValueError(f"fps must be > 0, got {fps!r}")
    return float(frame) / float(fps)


def accuracy_within(pred_times: Sequence[Optional[Number]],
                    gt_times: Sequence[Optional[Number]],
                    tol: float = TOL_SECONDS) -> float:
    """Acc@tol over videos whose ground-truth time is defined (not None).

    Both sequences are in SECONDS. A video with gt_time None (no such event) is
    excluded from the denominator. A hit needs a non-None prediction within tol.
    Returns 0.0 when no video has a defined ground truth.
    """
    if len(pred_times) != len(gt_times):
        raise ValueError(f"length mismatch: {len(pred_times)} pred vs {len(gt_times)} gt")
    n = 0
    hit = 0
    for p, g in zip(pred_times, gt_times):
        if g is None:
            continue
        n += 1
        if p is not None and abs(float(p) - float(g)) <= tol:
            hit += 1
    return hit / n if n else 0.0


def accuracy_within_frames(pred_frames: Sequence[Optional[Number]],
                           gt_frames: Sequence[Optional[Number]],
                           fps: Union[Number, Sequence[Number]],
                           tol: float = TOL_SECONDS) -> float:
    """Acc@tol from per-video frame indices. ``fps`` is a scalar or per-video list."""
    n = len(gt_frames)
    if isinstance(fps, (list, tuple)):
        if len(fps) != n:
            raise ValueError(f"fps length {len(fps)} != {n} videos")
        fps_list = list(fps)
    else:
        fps_list = [fps] * n
    pred_t = [None if f is None else frame_to_seconds(f, r)
              for f, r in zip(pred_frames, fps_list)]
    gt_t = [None if f is None else frame_to_seconds(f, r)
            for f, r in zip(gt_frames, fps_list)]
    return accuracy_within(pred_t, gt_t, tol)


def stage2_score(collision_acc: float, entry_acc: float,
                 dir_f1: float, evasion_f1: float) -> float:
    """S2 weighted sum of the four official components (each already computed)."""
    return (S2_W_COLLISION * collision_acc + S2_W_ENTRY * entry_acc
            + S2_W_DIR * dir_f1 + S2_W_EVASION * evasion_f1)


def stage3_score(accel_true: Sequence, accel_pred: Sequence,
                 steer_true: Sequence, steer_pred: Sequence,
                 stopped_label: str = STOPPED_LABEL,
                 accel_labels: Sequence = ACCEL_CLASSES,
                 steer_labels: Sequence = STEER_CLASSES) -> float:
    """S3 = 0.7*accel macro-F1 + 0.3*steer macro-F1 (steer drops TRUE STOPPED rows)."""
    if not (len(accel_true) == len(accel_pred) == len(steer_true) == len(steer_pred)):
        raise ValueError("accel/steer true/pred must all be the same length")
    accel_f1 = macro_f1(accel_true, accel_pred, accel_labels)
    kept_true = []
    kept_pred = []
    for at, st, sp in zip(accel_true, steer_true, steer_pred):
        if at != stopped_label:
            kept_true.append(st)
            kept_pred.append(sp)
    steer_f1 = macro_f1(kept_true, kept_pred, steer_labels) if kept_true else 0.0
    return S3_W_ACCEL * accel_f1 + S3_W_STEER * steer_f1


def overall_score(s1: float, s2: float, s3: float) -> float:
    """overall = 0.2*S1 + 0.4*S2 + 0.4*S3."""
    return W_S1 * s1 + W_S2 * s2 + W_S3 * s3
