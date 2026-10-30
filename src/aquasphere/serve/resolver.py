"""
Data-source resolution engine for surface satellite observations (SIH 26066).

Follows strict 4-stage precedence (never fabricate or silently simulate):
1. Local Zarr store        -> data_source = "local_store"
2. Disk cache (hashed key) -> data_source = "disk_cache"
3. Live ERDDAP             -> data_source = "live"
4. None available          -> HTTP 503 Service Unavailable
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from fastapi import HTTPException

from aquasphere.data.audit import store_is_synthetic
from aquasphere.data.sources import SOURCES
from aquasphere.data.store import SATELLITE_VARS, SurfaceZarrStore

logger = logging.getLogger(__name__)

CACHE_DIR = Path("cache/observations")
# OISST v2.1 Final on NOAA CoastWatch (the NCEI ERDDAP dataset this used to point at now 400s)
ERDDAP_URL = f"{SOURCES['oisst'].griddap}.csv"
# Which store to serve from: AQUASPHERE_STORE overrides; the default is the demo store the current
# checkpoint was trained against (see aquasphere.data.audit). Switch to the real multi-year store
# together with a model trained on it.
DEFAULT_STORE = Path(os.environ.get("AQUASPHERE_STORE", "data/store/surface.zarr"))
DAY_CACHE = 8  # days of full fields kept in memory for batch lookups
# AQUASPHERE_OFFLINE=1 disables live fetching (offline demos, deterministic tests)
NETWORK_DEFAULT = os.environ.get("AQUASPHERE_OFFLINE", "") not in ("1", "true", "yes")
LIVE_CONCURRENCY = 8  # live requests in flight at once for a batch of store misses


class CircuitBreaker:
    """Simple circuit breaker to avoid hammering remote ERDDAP during outages."""

    def __init__(self, failure_threshold: int = 3, recovery_time: float = 60.0) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_time = recovery_time
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.is_open = False

    def record_success(self) -> None:
        self.failure_count = 0
        self.is_open = False

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.is_open = True
            logger.warning("Circuit breaker opened for ERDDAP live requests.")

    def can_attempt(self) -> bool:
        if not self.is_open:
            return True
        if time.time() - self.last_failure_time > self.recovery_time:
            # Half-open state
            logger.info("Circuit breaker half-open: attempting recovery.")
            return True
        return False


class SurfaceResolver:
    """Resolves surface satellite observations following honest precedence."""

    def __init__(
        self,
        store_path: Path | str = DEFAULT_STORE,
        cache_dir: Path | str = CACHE_DIR,
        enable_network: bool = NETWORK_DEFAULT,
    ) -> None:
        self.store_path = Path(store_path)
        self.cache_dir = Path(cache_dir)
        self.enable_network = enable_network
        self.circuit_breaker = CircuitBreaker()
        self.mem_cache: dict[str, dict[str, Any]] = {}
        self.max_mem_entries = 1000
        self._days: OrderedDict[str, dict[str, np.ndarray]] = OrderedDict()

        # Attempt to open Zarr store if it exists
        self.zarr_store: SurfaceZarrStore | None = None
        self.store_synthetic = True
        if self.store_path.exists():
            try:
                self.zarr_store = SurfaceZarrStore(self.store_path, mode="r")
                self.store_synthetic = store_is_synthetic(self.zarr_store)
                logger.info(
                    "SurfaceResolver connected to %s Zarr store: %s",
                    "synthetic demo" if self.store_synthetic else "real",
                    self.store_path,
                )
            except Exception as e:
                logger.warning("Could not open Zarr store at %s: %s", self.store_path, e)

    @property
    def store_source(self) -> str:
        """Provenance label for observations served from the local store."""
        return "offline_synthetic" if self.store_synthetic else "local_store"

    def _day_fields(self, date: str) -> dict[str, np.ndarray] | None:
        """All fields for one store date, read once and kept in a small LRU."""
        if self.zarr_store is None or date not in self.zarr_store.date_to_idx:
            return None
        if date in self._days:
            self._days.move_to_end(date)
            return self._days[date]
        fields = self.zarr_store.read_day(date)
        self._days[date] = fields
        if len(self._days) > DAY_CACHE:
            self._days.popitem(last=False)
        return fields

    def store_series(
        self, lat: float, lon: float, dates: list[str]
    ) -> list[tuple[dict[str, float], str] | None]:
        """One cell through many stored dates, reading each time chunk once (Hovmoller views).

        Dates the store does not hold come back as None; nothing goes to the live chain.
        """
        store = self.zarr_store
        out: list[tuple[dict[str, float], str] | None] = [None] * len(dates)
        if store is None:
            return out
        held = [(n, store.date_to_idx[d]) for n, d in enumerate(dates) if d in store.date_to_idx]
        if not held:
            return out
        row, col = store.snap_indices(lat, lon)
        t_idx = np.array([t for _, t in held])
        cols = {
            v: np.asarray(
                store.root[v].get_orthogonal_selection((t_idx, row, col)), dtype=np.float64
            )
            for v in SATELLITE_VARS
            if v in store.root
        }
        for j, (n, _) in enumerate(held):
            obs = _valid_point({v: float(a[j]) for v, a in cols.items()})
            if obs is not None:
                out[n] = (obs, self.store_source)
        return out

    def _hash_key(self, lat: float, lon: float, date: str) -> str:
        """Compute deterministic SHA-256 cache key."""
        raw = f"{lat:.3f}_{lon:.3f}_{date}".encode()
        return hashlib.sha256(raw).hexdigest()

    def _read_disk_cache(self, key: str) -> dict[str, Any] | None:
        """Read cached observation from disk with hashed filename."""
        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.exists():
            try:
                data: dict[str, Any] = json.loads(cache_file.read_text(encoding="utf-8"))
                return data
            except Exception as e:
                logger.warning("Corrupted cache file %s: %s", cache_file, e)
        return None

    def _write_disk_cache(self, key: str, data: dict[str, Any]) -> None:
        """Atomically write observation to disk cache."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        temp_file = self.cache_dir / f"{key}.tmp.{time.time_ns()}"
        target_file = self.cache_dir / f"{key}.json"
        try:
            temp_file.write_text(json.dumps(data), encoding="utf-8")
            temp_file.replace(target_file)
        except Exception as e:
            logger.warning("Failed writing disk cache: %s", e)
            if temp_file.exists():
                temp_file.unlink(missing_ok=True)

    def _query_zarr_store(self, lat: float, lon: float, date: str) -> dict[str, float] | None:
        """Lookup collocated pixel from local Zarr store."""
        fields = self._day_fields(date)
        if fields is None or self.zarr_store is None:
            return None
        i, j = self.zarr_store.snap_indices(lat, lon)
        return _valid_point({k: float(a[i, j]) for k, a in fields.items()})

    async def _fetch_live_erddap(
        self, lat: float, lon: float, date: str
    ) -> dict[str, float] | None:
        """Fetch SST from remote NOAA ERDDAP with retry and circuit breaker."""
        if not self.enable_network or not self.circuit_breaker.can_attempt():
            return None

        # ERDDAP query: sst[(date):1:(date)][(0.0):1:(0.0)][(lat):1:(lat)][(lon):1:(lon)]
        target_time = f"{date}T12:00:00Z"
        query_url = f"{ERDDAP_URL}?sst[({target_time})][(0.0)][({lat:.2f})][({lon:.2f})]"

        for attempt in range(1, 3):
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(query_url)
                    if resp.status_code == 200:
                        lines = resp.text.strip().split("\n")
                        if len(lines) >= 3:
                            parts = lines[2].split(",")
                            if len(parts) >= 5:
                                self.circuit_breaker.record_success()
                                # ERDDAP snaps to the nearest time it has: a day missing from
                                # the product comes back as a neighbouring day. That is not an
                                # observation for the requested date, so don't use it.
                                if not parts[0].startswith(date):
                                    logger.info("Live OISST has no %s (nearest %s)", date, parts[0])
                                    return None
                                sst_val = float(parts[4])
                                if np.isfinite(sst_val):
                                    return {"sst": sst_val}
                                return None
            except Exception as e:
                logger.info("Live ERDDAP attempt %d failed: %s", attempt, e)
                await asyncio.sleep(0.2 * attempt)  # don't block the event loop

        self.circuit_breaker.record_failure()
        return None

    async def resolve(
        self,
        lat: float,
        lon: float,
        date: str,
        overrides: dict[str, float] | None = None,
    ) -> tuple[dict[str, float], str]:
        """Resolve surface observation for a point.

        Returns:
            (features_dict, data_source_str)
        """
        # If user explicitly provided manual overrides, use them
        if overrides and "sst" in overrides:
            return overrides, "user_override"

        cache_key = self._hash_key(lat, lon, date)

        # 0. In-memory LRU cache
        if cache_key in self.mem_cache:
            return self.mem_cache[cache_key]["features"], self.mem_cache[cache_key]["source"]

        # 1. Priority 1: Local Zarr store (labelled by whether it is real or the demo fixture).
        # Store hits are not copied into the disk cache: the store is already local.
        zarr_obs = self._query_zarr_store(lat, lon, date)
        if zarr_obs is not None:
            source = self.store_source
            self._update_mem_cache(cache_key, zarr_obs, source)
            return zarr_obs, source

        # 2. Priority 2: Disk Cache
        disk_obs = self._read_disk_cache(cache_key)
        if disk_obs is not None:
            features = disk_obs["features"]
            source = "disk_cache"
            self._update_mem_cache(cache_key, features, source)
            return features, source

        # 3. Priority 3: Live ERDDAP
        live_obs = await self._fetch_live_erddap(lat, lon, date)
        if live_obs is not None:
            source = "live"
            self._write_disk_cache(cache_key, {"features": live_obs, "source": source})
            self._update_mem_cache(cache_key, live_obs, source)
            return live_obs, source

        # 4. Priority 4: None Available -> Fail Explicitly (Never Simulate Silently)
        logger.error(
            "Surface observation unavailable for lat=%.2f, lon=%.2f, date=%s. "
            "Local store miss, disk cache miss, live ERDDAP unreachable.",
            lat,
            lon,
            date,
        )
        raise HTTPException(
            status_code=503,
            detail=(
                f"Surface satellite observation unavailable for ({lat:.2f}°N, {lon:.2f}°E) on {date}. "
                "Local Zarr store, disk cache, and remote NOAA ERDDAP all returned no valid data. "
                "Silent simulation is strictly prohibited by AquaSphere integrity policies."
            ),
        )

    async def resolve_many(
        self,
        points: list[tuple[float, float, str, dict[str, float] | None]],
        store_only: bool = False,
    ) -> list[tuple[dict[str, float], str] | None]:
        """Resolve many points at once; None marks a point with no observation.

        Store lookups read each date's fields once and index every point on that date with
        vectorised nearest-cell lookups, instead of one full read per point.

        store_only: on a date the local store holds, a cell with no value there (land, or a
        product gap) is final rather than sent down the live chain. Grids and series use it so
        hundreds of land cells do not each become a network request.
        """
        out: list[tuple[dict[str, float], str] | None] = [None] * len(points)
        pending: list[int] = []
        by_date: dict[str, list[int]] = {}
        for k, (lat, lon, date, overrides) in enumerate(points):
            if overrides and "sst" in overrides:
                out[k] = (overrides, "user_override")
                continue
            hit = self.mem_cache.get(self._hash_key(lat, lon, date))
            if hit is not None:
                out[k] = (hit["features"], hit["source"])
            elif self._day_fields(date) is not None:
                by_date.setdefault(date, []).append(k)
            else:
                pending.append(k)

        store = self.zarr_store
        for date, idx in by_date.items():
            fields = self._day_fields(date)
            if fields is None or store is None:
                pending.extend(idx)
                continue
            lats = np.array([points[k][0] for k in idx])
            lons = np.array([points[k][1] for k in idx])
            rows = np.abs(store.lat_grid[None, :] - lats[:, None]).argmin(axis=1)
            cols = np.abs(store.lon_grid[None, :] - lons[:, None]).argmin(axis=1)
            values = {v: a[rows, cols] for v, a in fields.items()}
            for n, k in enumerate(idx):
                obs = _valid_point({v: float(vals[n]) for v, vals in values.items()})
                if obs is None:
                    if not store_only:
                        pending.append(k)
                    continue
                out[k] = (obs, self.store_source)
                self._update_mem_cache(self._hash_key(*points[k][:3]), obs, self.store_source)

        # Store misses go through the normal chain (disk cache, live, 503), a few at a time so a
        # grid of live lookups doesn't run strictly one after another
        gate = asyncio.Semaphore(LIVE_CONCURRENCY)

        async def one(k: int) -> None:
            lat, lon, date, overrides = points[k]
            async with gate:
                try:
                    out[k] = await self.resolve(lat, lon, date, overrides)
                except HTTPException:
                    out[k] = None

        await asyncio.gather(*(one(k) for k in pending))
        return out

    def _update_mem_cache(self, key: str, features: dict[str, float], source: str) -> None:
        if len(self.mem_cache) >= self.max_mem_entries:
            # Simple eviction: clear oldest quarter
            keys_to_remove = list(self.mem_cache.keys())[: self.max_mem_entries // 4]
            for k in keys_to_remove:
                self.mem_cache.pop(k, None)
        self.mem_cache[key] = {"features": features, "source": source}


def _valid_point(point: dict[str, float]) -> dict[str, float] | None:
    """Drop missing / fill values; a point is usable only if it has SST."""
    valid = {k: v for k, v in point.items() if np.isfinite(v) and v > -900}
    return valid if "sst" in valid else None
