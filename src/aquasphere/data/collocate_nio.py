"""
Collocate the multi-year Argo table with the real surface store (roadmap Phase 2).

    python -m aquasphere.data.collocate_nio

For every profile, each satellite variable is sampled at the profile position on the profile's
date: bilinear interpolation between the four surrounding cells, falling back to the nearest
cell when a neighbour is land, and NaN when the product has no value that day. An availability
column (sst_avail, sss_avail, ...) records which channels are real for each profile, which is
exactly what the model's masks need. Nothing is filled with a default here.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from aquasphere.data.argo_ingest import OUTPUT as ARGO_TABLE
from aquasphere.data.audit import store_is_synthetic
from aquasphere.data.contracts import validate_argo_profiles
from aquasphere.data.satellite_fetch import STORE_PATH
from aquasphere.data.store import SATELLITE_VARS, SurfaceZarrStore

logger = logging.getLogger(__name__)

OUTPUT = Path("data/processed/argo_nio_collocated.parquet")
# Output column per store variable. SST goes to "sst" (the model's SST input); the profile's
# own near-surface temperature stays in t_0.
COLUMN = {
    "sst": "sst",
    "sss": "sss",
    "sla": "sla",
    "ug": "ug",
    "vg": "vg",
    "u10": "u10",
    "v10": "v10",
}


def sample_bilinear(
    field: np.ndarray,
    lat_grid: np.ndarray,
    lon_grid: np.ndarray,
    lats: np.ndarray,
    lons: np.ndarray,
) -> np.ndarray:
    """Bilinear samples of a 2-D field; nearest cell where a neighbour is NaN; NaN outside."""
    fi = np.interp(lats, lat_grid, np.arange(len(lat_grid)), left=np.nan, right=np.nan)
    fj = np.interp(lons, lon_grid, np.arange(len(lon_grid)), left=np.nan, right=np.nan)
    out = np.full(len(lats), np.nan, dtype=np.float64)
    ok = np.isfinite(fi) & np.isfinite(fj)
    i0 = np.clip(np.floor(fi[ok]).astype(int), 0, len(lat_grid) - 2)
    j0 = np.clip(np.floor(fj[ok]).astype(int), 0, len(lon_grid) - 2)
    a = fi[ok] - i0
    b = fj[ok] - j0
    f00, f10 = field[i0, j0], field[i0 + 1, j0]
    f01, f11 = field[i0, j0 + 1], field[i0 + 1, j0 + 1]
    bil = (1 - a) * (1 - b) * f00 + a * (1 - b) * f10 + (1 - a) * b * f01 + a * b * f11
    nearest = field[np.rint(fi[ok]).astype(int), np.rint(fj[ok]).astype(int)]
    out[ok] = np.where(np.isfinite(bil), bil, nearest)
    return out


def collocate(argo: pd.DataFrame, store: SurfaceZarrStore) -> pd.DataFrame:
    """Add satellite columns and <var>_avail flags to an Argo table."""
    out = argo.copy()
    for v in SATELLITE_VARS:
        out[COLUMN[v]] = np.nan
    lat_grid = store.lat_grid.astype(np.float64)
    lon_grid = store.lon_grid.astype(np.float64)
    dates = out["date"].astype(str).str[:10]
    for date, idx in dates.groupby(dates).groups.items():
        if date not in store.date_to_idx:
            continue
        fields = store.read_day(str(date))
        rows = out.loc[idx]
        lats = rows["lat"].to_numpy(dtype=np.float64)
        lons = rows["lon"].to_numpy(dtype=np.float64)
        for v, field in fields.items():
            out.loc[idx, COLUMN[v]] = sample_bilinear(field, lat_grid, lon_grid, lats, lons)
    for v in SATELLITE_VARS:
        out[f"{v}_avail"] = out[COLUMN[v]].notna().astype(np.int8)
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Collocate Argo profiles with the real surface store")
    p.add_argument("--argo", default=str(ARGO_TABLE))
    p.add_argument("--store", default=str(STORE_PATH))
    p.add_argument("--output", default=str(OUTPUT))
    a = p.parse_args()

    store = SurfaceZarrStore(a.store)
    if store_is_synthetic(store):
        raise SystemExit(f"{a.store} is not marked as real data; refusing to collocate from it.")
    argo = pd.read_parquet(a.argo)
    df = collocate(argo, store)
    validate_argo_profiles(df)
    Path(a.output).parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(a.output, index=False)
    avail = {v: f"{df[f'{v}_avail'].mean():.1%}" for v in SATELLITE_VARS}
    logger.info("Wrote %s: %d profiles; channel availability %s", a.output, len(df), avail)


if __name__ == "__main__":
    main()
