"""Shared domain constants used across the aquasphere package."""

from __future__ import annotations

# Geographic domain — North Indian Ocean
LAT_MIN: float = 5.0
LAT_MAX: float = 30.0
LON_MIN: float = 45.0
LON_MAX: float = 105.0

# Standard Argo interpolation depths (m)
STANDARD_DEPTHS: list[int] = [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000]

N_DEPTHS: int = len(STANDARD_DEPTHS)

# Depth column names used in DataFrames / CSVs
DEPTH_COLS: list[str] = [f"t_{d}" for d in STANDARD_DEPTHS]

# Depth observation mask column names (1 = observed, 0 = missing)
MASK_COLS: list[str] = [f"m_{d}" for d in STANDARD_DEPTHS]

# Depth groups for summary tables (label → list[depth_m])
DEPTH_GROUPS: dict[str, list[int]] = {
    "0\u201330 m": [0, 5, 10, 20, 30],
    "50\u2013150 m": [50, 75, 100, 125, 150],
    "200\u2013300 m": [200, 300],
    "500\u20131000 m": [500, 700, 1000],
}

# Temporal split boundaries (train ≤ VAL_YEAR-1, val == VAL_YEAR, test ≥ TEST_YEAR_START)
TRAIN_END_YEAR: int = 2022
VAL_YEAR: int = 2023
TEST_YEAR_START: int = 2024
