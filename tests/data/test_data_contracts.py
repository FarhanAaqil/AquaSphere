"""
Data contract and invariant tests for AquaSphere (SIH 26066).

Validates the Phase 3 exit gate criteria:
1. Store opens offline without network calls.
2. No NaN in unmasked target depths.
3. Coordinates strictly within the North Indian Ocean domain (5-30N, 45-105E).
4. Manifest hashes match physical files on disk (provenance integrity).
5. 9x9 spatial patch and scalar feature collocation contract.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from aquasphere.constants import LAT_MAX, LAT_MIN, LON_MAX, LON_MIN, STANDARD_DEPTHS
from aquasphere.data.argo import process_legacy_argo_csv
from aquasphere.data.collocate import Collocator
from aquasphere.data.manifest import DataManifest
from aquasphere.data.store import SATELLITE_VARS, SurfaceZarrStore


@pytest.fixture
def processed_argo_df() -> pd.DataFrame:
    """Fixture providing processed Argo profiles dataframe."""
    p = Path("data/processed/argo_profiles.parquet")
    if p.exists():
        return pd.read_parquet(p)

    legacy_csv = Path("data/argo_sst_training.csv")
    if legacy_csv.exists():
        return process_legacy_argo_csv(legacy_csv, output_parquet=p)

    pytest.skip("Neither parquet nor legacy CSV available")


def test_data_contract_no_nan_in_unmasked_targets(processed_argo_df):
    """Invariant: whenever mask m_d == 1, temperature t_d must not be NaN or non-physical."""
    for d in STANDARD_DEPTHS:
        t_col = f"t_{d}"
        m_col = f"m_{d}"
        assert t_col in processed_argo_df.columns
        assert m_col in processed_argo_df.columns

        valid_rows = processed_argo_df[m_col] == 1
        temps = processed_argo_df.loc[valid_rows, t_col].to_numpy()

        assert not np.any(np.isnan(temps)), f"NaN found in unmasked target {t_col}"
        # Seawater temperatures in the NIO must be between 1.0 deg C and 35.0 deg C
        assert np.all(temps >= 1.0), f"Temperature below 1.0 C in unmasked {t_col}"
        assert np.all(temps <= 35.0), f"Temperature above 35.0 C in unmasked {t_col}"


def test_data_contract_spatial_domain(processed_argo_df):
    """Invariant: all profiles must reside strictly within the SIH 26066 domain."""
    lats = processed_argo_df["lat"].to_numpy()
    lons = processed_argo_df["lon"].to_numpy()

    assert np.all(lats >= LAT_MIN), f"Profile latitude below {LAT_MIN}"
    assert np.all(lats <= LAT_MAX), f"Profile latitude above {LAT_MAX}"
    assert np.all(lons >= LON_MIN), f"Profile longitude below {LON_MIN}"
    assert np.all(lons <= LON_MAX), f"Profile longitude above {LON_MAX}"


def test_data_contract_manifest_integrity():
    """Invariant: all registered artifacts in data/manifest.json must match disk SHA-256."""
    manifest_p = Path("data/manifest.json")
    if not manifest_p.exists():
        pytest.skip("data/manifest.json not found")

    manifest = DataManifest(manifest_p)
    assert len(manifest.entries) > 0, "Manifest contains no registered artifacts"

    for name, entry in manifest.entries.items():
        p = Path(entry["path"])
        if p.exists():
            assert manifest.verify_artifact(name), f"Integrity check failed for artifact: {name}"


def test_data_contract_store_offline_readiness():
    """Gate Invariant: Surface Zarr store opens offline and yields valid physical slices."""
    store_p = Path("data/store/surface.zarr")
    if not store_p.exists():
        pytest.skip("Surface Zarr store not populated at data/store/surface.zarr")

    # Read strictly offline
    store = SurfaceZarrStore(store_p, mode="r")
    assert store.is_offline_ready()

    dates = store.get_available_dates()
    assert len(dates) > 0

    first_date = dates[0]
    day_fields = store.read_day(first_date)

    for v in SATELLITE_VARS:
        assert v in day_fields
        assert day_fields[v].shape == (len(store.lat_grid), len(store.lon_grid))
        assert not np.all(np.isnan(day_fields[v])), f"Field {v} is completely empty"


def test_data_contract_collocation(processed_argo_df):
    """Invariant: Collocation extracts valid 9x9 patches and scalar features for profiles."""
    store_p = Path("data/store/surface.zarr")
    if not store_p.exists():
        pytest.skip("Surface Zarr store not populated")

    collocator = Collocator(store_p)
    sample_profile = processed_argo_df.iloc[0]

    lat = float(sample_profile["lat"])
    lon = float(sample_profile["lon"])
    date = str(sample_profile["date"])

    res = collocator.collocate_profile(lat, lon, date, patch_size=9)

    assert "patches" in res
    assert "scalars" in res
    assert "masks" in res

    for v in SATELLITE_VARS:
        patch = res["patches"][v]
        assert patch.shape == (9, 9), f"Patch for {v} is not 9x9"
        assert not np.any(np.isnan(patch)), f"NaN in 9x9 patch for {v}"

    # Batch collocation test on small slice
    small_df = processed_argo_df.iloc[:5].copy()
    enriched = collocator.collocate_dataset(small_df, patch_size=9)
    assert len(enriched) == 5
    assert "sss" in enriched.columns
    assert "sla" in enriched.columns
    assert "u10" in enriched.columns
