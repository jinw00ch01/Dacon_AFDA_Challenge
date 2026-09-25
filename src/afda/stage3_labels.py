"""Stage 3 proxy-rule label generation (adopted rule s3_proxy_rule_v1b).

Turns the 10Hz auxiliary comma sensors (speed / steering / acceleration proxy)
into the four accel classes and three steer classes used as *proxy* training
targets. These are NOT official competition ground truth (AGENTS.md); every row
carries label_kind=continuous_auxiliary_not_official_gt upstream.

The rule is: per source, smooth each signal with a centered moving average of
`window` samples, then
  accel: speed < v_stop -> STOPPED
         accel > +a_db  -> ACCELERATING
         accel < -a_db  -> DECELERATING
         else           -> CONSTANT
  steer: centered = steer - bias; STOPPED rows are steer-masked to STRAIGHT.
         centered > +s_th -> (sign convention) ; centered < -s_th -> other ; else STRAIGHT

scripts/verify_s3_labels.py reproduces the published per-split class counts in
the release rule JSON, which pins down the smoothing/edge handling and the steer
sign convention empirically.
"""
from __future__ import annotations

ACCEL_CLASSES = ["ACCELERATING", "DECELERATING", "CONSTANT", "STOPPED"]
STEER_CLASSES = ["LEFT", "STRAIGHT", "RIGHT"]

# Positive centered steering angle means a LEFT turn under this rule's convention.
# scripts/verify_s3_labels.py confirms this: accel counts reproduce the released
# v1b counts exactly on all splits, and steer LEFT/RIGHT match exactly on test and
# validation (train differs by a single boundary row, ~0.01%, from a rolling-mean
# edge tie near +-s_th). The real-world sign is still pending video confirmation
# (docs/STATUS.md); these remain proxy targets, not official ground truth.
POSITIVE_STEER_IS_LEFT = True

DEFAULT_RULE = {"window": 5, "v_stop": 0.5, "a_db": 0.2, "s_th": 4.5, "bias": -0.3}


def classify_accel(speed_ma: float, accel_ma: float, v_stop: float, a_db: float) -> str:
    if speed_ma < v_stop:
        return "STOPPED"
    if accel_ma > a_db:
        return "ACCELERATING"
    if accel_ma < -a_db:
        return "DECELERATING"
    return "CONSTANT"


def classify_steer(steer_ma: float, bias: float, s_th: float, stopped: bool) -> str:
    if stopped:
        return "STRAIGHT"
    centered = steer_ma - bias
    if centered > s_th:
        return "LEFT" if POSITIVE_STEER_IS_LEFT else "RIGHT"
    if centered < -s_th:
        return "RIGHT" if POSITIVE_STEER_IS_LEFT else "LEFT"
    return "STRAIGHT"


def add_labels(df, rule=None):
    """Return a copy of `df` with accel_label / steer_label proxy columns.

    `df` must have source_id, speed_mps, steering_angle_deg,
    acceleration_mps2_proxy. Smoothing is grouped per source_id so windows never
    span two recordings.
    """
    rule = {**DEFAULT_RULE, **(rule or {})}
    window = int(rule["window"])
    out = df.copy()

    def smooth(series):
        return series.rolling(window, center=True, min_periods=1).mean()

    grouped = out.groupby("source_id", sort=False)
    speed_ma = grouped["speed_mps"].transform(smooth)
    accel_ma = grouped["acceleration_mps2_proxy"].transform(smooth)
    steer_ma = grouped["steering_angle_deg"].transform(smooth)

    accel, steer = [], []
    for s_ma, a_ma, st_ma in zip(speed_ma, accel_ma, steer_ma):
        a = classify_accel(s_ma, a_ma, rule["v_stop"], rule["a_db"])
        accel.append(a)
        steer.append(classify_steer(st_ma, rule["bias"], rule["s_th"], a == "STOPPED"))
    out["accel_label"] = accel
    out["steer_label"] = steer
    return out
