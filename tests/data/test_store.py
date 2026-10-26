"""
Unit tests for the offline Surface Zarr store and spatial patch extraction (SIH 26066).
"""

from pathlib import Path

import numpy as np

from aquasphere.data.satellite import generate_physical_surface_fields, populate_demo_store
from aquasphere.data.store import SATELLITE_VARS, SurfaceZarrStore


def test_surface_zarr_store_lifecycle(tmp_path: Path):
    store_p = tmp_path / "surface.zarr"
    dates = ["2025-04-01", "2025-04-02"]

    store = SurfaceZarrStore.create(store_path=store_p, dates=dates)
    assert store.store_path.exists()
    assert store.get_available_dates() == dates

    v_dict, m_dict = generate_physical_surface_fields("2025-04-01")
    store.write_day("2025-04-01", v_dict, m_dict)

    # Read day
    fields = store.read_day("2025-04-01")
    for v in SATELLITE_VARS:
        assert v in fields
        assert fields[v].shape == (len(store.lat_grid), len(store.lon_grid))
        assert not np.all(np.isnan(fields[v]))


def test_extract_point_and_patch(tmp_path: Path):
    store_p = tmp_path / "surface.zarr"
    dates = ["2025-04-01"]
    store = SurfaceZarrStore.create(store_path=store_p, dates=dates)
    v_dict, m_dict = generate_physical_surface_fields("2025-04-01")
    store.write_day("2025-04-01", v_dict, m_dict)

    # 1. Point extraction
    pt = store.extract_point(lat=15.0, lon=70.0, date_str="2025-04-01")
    assert "sst" in pt
    assert 20.0 <= pt["sst"] <= 35.0

    # 2. Patch extraction (center interior)
    patch = store.extract_patch(lat=15.0, lon=70.0, date_str="2025-04-01", patch_size=9)
    for v in SATELLITE_VARS:
        assert v in patch
        assert patch[v].shape == (9, 9)
        assert not np.any(np.isnan(patch[v]))

    # 3. Patch extraction at border (boundary padding)
    border_patch = store.extract_patch(lat=5.0, lon=45.0, date_str="2025-04-01", patch_size=9)
    for v in SATELLITE_VARS:
        assert v in border_patch
        assert border_patch[v].shape == (9, 9)


def test_store_offline_read(tmp_path: Path):
    store_p = tmp_path / "surface.zarr"
    dates = ["2025-05-01"]
    store_w = SurfaceZarrStore.create(store_path=store_p, dates=dates)
    v_dict, _ = generate_physical_surface_fields("2025-05-01")
    store_w.write_day("2025-05-01", v_dict)

    # Open strictly read-only offline
    store_r = SurfaceZarrStore(store_p, mode="r")
    assert store_r.is_offline_ready()
    day_r = store_r.read_day("2025-05-01")
    assert "sst" in day_r


def test_populate_demo_store(tmp_path: Path):
    demo_p = tmp_path / "demo_surface.zarr"
    test_dates = ["2025-04-01", "2025-04-15"]
    store = populate_demo_store(store_path=demo_p, dates=test_dates, overwrite=True)

    assert store.is_offline_ready()
    assert len(store.get_available_dates()) == 2
    # Verify SST is physically reasonable
    sst_field = store.read_day("2025-04-01", variables=["sst"])["sst"]
    assert np.all(sst_field > 20.0)
    assert np.all(sst_field < 35.0)
