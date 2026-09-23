"""Submission contracts inferred from the supplied competition baseline.

No score is computed here: official timestamp tolerance details are not supplied
as readable text and sparse public examples are not a validation benchmark.
"""
import math

SCHEMAS = {
    "stage1": ["ID", "answer"],
    "stage2": ["ID", "collision_frame", "entry_frame", "evasion_space", "entry_side"],
    "stage3": ["ID", "sample_index", "accel_label", "steer_label"],
}
ACCEL = {"ACCELERATING", "DECELERATING", "CONSTANT", "STOPPED"}
STEER = {"LEFT", "STRAIGHT", "RIGHT"}


def integer(value):
    if isinstance(value, bool):
        raise ValueError("Boolean is not a frame/index")
    try:
        number = float(value)
    except (ValueError, TypeError):
        raise ValueError(f"Not numeric: {value!r}") from None
    if not math.isfinite(number) or number < 0 or not number.is_integer():
        raise ValueError(f"Expected nonnegative integer: {value!r}")
    return int(number)


def validate(stage, columns, rows, expected):
    """expected: ID -> frame-number list (S2), sample count (S3), null (S1)."""
    if list(columns) != SCHEMAS[stage]:
        raise ValueError(f"{stage}: columns must be {SCHEMAS[stage]}")
    if not expected:
        raise ValueError("Expected-input manifest must not be empty")
    if stage == "stage3" and any(integer(count) == 0 for count in expected.values()):
        raise ValueError("Stage 3 expected videos must contain samples")
    if stage == "stage2":
        for numbers in expected.values():
            if not isinstance(numbers, list) or not numbers or len({integer(n) for n in numbers}) != len(numbers):
                raise ValueError("Stage 2 expected original frame numbers must be nonempty and unique")
    seen = set()
    per_id = {key: set() for key in expected}
    for row in rows:
        identity = row["ID"]
        if identity not in expected:
            raise ValueError(f"Unknown ID: {identity}")
        key = (identity, integer(row["sample_index"])) if stage == "stage3" else identity
        if key in seen:
            raise ValueError(f"Duplicate prediction: {key}")
        seen.add(key)
        if stage == "stage1":
            if row["answer"] not in {"ORIGINAL", "RERECORDED"}:
                raise ValueError("Invalid Stage 1 class")
        elif stage == "stage2":
            for field in ("collision_frame", "entry_frame"):
                if integer(row[field]) not in expected[identity]:
                    raise ValueError(f"{identity}: {field} not in original frame numbers")
            if integer(row["evasion_space"]) not in {0, 1} or row["entry_side"] not in {"LEFT", "RIGHT"}:
                raise ValueError("Invalid Stage 2 class")
        else:
            index = integer(row["sample_index"])
            if index >= integer(expected[identity]):
                raise ValueError("Stage 3 sample_index outside video")
            per_id[identity].add(index)
            if row["accel_label"] not in ACCEL or row["steer_label"] not in STEER:
                raise ValueError("Invalid Stage 3 class (steer required even if STOPPED)")
    if stage == "stage3":
        for identity, indices in per_id.items():
            if len(indices) != integer(expected[identity]):
                raise ValueError(f"{identity}: missing Stage 3 samples")
    elif seen != set(expected):
        raise ValueError("Missing prediction IDs")
    return {"stage": stage, "rows": len(seen), "ids": len(expected), "valid": True}
