"""
Download the open satellite products and build the multi-year surface store (roadmap Phase 2).

    python -m aquasphere.data.satellite_fetch --start 2015-01-01 --end 2025-12-31

For every dataset in aquasphere.data.sources and every calendar month, a NetCDF subset of the
study domain is fetched from ERDDAP (cached under data/cache/satellite/<key>/<YYYY-MM>.nc, retried
on 5xx), bilinearly regridded onto the store's 0.25° grid and written into a Zarr store. A day a
product does not cover stays NaN with its mask at 0; nothing is filled in.
"""

from __future__ import annotations

import argparse
import calendar
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from aquasphere.data.sources import SOURCES, DatasetSpec
from aquasphere.data.store import DEFAULT_LAT_GRID, DEFAULT_LON_GRID, SurfaceZarrStore

logger = logging.getLogger(__name__)

CACHE_ROOT = Path("data/cache/satellite")
STORE_PATH = Path("data/store/surface_nio.zarr")
# Fetch half a cell beyond the domain so bilinear interpolation has neighbours at the edges.
PAD = 0.5
TIME_CHUNK = 16

Fetcher = Callable[[str, Path], bool]


def month_starts(start: date, end: date) -> list[date]:
    out, cur = [], date(start.year, start.month, 1)
    while cur <= end:
        out.append(cur)
        cur = date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
    return out


def month_url(spec: DatasetSpec, month: date) -> str | None:
    """ERDDAP griddap NetCDF URL for one month of one dataset, or None before it starts."""
    first = max(month, date.fromisoformat(spec.start))
    last = date(month.year, month.month, calendar.monthrange(month.year, month.month)[1])
    if first > last:
        return None
    lat0, lat1 = float(DEFAULT_LAT_GRID[0]) - PAD, float(DEFAULT_LAT_GRID[-1]) + PAD
    lon0, lon1 = float(DEFAULT_LON_GRID[0]) - PAD, float(DEFAULT_LON_GRID[-1]) + PAD
    t = f"[({first.isoformat()}T00:00:00Z):1:({last.isoformat()}T23:59:59Z)]"
    space = f"{spec.extra_dim}[({lat0}):1:({lat1})][({lon0}):1:({lon1})]"
    query = ",".join(f"{v}{t}{space}" for v in spec.variables.values())
    return f"{spec.griddap}.nc?{query}"


def http_fetch(url: str, dest: Path, retries: int = 4, timeout: float = 300.0) -> bool:
    """Download url to dest. Returns False when ERDDAP says the range has no data (404)."""
    tmp = dest.with_suffix(".part")
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp, tmp.open("wb") as f:
                while chunk := resp.read(1 << 20):
                    f.write(chunk)
            tmp.replace(dest)
            return True
        except urllib.error.HTTPError as e:
            if e.code == 404:  # "Your query produced no matching results."
                return False
            if e.code < 500 or attempt == retries:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == retries:
                raise
        time.sleep(min(60.0, 5.0 * 2**attempt))
    return False


def fetch_month(spec: DatasetSpec, month: date, fetch: Fetcher = http_fetch) -> Path | None:
    """Cached path to one month's NetCDF, or None if the product has nothing for that month."""
    dest = CACHE_ROOT / spec.key / f"{month:%Y-%m}.nc"
    empty = dest.with_suffix(".empty")
    if dest.exists():
        return dest
    if empty.exists():
        return None
    url = month_url(spec, month)
    if url is None:
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    if fetch(url, dest):
        return dest
    empty.touch()  # remember "no data" so reruns don't re-ask
    return None


def regrid_month(spec: DatasetSpec, path: Path) -> dict[str, dict[str, np.ndarray]]:
    """Read a month file and bilinearly regrid every variable onto the store grid.

    Returns {date: {store_var: 2-D array}}.
    """
    out: dict[str, dict[str, np.ndarray]] = {}
    with xr.open_dataset(path) as ds:
        ds = ds.squeeze(drop=True)  # drop zlev / altitude singletons
        lat = "latitude" if "latitude" in ds.coords else "lat"
        lon = "longitude" if "longitude" in ds.coords else "lon"
        ds = ds.sortby([lat, lon])
        grid = ds.interp(
            {lat: DEFAULT_LAT_GRID.astype(float), lon: DEFAULT_LON_GRID.astype(float)},
            method="linear",
        )
        days = pd.to_datetime(grid["time"].values).strftime("%Y-%m-%d")
        for i, day in enumerate(days):
            fields = out.setdefault(day, {})
            for store_var, src_var in spec.variables.items():
                fields[store_var] = np.asarray(grid[src_var].values[i], dtype=np.float32)
    return out


