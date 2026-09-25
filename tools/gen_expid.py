#!/usr/bin/env python
"""Print a fresh experiment id (exp-<32 hex>) for AFDA experiment packets."""
import uuid

print("exp-" + uuid.uuid4().hex)
