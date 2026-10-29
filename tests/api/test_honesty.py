"""
API honesty contract (roadmap Phase 1, items A3 to A6).

The API must not invent or mislabel anything: training membership is real, missing observations
are null rather than 0 °C, labels describe what was actually computed, and missing results are a
404 instead of placeholder numbers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from aquasphere.serve.app import app, engine, resolver
from aquasphere.serve.membership import TrainingMembership

client = TestClient(app)
ARGO_CSV = Path("data/argo_sst_training.csv")


def _training_row() -> pd.Series:
    df = pd.read_csv(ARGO_CSV)
    df["float_id"] = df["profile_id"].astype(str).str.split("_").str[0]
    train = engine.membership.train_float_ids or set()
    return df[df["float_id"].isin(train)].iloc[0]


# ── Membership ────────────────────────────────────────────────────────────────


def test_membership_is_known_and_matches_training_split() -> None:
    assert engine.membership.known
    assert engine.membership.source != "unknown"
    # train.py: float-grouped 80/20 over 103 floats
    assert len(engine.membership.train_float_ids or set()) == 82


def test_membership_unknown_without_any_argo_table(tmp_path: Path) -> None:
    m = TrainingMembership.resolve(None, tables=(tmp_path / "missing.parquet",))
    assert not m.known
    assert m.float_in_training("123") is None
    assert m.point_in_training(15.0, 65.0, "2025-06-15") is None


def test_membership_prefers_ids_stored_in_checkpoint(tmp_path: Path) -> None:
    csv = tmp_path / "argo.csv"
    pd.DataFrame(
        {
            "profile_id": ["111_001", "222_001"],
            "lat": [10.0, 20.0],
            "lon": [60.0, 88.0],
            "date": ["2025-05-15", "2025-05-15"],
        }
    ).to_csv(csv, index=False)
    m = TrainingMembership.resolve({"train_float_ids": ["111"]}, tables=(csv,))
    assert m.source == "checkpoint"
    assert m.float_in_training("111") is True
    assert m.float_in_training("222") is False
    assert m.point_in_training(10.05, 60.05, "2025-05-15") is True
    assert m.point_in_training(20.0, 88.0, "2025-05-15") is False  # float 222 is not training


def test_predict_flags_a_training_point() -> None:
    row = _training_row()
    resp = client.post(
        "/predict",
        json={
            "lat": float(row.lat),
            "lon": float(row.lon),
            "date": str(row.date)[:10],
            "features": {"sst": float(row.sst)},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["in_training_set"] is True


def test_predict_far_from_training_is_not_flagged() -> None:
    resp = client.post(
        "/predict", json={"lat": 6.0, "lon": 104.0, "date": "2021-01-02", "features": {"sst": 28.0}}
    )
    assert resp.status_code == 200
    assert resp.json()["in_training_set"] is False


# ── /validation/profile ───────────────────────────────────────────────────────


def test_validation_profile_is_held_out_by_default() -> None:
    data = client.get("/validation/profile?lat=15.0&lon=65.0").json()
    assert data["in_training_set"] is False
    assert data["data_source"] == "local_store"


def test_validation_profile_can_include_training_floats() -> None:
    row = _training_row()
    data = client.get(
        f"/validation/profile?lat={row.lat}&lon={row.lon}&include_training=true"
    ).json()
    assert data["distance_km"] == pytest.approx(0.0, abs=1e-6)
    assert data["in_training_set"] is True


def test_validation_profile_missing_depths_are_null_not_zero() -> None:
    # Sweep the domain so profiles with shallow gaps are included
    seen_null = False
    for lat, lon in [(8, 52), (12, 70), (17, 65), (15, 88), (20, 90), (10, 80)]:
        data = client.get(f"/validation/profile?lat={lat}&lon={lon}").json()
        temps: list[Any] = data["true_temperatures"]
        assert 0.0 not in temps
        observed = [i for i, t in enumerate(temps) if t is not None]
        assert data["n_observed"] == len(observed)
        seen_null |= len(observed) < len(temps)
        if observed:
            diff = np.array([data["pred_temperatures"][i] - temps[i] for i in observed])
            assert data["rmse"] == pytest.approx(float(np.sqrt(np.mean(diff**2))), rel=1e-6)
    assert seen_null, "expected at least one profile with an unobserved depth"


# ── /meta, /explain, /grid, /validation ───────────────────────────────────────


def test_meta_lists_available_dates() -> None:
    data = client.get("/meta").json()
    assert isinstance(data["available_dates"], list)
    assert data["available_dates"] == sorted(data["available_dates"])


def test_ready_reports_how_membership_was_determined() -> None:
    details = client.get("/ready").json()["details"]
    assert details["training_membership"] == engine.membership.source


def test_explain_labels_its_method_and_source() -> None:
    resolver._update_mem_cache(
        resolver._hash_key(14.5, 66.0, "2023-07-01"), {"sst": 28.5, "sla": 0.02}, "disk_cache"
    )
    data = client.get("/explain?lat=14.5&lon=66.0&date=2023-07-01").json()
    assert data["method"] == "gradient_x_input"
    assert data["target"] == "temperature_100m"
    assert data["data_source"] == "disk_cache"


def test_grid_returns_true_pca_and_per_cell_source(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_resolve(lat: float, lon: float, date: str, overrides: Any = None) -> Any:
        return {"sst": 26.0 + 0.1 * lat - 0.02 * lon, "sla": 0.001 * lon}, "disk_cache"

    monkeypatch.setattr(resolver, "resolve", fake_resolve)
    data = client.get("/grid?date=2023-07-01&step=5").json()
    assert data["count"] == len(data["points"]) > 3
    assert data["projection"] == "pca"
    assert len(data["explained_variance"]) == 2
    assert 0.0 <= sum(data["explained_variance"]) <= 1.0 + 1e-9
    pcs = np.array([[p["pca1"], p["pca2"]] for p in data["points"]])
    assert np.allclose(pcs.mean(axis=0), 0.0, atol=1e-6)  # projections of centred embeddings
    assert {p["data_source"] for p in data["points"]} == {"disk_cache"}


def test_validation_metrics_404_instead_of_placeholder_numbers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)  # no docs/results/metrics.json here
    resp = client.get("/validation")
    assert resp.status_code == 404
    assert "make eval" in resp.json()["detail"]
