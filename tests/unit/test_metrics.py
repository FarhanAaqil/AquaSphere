"""
Unit tests for oceanographic and statistical metrics (SIH 26066).
"""

import numpy as np
import pandas as pd
import pytest

from aquasphere.constants import STANDARD_DEPTHS
from aquasphere.eval.metrics import (
    block_bootstrap_ci,
    compute_anomaly_correlation,
    compute_coverage,
    compute_d20,
    compute_depth_group_metrics,
    compute_errors,
    compute_mld,
    compute_oceanographic_metrics,
    compute_ohc300,
    compute_skill_score,
)


@pytest.fixture
def synthetic_profiles() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Generate realistic synthetic temperature profiles for testing.

    Returns:
        (y_true, y_pred, y_clim) of shape [50, 15]
    """
    rng = np.random.default_rng(42)
    n = 50
    # Standard profile: warm at surface (29 C), thermocline at 50-150m, cold deep (7 C)
    base_t = np.array(
        [29.0, 28.9, 28.8, 28.5, 28.0, 25.0, 22.0, 19.0, 16.5, 14.0, 12.0, 10.0, 8.5, 7.5, 7.0]
    )
    y_true = np.tile(base_t, (n, 1)) + rng.normal(0, 0.2, size=(n, 15))
    y_clim = np.tile(base_t, (n, 1))
    y_pred = y_true + rng.normal(0, 0.1, size=(n, 15))  # good model: closer than clim
    return y_true, y_pred, y_clim


def test_compute_errors_perfect_and_offset():
    y_true = np.ones((10, 15)) * 20.0
    y_pred_perf = y_true.copy()
    err_perf = compute_errors(y_true, y_pred_perf)

    assert err_perf["overall"]["rmse"] == 0.0
    assert err_perf["overall"]["mae"] == 0.0
    assert err_perf["overall"]["bias"] == 0.0

    y_pred_off = y_true + 1.5
    err_off = compute_errors(y_true, y_pred_off)
    assert np.isclose(err_off["overall"]["rmse"], 1.5)
    assert np.isclose(err_off["overall"]["bias"], 1.5)


def test_compute_errors_mismatch_raises():
    with pytest.raises(ValueError, match="Shape mismatch"):
        compute_errors(np.zeros((5, 15)), np.zeros((5, 10)))


def test_compute_skill_score(synthetic_profiles):
    y_true, y_pred, y_clim = synthetic_profiles

    # Model is better than climatology -> positive skill score
    res = compute_skill_score(y_true, y_pred, y_clim)
    assert res["overall_skill_score"] > 0.0

    # Model identical to climatology -> skill score = 0.0
    res_clim = compute_skill_score(y_true, y_clim, y_clim)
    assert np.isclose(res_clim["overall_skill_score"], 0.0, atol=1e-3)

    # Model identical to true -> skill score = 1.0
    res_perf = compute_skill_score(y_true, y_true, y_clim)
    assert np.isclose(res_perf["overall_skill_score"], 1.0, atol=1e-3)


def test_compute_anomaly_correlation(synthetic_profiles):
    y_true, y_pred, y_clim = synthetic_profiles
    corr_list = compute_anomaly_correlation(y_true, y_pred, y_clim)
    assert len(corr_list) == 15
    for item in corr_list:
        assert -1.0 <= item["anomaly_corr"] <= 1.0


def test_compute_mld_and_d20():
    # Construct a known profile with clear thermocline
    # 0m: 29C, 5m: 29C, 10m: 29C, 20m: 28.9C, 30m: 28.7C (drop of 0.3C from 10m)
    # Target T = 29.0 - 0.2 = 28.8C, which lies between 20m (28.9C) and 30m (28.7C)
    # Expected crossing at 25m.
    profile = np.array(
        [29.0, 29.0, 29.0, 28.9, 28.7, 25.0, 22.0, 19.0, 16.0, 14.0, 12.0, 10.0, 8.0, 7.0, 6.0]
    )

    mld = compute_mld(profile, depths=STANDARD_DEPTHS)
    assert np.isclose(mld, 25.0, atol=0.1)

    # D20: 20 deg C isotherm lies between 75m (22.0C) and 100m (19.0C)
    # Fraction: (20 - 22) / (19 - 22) = 2/3 -> 75 + 2/3 * 25 = 91.67m
    d20 = compute_d20(profile, depths=STANDARD_DEPTHS)
    assert np.isclose(d20, 91.67, atol=0.1)


def test_compute_ohc300():
    # Constant temperature column 20.0 deg C -> integrated index must be exactly 20.0
    profile = np.ones(15) * 20.0
    ohc = compute_ohc300(profile, depths=STANDARD_DEPTHS, max_depth=300.0)
    assert np.isclose(ohc, 20.0)


def test_compute_oceanographic_metrics(synthetic_profiles):
    y_true, y_pred, _ = synthetic_profiles
    oc = compute_oceanographic_metrics(y_true, y_pred)
    assert "mld" in oc and "rmse" in oc["mld"]
    assert "d20" in oc and "rmse" in oc["d20"]
    assert "ohc300" in oc and "rmse" in oc["ohc300"]


def test_compute_coverage():
    y_true = np.ones((100, 15)) * 25.0
    y_pred = y_true.copy()
    y_sigma = np.ones((100, 15)) * 1.0  # std = 1.0

    cov = compute_coverage(y_true, y_pred, y_sigma, nominal_coverage=0.90)
    assert cov["empirical_coverage"] == 1.0
    assert np.isclose(cov["sharpness"], 2 * 1.644853, atol=1e-2)


def test_compute_depth_group_metrics(synthetic_profiles):
    y_true, y_pred, _ = synthetic_profiles
    grouped = compute_depth_group_metrics(y_true, y_pred)
    assert len(grouped) == 4
    labels = [g["depth_group"] for g in grouped]
    assert "50\u2013150 m" in labels


def test_block_bootstrap_ci():
    rng = np.random.default_rng(42)
    floats = ["f1", "f2", "f3", "f4", "f5"]
    records = []
    for flt in floats:
        for _ in range(10):
            row = {"float_id": flt}
            for d in STANDARD_DEPTHS:
                row[f"t_{d}"] = 20.0 + rng.normal(0, 0.5)
            records.append(row)
    df = pd.DataFrame(records)
    cols = [f"t_{d}" for d in STANDARD_DEPTHS]
    y_pred = df[cols].to_numpy() + 0.5

    ci_res = block_bootstrap_ci(
        df,
        y_true_cols=cols,
        y_pred=y_pred,
        group_col="float_id",
        depth_slice=[50, 75, 100, 125, 150],
        n_boot=100,
        ci=0.95,
    )

    assert "ci_lower" in ci_res
    assert "ci_upper" in ci_res
    assert ci_res["ci_lower"] <= ci_res["mean"] <= ci_res["ci_upper"]
