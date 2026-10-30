"""Patch stacks: lags, anomaly against training-year climatology, land and edges."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import zarr

from aquasphere.data.patches import CHANNELS, LAGS, PATCH, PatchSource


def _store(path: Path) -> Path:
    dates = pd.date_range("2022-11-01", "2023-01-31").strftime("%Y-%m-%d").tolist()
    lat = np.arange(10.0, 13.0, 0.25, dtype=np.float32)  # 12 rows
    lon = np.arange(60.0, 64.0, 0.25, dtype=np.float32)  # 16 cols
    root = zarr.open_group(str(path), mode="w")
    root.attrs["dates"] = dates
    root.create_array("lat", data=lat)
    root.create_array("lon", data=lon)
    shape = (len(dates), len(lat), len(lon))
    # SST: day index everywhere, so lags and anomalies are easy to check
    sst = np.broadcast_to(np.arange(len(dates), dtype=np.float32)[:, None, None], shape).copy()
    sst[:, 0, 0] = np.nan  # one land cell
    root.create_array("sst", data=sst)
    for v in ("sla", "sss", "ug", "vg", "u10", "v10"):
        root.create_array(v, data=np.ones(shape, dtype=np.float32))
    return path


def test_lags_anomaly_land_and_edges(tmp_path: Path) -> None:
    src = PatchSource(_store(tmp_path / "s.zarr"))
    # Training years end 2022-12-31: 61 training days, climatology from Nov and Dec only
    assert src.n_train_days == 61
    assert src.land[0, 0] and not src.land[5, 5]

    day = np.array([src.index["2023-01-20"]])
    row, col = src.cells(np.array([10.0]), np.array([60.0]))  # corner cell: patch runs off-grid
    p, land = src.extract(day, row, col)
    assert p.shape == (1, len(LAGS), len(CHANNELS), PATCH, PATCH)
    centre = p[0, :, :, PATCH // 2 + 1, PATCH // 2 + 1].astype(np.float32)  # one cell in
    # Lag t-28 lands in December: anomaly = day index minus the December mean of day indices
    dec_mean = np.mean(np.arange(30, 61))
    assert np.isclose(centre[3, 0], (day[0] - 28) - dec_mean, atol=0.05)
    # Lag 0 is January, which has no training-year climatology: NaN, never a made-up value
    assert np.isnan(centre[0, 0])
    assert np.allclose(centre[:, 1], 1.0)
    # Off-grid pixels are NaN and count as land; the land cell is flagged
    assert np.isnan(p[0, 0, 1, 0, 0]) and land[0, 0, 0]
    assert land[0, PATCH // 2, PATCH // 2]  # (0, 0) is the land cell


def test_lags_before_the_store_start_are_missing(tmp_path: Path) -> None:
    src = PatchSource(_store(tmp_path / "s.zarr"))
    p, _ = src.extract(np.array([3]), np.array([6]), np.array([8]))
    assert np.all(np.isnan(p[0, 1:]))  # t-7, t-14, t-28 precede the first day
    assert np.all(np.isfinite(p[0, 0, 1]))
