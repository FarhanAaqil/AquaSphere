"""Property-based tests (hypothesis) for metrics, calibration and training membership."""

from __future__ import annotations

import numpy as np
import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.extra.numpy import arrays

from aquasphere.constants import STANDARD_DEPTHS
from aquasphere.eval.metrics import compute_d20, compute_skill_score
from aquasphere.serve.membership import POINT_TOLERANCE_DEG, TrainingMembership
from aquasphere.train.calibrate import ConformalCalibrator

N_DEPTHS = len(STANDARD_DEPTHS)
temps = st.floats(min_value=2.0, max_value=32.0, allow_nan=False)


@st.composite
def stratified_profiles(draw: st.DrawFn) -> np.ndarray:
    """Monotonically cooling profiles, warmer than 20 °C at the surface, colder at 1000 m."""
    surface = draw(st.floats(min_value=21.0, max_value=32.0))
    bottom = draw(st.floats(min_value=4.0, max_value=19.0))
    steps = np.array(
        draw(st.lists(st.floats(0.01, 1.0), min_size=N_DEPTHS - 1, max_size=N_DEPTHS - 1))
    )
    drops = np.concatenate([[0.0], np.cumsum(steps) / steps.sum()])
    return surface - (surface - bottom) * drops


@given(stratified_profiles())
def test_d20_lies_between_the_bracketing_depths(profile: np.ndarray) -> None:
    d20 = compute_d20(profile)
    assert np.isfinite(d20)
    i = int(np.argmax(profile < 20.0))  # first depth colder than 20 °C
    assert STANDARD_DEPTHS[i - 1] <= d20 <= STANDARD_DEPTHS[i]


@given(
    arrays(np.float64, (8, N_DEPTHS), elements=temps),
    arrays(np.float64, (8, N_DEPTHS), elements=temps),
)
@settings(max_examples=60)
def test_skill_is_one_for_perfect_and_zero_for_climatology(
    truth: np.ndarray, clim: np.ndarray
) -> None:
    if np.mean((truth - clim) ** 2) <= 1e-6:
        return  # climatology (near) perfect: the metric defines skill as 0 there
    perfect = compute_skill_score(truth, truth, clim)
    as_clim = compute_skill_score(truth, clim, clim)
    assert np.isclose(perfect["overall_skill_score"], 1.0)
    assert np.isclose(as_clim["overall_skill_score"], 0.0, atol=1e-3)  # rounded to 4 dp


@given(
    arrays(np.float64, (5, N_DEPTHS), elements=temps),
    arrays(np.float64, (5, N_DEPTHS), elements=st.floats(0.0, 5.0)),
    st.floats(min_value=0.5, max_value=3.0),
)
def test_conformal_interval_brackets_the_mean_and_scales_with_sigma(
    mean: np.ndarray, sigma: np.ndarray, q: float
) -> None:
    cal = ConformalCalibrator(
        scale_factor=q, nominal_coverage=0.9, n_calibration_samples=10, empirical_val_coverage=0.9
    )
    lower, upper = cal.predict_interval(mean, sigma)
    assert np.all(lower <= mean) and np.all(mean <= upper)
    np.testing.assert_allclose(upper - lower, 2 * q * sigma, rtol=1e-9, atol=1e-12)


@given(
    st.floats(6.0, 29.0),
    st.floats(46.0, 104.0),
    st.floats(-1.0, 1.0),
    st.floats(-1.0, 1.0),
)
def test_point_membership_matches_the_cell_tolerance(
    lat: float, lon: float, dlat: float, dlon: float
) -> None:
    pts = pd.DataFrame({"lat": [lat], "lon": [lon], "date": ["2025-05-15"]})
    m = TrainingMembership({"1"}, pts, "test")
    inside = abs(dlat) <= POINT_TOLERANCE_DEG and abs(dlon) <= POINT_TOLERANCE_DEG
    assert m.point_in_training(lat + dlat, lon + dlon, "2025-05-15") is inside
    assert m.point_in_training(lat, lon, "2025-05-16") is False
