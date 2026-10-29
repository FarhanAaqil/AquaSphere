"""Collocation with the real store: exact bilinear sampling, coastal fallback, honest gaps."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from aquasphere.data.collocate_nio import collocate, sample_bilinear
from aquasphere.data.store import (
    DEFAULT_LAT_GRID,
    DEFAULT_LON_GRID,
    SATELLITE_VARS,
    SurfaceZarrStore,
)

LAT = DEFAULT_LAT_GRID.astype(np.float64)
LON = DEFAULT_LON_GRID.astype(np.float64)


def _linear(a: float = 0.3, b: float = 0.02) -> np.ndarray:
    return 20.0 + a * LAT[:, None] + b * LON[None, :]


def test_bilinear_is_exact_for_linear_fields() -> None:
    lats = np.array([5.0, 12.37, 29.99, 17.5])
    lons = np.array([45.0, 66.61, 104.9, 80.125])
    got = sample_bilinear(_linear(), LAT, LON, lats, lons)
    np.testing.assert_allclose(got, 20.0 + 0.3 * lats + 0.02 * lons, atol=1e-9)


def test_nan_neighbour_falls_back_to_nearest_cell() -> None:
    f = _linear()
    i, j = 40, 80  # cell (LAT[40], LON[80])
    f[i + 1, j + 1] = np.nan  # one of the four neighbours is "land"
    lat, lon = LAT[i] + 0.05, LON[j] + 0.05  # nearest cell is (i, j)
    got = sample_bilinear(f, LAT, LON, np.array([lat]), np.array([lon]))
    assert got[0] == pytest.approx(f[i, j])


def test_outside_grid_is_nan_not_clamped() -> None:
    got = sample_bilinear(_linear(), LAT, LON, np.array([4.0, 15.0]), np.array([60.0, 106.0]))
    assert np.isnan(got).all()


def test_collocate_fills_available_channels_and_flags_gaps(tmp_path: Path) -> None:
    store = SurfaceZarrStore.create(tmp_path / "s.zarr", ["2020-05-01", "2020-05-02"])
    fields = {v: _linear().astype(np.float32) for v in SATELLITE_VARS}
    fields["sss"][:] = np.nan  # no salinity that day
    store.write_day("2020-05-01", fields)
    argo = pd.DataFrame(
        {
            "profile_id": ["a_1", "b_1", "c_1"],
            "lat": [12.37, 20.0, 15.0],
            "lon": [66.61, 88.0, 70.0],
            "date": ["2020-05-01", "2020-05-01", "2019-01-01"],  # last one: not in the store
        }
    )
    out = collocate(argo, store)
    assert out.loc[0, "sst"] == pytest.approx(20.0 + 0.3 * 12.37 + 0.02 * 66.61, abs=1e-4)
    assert out.loc[0, "sst_avail"] == 1 and out.loc[0, "sss_avail"] == 0
    assert np.isnan(out.loc[0, "sss"])
    assert out.loc[2, ["sst_avail", "sla_avail", "u10_avail"]].sum() == 0  # date not covered
    assert len(out) == 3 and list(out["profile_id"]) == ["a_1", "b_1", "c_1"]
