"""
Data splitting and leakage-prevention utilities for AquaSphere (SIH 26066).

Strictly enforces:
1. Float-grouped partitioning: every Argo float ID belongs to exactly one split.
2. Temporal hold-out: training on past observations, evaluating on future observations.
3. Spatial stress testing: holding out geographic boxes (e.g., Central Bay of Bengal).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Bounding box for secondary spatial stress test: Central Bay of Bengal
CENTRAL_BOB_BBOX: tuple[float, float, float, float] = (12.0, 18.0, 84.0, 92.0)


def extract_float_id(profile_id: str | int) -> str:
    """Extract WMO float identifier from a profile identifier string.

    Argo profiles are typically named '<float_id>_<cycle_number>',
    e.g. '2903137_086' -> '2903137'.
    """
    s = str(profile_id).strip()
    return s.split("_")[0] if "_" in s else s


def ensure_float_id_column(
    df: pd.DataFrame,
    profile_col: str = "profile_id",
    float_col: str = "float_id",
) -> pd.DataFrame:
    """Ensure dataframe has a dedicated float_id column, adding it if missing."""
    if float_col in df.columns:
        return df
    if profile_col in df.columns:
        df = df.copy()
        df[float_col] = df[profile_col].apply(extract_float_id)
        return df
    raise KeyError(
        f"Neither '{float_col}' nor '{profile_col}' found in columns: {list(df.columns)}"
    )


def assert_no_leakage(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame | None = None,
    group_col: str = "float_id",
    date_col: str | None = None,
    enforce_temporal_order: bool = False,
) -> None:
    """Assert that splits are completely leak-free.

    Raises ValueError if:
    1. Any group (float ID) is shared between any pairs of splits.
    2. Any DataFrame index is duplicated across splits.
    3. (If enforce_temporal_order is True) train dates exceed test dates.
    """
    train_groups = set(train_df[group_col].dropna().unique())
    val_groups = set(val_df[group_col].dropna().unique())

    # 1. Float overlap checks
    train_val_overlap = train_groups & val_groups
    if train_val_overlap:
        raise ValueError(
            f"Float leakage detected between train and val! "
            f"{len(train_val_overlap)} shared floats: {sorted(train_val_overlap)[:5]}"
        )

    if test_df is not None:
        test_groups = set(test_df[group_col].dropna().unique())
        train_test_overlap = train_groups & test_groups
        if train_test_overlap:
            raise ValueError(
                f"Float leakage detected between train and test! "
                f"{len(train_test_overlap)} shared floats: {sorted(train_test_overlap)[:5]}"
            )
        val_test_overlap = val_groups & test_groups
        if val_test_overlap:
            raise ValueError(
                f"Float leakage detected between val and test! "
                f"{len(val_test_overlap)} shared floats: {sorted(val_test_overlap)[:5]}"
            )

    # 2. Index disjointness check
    idx_tr = set(train_df.index)
    idx_va = set(val_df.index)
    if idx_tr & idx_va:
        raise ValueError("Duplicate rows detected between train and val sets.")
    if test_df is not None:
        idx_te = set(test_df.index)
        if (idx_tr & idx_te) or (idx_va & idx_te):
            raise ValueError("Duplicate rows detected across train/val and test sets.")

    # 3. Temporal order check
    if enforce_temporal_order and date_col is not None and test_df is not None:
        train_max_date = pd.to_datetime(train_df[date_col]).max()
        test_min_date = pd.to_datetime(test_df[date_col]).min()
        if train_max_date > test_min_date:
            raise ValueError(
                f"Temporal leakage detected: max train date ({train_max_date}) "
                f"> min test date ({test_min_date})"
            )


def make_float_grouped_split(
    df: pd.DataFrame,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    seed: int = 42,
    group_col: str = "float_id",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split data by float ID so that all profiles from any float stay in one split.

    Args:
        df: Input dataframe containing float profiles.
        train_ratio: Fraction of floats allocated to train.
        val_ratio: Fraction of floats allocated to validation.
        test_ratio: Fraction of floats allocated to test.
        seed: Random seed for deterministic reproducibility.
        group_col: Column name containing float identifiers.

    Returns:
        (train_df, val_df, test_df)
    """
    df = ensure_float_id_column(df, float_col=group_col)

    if not np.isclose(train_ratio + val_ratio + test_ratio, 1.0):
        raise ValueError("train_ratio, val_ratio, and test_ratio must sum to 1.0")

    unique_floats = np.array(sorted(df[group_col].dropna().unique()))
    n_floats = len(unique_floats)

    if n_floats < 3:
        raise ValueError(f"Need at least 3 unique floats to create 3-way split, got {n_floats}")

    rng = np.random.default_rng(seed)
    shuffled_floats = rng.permutation(unique_floats)

    n_train = max(1, round(train_ratio * n_floats))
    n_val = max(1, round(val_ratio * n_floats))

    # Ensure test gets at least 1 float if test_ratio > 0
    if test_ratio > 0 and (n_train + n_val >= n_floats):
        if n_train > n_val and n_train > 1:
            n_train -= 1
        elif n_val > 1:
            n_val -= 1

    train_floats = set(shuffled_floats[:n_train])
    val_floats = set(shuffled_floats[n_train : n_train + n_val])
    test_floats = set(shuffled_floats[n_train + n_val :])

    train_df = df[df[group_col].isin(train_floats)].copy()
    val_df = df[df[group_col].isin(val_floats)].copy()
    test_df = df[df[group_col].isin(test_floats)].copy()

    assert_no_leakage(train_df, val_df, test_df, group_col=group_col)

    logger.info(
        "Float-grouped split created: Train=%d (%d floats), Val=%d (%d floats), Test=%d (%d floats)",
        len(train_df),
        len(train_floats),
        len(val_df),
        len(val_floats),
        len(test_df),
        len(test_floats),
    )
    return train_df, val_df, test_df


