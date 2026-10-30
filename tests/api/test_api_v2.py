"""/v2 product routes, ops middleware and derived ocean products."""

from __future__ import annotations

import io
from typing import Any

import numpy as np
import pytest
import xarray as xr
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aquasphere.constants import STANDARD_DEPTHS
from aquasphere.serve import ops, products
from aquasphere.serve.api_v2 import build_router
from aquasphere.serve.app import app as real_app
from aquasphere.serve.engine import InferenceEngine

DATES = [f"2023-01-{d:02d}" for d in range(1, 29)]


class FakeStore:
    dates = DATES

    def get_available_dates(self) -> list[str]:
        return list(DATES)


class FakeResolver:
    """Observations everywhere except east of 100°E and on 2023-01-03 (no data, never filled)."""

    zarr_store = FakeStore()

    async def resolve_many(
        self, pts: list[tuple[float, float, str, Any]], store_only: bool = False
    ) -> list[tuple[dict[str, float], str] | None]:
        out: list[tuple[dict[str, float], str] | None] = []
        for lat, lon, date, _ in pts:
            if lon > 100 or date == "2023-01-03":
                out.append(None)
            else:
                out.append(({"sst": 29.0 - 0.1 * (lat - 15), "sla": 0.05}, "local_store"))
        return out

    def store_series(
        self, lat: float, lon: float, dates: list[str]
    ) -> list[tuple[dict[str, float], str] | None]:
        return [
            None if d == "2023-01-03" else ({"sst": 29.0, "sla": 0.05}, "local_store")
            for d in dates
        ]


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> TestClient:
    from tests.api.test_engine_v2 import engine as v2_engine_fixture

    engine: InferenceEngine = v2_engine_fixture.__wrapped__(tmp_path_factory)  # type: ignore[attr-defined]
    app = FastAPI()
    app.include_router(build_router(engine, FakeResolver()))
    return TestClient(app)


# ── products ──────────────────────────────────────────────────────────────────


def test_tchp_and_d26_on_known_profiles() -> None:
    z = np.asarray(STANDARD_DEPTHS, dtype=float)
    # 30 °C mixed layer to 50 m, then 26 °C at 100 m, cooling below: D26 = 100 m
    t = np.interp(z, [0, 50, 100, 1000], [30, 30, 26, 5])
    assert products.isotherm_depth(t, 26.0) == pytest.approx(100.0)
    # Integral of (T - 26): 4 °C x 50 m + triangle 0.5 x 4 x 50 = 300 °C m
    expected = 1026 * 4178 * 300 * 1e-7
    assert products.tchp(t) == pytest.approx(expected, rel=2e-3)
    cold = np.interp(z, [0, 1000], [24, 5])
    assert products.isotherm_depth(cold, 26.0) == 0.0 and products.tchp(cold) == 0.0
    assert products.tchp(np.full(15, np.nan)) is None


def test_great_circle_endpoints_and_distance() -> None:
    lat, lon, dist = products.great_circle(10.0, 60.0, 10.0, 70.0, 11)
    assert lat[0] == pytest.approx(10.0) and lon[-1] == pytest.approx(70.0)
    assert dist[-1] == pytest.approx(1095.0, rel=0.01)  # 10° of longitude at 10°N
    assert np.all(np.diff(dist) > 0) and lat[5] > 10.0  # great circle bulges poleward


def test_exports_carry_provenance() -> None:
    row = {
        "lat": 15.0,
        "lon": 65.0,
        "date": "2023-01-05",
        "depths": list(STANDARD_DEPTHS),
        "temperatures": [20.0] * 15,
        "uncertainties": [0.5] * 15,
        "interval_lower": [19.0] * 15,
        "interval_upper": [21.0] * 15,
        "data_source": "local_store",
        "mode": "nowcast",
    }
    meta = {"model_version": "tier_a_v2.0", "git_sha": "abc123", "input_mode": "nowcast"}
    csv = products.to_csv([row], meta)
    assert "# model_version=tier_a_v2.0" in csv and "# git_sha=abc123" in csv
    body = [ln for ln in csv.splitlines() if not ln.startswith("#")]
    assert len(body) == 1 + 15 and body[1].endswith("local_store,nowcast")
    ds = xr.open_dataset(io.BytesIO(products.to_netcdf([row], meta)), engine="scipy")
    assert (
        ds["temperature"].shape == (1, 15) and ds.attrs["aquasphere_model_version"] == "tier_a_v2.0"
    )


# ── /v2 routes ────────────────────────────────────────────────────────────────


def test_meta_reports_v2_capabilities(client: TestClient) -> None:
    m = client.get("/v2/meta").json()
    assert m["protocol"] == "v2" and m["dissimilarity"] is True
    assert m["modes"] == ["delayed", "nowcast"] and "tchp" in m["layers"]


