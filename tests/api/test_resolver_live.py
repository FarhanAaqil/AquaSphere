"""Live OISST fallback: real values pass, a neighbouring day returned by ERDDAP does not."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import HTTPException

from aquasphere.serve import resolver as resolver_mod
from aquasphere.serve.resolver import SurfaceResolver

HEADER = "time,zlev,latitude,longitude,sst\nUTC,m,degrees_north,degrees_east,degree_C\n"


def _fake_erddap(monkeypatch: pytest.MonkeyPatch, body: str, status: int = 200) -> list[str]:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(status, text=body)

    real = httpx.AsyncClient

    def client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        return real(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(resolver_mod.httpx, "AsyncClient", client)
    return seen


def _resolver(tmp_path: Path) -> SurfaceResolver:
    return SurfaceResolver(
        store_path=tmp_path / "none.zarr", cache_dir=tmp_path / "c", enable_network=True
    )


def test_live_value_for_the_requested_day_is_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = _fake_erddap(monkeypatch, HEADER + "2024-06-15T12:00:00Z,0.0,15.125,65.125,30.74\n")
    obs, src = asyncio.run(_resolver(tmp_path).resolve(15.0, 65.0, "2024-06-15"))
    assert (obs, src) == ({"sst": 30.74}, "live")
    assert "ncdcOisst21Agg" in seen[0]  # the CoastWatch dataset, not the retired NCEI one


def test_neighbouring_day_from_erddap_is_not_passed_off_as_the_requested_day(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # ERDDAP has no 2023-12-25 in this product and snaps to 2023-12-22
    _fake_erddap(monkeypatch, HEADER + "2023-12-22T12:00:00Z,0.0,15.125,65.125,27.1\n")
    with pytest.raises(HTTPException) as e:
        asyncio.run(_resolver(tmp_path).resolve(15.0, 65.0, "2023-12-25"))
    assert e.value.status_code == 503


def test_offline_switch_disables_live_fetching(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = _fake_erddap(monkeypatch, HEADER + "2024-06-15T12:00:00Z,0.0,15.125,65.125,30.74\n")
    r = SurfaceResolver(
        store_path=tmp_path / "none.zarr", cache_dir=tmp_path / "c", enable_network=False
    )
    with pytest.raises(HTTPException):
        asyncio.run(r.resolve(15.0, 65.0, "2024-06-15"))
    assert seen == []
