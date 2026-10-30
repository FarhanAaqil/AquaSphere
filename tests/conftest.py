"""Test-wide settings, applied before any test module imports the app."""

from __future__ import annotations

import os
from pathlib import Path

# The app tests assert v1 contract details (CI has no checkpoints at all). A locally trained
# protocol v2 checkpoint must not change what they test; tests/api/test_engine_v2.py covers v2.
os.environ["AQUASPHERE_CHECKPOINT_V2"] = str(
    Path(__file__).parent / "fixtures" / "no_v2_checkpoint_in_tests.pt"
)
