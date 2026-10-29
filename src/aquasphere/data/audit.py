"""
Synthetic-input audit.

Early tables were "collocated" against the synthetic demo store (aquasphere.data.satellite), so
their SSS / SLA / current / wind columns are generated fields, not observations. This audit
proves it rather than assuming it: it re-collocates a table against a synthetic store and checks
whether each satellite column is reproduced exactly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aquasphere.data.collocate import Collocator
from aquasphere.data.store import SATELLITE_VARS, SurfaceZarrStore

# Table column holding each store variable after collocation (the collocator renames sst)
COLUMN_FOR = {v: ("sat_sst" if v == "sst" else v) for v in SATELLITE_VARS}
TOLERANCE = 1e-6


def store_is_synthetic(store: SurfaceZarrStore) -> bool:
    """Stores built by the real-data builder say so; anything else is the demo fixture."""
    return store.root.attrs.get("synthetic", True) is not False


def synthetic_channel_audit(table_path: Path | str, store_path: Path | str) -> dict[str, Any]:
    """Which satellite columns of a table are exact copies of a synthetic store's values?"""
    table_path, store_path = Path(table_path), Path(store_path)
    result: dict[str, Any] = {
        "table": table_path.as_posix(),
        "store": store_path.as_posix(),
        "synthetic_channels": [],
        "other_channels": [],
        "method": "re-collocated against the store; a column is synthetic if reproduced to 1e-6",
    }
    if not table_path.exists() or not store_path.exists():
        result["status"] = "not_checked"
        return result

    store = SurfaceZarrStore(store_path)
    if not store_is_synthetic(store):
        result["status"] = "store_not_synthetic"
        return result

    df = pd.read_parquet(table_path) if table_path.suffix == ".parquet" else pd.read_csv(table_path)
    present = [v for v in SATELLITE_VARS if COLUMN_FOR[v] in df.columns]
    if not present:
        result["status"] = "no_satellite_columns"
        return result

    base = df.drop(columns=[COLUMN_FOR[v] for v in present])
    redo = Collocator(store).collocate_dataset(base)
    for v in present:
        col = COLUMN_FOR[v]
        diff = np.abs(redo[col].to_numpy(dtype=float) - df[col].to_numpy(dtype=float))
        exact = bool(np.nanmax(diff) <= TOLERANCE) if np.isfinite(diff).any() else False
        result["synthetic_channels" if exact else "other_channels"].append(col)
    result["status"] = "synthetic_found" if result["synthetic_channels"] else "clean"
    return result