def make_spatiotemporal_split(
    df: pd.DataFrame,
    date_col: str = "date",
    group_col: str = "float_id",
    train_end_date: str | None = None,
    val_end_date: str | None = None,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Create a time-blocked and float-grouped split.

    If train_end_date and val_end_date are provided and span the data range,
    allocates floats based on temporal boundaries.
    Otherwise, computes time-cutoff dates using quantiles and groups floats
    by their median profile timestamp to avoid temporal and float leakage.
    """
    df = ensure_float_id_column(df, float_col=group_col).copy()
    df[date_col] = pd.to_datetime(df[date_col])

    # If explicit boundary dates are not provided, determine by quantiles
    if train_end_date is None or val_end_date is None:
        dates_sorted = df[date_col].sort_values()
        q_train = train_ratio
        q_val = train_ratio + val_ratio
        t_split1 = dates_sorted.quantile(q_train)
        t_split2 = dates_sorted.quantile(q_val)
    else:
        t_split1 = pd.to_datetime(train_end_date)
        t_split2 = pd.to_datetime(val_end_date)

    # For each float, compute its median timestamp
    float_medians = df.groupby(group_col)[date_col].median()

    # Assign floats to partitions according to median timestamp
    train_floats = set(float_medians[float_medians <= t_split1].index)
    val_floats = set(float_medians[(float_medians > t_split1) & (float_medians <= t_split2)].index)
    test_floats = set(float_medians[float_medians > t_split2].index)

    # Ensure every split has at least one float if possible
    if not val_floats or not test_floats:
        # Fallback to float grouped split with temporal sort
        sorted_floats = float_medians.sort_values().index.tolist()
        n = len(sorted_floats)
        n_tr = max(1, round(n * train_ratio))
        n_va = max(1, round(n * val_ratio))
        if n_tr + n_va >= n:
            n_tr = max(1, n - 2)
            n_va = 1
        train_floats = set(sorted_floats[:n_tr])
        val_floats = set(sorted_floats[n_tr : n_tr + n_va])
        test_floats = set(sorted_floats[n_tr + n_va :])

    train_df = df[df[group_col].isin(train_floats)].copy()
    val_df = df[df[group_col].isin(val_floats)].copy()
    test_df = df[df[group_col].isin(test_floats)].copy()

    assert_no_leakage(train_df, val_df, test_df, group_col=group_col)

    return train_df, val_df, test_df


def make_spatial_box_split(
    df: pd.DataFrame,
    bbox: Sequence[float] = CENTRAL_BOB_BBOX,
    lat_col: str = "lat",
    lon_col: str = "lon",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Hold out a geographic bounding box [lat_min, lat_max, lon_min, lon_max].

    Returns:
        (train_exterior_df, held_out_box_df)
    """
    lat_min, lat_max, lon_min, lon_max = bbox
    in_box = (
        (df[lat_col] >= lat_min)
        & (df[lat_col] <= lat_max)
        & (df[lon_col] >= lon_min)
        & (df[lon_col] <= lon_max)
    )
    held_out_box = df[in_box].copy()
    exterior = df[~in_box].copy()
    return exterior, held_out_box
