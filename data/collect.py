"""
OceanEmbed — Data Collection Script (v2 — bulk fetch)
=======================================================
Fetches real Argo float profiles from the Argovis API using BULK
polygon queries (one request returns all profiles with data for a
date window), then collocates sea-surface temperature from NOAA
OISST v2.1 via ERDDAP.

Geographic scope : North Indian Ocean  5°N–30°N, 45°E–105°E
Temporal scope   : most recent 18 months
Output           : data/argo_sst_training.csv

The key speedup vs. v1: instead of listing IDs then fetching each
profile individually (6737 × 0.7s = ~80 min), we query Argovis
in 7-day windows WITH &data=temperature,pressure, getting all profiles
in that window in a single response (~600 windows × 2s = ~20 min).
OISST is still per-profile but responses are cached to disk.

Usage:
    python data/collect.py
    python data/collect.py --max-windows 30   # quick smoke test (~150 rows)

Caching: raw API responses saved under data/cache/ — re-runs are instant.
"""

import argparse
import csv
import json
import logging
import math
import os
import time
from datetime import datetime, timedelta, timezone
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

POLYGON = [[45, 5], [105, 5], [105, 30], [45, 30], [45, 5]]   # lon,lat — closed ring
STANDARD_DEPTHS = [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000]

SCRIPT_DIR  = Path(__file__).parent
CACHE_DIR   = SCRIPT_DIR / "cache"
OUTPUT_CSV  = SCRIPT_DIR / "argo_sst_training.csv"
LOG_FILE    = SCRIPT_DIR / "collect.log"

WINDOW_DAYS    = 7     # bulk-fetch window size
ARGOVIS_DELAY  = 1.0   # seconds between Argovis bulk requests
ERDDAP_DELAY   = 0.25  # seconds between OISST point requests
REQUEST_TIMEOUT = 60

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
# Cache helpers
# ---------------------------------------------------------------------------
def _safe_key(url: str) -> str:
    for ch in "/?&=:[]{}":
        url = url.replace(ch, "_")
    return url[:200]


def cached_get_json(url: str, delay: float) -> list | dict | None:
    """GET with disk cache → parsed JSON or None on error."""
    cp = CACHE_DIR / (_safe_key(url) + ".json")
    if cp.exists():
        try:
            return json.loads(cp.read_text(encoding="utf-8"))
        except Exception:
            cp.unlink(missing_ok=True)

    time.sleep(delay)
    try:
        r = requests.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        cp.write_text(json.dumps(data), encoding="utf-8")
        return data
    except Exception as exc:
        log.warning("GET failed  %.120s  →  %s", url, exc)
        return None


def cached_get_text(url: str, delay: float) -> str | None:
    """GET with disk cache → raw text or None on error."""
    cp = CACHE_DIR / (_safe_key(url) + ".txt")
    if cp.exists():
        return cp.read_text(encoding="utf-8")

    time.sleep(delay)
    try:
        r = requests.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        cp.write_text(r.text, encoding="utf-8")
        return r.text
    except Exception as exc:
        log.warning("GET failed  %.120s  →  %s", url, exc)
        return None


# ---------------------------------------------------------------------------
# Argovis — bulk fetch a date window
# ---------------------------------------------------------------------------
def fetch_window(start_str: str, end_str: str) -> list[dict]:
    """
    Fetch all Argo core profiles with temperature+pressure data in the
    North Indian Ocean bounding polygon for a date window.
    Returns a list of profile dicts (may be empty).
    """
    polygon_str = json.dumps(POLYGON)
    url = (
        f"{ARGOVIS_BASE}/argo"
        f"?polygon={polygon_str}"
        f"&startDate={start_str}T00:00:00Z"
        f"&endDate={end_str}T23:59:59Z"
        f"&data=temperature,pressure"
    )
    data = cached_get_json(url, delay=ARGOVIS_DELAY)
    if not data or not isinstance(data, list):
        return []
    return data


# ---------------------------------------------------------------------------
# Parse a single Argovis profile record
# ---------------------------------------------------------------------------
def parse_profile(record: dict) -> dict | None:
    """
    Extract lat, lon, date, temps interpolated to standard depths.
    Returns dict or None if unusable.
    """
    try:
        coords    = record["geolocation"]["coordinates"]
        lon, lat  = float(coords[0]), float(coords[1])
        timestamp = record["timestamp"]
        date_str  = timestamp[:10]

        data_info = record.get("data_info", [[]])[0]
        raw_data  = record.get("data", [])

        if not data_info or not raw_data:
            return None

        try:
            t_idx = data_info.index("temperature")
            p_idx = data_info.index("pressure")
        except ValueError:
            return None

        temps_raw     = raw_data[t_idx]
        pressures_raw = raw_data[p_idx]

        if not temps_raw or not pressures_raw:
            return None
        if len(temps_raw) != len(pressures_raw):
            return None

        # Filter NaN / None
        pairs = [
            (float(p), float(t))
            for p, t in zip(pressures_raw, temps_raw)
            if p is not None and t is not None
            and not math.isnan(float(p)) and not math.isnan(float(t))
        ]
        if len(pairs) < 5:
            return None

        pairs.sort()
        depths_m = [p for p, _ in pairs]   # decibar ≈ meters
        temps    = [t for _, t in pairs]

        # Interpolate onto standard depths
        arr = np.interp(STANDARD_DEPTHS, depths_m, temps, left=np.nan, right=np.nan)
        if np.sum(~np.isnan(arr)) < 10:
            return None

        return {
            "lat":    lat,
            "lon":    lon,
            "date":   date_str,
            "interp": arr.tolist(),
        }
    except Exception as exc:
        log.debug("parse_profile error: %s", exc)
        return None


