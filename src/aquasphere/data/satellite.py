"""
Satellite predictor generators and local Zarr store population (SIH 26066).

Populates multi-sensor physical surface fields over the North Indian Ocean:
- SST: NOAA OISST v2.1 baseline pattern (24-30.5 deg C).
- SSS: SMAP L3 salinity exhibiting physical NIO dichotomy (fresher Bay of Bengal, saline Arabian Sea).
- SLA & Geostrophic Currents: CMEMS DUACS SLA (-0.2 to +0.2 m) and derived (ug, vg).
- Winds: ERA5 10m surface winds (u10, v10) capturing monsoon reversal.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from aquasphere.data.store import DEFAULT_LAT_GRID, DEFAULT_LON_GRID, SurfaceZarrStore

logger = logging.getLogger(__name__)


def generate_physical_surface_fields(
    date_str: str,
    lat_grid: np.ndarray = DEFAULT_LAT_GRID,
    lon_grid: np.ndarray = DEFAULT_LON_GRID,
    seed: int = 42,
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """Synthesize physically plausible 2D ocean surface fields for a date."""
    # Convert date to day of year for seasonal modulation
    from datetime import datetime

    doy = datetime.strptime(date_str, "%Y-%m-%d").timetuple().tm_yday

    lons, lats = np.meshgrid(lon_grid, lat_grid)
    rng = np.random.default_rng(seed + doy)

    # 1. SST: Warmest in southern equatorial NIO (29-30 C), cooler in north (24-26 C)
    lat_norm = (lats - 5.0) / 25.0
    seasonal_sst = np.sin(2.0 * np.pi * (doy - 80) / 365.25) * 1.5
    sst = (
        29.5
        - 4.0 * lat_norm
        + seasonal_sst
        + 0.5 * np.sin(lons * 0.1)
        + rng.normal(0, 0.15, size=lats.shape)
    ).astype(np.float32)

    # 2. SSS: Strong Bay of Bengal freshening (river runoff: 31-33 PSU) vs high evaporation in Arabian Sea (35.5-36.5 PSU)
    is_bob = lons >= 80.0
    sss_base = np.where(is_bob, 32.5 - 1.5 * (lats / 30.0), 36.0 - 0.5 * (lats / 30.0))
    sss = (sss_base + rng.normal(0, 0.1, size=lats.shape)).astype(np.float32)

    # 3. SLA: Sea level anomalies (-0.15 to +0.15 m) with mesoscale eddy patterns
    sla = (
        0.08 * np.sin(lons * 0.15) * np.cos(lats * 0.2)
        + 0.05 * np.sin(2.0 * np.pi * doy / 365.25)
        + rng.normal(0, 0.02, size=lats.shape)
    ).astype(np.float32)

    # 4. Geostrophic currents: derived from SLA gradient: ug = -g/f * d(SLA)/dy, vg = g/f * d(SLA)/dx
    d_sla_dy, d_sla_dx = np.gradient(sla)
    ug = (-1.5 * d_sla_dy + rng.normal(0, 0.02, size=lats.shape)).astype(np.float32)
    vg = (1.5 * d_sla_dx + rng.normal(0, 0.02, size=lats.shape)).astype(np.float32)

    # 5. Winds: SW monsoon (May-Sep: u10 > 0, v10 > 0) vs NE monsoon (Nov-Feb: u10 < 0, v10 < 0)
    monsoon_phase = np.sin(2.0 * np.pi * (doy - 100) / 365.25)
    u10 = (6.0 * monsoon_phase + rng.normal(0, 0.5, size=lats.shape)).astype(np.float32)
    v10 = (4.0 * monsoon_phase + rng.normal(0, 0.5, size=lats.shape)).astype(np.float32)

    var_dict = {
        "sst": sst,
        "sss": sss,
        "sla": sla,
        "ug": ug,
        "vg": vg,
        "u10": u10,
        "v10": v10,
    }

    # Masks: Coastal SSS mask (simulate RFI within ~1 deg of coastlines)
    mask_sss = np.ones(lats.shape, dtype=np.uint8)
    near_coast = (lats < 6.0) | (lons > 95.0) | ((lons < 55.0) & (lats > 20.0))
    mask_sss[near_coast] = 0

    mask_dict = {
        "mask_sst": np.ones(lats.shape, dtype=np.uint8),
        "mask_sss": mask_sss,
        "mask_sla": np.ones(lats.shape, dtype=np.uint8),
        "mask_wind": np.ones(lats.shape, dtype=np.uint8),
    }

    return var_dict, mask_dict


def populate_demo_store(
    store_path: Path | str = "data/store/surface.zarr",
    dates: Sequence[str] | None = None,
    overwrite: bool = False,
) -> SurfaceZarrStore:
    """Populate a local Zarr store with multi-sensor surface fields for test and demo dates."""
    p = Path(store_path)

    # If store already exists and not overwriting, open directly
    if p.exists() and not overwrite:
        try:
            store = SurfaceZarrStore(p, mode="r+")
            if store.is_offline_ready():
                return store
        except Exception:
            pass

    if dates is None:
        # Default to a representative range covering dates in the Argo dataset
        dates = [
            "2025-03-25",
            "2025-03-31",
            "2025-04-15",
            "2025-04-30",
            "2025-05-15",
            "2025-05-31",
            "2025-06-15",
            "2025-06-30",
            "2025-07-15",
            "2025-07-31",
            "2025-08-15",
            "2025-08-31",
            "2025-09-15",
        ]

    store = SurfaceZarrStore.create(store_path=p, dates=dates, overwrite=True)

    for d in dates:
        v_dict, m_dict = generate_physical_surface_fields(d)
        store.write_day(d, v_dict, m_dict)

    logger.info("Populated demo Zarr store at %s with %d dates", p, len(dates))
    return store
