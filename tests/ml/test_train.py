"""
Unit and behavioural tests for AquaSphere Tier A training pipeline (SIH 26066).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from aquasphere.train.train import (
    build_monthly_climatology,
    compute_doy_features,
    main,
    prepare_features_and_targets,
    train_tier_a,
)

FIXTURE_PATH = Path("tests/fixtures/argo_200.parquet")


def test_compute_doy_features() -> None:
    dates = pd.Series(["2023-01-01", "2023-07-02", "2023-12-31"])
    sin_doy, cos_doy = compute_doy_features(dates)

    assert len(sin_doy) == 3
    assert len(cos_doy) == 3
    assert np.all(sin_doy >= -1.0) and np.all(sin_doy <= 1.0)
    assert np.all(cos_doy >= -1.0) and np.all(cos_doy <= 1.0)


def test_build_monthly_climatology_and_prepare_features() -> None:
    df = pd.read_parquet(FIXTURE_PATH)
    clim = build_monthly_climatology(df)

    assert clim.shape == (12, 15)
    assert not np.isnan(clim).any()

    x, y, m, y_clim = prepare_features_and_targets(df, clim_matrix=clim, predict_anomaly=True)
    assert x.shape == (len(df), 18)
    assert y.shape == (len(df), 15)
    assert m.shape == (len(df), 15)
    assert y_clim.shape == (len(df), 15)
    assert not np.isnan(x).any()


def test_train_tier_a_smoke_fixture() -> None:
    res = train_tier_a(
        config_path="configs/model_a.yaml",
        epochs_override=2,
        fixture_path=FIXTURE_PATH,
        no_save=True,
        seed_override=42,
        batch_size_override=64,
        device="cpu",
    )
    assert "best_val_rmse" in res
    assert "best_thermo_rmse" in res
    assert "calibrator" in res
    assert res["n_train"] > 0
    assert res["n_val"] > 0
    assert len(res["history"]) == 2
    assert res["best_val_rmse"] > 0.0


def test_train_tier_a_batch_overfit() -> None:
    # Overfit a tiny 16-sample batch to demonstrate learning capacity
    df = pd.read_parquet(FIXTURE_PATH).iloc[:16].copy()
    temp_p = Path("tests/fixtures/_tmp_overfit.parquet")
    df.to_parquet(temp_p)

    try:
        res = train_tier_a(
            config_path="configs/model_a.yaml",
            epochs_override=10,
            fixture_path=temp_p,
            no_save=True,
            seed_override=1337,
            batch_size_override=16,
            device="cpu",
        )
        # Training loss should decrease from epoch 1 to epoch 10
        initial_loss = res["history"][0]["train_loss"]
        final_loss = res["history"][-1]["train_loss"]
        assert final_loss < initial_loss
    finally:
        if temp_p.exists():
            temp_p.unlink()


def test_train_main_cli_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    test_args = [
        "aquasphere-train",
        "--config",
        "configs/model_a.yaml",
        "--fixture",
        str(FIXTURE_PATH),
        "--epochs",
        "1",
        "--no-save",
        "--batch-size",
        "64",
    ]
    monkeypatch.setattr(sys, "argv", test_args)
    # Ensure calling main executes cleanly without error
    main()
