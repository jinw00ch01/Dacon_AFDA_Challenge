"""AFDA shared decode/preprocess/model modules for training and inference.

The submission ``inference.py`` ships as a self-contained file (only the
model/ and requirements.txt travel in the ZIP), so it inlines the same
numeric preprocessing that lives here. ``tests/test_afda.py`` asserts the two
copies stay byte-for-byte equivalent on synthetic input to prevent drift.

Nothing here trains or scores a model; these are the shared building blocks.
"""

from . import preprocess, models

__all__ = ["preprocess", "models"]
