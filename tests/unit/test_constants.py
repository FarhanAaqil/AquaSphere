"""Smoke tests for aquasphere.constants — run with `pytest tests/unit/`."""

from __future__ import annotations

from aquasphere.constants import (
    DEPTH_COLS,
    DEPTH_GROUPS,
    LAT_MAX,
    LAT_MIN,
    LON_MAX,
    LON_MIN,
    N_DEPTHS,
    STANDARD_DEPTHS,
    TEST_YEAR_START,
    TRAIN_END_YEAR,
    VAL_YEAR,
)


def test_standard_depths_count() -> None:
    """Exactly 15 standard depths as per the problem statement."""
    assert N_DEPTHS == 15
    assert len(STANDARD_DEPTHS) == 15


def test_standard_depths_sorted() -> None:
    """Depths must be monotonically increasing (0 → 1000 m)."""
    assert STANDARD_DEPTHS == sorted(STANDARD_DEPTHS)


def test_standard_depths_bounds() -> None:
    assert STANDARD_DEPTHS[0] == 0
    assert STANDARD_DEPTHS[-1] == 1000


def test_depth_cols_match_depths() -> None:
    """Column names must be t_{depth} for every standard depth."""
    assert DEPTH_COLS == [f"t_{d}" for d in STANDARD_DEPTHS]
    assert len(DEPTH_COLS) == N_DEPTHS


def test_depth_groups_cover_all_depths() -> None:
    """Every standard depth appears in exactly one group."""
    all_grouped = [d for depths in DEPTH_GROUPS.values() for d in depths]
    assert sorted(all_grouped) == sorted(STANDARD_DEPTHS)
    # Check no duplicates
    assert len(all_grouped) == len(set(all_grouped))


def test_domain_bounds() -> None:
    """Domain must match SIH 26066 spec: 5-30 N, 45-105 E."""
    assert LAT_MIN == 5.0
    assert LAT_MAX == 30.0
    assert LON_MIN == 45.0
    assert LON_MAX == 105.0


def test_split_years_ordered() -> None:
    """Split boundary years must be strictly increasing."""
    assert TRAIN_END_YEAR < VAL_YEAR < TEST_YEAR_START


def test_split_years_no_overlap() -> None:
    """Train ends before val starts; val ends before test starts."""
    assert VAL_YEAR == TRAIN_END_YEAR + 1
    assert TEST_YEAR_START == VAL_YEAR + 1
