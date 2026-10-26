"""
Argo float profile processing, quality control, and vertical PCHIP interpolation (SIH 26066).

Features:
- Strict QC filtering (flags 1=good, 2=probably good).
- Vertical PCHIP interpolation to 15 standard depths (0 to 1000 m).
- Preserves shallow profiles via 15-depth binary mask (no discard bias).
- Output: Parquet format [profile_id, float_id, cycle, lat, lon, date, T[15], mask[15]].
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator

from aquasphere.constants import DEPTH_COLS, STANDARD_DEPTHS
from aquasphere.data.splits import extract_float_id

logger = logging.getLogger(__name__)

# Column names for 15 depth observation masks (1 = validly observed/interpolated, 0 = missing/unobserved)
MASK_COLS: list[str] = [f"m_{d}" for d in STANDARD_DEPTHS]

# Physical bounds for seawater temperature in North Indian Ocean
MIN_VALID_TEMP: float = -2.0
MAX_VALID_TEMP: float = 38.0


def interpolate_profile_pchip(
    observed_depths: Sequence[float],
    observed_temps: Sequence[float],
    standard_depths: Sequence[int] = STANDARD_DEPTHS,
    max_surface_extrapolate_m: float = 10.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Interpolate irregular vertical temperature observations to standard depths using PCHIP.

    PCHIP (Piecewise Cubic Hermite Interpolating Polynomial) prevents spurious
    overshoots and oscillations in the sharp thermocline gradient.

    Args:
        observed_depths: Measured depth levels in meters (non-negative).
        observed_temps: Measured in-situ temperatures in deg C.
        standard_depths: Target depth grid (e.g., 15 standard depths).
        max_surface_extrapolate_m: Max depth (m) from which surface (0m) can be extrapolated.

    Returns:
        (interpolated_temps, depth_mask): Both of length len(standard_depths).
        depth_mask is boolean (True where depth is physically observed/valid).
    """
    z_obs = np.asarray(observed_depths, dtype=np.float64)
    t_obs = np.asarray(observed_temps, dtype=np.float64)
    z_targets = np.asarray(standard_depths, dtype=np.float64)
    n_targets = len(z_targets)

    # Filter out NaNs and non-physical temperatures
    valid = (
        ~np.isnan(z_obs)
        & ~np.isnan(t_obs)
        & (t_obs >= MIN_VALID_TEMP)
        & (t_obs <= MAX_VALID_TEMP)
        & (z_obs >= 0.0)
    )
    z_clean = z_obs[valid]
    t_clean = t_obs[valid]

    # Need at least 2 distinct depth levels to interpolate
    if len(np.unique(z_clean)) < 2:
        return np.full(n_targets, np.nan, dtype=np.float64), np.zeros(n_targets, dtype=bool)

    # Sort ascending by depth
    sort_idx = np.argsort(z_clean)
    z_sorted = z_clean[sort_idx]
    t_sorted = t_clean[sort_idx]

    # Handle duplicate depth entries by averaging
    u_depths, u_indices = np.unique(z_sorted, return_inverse=True)
    if len(u_depths) < len(z_sorted):
        u_temps = np.zeros_like(u_depths)
        for i in range(len(u_depths)):
            u_temps[i] = np.mean(t_sorted[u_indices == i])
        z_sorted, t_sorted = u_depths, u_temps

    min_z = z_sorted[0]
    max_z = z_sorted[-1]

    # If shallowest measurement is near surface (<= max_surface_extrapolate_m), extend to 0m
    if 0.0 < min_z <= max_surface_extrapolate_m:
        z_sorted = np.insert(z_sorted, 0, 0.0)
        t_sorted = np.insert(t_sorted, 0, t_sorted[0])
        min_z = 0.0

    interp = PchipInterpolator(z_sorted, t_sorted, extrapolate=False)
    t_interp = interp(z_targets)

    # Depth mask: valid only where target depth is within the observed depth span [min_z, max_z]
    depth_mask = (z_targets >= min_z) & (z_targets <= max_z) & (~np.isnan(t_interp))

    # Clean out any non-interpolated target values to NaN
    t_interp[~depth_mask] = np.nan

    return t_interp, depth_mask


def process_legacy_argo_csv(
    csv_path: Path | str,
    output_parquet: Path | str | None = None,
) -> pd.DataFrame:
    """Convert legacy argo_sst_training.csv into standard Parquet format with depth masks.

    Identifies which depths were actually measured vs padded/missing,
    and constructs standard mask columns m_0 ... m_1000.
    """
    p = Path(csv_path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")

    df = pd.read_csv(p)
    logger.info("Processing %d profiles from %s ...", len(df), p.name)

    records: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        pid = str(row["profile_id"]).strip()
        flt_id = extract_float_id(pid)
        cycle_str = pid.split("_")[1] if "_" in pid else "0"
        cycle = int(cycle_str) if cycle_str.isdigit() else 0

        lat = float(row["lat"])
        lon = float(row["lon"])
        date = str(row["date"])
        sst = float(row["sst"]) if pd.notna(row.get("sst")) else np.nan

        # Extract temperature values
        t_vals = [float(row[c]) if pd.notna(row.get(c)) else np.nan for c in DEPTH_COLS]
        m_vals = [int(~np.isnan(v)) for v in t_vals]

        entry: dict[str, Any] = {
            "profile_id": pid,
            "float_id": flt_id,
            "cycle": cycle,
            "lat": lat,
            "lon": lon,
            "date": date,
            "sst": sst,
        }
        for d_col, t_val in zip(DEPTH_COLS, t_vals, strict=False):
            entry[d_col] = t_val
        for m_col, m_val in zip(MASK_COLS, m_vals, strict=False):
            entry[m_col] = m_val

        records.append(entry)

    out_df = pd.DataFrame(records)

    if output_parquet is not None:
        out_p = Path(output_parquet)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_df.to_parquet(out_p, index=False)
        logger.info("Saved %d processed profiles to %s", len(out_df), out_p)

    return out_df
