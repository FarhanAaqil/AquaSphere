"""
Multi-year Argo ingest for the North Indian Ocean (roadmap Phase 2, blueprint §10).

    python -m aquasphere.data.argo_ingest --start 2015-01-01 --end 2025-12-31

Pulls every core Argo profile in 5-30°N, 45-105°E from the Argovis API in weekly windows
(responses cached under data/cache/argovis/), then for each profile:

* keeps it only if position and time QC flags are 1 (good);
* keeps only levels whose temperature AND pressure QC flags are 1;
* converts pressure to depth (UNESCO 1983, Fofonoff & Millard) and PCHIP-interpolates onto the
  15 standard depths, masking depths outside the observed span;
* records the data mode of the temperature: R (real-time), A (real-time adjusted) or
  D (delayed mode), so headline results can prefer delayed-mode data (blueprint §10.2).

The result is validated against the pandera contract before it is written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aquasphere.constants import LAT_MAX, LAT_MIN, LON_MAX, LON_MIN, STANDARD_DEPTHS
from aquasphere.data.argo import interpolate_profile_pchip
from aquasphere.data.contracts import validate_argo_profiles

logger = logging.getLogger(__name__)

ARGOVIS = "https://argovis-api.colorado.edu/argo"
CACHE_DIR = Path("data/cache/argovis")
OUTPUT = Path("data/processed/argo_nio_2015_2025.parquet")
POLYGON = [
    [LON_MIN, LAT_MIN],
    [LON_MAX, LAT_MIN],
    [LON_MAX, LAT_MAX],
    [LON_MIN, LAT_MAX],
    [LON_MIN, LAT_MIN],
]
DATA_KEYS = "temperature,pressure,temperature_argoqc,pressure_argoqc"
MIN_GOOD_LEVELS = 5
MIN_STANDARD_DEPTHS = 3
GOOD = 1


def pressure_to_depth(pressure_dbar: np.ndarray, lat: float) -> np.ndarray:
    """Depth (m) from pressure (dbar), UNESCO 1983 (Fofonoff & Millard), standard ocean."""
    p = np.asarray(pressure_dbar, dtype=np.float64)
    x = np.sin(np.radians(lat)) ** 2
    gr = 9.780318 * (1.0 + (5.2788e-3 + 2.36e-5 * x) * x) + 1.092e-6 * p
    depth: np.ndarray = ((((-1.82e-15 * p + 2.279e-10) * p - 2.2512e-5) * p + 9.72659) * p) / gr
    return depth


def weekly_windows(start: date, end: date) -> Iterator[tuple[date, date]]:
    cur = start
    while cur <= end:
        stop = min(cur + timedelta(days=6), end)
        yield cur, stop
        cur = stop + timedelta(days=1)


def window_url(first: date, last: date) -> str:
    poly = json.dumps(POLYGON).replace(" ", "")
    return (
        f"{ARGOVIS}?polygon={poly}&startDate={first.isoformat()}T00:00:00Z"
        f"&endDate={last.isoformat()}T23:59:59Z&data={DATA_KEYS}"
    )


def fetch_window(first: date, last: date, retries: int = 4, delay: float = 0.5) -> list[Any]:
    """Cached Argovis bulk query for one window. An empty window is cached as []."""
    url = window_url(first, last)
    key = hashlib.sha256(url.encode()).hexdigest()[:16]
    path = CACHE_DIR / f"{first.isoformat()}_{last.isoformat()}_{key}.json"
    if path.exists():
        cached: list[Any] = json.loads(path.read_text(encoding="utf-8"))
        return cached
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=120) as resp:
                body = resp.read().decode("utf-8")
            data = json.loads(body) if body.strip() else []
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:  # Argovis answers 404 for a window with no profiles
                data = []
                break
            if (e.code < 500 and e.code != 429) or attempt == retries:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == retries:
                raise
        time.sleep(min(60.0, 5.0 * 2**attempt))
    if not isinstance(data, list):
        data = []
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    time.sleep(delay)
    return data


def data_mode(record: dict[str, Any]) -> str:
    """R / A / D for the temperature variable, falling back to the source file prefix."""
    info = record.get("data_info") or [[], [], []]
    try:
        modes = info[2][info[0].index("temperature")]
        if modes and modes[1] in ("R", "A", "D"):
            return str(modes[1])
    except (IndexError, ValueError, TypeError):
        pass
    for src in record.get("source") or []:
        name = str(src.get("url", "")).rsplit("/", 1)[-1]
        if name[:1] in ("R", "D"):
            return name[0]
    return "R"  # unknown: treat as the least trusted mode


def parse_record(record: dict[str, Any]) -> dict[str, Any] | None:
    """One Argovis profile -> one row on the 15 standard depths, or None if unusable."""
    if record.get("geolocation_argoqc") != GOOD or record.get("timestamp_argoqc") != GOOD:
        return None
    lon, lat = (float(c) for c in record["geolocation"]["coordinates"])
    if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
        return None

    info = record.get("data_info") or [[]]
    keys: list[str] = info[0]
    data = record.get("data") or []
    try:
        cols = {k: np.asarray(data[keys.index(k)], dtype=np.float64) for k in DATA_KEYS.split(",")}
    except (ValueError, IndexError, TypeError):
        return None

    good = (
        (cols["temperature_argoqc"] == GOOD)
        & (cols["pressure_argoqc"] == GOOD)
        & np.isfinite(cols["temperature"])
        & np.isfinite(cols["pressure"])
    )
    if good.sum() < MIN_GOOD_LEVELS:
        return None

    depth = pressure_to_depth(cols["pressure"][good], lat)
    temps, mask = interpolate_profile_pchip(depth.tolist(), cols["temperature"][good].tolist())
    if mask.sum() < MIN_STANDARD_DEPTHS:
        return None

    profile_id = str(record["_id"])
    row: dict[str, Any] = {
        "profile_id": profile_id,
        "float_id": profile_id.split("_")[0],
        "cycle": int(record.get("cycle_number") or 0),
        "lat": lat,
        "lon": lon,
        "date": str(record["timestamp"])[:10],
        "timestamp": str(record["timestamp"]),
        "data_mode": data_mode(record),
        "n_good_levels": int(good.sum()),
        "max_depth_m": float(depth.max()),
        "sst": np.nan,  # filled by collocation with the surface store
    }
    for d, t, m in zip(STANDARD_DEPTHS, temps, mask, strict=True):
        row[f"t_{d}"] = float(t) if m else np.nan
        row[f"m_{d}"] = int(m)
    return row


def ingest(start: date, end: date, output: Path = OUTPUT) -> pd.DataFrame:
    rows: dict[str, dict[str, Any]] = {}
    seen = rejected = 0
    windows = list(weekly_windows(start, end))
    for i, (first, last) in enumerate(windows, 1):
        for record in fetch_window(first, last):
            seen += 1
            row = parse_record(record)
            if row is None:
                rejected += 1
            else:
                rows[row["profile_id"]] = row  # windows don't overlap, but dedupe anyway
        if i % 25 == 0 or i == len(windows):
            logger.info(
                "Window %d/%d: %d profiles kept of %d seen", i, len(windows), len(rows), seen
            )

    df = pd.DataFrame(list(rows.values())).sort_values(["date", "profile_id"], ignore_index=True)
    validate_argo_profiles(df)
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output, index=False)
    logger.info(
        "Wrote %s: %d profiles from %d floats (%d rejected by QC). Data modes: %s",
        output,
        len(df),
        df["float_id"].nunique(),
        rejected,
        df["data_mode"].value_counts().to_dict(),
    )
    return df


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Ingest NIO Argo profiles from Argovis")
    p.add_argument("--start", default="2015-01-01")
    p.add_argument("--end", default="2025-12-31")
    p.add_argument("--output", default=str(OUTPUT))
    a = p.parse_args()
    ingest(date.fromisoformat(a.start), date.fromisoformat(a.end), Path(a.output))


if __name__ == "__main__":
    main()
