"""Baseline ladder v2 on a small synthetic table where the right answer is known."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from aquasphere.constants import STANDARD_DEPTHS
from aquasphere.eval import baselines_v2 as b

N_D = len(STANDARD_DEPTHS)


def _table(n: int, seed: int) -> pd.DataFrame:
    """Profiles whose subsurface anomaly is driven by SST anomaly and SLA (plus noise)."""
    rng = np.random.default_rng(seed)
    lat = rng.uniform(6, 28, n)
    lon = rng.uniform(46, 104, n)
    date = pd.to_datetime("2016-01-01") + pd.to_timedelta(rng.integers(0, 365 * 6, n), unit="D")
    month = date.month.to_numpy()
    base = (
        28
        - 0.02 * np.array(STANDARD_DEPTHS)[None, :]
        + 0.5 * np.sin(month / 12 * 2 * np.pi)[:, None]
    )
    sst_anom = rng.normal(0, 0.6, n)
    sla = rng.normal(0, 0.1, n)
    depth_gain = np.exp(-np.array(STANDARD_DEPTHS) / 150)[None, :]
    t = (
        base
        + (1.5 * sst_anom[:, None] + 8 * sla[:, None]) * depth_gain
        + rng.normal(0, 0.1, (n, N_D))
    )
    df = pd.DataFrame(
        {
            "profile_id": [f"{i // 5}_{i}" for i in range(n)],
            "lat": lat,
            "lon": lon,
            "date": date.strftime("%Y-%m-%d"),
        }
    )
    df["sst"] = 28 + 0.5 * np.sin(month / 12 * 2 * np.pi) + sst_anom
    df["sla"] = np.where(rng.random(n) < 0.8, sla, np.nan)  # altimetry sometimes missing
    for c in ("sss", "ug", "vg", "u10", "v10"):
        df[c] = rng.normal(size=n)
    for k, d in enumerate(STANDARD_DEPTHS):
        observed = rng.random(n) < (0.95 if d <= 700 else 0.6)
        df[f"t_{d}"] = np.where(observed, t[:, k], np.nan)
        df[f"m_{d}"] = observed.astype(int)
    return df


@pytest.fixture(scope="module")
def data() -> tuple[pd.DataFrame, pd.DataFrame]:
    return _table(1500, 0), _table(300, 1)


def _thermo_rmse(model: object, val: pd.DataFrame) -> float:
    y, mask = b.targets(val)
    pred = model.predict(val)  # type: ignore[attr-defined]
    idx = [STANDARD_DEPTHS.index(d) for d in (50, 75, 100, 125, 150)]
    e = (pred - y)[:, idx][mask[:, idx]]
    return float(np.sqrt(np.mean(e**2)))


def test_climatology_falls_back_when_cells_are_sparse() -> None:
    df = _table(40, 2)
    y, _ = b.targets(df)
    clim = b.Climatology().fit(df, y)
    far = df.iloc[:1].assign(lat=29.9, lon=104.9)  # a cell with no training data
    assert np.isfinite(clim.predict(far)).all()


def test_anomaly_models_beat_climatology(data: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    train, val = data
    b0 = _thermo_rmse(b.B0Climatology().fit(train), val)
    assert _thermo_rmse(b.B1Ridge().fit(train), val) < 0.8 * b0
    assert _thermo_rmse(b.B2LightGBM().fit(train), val) < 0.8 * b0


def test_networks_train_and_ensemble_gives_positive_spread(
    data: tuple[pd.DataFrame, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(b.B3V1Net, "EPOCHS", 5)
    monkeypatch.setattr(b.B4DeepEnsemble, "EPOCHS", 6)
    monkeypatch.setattr(b.B4DeepEnsemble, "WARMUP", 2)
    monkeypatch.setattr(b.B4DeepEnsemble, "MEMBERS", 2)
    train, val = data
    assert np.isfinite(_thermo_rmse(b.B3V1Net().fit(train), val))
    ens = b.B4DeepEnsemble().fit(train)
    mu, sigma = ens.predict_dist(val)
    assert mu.shape == sigma.shape == (len(val), N_D)
    assert (sigma > 0).all()


def test_fits_are_reproducible_for_a_seed(data: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    train, val = data
    a = b.B2LightGBM().fit(train, seed=3).predict(val)
    c = b.B2LightGBM().fit(train, seed=3).predict(val)
    np.testing.assert_allclose(a, c)
