from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from aquasphere.eval.baselines import (
    ClimatologyBaseline,
    GradientBoostedBaseline,
    RidgeAnomalyBaseline,
    V1OceanEmbedNetBaseline,
    prepare_features,
)


@pytest.fixture
def mock_train_test_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate simple training and test DataFrames."""
    rng = np.random.default_rng(42)
    n_train = 60
    n_test = 20

    def _make_df(n: int, start_doy: int) -> pd.DataFrame:
        records = []
        for i in range(n):
            lat = 10.0 + rng.uniform(0, 10)
            lon = 60.0 + rng.uniform(0, 20)
            doy = (start_doy + i * 2) % 365 + 1
            sst = 28.0 + rng.normal(0, 1.0)
            row = {
                "profile_id": f"flt_{i:03d}_001",
                "float_id": f"flt_{i:03d}",
                "lat": lat,
                "lon": lon,
                "day_of_year": doy,
                "date": f"2023-01-{(i % 28) + 1:02d}",
                "sst": sst,
            }
            # Vertical temperatures
            for d in [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000]:
                row[f"t_{d}"] = max(5.0, sst - (d**0.4) * 1.5 + rng.normal(0, 0.2))
            records.append(row)
        return pd.DataFrame(records)

    return _make_df(n_train, 10), _make_df(n_test, 200)


def test_prepare_features(mock_train_test_data):
    df_train, _ = mock_train_test_data
    x = prepare_features(df_train)
    assert x.shape == (len(df_train), 5)
    # Check sin and cos DOY values are in [-1, 1]
    assert np.all(x[:, 2] >= -1.0) and np.all(x[:, 2] <= 1.0)
    assert np.all(x[:, 3] >= -1.0) and np.all(x[:, 3] <= 1.0)


def test_climatology_baseline(mock_train_test_data):
    df_train, df_test = mock_train_test_data
    clim = ClimatologyBaseline()
    clim.fit(df_train)
    preds = clim.predict(df_test)

    assert preds.shape == (len(df_test), 15)
    assert not np.any(np.isnan(preds))
    # Surface temperature should be around 20-30 deg C
    assert np.all(preds[:, 0] > 20.0)
    # Deep temperature should be colder
    assert np.all(preds[:, -1] < preds[:, 0])


def test_ridge_anomaly_baseline(mock_train_test_data):
    df_train, df_test = mock_train_test_data
    ridge_base = RidgeAnomalyBaseline(alpha=1.0)
    ridge_base.fit(df_train)
    preds = ridge_base.predict(df_test)

    assert preds.shape == (len(df_test), 15)
    assert not np.any(np.isnan(preds))


def test_gradient_boosted_baseline(mock_train_test_data):
    df_train, df_test = mock_train_test_data
    gbdt = GradientBoostedBaseline(max_iter=10, max_depth=3, random_state=42)
    gbdt.fit(df_train)
    preds = gbdt.predict(df_test)

    assert preds.shape == (len(df_test), 15)
    assert not np.any(np.isnan(preds))


def test_v1_oceanembed_baseline_runs(mock_train_test_data):
    _, df_test = mock_train_test_data
    model_path = Path("model/model.pt")
    scaler_path = Path("model/scaler.json")

    if model_path.exists() and scaler_path.exists():
        v1 = V1OceanEmbedNetBaseline(model_path=model_path, scaler_path=scaler_path)
        assert v1.loaded
        preds = v1.predict(df_test)
        assert preds.shape == (len(df_test), 15)
        assert not np.any(np.isnan(preds))
        # Surface should be warmer than 1000m depth
        assert np.mean(preds[:, 0]) > np.mean(preds[:, -1])
