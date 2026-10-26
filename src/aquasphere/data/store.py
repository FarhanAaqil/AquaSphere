"""
Local offline Zarr store for multi-sensor satellite predictors (SIH 26066).

Manages high-performance gridded storage on a 0.25 deg North Indian Ocean grid:
- Variables: sst, sss, sla, ug, vg, u10, v10
- Masks: mask_sst, mask_sss, mask_sla, mask_wind
- Coordinates: (time, lat, lon)
- Fast 9x9 spatial patch and point extraction for profile collocation.
- Completely offline capable.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import zarr

from aquasphere.constants import LAT_MAX, LAT_MIN, LON_MAX, LON_MIN

logger = logging.getLogger(__name__)

# Standard surface variables
SATELLITE_VARS: list[str] = ["sst", "sss", "sla", "ug", "vg", "u10", "v10"]
MASK_VARS: list[str] = ["mask_sst", "mask_sss", "mask_sla", "mask_wind"]

# Default 0.25 deg coordinate grids for North Indian Ocean (5-30N, 45-105E)
DEFAULT_LAT_GRID: np.ndarray = np.round(np.arange(LAT_MIN, LAT_MAX + 0.001, 0.25), 2)
DEFAULT_LON_GRID: np.ndarray = np.round(np.arange(LON_MIN, LON_MAX + 0.001, 0.25), 2)


class SurfaceZarrStore:
    """Read/write interface to local surface.zarr store."""

    def __init__(self, store_path: Path | str, mode: str = "r") -> None:
        self.store_path = Path(store_path)
        self.mode = mode
        if not self.store_path.exists() and mode == "r":
            raise FileNotFoundError(f"Zarr store does not exist: {self.store_path}")
        self.root = zarr.open_group(str(self.store_path), mode=mode)
        self._load_metadata()

    def _load_metadata(self) -> None:
        """Load coordinates and index mapping from zarr attributes/arrays."""
        if "lat" in self.root and "lon" in self.root:
            self.lat_grid = np.asarray(self.root["lat"][:], dtype=np.float32)
            self.lon_grid = np.asarray(self.root["lon"][:], dtype=np.float32)
        else:
            self.lat_grid = DEFAULT_LAT_GRID.astype(np.float32)
            self.lon_grid = DEFAULT_LON_GRID.astype(np.float32)

        # Dates list stored in group attributes
        dates = self.root.attrs.get("dates", [])
        self.dates = list(dates)
        self.date_to_idx = {d: i for i, d in enumerate(self.dates)}

    @classmethod
    def create(
        cls,
        store_path: Path | str,
        dates: Sequence[str],
        lat_grid: np.ndarray = DEFAULT_LAT_GRID,
        lon_grid: np.ndarray = DEFAULT_LON_GRID,
        overwrite: bool = True,
    ) -> SurfaceZarrStore:
        """Create a new Zarr store with initialized coordinate grids and variables."""
        p = Path(store_path)
        if p.exists() and overwrite:
            import shutil

            shutil.rmtree(p, ignore_errors=True)

        p.parent.mkdir(parents=True, exist_ok=True)
        root = zarr.open_group(str(p), mode="w")

        n_times = len(dates)
        n_lats = len(lat_grid)
        n_lons = len(lon_grid)

        # Coordinate arrays
        root.create_array("lat", shape=(n_lats,), dtype="float32")
        root["lat"][:] = lat_grid.astype(np.float32)

        root.create_array("lon", shape=(n_lons,), dtype="float32")
        root["lon"][:] = lon_grid.astype(np.float32)

        # Surface variables [time, lat, lon]
        for v in SATELLITE_VARS:
            root.create_array(
                v,
                shape=(n_times, n_lats, n_lons),
                chunks=(1, n_lats, n_lons),
                dtype="float32",
                fill_value=np.nan,
            )

        # Mask variables [time, lat, lon]
        for m in MASK_VARS:
            root.create_array(
                m,
                shape=(n_times, n_lats, n_lons),
                chunks=(1, n_lats, n_lons),
                dtype="uint8",
                fill_value=0,
            )

        root.attrs["dates"] = list(dates)
        root.attrs["grid_resolution"] = 0.25
        root.attrs["domain"] = {
            "lat_min": float(lat_grid.min()),
            "lat_max": float(lat_grid.max()),
            "lon_min": float(lon_grid.min()),
            "lon_max": float(lon_grid.max()),
        }

        logger.info(
            "Initialized Surface Zarr store at %s (%d dates, %dx%d grid)",
            p,
            n_times,
            n_lats,
            n_lons,
        )
        return cls(store_path=p, mode="r+")

    def write_day(
        self,
        date_str: str,
        var_arrays: dict[str, np.ndarray],
        mask_arrays: dict[str, np.ndarray] | None = None,
    ) -> None:
        """Write 2D surface observation fields for a specific date."""
        if date_str not in self.date_to_idx:
            raise KeyError(f"Date '{date_str}' not in store date index")

        t_idx = self.date_to_idx[date_str]

        for v, arr in var_arrays.items():
            if v in self.root:
                self.root[v][t_idx, :, :] = np.asarray(arr, dtype=np.float32)

        if mask_arrays:
            for m, arr in mask_arrays.items():
                if m in self.root:
                    self.root[m][t_idx, :, :] = np.asarray(arr, dtype=np.uint8)

    def read_day(
        self,
        date_str: str,
        variables: Sequence[str] | None = None,
    ) -> dict[str, np.ndarray]:
        """Read 2D fields for a specific date."""
        if date_str not in self.date_to_idx:
            raise KeyError(f"Date '{date_str}' not found in store")

        t_idx = self.date_to_idx[date_str]
        vars_to_read = variables or SATELLITE_VARS

        result: dict[str, np.ndarray] = {}
        for v in vars_to_read:
            if v in self.root:
                result[v] = np.asarray(self.root[v][t_idx, :, :], dtype=np.float32)

        return result

    def snap_indices(self, lat: float, lon: float) -> tuple[int, int]:
        """Find nearest row (lat) and col (lon) index in grid."""
        lat_idx = int(np.argmin(np.abs(self.lat_grid - lat)))
        lon_idx = int(np.argmin(np.abs(self.lon_grid - lon)))
        return lat_idx, lon_idx

    def extract_point(self, lat: float, lon: float, date_str: str) -> dict[str, float]:
        """Extract point observations at closest grid cell."""
        lat_idx, lon_idx = self.snap_indices(lat, lon)
        fields = self.read_day(date_str)
        return {v: float(arr[lat_idx, lon_idx]) for v, arr in fields.items()}

    def extract_patch(
        self,
        lat: float,
        lon: float,
        date_str: str,
        patch_size: int = 9,
    ) -> dict[str, np.ndarray]:
        """Extract a patch_size x patch_size grid centered at (lat, lon).

        If the patch extends past grid borders, pads with edge values or NaNs.
        """
        center_lat_idx, center_lon_idx = self.snap_indices(lat, lon)
        half = patch_size // 2

        fields = self.read_day(date_str)
        patches: dict[str, np.ndarray] = {}

        n_lats = len(self.lat_grid)
        n_lons = len(self.lon_grid)

        r_start = center_lat_idx - half
        r_end = center_lat_idx + half + 1
        c_start = center_lon_idx - half
        c_end = center_lon_idx + half + 1

        pad_top = max(0, -r_start)
        pad_bottom = max(0, r_end - n_lats)
        pad_left = max(0, -c_start)
        pad_right = max(0, c_end - n_lons)

        r_start_c = max(0, r_start)
        r_end_c = min(n_lats, r_end)
        c_start_c = max(0, c_start)
        c_end_c = min(n_lons, c_end)

        for v, arr in fields.items():
            crop = arr[r_start_c:r_end_c, c_start_c:c_end_c]
            if pad_top > 0 or pad_bottom > 0 or pad_left > 0 or pad_right > 0:
                crop = np.pad(
                    crop,
                    ((pad_top, pad_bottom), (pad_left, pad_right)),
                    mode="edge",
                )
            patches[v] = crop

        return patches

    def get_available_dates(self) -> list[str]:
        """Return list of dates available in the store."""
        return list(self.dates)

    def is_offline_ready(self) -> bool:
        """Check if store can be opened and read without network."""
        return bool(len(self.dates) > 0 and "sst" in self.root)
