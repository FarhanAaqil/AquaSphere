"""
OceanEmbed — Data Collection Script
====================================
Fetches real Argo float profiles from the Argovis API and collocated
sea-surface temperature from NOAA OISST v2.1 via ERDDAP.

Geographic scope : North Indian Ocean  5°N–30°N, 45°E–105°E
Temporal scope   : most recent 18 months
Output           : data/argo_sst_training.csv

Usage:
    python data/collect.py
    python data/collect.py --max-profiles 200   # quick smoke test

Caching: raw API responses are saved under data/cache/ so re-runs skip
already-downloaded data.  Delete data/cache/ to force a full re-download.
"""

import argparse
import csv
import json
import logging
import math
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ARGOVIS_BASE = "https://argovis-api.colorado.edu"
ERDDAP_BASE  = (
    "https://www.ncei.noaa.gov/erddap/griddap/"
    "ncdc_oisst_v2_avhrr_by_time_zlev_lat_lon.csv"
)

POLYGON = [[45, 5], [105, 5], [105, 30], [45, 30], [45, 5]]   # lon, lat
STANDARD_DEPTHS = [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000]

SCRIPT_DIR  = Path(__file__).parent
CACHE_DIR   = SCRIPT_DIR / "cache"
OUTPUT_CSV  = SCRIPT_DIR / "argo_sst_training.csv"
LOG_FILE    = SCRIPT_DIR / "collect.log"

# Seconds to wait between requests to be polite to free APIs
ARGOVIS_DELAY = 0.4
ERDDAP_DELAY  = 0.3
REQUEST_TIMEOUT = 30

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
log = logging.getLogger("collect")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def cache_path(key: str, suffix: str = ".json") -> Path:
    safe = key.replace("/", "_").replace(":", "_").replace("?", "_").replace("&", "_")
    return CACHE_DIR / (safe[:180] + suffix)


def cached_get(url: str, delay: float = 0.4, suffix: str = ".json") -> dict | list | str | None:
    """GET with disk cache.  Returns parsed JSON or raw text, or None on error."""
    cp = cache_path(url, suffix)
    if cp.exists():
        raw = cp.read_text(encoding="utf-8")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    time.sleep(delay)
    try:
        r = requests.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
    except Exception as exc:
        log.warning("GET failed  %s  →  %s", url, exc)
        return None

    cp.write_text(r.text, encoding="utf-8")
    try:
        return r.json()
    except Exception:
        return r.text


# ---------------------------------------------------------------------------
# Argovis
# ---------------------------------------------------------------------------
def list_profile_ids(start_date: str, end_date: str) -> list[str]:
    """Return list of profile IDs in the bounding polygon for a date range."""
    polygon_str = json.dumps(POLYGON)
    url = (
        f"{ARGOVIS_BASE}/argo"
        f"?polygon={polygon_str}"
        f"&startDate={start_date}T00:00:00Z"
        f"&endDate={end_date}T23:59:59Z"
        f"&data=temperature,pressure"
        f"&compression=minimal"
    )
    data = cached_get(url, delay=ARGOVIS_DELAY)
    if not data:
        return []
    if isinstance(data, list):
        return [row[0] for row in data if isinstance(row, list) and row]
    return []


def fetch_profile(profile_id: str) -> dict | None:
    """Fetch a single Argo profile with temperature + pressure arrays."""
    url = f"{ARGOVIS_BASE}/argo?id={profile_id}&data=temperature,pressure"
    data = cached_get(url, delay=ARGOVIS_DELAY)
    if not data or not isinstance(data, list) or not data:
        return None
    return data[0]


def parse_profile(record: dict) -> dict | None:
    """
    Extract lat, lon, date, and T-at-depth from an Argovis record.
    Returns a dict with keys: lat, lon, date, depths, temps
    or None if the record is unusable.
    """
    try:
        coords = record["geolocation"]["coordinates"]   # [lon, lat]
        lon, lat = float(coords[0]), float(coords[1])
        timestamp = record["timestamp"]                  # ISO 8601
        date_str = timestamp[:10]                        # YYYY-MM-DD

        data_info = record.get("data_info", [[]])[0]    # list of variable names
        raw_data  = record.get("data", [])

        if not data_info or not raw_data:
            return None

        # Find indices of temperature and pressure
        try:
            t_idx = data_info.index("temperature")
            p_idx = data_info.index("pressure")
        except ValueError:
            return None

        temps     = raw_data[t_idx]
        pressures = raw_data[p_idx]

        if not temps or not pressures or len(temps) != len(pressures):
            return None

        # Filter out NaN / None values
        pairs = [(float(p), float(t)) for p, t in zip(pressures, temps)
                 if p is not None and t is not None
                 and not math.isnan(float(p)) and not math.isnan(float(t))]

        if len(pairs) < 5:
            return None

        depths_raw = [p for p, _ in pairs]   # decibar ≈ meters (within ~1%)
        temps_raw  = [t for _, t in pairs]

        # Sort by depth
        sorted_pairs = sorted(zip(depths_raw, temps_raw))
        depths_raw = [d for d, _ in sorted_pairs]
        temps_raw  = [t for _, t in sorted_pairs]

        return {"lat": lat, "lon": lon, "date": date_str,
                "depths": depths_raw, "temps": temps_raw}

    except Exception as exc:
        log.debug("parse_profile error: %s", exc)
        return None


