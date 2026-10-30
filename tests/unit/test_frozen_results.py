"""Results files only change on purpose: their hashes must match docs/results/frozen_results.json
(re-run scripts/freeze_results.py after a deliberate re-evaluation)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FROZEN = ROOT / "docs" / "results" / "frozen_results.json"


def test_results_match_their_frozen_hashes() -> None:
    if not FROZEN.exists():
        pytest.skip("results not frozen yet")
    sys.path.insert(0, str(ROOT / "scripts"))
    from freeze_results import current

    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))["sha256"]
    now = current()
    changed = sorted(k for k in frozen if now.get(k) != frozen[k])
    added = sorted(set(now) - set(frozen))
    assert changed == [], f"results changed without re-freezing: {changed}"
    assert added == [], f"new results files not frozen: {added}"
