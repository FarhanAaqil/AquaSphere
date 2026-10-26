"""
Unit tests for Argo profile PCHIP interpolation and depth masking (SIH 26066).
"""

from pathlib import Path

import numpy as np
import pytest

from aquasphere.constants import DEPTH_COLS, STANDARD_DEPTHS
from aquasphere.data.argo import MASK_COLS, interpolate_profile_pchip, process_legacy_argo_csv


def test_interpolate_profile_pchip_full_depth():
    # Observation depths spanning 0 to 1000 m
    obs_z = [0.0, 10.0, 30.0, 75.0, 150.0, 300.0, 700.0, 1000.0]
    obs_t = [29.0, 28.8, 28.0, 23.0, 17.0, 11.0, 8.0, 6.5]

    t_interp, mask = interpolate_profile_pchip(obs_z, obs_t, standard_depths=STANDARD_DEPTHS)

    assert len(t_interp) == 15
    assert len(mask) == 15
    # All 15 standard depths lie within [0, 1000]
    assert np.all(mask)
    assert not np.any(np.isnan(t_interp))
    # Monotonic decrease in temperature
    assert np.all(np.diff(t_interp) <= 0.0)


def test_interpolate_profile_pchip_shallow_profile():
    # Profile only reaching 200 m depth
    obs_z = [5.0, 20.0, 50.0, 100.0, 200.0]
    obs_t = [28.5, 28.2, 26.0, 21.0, 15.0]

    t_interp, mask = interpolate_profile_pchip(
        obs_z, obs_t, standard_depths=STANDARD_DEPTHS, max_surface_extrapolate_m=10.0
    )

    # 0m should be valid due to surface extrapolation from 5m
    assert mask[STANDARD_DEPTHS.index(0)]
    assert np.isclose(t_interp[0], 28.5)

    # Depths <= 200m should be valid
    for d in [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200]:
        idx = STANDARD_DEPTHS.index(d)
        assert mask[idx], f"Depth {d}m should be masked valid"
        assert not np.isnan(t_interp[idx])

    # Depths > 200m (300, 500, 700, 1000m) should be unobserved (False mask, NaN value)
    for d in [300, 500, 700, 1000]:
        idx = STANDARD_DEPTHS.index(d)
        assert not mask[idx], f"Depth {d}m should be masked invalid"
        assert np.isnan(t_interp[idx])


def test_interpolate_profile_pchip_insufficient_data():
    # Only 1 valid observation depth
    t_interp, mask = interpolate_profile_pchip([10.0], [25.0])
    assert not np.any(mask)
    assert np.all(np.isnan(t_interp))


def test_process_legacy_argo_csv(tmp_path: Path):
    legacy_csv = Path("data/argo_sst_training.csv")
    if not legacy_csv.exists():
        pytest.skip("Legacy CSV not found")

    out_parquet = tmp_path / "argo_profiles.parquet"
    df = process_legacy_argo_csv(legacy_csv, output_parquet=out_parquet)

    assert out_parquet.exists()
    assert len(df) == 2253
    assert "float_id" in df.columns
    assert "cycle" in df.columns
    for c in DEPTH_COLS:
        assert c in df.columns
    for m in MASK_COLS:
        assert m in df.columns
