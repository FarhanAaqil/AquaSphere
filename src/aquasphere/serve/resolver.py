"""
Data-source resolution engine for surface satellite observations (SIH 26066).

Follows strict 4-stage precedence (never fabricate or silently simulate):
1. Local Zarr store        -> data_source = "local_store"
2. Disk cache (hashed key) -> data_source = "disk_cache"
3. Live ERDDAP             -> data_source = "live"
4. None available          -> HTTP 503 Service Unavailable
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from fastapi import HTTPException

from aquasphere.data.store import SurfaceZarrStore

logger = logging.getLogger(__name__)

CACHE_DIR = Path("cache/observations")
ERDDAP_URL = "https://www.ncei.noaa.gov/erddap/griddap/ncdc_oisst_v2_avhrr_by_time_zlev_lat_lon.csv"


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
        store_path: Path | str = "data/store/surface.zarr",
        cache_dir: Path | str = CACHE_DIR,
        enable_network: bool = True,
    ) -> None:
        self.store_path = Path(store_path)
        self.cache_dir = Path(cache_dir)
        self.enable_network = enable_network
        self.circuit_breaker = CircuitBreaker()
        self.mem_cache: dict[str, dict[str, Any]] = {}
        self.max_mem_entries = 1000

        # Attempt to open Zarr store if it exists
        self.zarr_store: SurfaceZarrStore | None = None
        if self.store_path.exists():
            try:
                self.zarr_store = SurfaceZarrStore(self.store_path, mode="r")
                logger.info("SurfaceResolver connected to local Zarr store: %s", self.store_path)
            except Exception as e:
                logger.warning("Could not open Zarr store at %s: %s", self.store_path, e)

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
        if self.zarr_store is None:
            return None

        try:
            pt = self.zarr_store.extract_point(lat, lon, date)
            valid = {k: v for k, v in pt.items() if np.isfinite(v) and v > -900}
            if "sst" in valid:
                return valid
            return None
        except Exception as e:
            logger.debug("Zarr query error: %s", e)
            return None

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
                                sst_val = float(parts[4])
                                if np.isfinite(sst_val):
                                    self.circuit_breaker.record_success()
                                    return {"sst": sst_val}
            except Exception as e:
                logger.info("Live ERDDAP attempt %d failed: %s", attempt, e)
                time.sleep(0.2 * attempt)

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

        # 1. Priority 1: Local Zarr Store
        zarr_obs = self._query_zarr_store(lat, lon, date)
        if zarr_obs is not None:
            source = "local_store"
            self._write_disk_cache(cache_key, {"features": zarr_obs, "source": source})
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

    def _update_mem_cache(self, key: str, features: dict[str, float], source: str) -> None:
        if len(self.mem_cache) >= self.max_mem_entries:
            # Simple eviction: clear oldest quarter
            keys_to_remove = list(self.mem_cache.keys())[: self.max_mem_entries // 4]
            for k in keys_to_remove:
                self.mem_cache.pop(k, None)
        self.mem_cache[key] = {"features": features, "source": source}
