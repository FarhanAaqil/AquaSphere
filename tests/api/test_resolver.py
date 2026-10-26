"""
Unit tests for SurfaceResolver and CircuitBreaker (SIH 26066).
"""

from pathlib import Path

import pytest
from fastapi import HTTPException

from aquasphere.serve.resolver import CircuitBreaker, SurfaceResolver


def test_circuit_breaker_logic() -> None:
    cb = CircuitBreaker(failure_threshold=2, recovery_time=1.0)
    assert cb.can_attempt() is True
    assert cb.is_open is False

    cb.record_failure()
    assert cb.failure_count == 1
    assert cb.is_open is False

    cb.record_failure()
    assert cb.failure_count == 2
    assert cb.is_open is True
    assert cb.can_attempt() is False

    cb.record_success()
    assert cb.is_open is False
    assert cb.failure_count == 0


def test_resolver_disk_cache_roundtrip(tmp_path: Path) -> None:
    cache_dir = tmp_path / "obs_cache"
    resolver = SurfaceResolver(store_path=tmp_path / "dummy.zarr", cache_dir=cache_dir)

    key = resolver._hash_key(12.0, 65.0, "2023-05-01")
    assert resolver._read_disk_cache(key) is None

    test_data = {"features": {"sst": 29.2, "sss": 35.1}, "source": "disk_cache"}
    resolver._write_disk_cache(key, test_data)

    cached = resolver._read_disk_cache(key)
    assert cached is not None
    assert cached["features"]["sst"] == pytest.approx(29.2)
    assert cached["source"] == "disk_cache"


@pytest.mark.asyncio
async def test_resolver_resolve_precedence(tmp_path: Path) -> None:
    cache_dir = tmp_path / "obs_cache"
    resolver = SurfaceResolver(store_path=tmp_path / "dummy.zarr", cache_dir=cache_dir)

    # 1. User overrides take immediate priority
    feats, src = await resolver.resolve(15.0, 70.0, "2023-01-01", overrides={"sst": 28.0})
    assert src == "user_override"
    assert feats["sst"] == 28.0

    # 2. Disk cache hit
    key = resolver._hash_key(15.0, 70.0, "2023-01-02")
    resolver._write_disk_cache(key, {"features": {"sst": 27.5}, "source": "disk_cache"})
    feats, src = await resolver.resolve(15.0, 70.0, "2023-01-02")
    assert src == "disk_cache"
    assert feats["sst"] == 27.5

    # 3. None available raises 503
    resolver.enable_network = False
    with pytest.raises(HTTPException) as exc_info:
        await resolver.resolve(15.0, 70.0, "2023-01-03")
    assert exc_info.value.status_code == 503
    assert "Silent simulation is strictly prohibited" in str(exc_info.value.detail)


def test_resolver_mem_cache_eviction(tmp_path: Path) -> None:
    resolver = SurfaceResolver(store_path=tmp_path / "dummy.zarr", cache_dir=tmp_path / "cache")
    resolver.max_mem_entries = 4

    for i in range(6):
        resolver._update_mem_cache(f"key_{i}", {"sst": 25.0 + i}, "test")

    # Cache should have evicted oldest entries and maintained cap
    assert len(resolver.mem_cache) <= 5
