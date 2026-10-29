"""Protocol v2 metrics: CRPS, reliability, bands, float bootstrap, Holm, power."""

from __future__ import annotations

import numpy as np
import pytest
from scipy.integrate import quad
from scipy.stats import norm

from aquasphere.eval import metrics_v2 as m

N_D = len(m.DEPTHS)


def test_crps_gaussian_matches_its_integral_definition() -> None:
    mu, sigma, y = 20.0, 1.5, 21.2
    integral, _ = quad(
        lambda x: (norm.cdf(x, mu, sigma) - (x >= y)) ** 2, mu - 15, mu + 15, points=[y]
    )
    assert m.crps_gaussian(np.array(y), np.array(mu), np.array(sigma)) == pytest.approx(
        integral, abs=1e-6
    )


def test_crps_shrinks_to_absolute_error_for_tiny_sigma() -> None:
    assert m.crps_gaussian(np.array(3.0), np.array(1.0), np.array(1e-12)) == pytest.approx(
        2.0, abs=1e-6
    )


def test_reliability_is_nominal_for_well_specified_gaussians() -> None:
    rng = np.random.default_rng(0)
    mu = rng.normal(size=(20000, N_D))
    sigma = np.full_like(mu, 0.7)
    y = mu + sigma * rng.normal(size=mu.shape)
    rel = m.reliability(y, mu, sigma, np.ones_like(mu, bool))
    np.testing.assert_allclose(rel["empirical"], rel["nominal"], atol=0.01)


def test_bands_cover_all_depths_once_and_headline_excludes_shallow() -> None:
    flat = [d for ds in m.DEPTH_BANDS.values() for d in ds]
    assert sorted(flat) == sorted(m.DEPTHS.tolist())
    assert min(m.HEADLINE) == 20


def test_rmse_and_skill_respect_the_mask() -> None:
    err = np.ones((4, N_D))
    err[0, :] = 100.0  # an unobserved profile must not count
    mask = np.ones((4, N_D), bool)
    mask[0] = False
    assert m.rmse(err, mask) == pytest.approx(1.0)
    assert m.skill(err * 0.5, err, mask) == pytest.approx(0.75)


def _two_models(n_floats: int, per_float: int, gap: float, seed: int = 1) -> tuple[np.ndarray, ...]:
    rng = np.random.default_rng(seed)
    groups = np.repeat(np.arange(n_floats), per_float)
    float_effect = rng.normal(0, 0.5, n_floats)[groups][:, None]  # correlated errors within a float
    noise = rng.normal(0, 1, (len(groups), N_D))
    err_b = float_effect + noise
    err_a = err_b * (1 + gap)
    return err_a, err_b, np.ones_like(err_a, bool), groups


def test_paired_difference_detects_a_real_gap_and_not_a_null_one() -> None:
    a, b, mask, g = _two_models(40, 20, gap=0.15)
    res = m.paired_rmse_difference(a, b, mask, g, m.THERMOCLINE, n_boot=1000)
    assert res["diff"] > 0 and res["ci_low"] > 0 and res["p"] < 0.01
    same = m.paired_rmse_difference(b, b, mask, g, m.THERMOCLINE, n_boot=500)
    assert same["diff"] == 0.0 and same["p"] == 1.0


def test_bootstrap_ci_contains_the_point_estimate() -> None:
    _, b, mask, g = _two_models(30, 10, gap=0.0)
    r = m.bootstrap_rmse(b, mask, g, m.THERMOCLINE, n_boot=500)
    assert r["ci_low"] < r["rmse"] < r["ci_high"] and r["se"] > 0


def test_holm_adjustment() -> None:
    adj = m.holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert adj == pytest.approx({"a": 0.03, "c": 0.06, "b": 0.06})
    assert all(0 <= v <= 1 for v in m.holm({"x": 0.9, "y": 0.8}).values())


def test_minimum_detectable_difference() -> None:
    assert m.minimum_detectable_difference(0.1) == pytest.approx(
        0.1 * (1.959964 + 0.841621), rel=1e-5
    )
