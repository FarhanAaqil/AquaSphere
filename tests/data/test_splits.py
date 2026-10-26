"""
Tests for leak-free data splitting and assertion rules (SIH 26066).
"""

import numpy as np
import pandas as pd
import pytest

from aquasphere.data.splits import (
    assert_no_leakage,
    ensure_float_id_column,
    extract_float_id,
    make_float_grouped_split,
    make_spatial_box_split,
    make_spatiotemporal_split,
)


@pytest.fixture
def mock_argo_df() -> pd.DataFrame:
    """Create a realistic mock Argo dataset with 10 floats across time."""
    records = []
    floats = [f"290{i:04d}" for i in range(1, 11)]
    dates = pd.date_range("2023-01-01", "2023-12-31", periods=100)

    idx = 0
    for i, flt in enumerate(floats):
        for cycle in range(1, 11):
            date = dates[idx % len(dates)]
            idx += 1
            lat = 10.0 + (i * 1.5) + (cycle * 0.1)
            lon = 60.0 + (i * 2.0) + (cycle * 0.1)
            records.append(
                {
                    "profile_id": f"{flt}_{cycle:03d}",
                    "date": date.strftime("%Y-%m-%d"),
                    "lat": lat,
                    "lon": lon,
                    "sst": 28.0 + np.sin(cycle),
                }
            )
    return pd.DataFrame(records)


def test_extract_float_id():
    assert extract_float_id("2903137_086") == "2903137"
    assert extract_float_id("6903140_327") == "6903140"
    assert extract_float_id("2903137") == "2903137"
    assert extract_float_id(5907082) == "5907082"


def test_ensure_float_id_column(mock_argo_df):
    df = ensure_float_id_column(mock_argo_df)
    assert "float_id" in df.columns
    assert df["float_id"].nunique() == 10

    # If float_id is already present, returns as-is
    df2 = ensure_float_id_column(df)
    assert "float_id" in df2.columns

    # If neither column is present, raises KeyError
    bad_df = pd.DataFrame({"some_col": [1, 2]})
    with pytest.raises(KeyError, match="Neither 'float_id' nor 'profile_id'"):
        ensure_float_id_column(bad_df)


def test_make_float_grouped_split_no_leakage(mock_argo_df):
    tr, va, te = make_float_grouped_split(
        mock_argo_df, train_ratio=0.7, val_ratio=0.15, test_ratio=0.15, seed=42
    )

    assert len(tr) + len(va) + len(te) == len(mock_argo_df)
    tr_floats = set(tr["float_id"].unique())
    va_floats = set(va["float_id"].unique())
    te_floats = set(te["float_id"].unique())

    assert len(tr_floats & va_floats) == 0
    assert len(tr_floats & te_floats) == 0
    assert len(va_floats & te_floats) == 0

    assert len(tr) > 0
    assert len(va) > 0
    assert len(te) > 0


def test_make_float_grouped_split_validation_errors(mock_argo_df):
    # Ratios not summing to 1.0
    with pytest.raises(ValueError, match=r"must sum to 1\.0"):
        make_float_grouped_split(mock_argo_df, train_ratio=0.5, val_ratio=0.2, test_ratio=0.2)

    # Fewer than 3 floats
    tiny_df = mock_argo_df[mock_argo_df["profile_id"].str.startswith("2900001")]
    with pytest.raises(ValueError, match="Need at least 3 unique floats"):
        make_float_grouped_split(tiny_df)


def test_make_spatiotemporal_split_quantile_and_dates(mock_argo_df):
    # Default quantile-based split
    tr, va, te = make_spatiotemporal_split(mock_argo_df, train_ratio=0.7, val_ratio=0.15, seed=42)
    assert len(tr) + len(va) + len(te) == len(mock_argo_df)
    tr_floats = set(tr["float_id"].unique())
    va_floats = set(va["float_id"].unique())
    te_floats = set(te["float_id"].unique())
    assert len(tr_floats & va_floats) == 0
    assert len(tr_floats & te_floats) == 0
    assert len(va_floats & te_floats) == 0

    # Explicit boundary dates
    tr2, va2, te2 = make_spatiotemporal_split(
        mock_argo_df,
        train_end_date="2023-06-30",
        val_end_date="2023-09-30",
        seed=42,
    )
    assert len(tr2) > 0
    assert len(va2) > 0
    assert len(te2) > 0


def test_assert_no_leakage_cases(mock_argo_df):
    df = ensure_float_id_column(mock_argo_df)

    # Case 1: Train & Val float leak
    tr = df[df["float_id"].isin(["2900001", "2900002"])]
    va = df[df["float_id"].isin(["2900002", "2900003"])]
    with pytest.raises(ValueError, match="between train and val"):
        assert_no_leakage(tr, va)

    # Case 2: Train & Test float leak
    te = df[df["float_id"].isin(["2900001", "2900004"])]
    va_clean = df[df["float_id"].isin(["2900003"])]
    with pytest.raises(ValueError, match="between train and test"):
        assert_no_leakage(tr, va_clean, te)

    # Case 3: Val & Test float leak
    tr_clean = df[df["float_id"].isin(["2900001"])]
    va_leak = df[df["float_id"].isin(["2900002"])]
    te_leak = df[df["float_id"].isin(["2900002"])]
    with pytest.raises(ValueError, match="between val and test"):
        assert_no_leakage(tr_clean, va_leak, te_leak)

    # Case 4: Row index overlap
    tr_row = pd.DataFrame({"float_id": ["f1"]}, index=[0])
    va_row = pd.DataFrame({"float_id": ["f2"]}, index=[0])
    with pytest.raises(ValueError, match="Duplicate rows detected"):
        assert_no_leakage(tr_row, va_row)

    # Case 5: Temporal leakage check
    tr_future = pd.DataFrame({"float_id": ["flt_1"], "date": ["2024-01-01"]}, index=[0])
    va_clean = pd.DataFrame({"float_id": ["flt_2"], "date": ["2023-06-01"]}, index=[1])
    te_past = pd.DataFrame({"float_id": ["flt_3"], "date": ["2023-01-01"]}, index=[2])
    with pytest.raises(ValueError, match="Temporal leakage detected"):
        assert_no_leakage(
            tr_future, va_clean, te_past, date_col="date", enforce_temporal_order=True
        )


def test_make_spatial_box_split(mock_argo_df):
    bbox = (12.0, 18.0, 60.0, 75.0)
    ext, inside = make_spatial_box_split(mock_argo_df, bbox=bbox)
    assert len(ext) + len(inside) == len(mock_argo_df)
    assert all((inside["lat"] >= 12.0) & (inside["lat"] <= 18.0))
    assert all((inside["lon"] >= 60.0) & (inside["lon"] <= 75.0))