# ---------------------------------------------------------------------------
# OISST via ERDDAP
# ---------------------------------------------------------------------------
def snap(value: float, step: float = 0.25) -> float:
    return round(round(value / step) * step, 2)


def fetch_oisst(lat: float, lon: float, date_str: str) -> float | None:
    slat    = snap(lat)
    slon360 = snap(lon) if snap(lon) >= 0 else snap(lon) + 360

    url = (
        f"{ERDDAP_BASE}"
        f"?sst[({date_str}T12:00:00Z)][0][({slat:.2f})]"
        f"[({slon360:.2f})]"
    )
    raw = cached_get_text(url, delay=ERDDAP_DELAY)
    if not raw:
        return None
    try:
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
        for line in lines[2:]:
            val = float(line.split(",")[-1])
            if -5 < val < 45:
                return round(val, 3)
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def collect(max_windows: int | None = None):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    now   = datetime.now(timezone.utc)
    start = now - timedelta(days=548)   # ~18 months

    # Build list of (start, end) 7-day windows
    windows = []
    cursor = start
    while cursor < now:
        w_end = min(cursor + timedelta(days=WINDOW_DAYS - 1), now)
        windows.append((cursor.strftime("%Y-%m-%d"), w_end.strftime("%Y-%m-%d")))
        cursor = w_end + timedelta(days=1)

    log.info("Date range: %s → %s  |  %d windows of %d days",
             start.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d"),
             len(windows), WINDOW_DAYS)

    if max_windows:
        windows = windows[:max_windows]
        log.info("Capped at %d windows (--max-windows flag)", max_windows)

    rows: list[dict] = []
    seen_ids: set[str] = set()
    total_skipped = 0

    for wi, (ws, we) in enumerate(windows):
        log.info("Window %d/%d  %s → %s", wi + 1, len(windows), ws, we)
        profiles = fetch_window(ws, we)
        log.info("  → %d profile records", len(profiles))

        for record in profiles:
            pid = record.get("_id", "")
            if pid in seen_ids:
                continue
            seen_ids.add(pid)

            parsed = parse_profile(record)
            if not parsed:
                total_skipped += 1
                continue

            sst = fetch_oisst(parsed["lat"], parsed["lon"], parsed["date"])
            if sst is None:
                total_skipped += 1
                log.debug("No OISST for %s @ %s %s %s",
                          pid, parsed["lat"], parsed["lon"], parsed["date"])
                continue

            doy = datetime.strptime(parsed["date"], "%Y-%m-%d").timetuple().tm_yday

            row: dict = {
                "profile_id":  pid,
                "lat":         round(parsed["lat"], 4),
                "lon":         round(parsed["lon"], 4),
                "date":        parsed["date"],
                "day_of_year": doy,
                "sst":         sst,
            }
            for j, d in enumerate(STANDARD_DEPTHS):
                v = parsed["interp"][j]
                row[f"t_{d}"] = "" if math.isnan(v) else round(v, 3)
            rows.append(row)

        log.info("  Running total: %d valid rows, %d skipped", len(rows), total_skipped)

        # Write incrementally every 5 windows so progress is never lost
        if (wi + 1) % 5 == 0 and rows:
            _write_csv(rows)
            log.info("  Checkpoint: wrote %d rows to CSV", len(rows))

    log.info("Done. %d valid rows, %d skipped. Writing final CSV.", len(rows), total_skipped)
    if rows:
        _write_csv(rows)
        log.info("Wrote %d rows → %s", len(rows), OUTPUT_CSV)
    else:
        log.error("No rows collected — check network and API availability.")


def _write_csv(rows: list[dict]):
    fieldnames = (
        ["profile_id", "lat", "lon", "date", "day_of_year", "sst"]
        + [f"t_{d}" for d in STANDARD_DEPTHS]
    )
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect Argo + OISST training data (bulk)")
    parser.add_argument("--max-windows", type=int, default=None,
                        help="Stop after N date windows (7 days each). For testing.")
    args = parser.parse_args()
    collect(max_windows=args.max_windows)
