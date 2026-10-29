"""The frozen hypotheses file keeps the blueprint's thresholds and confirmatory family."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

FILE = Path(__file__).resolve().parents[2] / "docs" / "hypotheses.yaml"


@pytest.fixture(scope="module")
def doc() -> dict:  # type: ignore[type-arg]
    if not FILE.exists():
        pytest.skip("docs/hypotheses.yaml not frozen yet")
    return yaml.safe_load(FILE.read_text(encoding="utf-8"))


def test_status_and_family(doc: dict) -> None:  # type: ignore[type-arg]
    assert doc["status"] == "frozen"
    assert doc["protocol"]["multiple_testing"] == {
        "method": "holm",
        "family": ["H1a", "H1b", "H2", "H3", "H4"],
    }
    assert set(doc["confirmatory"]) == {"H1a", "H1b", "H2", "H3", "H4"}


def test_thresholds_are_the_blueprint_values(doc: dict) -> None:  # type: ignore[type-arg]
    c = doc["confirmatory"]
    assert c["H1a"]["threshold"] == {"relative_reduction_min": 0.15}
    assert c["H1b"]["threshold"] == {"ratio_min": 0.85}
    assert c["H2"]["threshold"] == {
        "relative_reduction_full_labels_min": 0.05,
        "relative_reduction_10pct_labels_min": 0.10,
    }
    assert c["H3"]["threshold"] == {"overall_band": [0.87, 0.93], "per_stratum_band": [0.85, 0.95]}
    assert c["H4"]["threshold"] == {"relative_gap_min": 0.20}


def test_protocol_matches_the_code(doc: dict) -> None:  # type: ignore[type-arg]
    from aquasphere.eval.protocol import PERIODS

    p = doc["protocol"]["periods"]
    assert p["train"] == list(PERIODS["train"])
    assert p["validation"] == list(PERIODS["val"])
    assert p["test"] == list(PERIODS["test"])
