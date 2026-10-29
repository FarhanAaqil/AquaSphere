"""Surface store builder: URLs, regridding, masking and coverage, with no network access."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from aquasphere.data import satellite_fetch as sf
from aquasphere.data.sources import SOURCES, DatasetSpec
from aquasphere.data.store import DEFAULT_LAT_GRID, DEFAULT_LON_GRID, SurfaceZarrStore

SPEC = DatasetSpec(
    key="fake",
    server="https://example.invalid/erddap",
    dataset_id="fakeSST",
    variables={"sst": "sst"},
    mask="mask_sst",
    start="2020-01-05",
)


def _month_file(path: Path, month: date, n_days: int, skip: set[int] = frozenset()) -> None:
    """A source-like file on a 0.125-offset grid holding a field linear in lat and lon."""
    lat = np.arange(4.375, 30.7, 0.25)  # cell centres offset from the store grid
    lon = np.arange(44.375, 105.7, 0.25)
    days = [
        pd.Timestamp(month) + pd.Timedelta(days=i, hours=12) for i in range(n_days) if i not in skip
    ]
    field = 20.0 + 0.1 * lat[:, None] + 0.01 * lon[None, :]
    data = np.broadcast_to(field, (len(days), len(lat), len(lon))).copy()
    data[:, :3, :3] = np.nan  # a "land" corner
    xr.Dataset(
        {"sst": (("time", "zlev", "latitude", "longitude"), data[:, None])},
        coords={"time": days, "zlev": [0.0], "latitude": lat, "longitude": lon},
    ).to_netcdf(path)


@pytest.fixture(autouse=True)
def _tmp_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sf, "CACHE_ROOT", tmp_path / "cache")


def test_month_url_pads_domain_and_respects_product_start() -> None:
    assert sf.month_url(SPEC, date(2019, 12, 1)) is None  # product starts 2020-01-05
    url = sf.month_url(SPEC, date(2020, 1, 1))
    assert url is not None
    assert url.startswith("https://example.invalid/erddap/griddap/fakeSST.nc?sst")
    assert "(2020-01-05T00:00:00Z):1:(2020-01-31T23:59:59Z)" in url
    assert "[(4.5):1:(30.5)][(44.5):1:(105.5)]" in url


def test_every_registered_source_maps_into_store_variables() -> None:
    store_vars = {"sst", "sss", "sla", "ug", "vg", "u10", "v10"}
    for spec in SOURCES.values():
        assert set(spec.variables) <= store_vars
        assert spec.mask in {"mask_sst", "mask_sss", "mask_sla", "mask_wind"}
        assert sf.month_url(spec, date(2024, 1, 1)) is not None


def test_regrid_is_exact_for_a_linear_field(tmp_path: Path) -> None:
    p = tmp_path / "m.nc"
    _month_file(p, date(2020, 2, 1), n_days=3)
    days = sf.regrid_month(SPEC, p)
    assert sorted(days) == ["2020-02-01", "2020-02-02", "2020-02-03"]
    grid = days["2020-02-02"]["sst"]
    assert grid.shape == (len(DEFAULT_LAT_GRID), len(DEFAULT_LON_GRID))
    expected = 20.0 + 0.1 * DEFAULT_LAT_GRID[:, None] + 0.01 * DEFAULT_LON_GRID[None, :]
    ok = np.isfinite(grid)
    assert ok.mean() > 0.95  # only the NaN corner is lost
    np.testing.assert_allclose(grid[ok], expected[ok], atol=1e-4)


def test_build_store_masks_gaps_and_records_coverage(tmp_path: Path) -> None:
    def fake_fetch(url: str, dest: Path) -> bool:
        if "2020-03" in url:
            return False  # ERDDAP 404: no data this month
        month = date(2020, 2, 1) if "2020-02" in url else date(2020, 1, 1)
        n = 29 if month.month == 2 else 31
        _month_file(dest, month, n_days=n, skip={3})  # one missing day per month
        return True

    store_path = tmp_path / "store.zarr"
    covered = sf.build_store(
        date(2020, 1, 1), date(2020, 3, 31), store_path, [SPEC], fetch=fake_fetch, workers=2
    )
    # Jan: product starts on the 5th and the 4th is missing anyway -> 27 days; Feb: 28; Mar: 0
    assert covered == {"fake": {"sst": 27 + 28}}

    store = SurfaceZarrStore(store_path)
    assert store.root.attrs["synthetic"] is False
    assert store.root.attrs["sources"]["fake"]["dataset_id"] == "fakeSST"
    assert len(store.dates) == 91

    def sst_and_mask(day: str) -> tuple[np.ndarray, np.ndarray]:
        i = store.date_to_idx[day]
        return store.root["sst"][i], store.root["mask_sst"][i]

    sst, mask = sst_and_mask("2020-02-10")
    assert np.isfinite(sst).mean() > 0.95
    np.testing.assert_array_equal(mask, np.isfinite(sst).astype(np.uint8))
    for empty_day in ("2020-01-02", "2020-02-04", "2020-03-15"):  # before start / gap / 404 month
        sst, mask = sst_and_mask(empty_day)
        assert np.isnan(sst).all()
        assert mask.sum() == 0
    # the 404 month is remembered so a rerun does not ask again
    assert (sf.CACHE_ROOT / "fake" / "2020-03.empty").exists()
