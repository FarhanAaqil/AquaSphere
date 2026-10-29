"""The synthetic-input audit detects columns copied from a synthetic store, and nothing else."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from aquasphere.data.audit import synthetic_channel_audit
from aquasphere.data.collocate import Collocator
from aquasphere.data.store import (
    DEFAULT_LAT_GRID,
    DEFAULT_LON_GRID,
    SATELLITE_VARS,
    SurfaceZarrStore,
)

DATES = ["2020-01-01", "2020-01-02"]


def _store(path: Path, synthetic: bool | None) -> SurfaceZarrStore:
    store = SurfaceZarrStore.create(path, DATES)
    rng = np.random.default_rng(0)
    shape = (len(DEFAULT_LAT_GRID), len(DEFAULT_LON_GRID))
    for d in DATES:
        store.write_day(
            d, {v: rng.normal(size=shape).astype(np.float32) + 20 for v in SATELLITE_VARS}
        )
    if synthetic is not None:
        store.root.attrs["synthetic"] = synthetic
    return store


def _table(path: Path, store: SurfaceZarrStore) -> pd.DataFrame:
    base = pd.DataFrame(
        {"lat": [10.0, 15.2, 22.7], "lon": [60.0, 88.4, 65.1], "date": DATES + DATES[:1]}
    )
    df = Collocator(store).collocate_dataset(base)
    df.to_parquet(path, index=False)
    return df


def test_detects_columns_copied_from_a_synthetic_store(tmp_path: Path) -> None:
    store = _store(tmp_path / "demo.zarr", synthetic=None)  # old demo stores carry no flag
    _table(tmp_path / "t.parquet", store)
    r = synthetic_channel_audit(tmp_path / "t.parquet", tmp_path / "demo.zarr")
    assert r["status"] == "synthetic_found"
    # the base table has no in-situ sst, so the collocated SST lands in "sst", not "sat_sst"
    assert set(r["synthetic_channels"]) == {"sss", "sla", "ug", "vg", "u10", "v10"}


def test_a_column_with_other_values_is_not_flagged(tmp_path: Path) -> None:
    store = _store(tmp_path / "demo.zarr", synthetic=None)
    df = _table(tmp_path / "t.parquet", store)
    df["sla"] = df["sla"] + 0.01  # not what the synthetic store holds
    df.to_parquet(tmp_path / "t.parquet", index=False)
    r = synthetic_channel_audit(tmp_path / "t.parquet", tmp_path / "demo.zarr")
    assert "sla" in r["other_channels"]
    assert "sla" not in r["synthetic_channels"]


def test_real_store_is_not_audited_as_synthetic(tmp_path: Path) -> None:
    store = _store(tmp_path / "real.zarr", synthetic=False)
    _table(tmp_path / "t.parquet", store)
    assert synthetic_channel_audit(tmp_path / "t.parquet", tmp_path / "real.zarr")["status"] == (
        "store_not_synthetic"
    )


def test_missing_inputs_are_reported_not_guessed(tmp_path: Path) -> None:
    r = synthetic_channel_audit(tmp_path / "nope.parquet", tmp_path / "nope.zarr")
    assert r["status"] == "not_checked"
    assert r["synthetic_channels"] == []
