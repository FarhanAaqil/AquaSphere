"""
API Contract and Integration tests for AquaSphere FastAPI serving layer (SIH 26066).
"""

import numpy as np
import pytest
from fastapi.testclient import TestClient

from aquasphere.constants import STANDARD_DEPTHS
from aquasphere.serve.app import app, engine, resolver

client = TestClient(app)


def test_health_endpoint() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["uptime_seconds"] >= 0.0


def test_ready_endpoint() -> None:
    resp = client.get("/ready")
    assert resp.status_code == 200
    data = resp.json()
    # Ready only with trained weights whose provenance is not contradicted (CI has no checkpoint)
    trained = engine.weights == "trained"
    assert data["ready"] is (trained and engine.provenance_status != "mismatch")
    assert data["details"]["weights"] == engine.weights
    assert data["model_loaded"] is True
    assert "model_version" in data["details"]
    assert "provenance_status" in data["details"]


def test_meta_endpoint() -> None:
    resp = client.get("/meta")
    assert resp.status_code == 200
    data = resp.json()
    assert data["domain"]["lat_min"] == 5.0
    assert data["domain"]["lat_max"] == 30.0
    assert data["domain"]["lon_min"] == 45.0
    assert data["domain"]["lon_max"] == 105.0
    assert data["standard_depths"] == list(STANDARD_DEPTHS)


def test_predict_single_with_overrides() -> None:
    payload = {
        "lat": 12.5,
        "lon": 68.0,
        "date": "2023-05-15",
        "features": {
            "sst": 29.8,
            "sss": 35.4,
            "sla": 0.08,
            "ug": 0.1,
            "vg": -0.2,
        },
    }
    resp = client.post("/predict", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["lat"] == pytest.approx(12.5)
    assert data["lon"] == pytest.approx(68.0)
    assert len(data["depths"]) == 15
    assert len(data["temperatures"]) == 15
    assert len(data["uncertainties"]) == 15
    assert len(data["interval_lower"]) == 15
    assert len(data["interval_upper"]) == 15

    # Conformal interval bounds must be strictly lower < upper
    for low, up in zip(data["interval_lower"], data["interval_upper"], strict=False):
        assert low < up

    # Embedding vector has 16 dimensions and norm approx 1.0
    emb = np.array(data["embedding"])
    assert len(emb) == 16
    assert np.linalg.norm(emb) == pytest.approx(1.0, abs=1e-4)

    assert data["data_source"] == "user_override"


def test_predict_out_of_domain_rejected_422() -> None:
    # Latitude out of domain (50°N is North Atlantic, outside North Indian Ocean 5-30°N)
    payload_bad_lat = {
        "lat": 50.0,
        "lon": 65.0,
        "date": "2023-05-15",
    }
    resp1 = client.post("/predict", json=payload_bad_lat)
    assert resp1.status_code == 422

    # Longitude out of domain (10°E is outside 45-105°E)
    payload_bad_lon = {
        "lat": 15.0,
        "lon": 10.0,
        "date": "2023-05-15",
    }
    resp2 = client.post("/predict", json=payload_bad_lon)
    assert resp2.status_code == 422

    # Invalid date format
    payload_bad_date = {
        "lat": 15.0,
        "lon": 65.0,
        "date": "15-05-2023",
    }
    resp3 = client.post("/predict", json=payload_bad_date)
    assert resp3.status_code == 422


def test_predict_batch_endpoint() -> None:
    payload = {
        "items": [
            {
                "lat": 10.0,
                "lon": 60.0,
                "date": "2023-06-01",
                "features": {"sst": 28.5},
            },
            {
                "lat": 15.0,
                "lon": 70.0,
                "date": "2023-06-02",
                "features": {"sst": 29.0},
            },
            {
                "lat": 20.0,
                "lon": 85.0,
                "date": "2023-06-03",
                "features": {"sst": 29.5},
            },
        ]
    }
    resp = client.post("/predict_batch", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["count"] == 3
    assert len(data["predictions"]) == 3
    for p in data["predictions"]:
        assert len(p["temperatures"]) == 15
        assert len(p["embedding"]) == 16


def test_validation_profile_held_out_lookup() -> None:
    # Query held-out profile near (12.0°N, 70.0°E)
    resp = client.get("/validation/profile?lat=12.0&lon=70.0")
    assert resp.status_code == 200
    data = resp.json()

    assert "float_id" in data
    assert "distance_km" in data
    assert data["distance_km"] >= 0.0
    assert len(data["true_temperatures"]) == 15
    assert len(data["pred_temperatures"]) == 15
    assert data["rmse"] >= 0.0


def test_validation_metrics_endpoint() -> None:
    resp = client.get("/validation")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)


def test_explain_endpoint() -> None:
    # Feature attribution via gradient sensitivity
    # First seed the resolver memory cache for this coordinate
    resolver._update_mem_cache(
        resolver._hash_key(14.0, 68.0, "2023-07-01"),
        {"sst": 28.5, "sss": 35.0, "sla": 0.02},
        "disk_cache",
    )
    resp = client.get("/explain?lat=14.0&lon=68.0&date=2023-07-01")
    assert resp.status_code == 200
    data = resp.json()

    assert data["method"] == "gradient_x_input"
    assert "sst" in data["feature_attributions"]
    assert "lat" in data["feature_attributions"]
    assert pytest.approx(sum(data["feature_attributions"].values()), abs=1e-3) == 1.0


def test_offline_fallback_honesty() -> None:
    # Disable network and ensure that asking for an un-cached, un-stored coordinate
    # raises 503 instead of fabricating fake numbers
    prev_network = resolver.enable_network
    resolver.enable_network = False
    try:
        # Clear mem cache for this arbitrary test coordinate
        test_key = resolver._hash_key(28.0, 95.0, "2021-02-02")
        resolver.mem_cache.pop(test_key, None)

        resp = client.post(
            "/predict",
            json={"lat": 28.0, "lon": 95.0, "date": "2021-02-02"},
        )
        # Must return 503 Service Unavailable with explicit message
        assert resp.status_code == 503
        assert "Silent simulation is strictly prohibited" in resp.json()["detail"]
    finally:
        resolver.enable_network = prev_network


def test_predict_get_query_params() -> None:
    # Pre-seed resolver memory cache to ensure resolution succeeds
    resolver._update_mem_cache(
        resolver._hash_key(14.0, 70.0, "2023-06-01"),
        {"sst": 29.5, "sss": 36.0, "sla": 0.05, "ug": 0.1, "vg": -0.1},
        "disk_cache",
    )
    resp = client.get("/predict?lat=14.0&lon=70.0&date=2023-06-01")
    assert resp.status_code == 200
    data = resp.json()
    assert data["lat"] == pytest.approx(14.0)
    assert data["lon"] == pytest.approx(70.0)
    assert len(data["temperatures"]) == 15
    assert len(data["embedding"]) == 16


def test_frontend_static_serving() -> None:
    # Check index.html serving
    resp_root = client.get("/")
    assert resp_root.status_code == 200
    assert "AquaSphere" in resp_root.text
    assert "<nav" in resp_root.text

    # Design tokens, vendored libraries, fonts and data files are all served locally
    resp_css = client.get("/styles/tokens.css")
    assert resp_css.status_code == 200
    assert "--abyss-0" in resp_css.text

    assert client.get("/vendor/three/three.module.min.js").status_code == 200
    assert client.get("/fonts/inter-variable.woff2").status_code == 200
    assert client.get("/assets/icons.svg").status_code == 200
    assert client.get("/data/heldout.json").status_code == 200
