"""Batch resolution: same answers as per-point resolution, honest store labels, one read per date."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

import aquasphere.serve.app  # noqa: F401  (registers the module)
from aquasphere.data.store import (
    DEFAULT_LAT_GRID,
    DEFAULT_LON_GRID,
    SATELLITE_VARS,
    SurfaceZarrStore,
)
from aquasphere.serve.resolver import SurfaceResolver

# The package re-exports the FastAPI object as `app`, so take the module itself
app_module = sys.modules["aquasphere.serve.app"]

DATES = ["2021-03-01", "2021-03-02"]


def _make_store(path: Path, synthetic: bool | None) -> None:
    store = SurfaceZarrStore.create(path, DATES)
    shape = (len(DEFAULT_LAT_GRID), len(DEFAULT_LON_GRID))
    lat = DEFAULT_LAT_GRID[:, None].astype(np.float32)
    for n, d in enumerate(DATES):
        fields = {v: np.full(shape, 1.0 + n, np.float32) for v in SATELLITE_VARS}
        fields["sst"] = (25.0 + 0.1 * lat + n + 0 * fields["sst"]).astype(np.float32)
        fields["sst"][:5, :5] = np.nan  # a land corner: SST missing -> not usable
        store.write_day(d, fields)
    if synthetic is not None:
        store.root.attrs["synthetic"] = synthetic


def _resolver(tmp_path: Path, synthetic: bool | None = False) -> SurfaceResolver:
    _make_store(tmp_path / "s.zarr", synthetic)
    return SurfaceResolver(
        store_path=tmp_path / "s.zarr", cache_dir=tmp_path / "cache", enable_network=False
    )


@pytest.mark.parametrize(("flag", "label"), [(False, "local_store"), (None, "offline_synthetic")])
def test_store_hits_are_labelled_by_what_the_store_is(
    tmp_path: Path, flag: bool | None, label: str
) -> None:
    r = _resolver(tmp_path, flag)
    obs, src = asyncio.run(r.resolve(15.0, 65.0, "2021-03-01"))
    assert src == label
    assert obs["sst"] == pytest.approx(25.0 + 0.1 * 15.0, abs=1e-4)


def test_resolve_many_matches_point_by_point(tmp_path: Path) -> None:
    r = _resolver(tmp_path)
    rng = np.random.default_rng(1)
    points: list[tuple[float, float, str, Any]] = [
        (float(rng.uniform(6, 29)), float(rng.uniform(46, 104)), DATES[i % 2], None)
        for i in range(60)
    ]
    points.append((10.0, 60.0, "2021-03-01", {"sst": 30.0}))  # user override
    batch = asyncio.run(r.resolve_many(points))

    fresh = _resolver(tmp_path / "again")
    for p, got in zip(points, batch, strict=True):
        assert got is not None
        expected = asyncio.run(fresh.resolve(p[0], p[1], p[2], p[3]))
        assert got == expected


def test_resolve_many_reads_each_date_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    r = _resolver(tmp_path)
    assert r.zarr_store is not None
    calls: list[str] = []
    real = r.zarr_store.read_day
    monkeypatch.setattr(r.zarr_store, "read_day", lambda d, v=None: calls.append(d) or real(d, v))
    pts = [(10.0 + i * 0.1, 60.0, DATES[i % 2], None) for i in range(200)]
    asyncio.run(r.resolve_many(pts))
    assert sorted(calls) == sorted(DATES)


def test_unavailable_points_come_back_as_none(tmp_path: Path) -> None:
    r = _resolver(tmp_path)
    out = asyncio.run(
        r.resolve_many(
            [
                (
                    float(DEFAULT_LAT_GRID[1]),
                    float(DEFAULT_LON_GRID[1]),
                    "2021-03-01",
                    None,
                ),  # land
                (15.0, 65.0, "1999-01-01", None),  # not in store, network off
                (15.0, 65.0, "2021-03-02", None),
            ]
        )
    )
    assert out[0] is None and out[1] is None
    assert out[2] is not None and out[2][1] == "local_store"


def test_batch_endpoint_keeps_the_503_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_module, "resolver", _resolver(tmp_path))
    client = TestClient(app_module.app)
    ok = client.post(
        "/predict_batch", json={"items": [{"lat": 15.0, "lon": 65.0, "date": "2021-03-01"}]}
    )
    assert ok.status_code == 200
    assert ok.json()["predictions"][0]["data_source"] == "local_store"
    bad = client.post(
        "/predict_batch",
        json={
            "items": [
                {"lat": 15.0, "lon": 65.0, "date": "2021-03-01"},
                {"lat": 15.0, "lon": 65.0, "date": "1999-01-01"},
            ]
        },
    )
    assert bad.status_code == 503
    assert "1 of 2 points" in bad.json()["detail"]


def test_grid_skips_cells_without_observations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_module, "resolver", _resolver(tmp_path))
    client = TestClient(app_module.app)
    data = client.get("/grid?date=2021-03-01&step=5").json()
    all_cells = 6 * 13  # 5..30 by 5 x 45..105 by 5
    assert 0 < data["count"] < all_cells  # the NaN corner cell is left out, not invented
    assert {p["data_source"] for p in data["points"]} == {"local_store"}
    empty = client.get("/grid?date=1999-01-01&step=5").json()
    assert empty["count"] == 0
