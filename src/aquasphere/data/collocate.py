"""
Spatial and temporal collocation of satellite observations with Argo profiles (SIH 26066).

Extracts for each Argo profile:
- 9x9 spatial patches (≈ 2.25 deg) for each satellite variable (sst, sss, sla, ug, vg, u10, v10).
- Center-pixel scalar feature fallback.
- Channel availability masks (e.g. SSS missing near coast).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aquasphere.data.store import SATELLITE_VARS, SurfaceZarrStore

logger = logging.getLogger(__name__)


class Collocator:
    """Collocates in-situ Argo profiles with the local surface Zarr store."""

    def __init__(self, store: SurfaceZarrStore | Path | str = "data/store/surface.zarr") -> None:
        if isinstance(store, (str, Path)):
            self.store = SurfaceZarrStore(store, mode="r")
        else:
            self.store = store
        self.available_dates = sorted(self.store.get_available_dates())
        self._day_cache: dict[str, dict[str, np.ndarray]] = {}

    def _get_day_fields(self, date_str: str) -> dict[str, np.ndarray]:
        """Fetch and cache all 2D surface fields for a date."""
        if date_str not in self._day_cache:
            self._day_cache[date_str] = self.store.read_day(date_str)
        return self._day_cache[date_str]

    def find_nearest_date(self, target_date: str) -> str:
        """Find the closest date in the store to target_date."""
        if not self.available_dates:
            raise RuntimeError("No dates available in Zarr store")
        if target_date in self.store.date_to_idx:
            return target_date

        target_dt = pd.to_datetime(target_date)
        store_dts = pd.to_datetime(self.available_dates)
        diffs = np.abs(store_dts - target_dt)
        nearest_idx = int(np.argmin(diffs))
        return self.available_dates[nearest_idx]

    def collocate_profile(
        self,
        lat: float,
        lon: float,
        date_str: str,
        patch_size: int = 9,
    ) -> dict[str, Any]:
        """Collocate a single Argo profile with surface predictors."""
        matched_date = self.find_nearest_date(date_str)
        patches = self.store.extract_patch(lat, lon, matched_date, patch_size=patch_size)
        scalars = self.store.extract_point(lat, lon, matched_date)

        # Build availability masks: 1 if scalar is valid, 0 if NaN or fill
        masks: dict[str, int] = {}
        for v in SATELLITE_VARS:
            val = scalars.get(v, np.nan)
            masks[f"mask_{v}"] = int(~np.isnan(val) and val != 0.0)

        return {
            "date_requested": date_str,
            "date_matched": matched_date,
            "scalars": scalars,
            "patches": patches,
            "masks": masks,
        }

    def collocate_dataset(
        self,
        df: pd.DataFrame,
        patch_size: int = 9,
        date_col: str = "date",
        lat_col: str = "lat",
        lon_col: str = "lon",
    ) -> pd.DataFrame:
        """Enrich a dataframe of profiles with collocated satellite scalar features and masks."""
        df_out = df.copy()

        scalar_records: list[dict[str, float]] = []
        mask_records: list[dict[str, int]] = []

        for _, row in df_out.iterrows():
            lat = float(row[lat_col])
            lon = float(row[lon_col])
            date = str(row[date_col])

            matched_date = self.find_nearest_date(date)
            fields = self._get_day_fields(matched_date)
            lat_idx, lon_idx = self.store.snap_indices(lat, lon)
            scalars = {v: float(fields[v][lat_idx, lon_idx]) for v in SATELLITE_VARS if v in fields}
            masks = {
                f"mask_{v}": int(
                    ~np.isnan(scalars.get(v, np.nan)) and scalars.get(v, np.nan) != 0.0
                )
                for v in SATELLITE_VARS
            }
            scalar_records.append(scalars)
            mask_records.append(masks)

        # Add scalar columns
        scalars_df = pd.DataFrame(scalar_records, index=df_out.index)
        for col in scalars_df.columns:
            # Avoid overwriting in-situ sst if present, name satellite sst satellite_sst if conflict
            target_col = f"sat_{col}" if col in df_out.columns and col == "sst" else col
            df_out[target_col] = scalars_df[col]

        # Add mask columns
        masks_df = pd.DataFrame(mask_records, index=df_out.index)
        for col in masks_df.columns:
            df_out[col] = masks_df[col]

        logger.info(
            "Collocated %d profiles with %d satellite variables", len(df_out), len(SATELLITE_VARS)
        )
        return df_out
