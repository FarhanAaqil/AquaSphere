"""Serving a protocol v2 checkpoint: modes, Mondrian intervals, dissimilarity, explain."""

from __future__ import annotations

import numpy as np
import pytest
import torch
from fastapi.testclient import TestClient

from aquasphere.eval.applicability import DissimilarityIndex
from aquasphere.eval.baselines_v2 import targets
from aquasphere.serve.app import app
from aquasphere.serve.engine import InferenceEngine
from aquasphere.train import conformal_v2 as cv
from aquasphere.train.v2 import FEATURES, Config, ProfileModel
from tests.unit.test_baselines_v2 import _table

FEATS = {"sst": 28.7, "sss": 34.9, "sla": 0.08, "ug": 0.1, "vg": -0.05, "u10": 4.0, "v10": 1.0}


@pytest.fixture(scope="module")
def engine(tmp_path_factory: pytest.TempPathFactory) -> InferenceEngine:
    tmp = tmp_path_factory.mktemp("v2")
    train, val = _table(800, 0), _table(300, 1)
    for df in (train, val):
        df["float_id"] = df["profile_id"].str.split("_").str[0]
    model = ProfileModel(Config(epochs=4)).fit(train, seed=0)
    y, mask = targets(val)
    reg, sea = cv.strata(val)
    calib = {}
    for mode in ("delayed", "nowcast"):
        mean, sigma, _ = model.predict(val, mode=mode)
        sc = np.where(mask, np.abs(y - mean) / sigma, np.nan)
        calib[mode] = cv.MondrianConformal().fit(sc, mask, reg, sea).to_dict()
    _, _, emb = model.predict(train)
    di = DissimilarityIndex().fit(emb, train["float_id"].to_numpy())
    path = tmp / "model.pt"
    torch.save(
        {
            "format": "aquasphere-v2",
            "model_version": "tier_a_v2.test",
            **model.state(),
            "conformal": calib,
            "dissimilarity": di.to_dict(),
            "provenance": {},
        },
        path,
    )
    return InferenceEngine(checkpoint_path=tmp / "no_v1.pt", v2_checkpoint_path=path)


def test_v2_checkpoint_is_served(engine: InferenceEngine) -> None:
    assert engine.v2 is not None
    assert engine.model_version == "tier_a_v2.test"
    assert engine.weights == "trained"
    assert engine.interval_method == "mondrian_conformal_region_season"


def test_point_prediction_carries_v2_fields(engine: InferenceEngine) -> None:
    p = engine.predict_point(15.0, 65.0, "2023-07-10", FEATS, source="local_store")
    assert p["mode"] == "delayed" and p["model_version"] == "tier_a_v2.test"
    assert len(p["temperatures"]) == 15 and p["ohc300"] is not None
    lo, hi, t = (np.array(p[k]) for k in ("interval_lower", "temperatures", "interval_upper"))
    assert np.all(lo < hi) and np.all((lo <= t) | np.isclose(lo, t))
    assert p["di"] is not None and p["di"] >= 0 and isinstance(p["in_domain"], bool)


def test_nowcast_withholds_delayed_sensors(engine: InferenceEngine) -> None:
    other = {**FEATS, "sss": 30.0, "u10": -9.0, "ug": 0.9}
    a = engine.predict_point(15.0, 65.0, "2023-07-10", FEATS, mode="nowcast")
    b = engine.predict_point(15.0, 65.0, "2023-07-10", other, mode="nowcast")
    assert a["temperatures"] == b["temperatures"] and a["mode"] == "nowcast"
    c = engine.predict_point(15.0, 65.0, "2023-07-10", other, mode="delayed")
    assert c["temperatures"] != b["temperatures"]
    with pytest.raises(ValueError):
        engine.predict_point(15.0, 65.0, "2023-07-10", FEATS, mode="forecast")


def test_a_training_profile_is_inside_the_applicability_domain(engine: InferenceEngine) -> None:
    row = _table(800, 0).iloc[3]  # a profile the model was trained on
    feats = {c: float(row[c]) for c in FEATS if np.isfinite(row[c])}
    p = engine.predict_point(float(row.lat), float(row.lon), str(row.date), feats)
    assert p["di"] < 1e-3 and p["in_domain"] is True  # its embedding is in the reference set


def test_batch_matches_points_and_explain_uses_v2_features(engine: InferenceEngine) -> None:
    pts = [
        {"lat": 12.0, "lon": 88.0, "date": "2023-01-05"},
        {"lat": 20.0, "lon": 62.0, "date": "2023-08-01"},
    ]
    batch = engine.predict_batch(pts, [FEATS, FEATS], ["local_store"] * 2)
    one = engine.predict_point(20.0, 62.0, "2023-08-01", FEATS)
    assert np.allclose(batch[1]["temperatures"], one["temperatures"], atol=1e-5)
    attr = engine.explain_point(15.0, 65.0, "2023-07-10", FEATS)
    assert set(attr) == set(FEATURES) and abs(sum(attr.values()) - 1.0) < 1e-3


def test_api_accepts_mode_and_rejects_unknown_modes() -> None:
    client = TestClient(app)
    body = {
        "lat": 15.0,
        "lon": 65.0,
        "date": "2025-06-15",
        "features": {"sst": 29.0},
        "mode": "nowcast",
    }
    r = client.post("/predict", json=body)
    assert r.status_code == 200 and r.json()["mode"] == "nowcast"
    assert r.json()["interval_method"] == "conformal_per_depth"  # v1 in the test app
    assert client.post("/predict", json={**body, "mode": "forecast"}).status_code == 422
    b = client.post(
        "/predict_batch",
        json={"items": [{**body, "mode": "delayed"}, body]},
    )
    assert b.status_code == 200
    assert [p["mode"] for p in b.json()["predictions"]] == ["delayed", "nowcast"]


def test_held_out_lookup_never_returns_training_floats(engine: InferenceEngine) -> None:
    table = _table(50, 3)
    engine.val_df = table.assign(float_id=table["profile_id"].str.split("_").str[0])
    # Those float ids were all in the synthetic training set: nothing is held out
    assert engine.find_nearest_held_out_profile(15.0, 65.0) is None
    engine.val_df = table.assign(float_id="held_" + table["profile_id"].str.split("_").str[0])
    res = engine.find_nearest_held_out_profile(15.0, 65.0)
    assert res is not None and res["in_training_set"] is False
    assert len(res["pred_temperatures"]) == 15 and res["rmse"] is not None