def test_grid_layers_leave_missing_cells_out(client: TestClient) -> None:
    r = client.get(
        "/v2/grid", params={"date": "2023-01-05", "depth": 100, "step": 5, "mode": "nowcast"}
    )
    assert r.status_code == 200
    g = r.json()
    assert g["missing"] > 0 and all(c["lon"] <= 100 for c in g["cells"])
    c = g["cells"][0]
    assert c["anomaly"] == pytest.approx(c["temperature"] - c["climatology"])
    assert c["interval_width"] > 0 and c["di"] is not None and g["mode"] == "nowcast"
    assert client.get("/v2/grid", params={"date": "2023-01-05", "depth": 101}).status_code == 422
    assert client.get("/v2/grid", params={"date": "2023-01-03", "step": 5}).status_code == 503


def test_transect_and_timeseries_sections(client: TestClient) -> None:
    t = client.get(
        "/v2/transect",
        params={"lat1": 15, "lon1": 90, "lat2": 15, "lon2": 104, "date": "2023-01-05", "n": 15},
    ).json()
    assert t["kind"] == "transect" and len(t["temperature"]) == len(t["axis"]) < 15
    assert len(t["skipped"]) == 15 - len(t["axis"])  # points east of 100°E have no data
    assert all(len(row) == 15 for row in t["temperature"])
    s = client.get(
        "/v2/timeseries",
        params={"lat": 15, "lon": 65, "start": "2023-01-01", "end": "2023-01-10", "step_days": 1},
    ).json()
    assert s["skipped"] == ["2023-01-03"] and "2023-01-03" not in s["axis"]
    assert len(s["axis"]) == 9 and s["axis"] == s["dates"]
    bad = client.get(
        "/v2/timeseries", params={"lat": 15, "lon": 65, "start": "2023-02-01", "end": "2023-01-01"}
    )
    assert bad.status_code == 422


def test_exports_and_drift(client: TestClient) -> None:
    csv = client.get("/v2/export/profile", params={"lat": 15, "lon": 65, "date": "2023-01-05"})
    assert csv.status_code == 200 and csv.headers["content-type"].startswith("text/csv")
    assert "attachment" in csv.headers["content-disposition"] and "# model_version=" in csv.text
    nc = client.get("/v2/export/grid", params={"date": "2023-01-05", "step": 5, "format": "netcdf"})
    assert nc.status_code == 200 and nc.content[:3] == b"CDF"
    d = client.get(
        "/v2/drift", params={"start": "2023-01-01", "end": "2023-01-28", "step_days": 7, "step": 5}
    ).json()
    assert [p["date"] for p in d["points"]] == [
        "2023-01-01",
        "2023-01-08",
        "2023-01-15",
        "2023-01-22",
    ]
    assert all(0 <= p["share_outside"] <= 1 and p["mean_di"] >= 0 for p in d["points"])


# ── ops middleware on the real app ────────────────────────────────────────────


def test_metrics_etag_gzip_and_request_ids() -> None:
    c = TestClient(real_app)
    r = c.get("/meta")
    assert r.status_code == 200 and "etag" in r.headers and r.headers["x-request-id"]
    again = c.get("/meta", headers={"If-None-Match": r.headers["etag"]})
    assert again.status_code == 304 and again.content == b""
    big = c.get("/openapi.json", headers={"Accept-Encoding": "gzip"})
    assert big.headers.get("content-encoding") == "gzip"
    text = c.get("/metrics").text
    assert 'aquasphere_requests_total{route="/meta",method="GET",status="200"}' in text
    assert "aquasphere_request_seconds_bucket" in text and "aquasphere_model_ready" in text


def test_rate_limit_returns_429_with_retry_after() -> None:
    app = FastAPI()

    @app.get("/v2/x")
    def x() -> dict[str, int]:
        return {"ok": 1}

    @app.get("/js/app.js")
    def static() -> dict[str, int]:
        return {"ok": 1}

    app.add_middleware(ops.OpsMiddleware, metrics=ops.Metrics(), per_minute=3)
    c = TestClient(app)
    codes = [c.get("/v2/x").status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200] and codes[3:] == [429, 429]
    r = c.get("/v2/x")
    assert int(r.headers["retry-after"]) >= 1
    # Static assets are never limited, so a page always loads
    assert all(c.get("/js/app.js").status_code == 200 for _ in range(10))


def test_batch_v2_lists_missing_points_instead_of_failing(client: TestClient) -> None:
    items = [
        {"lat": 15, "lon": 65, "date": "2023-01-05"},
        {"lat": 15, "lon": 102, "date": "2023-01-05"},  # no data east of 100E
        {"lat": 12, "lon": 88, "date": "2023-01-05", "mode": "nowcast"},
    ]
    r = client.post("/v2/predict_batch", json={"items": items}).json()
    assert r["missing"] == [1] and r["index"] == [0, 2] and r["count"] == 2
    assert [p["mode"] for p in r["predictions"]] == ["delayed", "nowcast"]
    none = client.post("/v2/predict_batch", json={"items": [items[1]]})
    assert none.status_code == 503