def interpolate_to_standard(depths_raw, temps_raw) -> list[float] | None:
    """Linear interpolation of T onto the 15 standard depths."""
    try:
        arr = np.interp(STANDARD_DEPTHS, depths_raw, temps_raw,
                        left=np.nan, right=np.nan)
        # Accept profiles with at least 10 of 15 depths valid
        if np.sum(~np.isnan(arr)) < 10:
            return None
        return arr.tolist()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# OISST via ERDDAP
# ---------------------------------------------------------------------------
def snap(value: float, step: float = 0.25) -> float:
    """Round to nearest OISST grid cell (0.25° resolution)."""
    return round(round(value / step) * step, 2)


def fetch_oisst(lat: float, lon: float, date_str: str) -> float | None:
    """
    Fetch a single SST value from NOAA OISST v2.1 via ERDDAP.
    Returns temperature in °C, or None on failure.
    """
    slat = snap(lat)
    slon = snap(lon)
    # ERDDAP wants lon in 0–360 range for this dataset
    slon360 = slon if slon >= 0 else slon + 360

    url = (
        f"{ERDDAP_BASE}"
        f"?sst[({date_str}T12:00:00Z)][0][({slat:.2f})]"
        f"[({slon360:.2f})]"
    )
    raw = cached_get(url, delay=ERDDAP_DELAY, suffix=".csv")
    if not raw:
        return None

    # Parse the CSV (3 lines: units row, header, data)
    try:
        lines = [l.strip() for l in str(raw).splitlines() if l.strip()]
        # Find the data line (after headers)
        for line in lines[2:]:
            parts = line.split(",")
            # Last column is sst value
            val = float(parts[-1])
            if -5 < val < 45:    # sanity check
                return round(val, 3)
    except Exception as exc:
        log.debug("OISST parse error: %s | raw: %.80s", exc, str(raw))
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def collect(max_profiles: int | None = None):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Build date range: last 18 months
    end   = datetime.utcnow()
    start = end - timedelta(days=548)   # ~18 months
    start_str = start.strftime("%Y-%m-%d")
    end_str   = end.strftime("%Y-%m-%d")

    log.info("Date range: %s → %s", start_str, end_str)
    log.info("Listing Argo profiles in North Indian Ocean bounding box …")

    # Collect IDs in monthly chunks to keep URL lengths manageable
    all_ids: list[str] = []
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=45), end)
        ids = list_profile_ids(cursor.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d"))
        log.info("  %s → %s : %d profiles found", cursor.strftime("%Y-%m-%d"),
                 chunk_end.strftime("%Y-%m-%d"), len(ids))
        all_ids.extend(ids)
        cursor = chunk_end + timedelta(days=1)

    # Deduplicate (same float can appear in overlapping windows)
    all_ids = list(dict.fromkeys(all_ids))
    log.info("Total unique profile IDs: %d", len(all_ids))

    if max_profiles:
        all_ids = all_ids[:max_profiles]
        log.info("Capped at %d profiles (--max-profiles flag)", max_profiles)

    # Fetch + process each profile
    rows: list[dict] = []
    skipped = 0

    for i, pid in enumerate(all_ids):
        if i % 50 == 0:
            log.info("Progress: %d / %d  (rows so far: %d, skipped: %d)",
                     i, len(all_ids), len(rows), skipped)

        record = fetch_profile(pid)
        if not record:
            skipped += 1
            log.debug("No record for %s", pid)
            continue

        parsed = parse_profile(record)
        if not parsed:
            skipped += 1
            log.debug("Unparseable profile %s", pid)
            continue

        interped = interpolate_to_standard(parsed["depths"], parsed["temps"])
        if not interped:
            skipped += 1
            log.debug("Interpolation failed for %s (too sparse)", pid)
            continue

        # Fetch collocated SST
        sst = fetch_oisst(parsed["lat"], parsed["lon"], parsed["date"])
        if sst is None:
            skipped += 1
            log.debug("No OISST SST for %s @ %s %s %s",
                      pid, parsed["lat"], parsed["lon"], parsed["date"])
            continue

        doy = datetime.strptime(parsed["date"], "%Y-%m-%d").timetuple().tm_yday

        row = {
            "profile_id": pid,
            "lat":        round(parsed["lat"], 4),
            "lon":        round(parsed["lon"], 4),
            "date":       parsed["date"],
            "day_of_year": doy,
            "sst":        sst,
        }
        for j, d in enumerate(STANDARD_DEPTHS):
            val = interped[j]
            row[f"t_{d}"] = round(val, 3) if not math.isnan(val) else ""
        rows.append(row)

    log.info("Finished. %d valid rows, %d skipped.", len(rows), skipped)

    if not rows:
        log.error("No rows collected — check network and API availability.")
        return

    # Write CSV
    fieldnames = (
        ["profile_id", "lat", "lon", "date", "day_of_year", "sst"]
        + [f"t_{d}" for d in STANDARD_DEPTHS]
    )
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    log.info("Wrote %d rows → %s", len(rows), OUTPUT_CSV)


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect Argo + OISST training data")
    parser.add_argument("--max-profiles", type=int, default=None,
                        help="Stop after this many profiles (for quick tests)")
    args = parser.parse_args()
    collect(max_profiles=args.max_profiles)