def store_dates(start: date, end: date) -> list[str]:
    n = (end - start).days + 1
    return [(start + timedelta(days=i)).isoformat() for i in range(n)]


def build_store(
    start: date,
    end: date,
    store_path: Path = STORE_PATH,
    sources: Iterable[DatasetSpec] = SOURCES.values(),
    fetch: Fetcher = http_fetch,
    workers: int = 4,
) -> dict[str, dict[str, int]]:
    """Download everything needed and write the store. Returns days covered per dataset/var."""
    sources = list(sources)
    months = month_starts(start, end)
    dates = store_dates(start, end)
    store = SurfaceZarrStore.create(store_path, dates, time_chunk=TIME_CHUNK)

    # 1. Download (I/O bound, so threads); one failed month is logged and left masked.
    jobs = [(spec, m) for spec in sources for m in months]
    paths: dict[tuple[str, date], Path] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_month, spec, m, fetch): (spec, m) for spec, m in jobs}
        for n, fut in enumerate(as_completed(futures), 1):
            spec, m = futures[fut]
            try:
                p = fut.result()
                if p is not None:
                    paths[(spec.key, m)] = p
            except Exception as e:
                logger.error("Download failed for %s %s: %s", spec.key, f"{m:%Y-%m}", e)
            if n % 50 == 0 or n == len(jobs):
                logger.info("Downloaded %d/%d dataset-months", n, len(jobs))

    # 2. Regrid and write, one dataset-month at a time, as a contiguous block per variable
    covered: dict[str, dict[str, int]] = {s.key: {} for s in sources}
    shape = (len(DEFAULT_LAT_GRID), len(DEFAULT_LON_GRID))
    for spec in sources:
        for m in months:
            p = paths.get((spec.key, m))
            if p is None:
                continue
            # Never accept days before the product's documented start, whatever the server sends
            days = {d: f for d, f in regrid_month(spec, p).items() if d >= spec.start}
            month_days = [d for d in dates if d[:7] == f"{m:%Y-%m}"]
            if not month_days:
                continue
            blocks = {
                v: np.full((len(month_days), *shape), np.nan, np.float32) for v in spec.variables
            }
            for i, day in enumerate(month_days):
                for v, arr in days.get(day, {}).items():
                    blocks[v][i] = arr
            first_var = next(iter(spec.variables))
            mask = np.isfinite(blocks[first_var]).astype(np.uint8)
            store.write_block(month_days[0], blocks, {spec.mask: mask})
            for v in spec.variables:
                n = int(sum(1 for d in month_days if d in days))
                covered[spec.key][v] = covered[spec.key].get(v, 0) + n
        logger.info("Wrote %s: %s days", spec.key, covered[spec.key])

    store.root.attrs.update(
        {
            "synthetic": False,
            "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "sources": {
                s.key: {
                    "dataset_id": s.dataset_id,
                    "server": s.server,
                    "variables": s.variables,
                    "title": s.title,
                    "start": s.start,
                }
                for s in sources
            },
            "coverage_days": covered,
        }
    )
    return covered


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Build the multi-year surface store from open data")
    p.add_argument("--start", default="2015-01-01")
    p.add_argument("--end", default="2025-12-31")
    p.add_argument("--store", default=str(STORE_PATH))
    p.add_argument("--only", nargs="*", choices=sorted(SOURCES), help="Subset of datasets")
    p.add_argument("--workers", type=int, default=4)
    a = p.parse_args()
    specs = [SOURCES[k] for k in (a.only or SOURCES)]
    covered = build_store(
        date.fromisoformat(a.start),
        date.fromisoformat(a.end),
        Path(a.store),
        specs,
        workers=a.workers,
    )
    print(covered)


if __name__ == "__main__":
    main()
