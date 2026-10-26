"""
Unit tests for Conformal Calibration in AquaSphere (SIH 26066).
"""

import numpy as np
import pytest

from aquasphere.train.calibrate import ConformalCalibrator, fit_conformal_calibrator


def test_conformal_calibrator_dataclass_and_serialization() -> None:
    calibrator = ConformalCalibrator(
        scale_factor=1.65,
        nominal_coverage=0.90,
        n_calibration_samples=100,
        empirical_val_coverage=0.895,
    )
    d = calibrator.to_dict()
    assert d["scale_factor"] == pytest.approx(1.65)
    assert d["nominal_coverage"] == pytest.approx(0.90)

    loaded = ConformalCalibrator.from_dict(d)
    assert loaded.scale_factor == calibrator.scale_factor
    assert loaded.nominal_coverage == calibrator.nominal_coverage
    assert loaded.n_calibration_samples == calibrator.n_calibration_samples
    assert loaded.empirical_val_coverage == calibrator.empirical_val_coverage


def test_conformal_calibrator_predict_interval() -> None:
    calibrator = ConformalCalibrator(
        scale_factor=2.0,
        nominal_coverage=0.90,
        n_calibration_samples=50,
        empirical_val_coverage=0.91,
    )
    y_pred = np.array([[20.0, 15.0], [25.0, 10.0]])
    sigma = np.array([[1.0, 0.5], [2.0, 1.5]])

    lower, upper = calibrator.predict_interval(y_pred, sigma)
    assert lower.shape == (2, 2)
    assert upper.shape == (2, 2)
    assert np.all(lower < upper)
    np.testing.assert_allclose(lower, y_pred - 2.0 * sigma)
    np.testing.assert_allclose(upper, y_pred + 2.0 * sigma)


def test_fit_conformal_calibrator_synthetic_coverage() -> None:
    np.random.seed(42)
    n_samples = 200
    n_depths = 15

    y_true = np.random.normal(loc=20.0, scale=3.0, size=(n_samples, n_depths)).astype(np.float32)
    noise = np.random.normal(loc=0.0, scale=0.5, size=(n_samples, n_depths)).astype(np.float32)
    y_pred = y_true + noise
    sigma = np.full((n_samples, n_depths), 0.5, dtype=np.float32)
    mask = np.ones((n_samples, n_depths), dtype=np.float32)

    calibrator = fit_conformal_calibrator(y_true, y_pred, sigma, mask=mask, alpha=0.10)
    assert calibrator.scale_factor > 0.0
    assert calibrator.n_calibration_samples == n_samples
    # Empirical coverage on validation should be around nominal 90% (80% - 98%)
    assert 0.80 <= calibrator.empirical_val_coverage <= 1.0


def test_fit_conformal_calibrator_shape_mismatch() -> None:
    y_true = np.ones((10, 5))
    y_pred = np.ones((10, 6))
    sigma = np.ones((10, 5))

    with pytest.raises(ValueError, match="Shape mismatch"):
        fit_conformal_calibrator(y_true, y_pred, sigma)


def test_fit_conformal_calibrator_empty_scores() -> None:
    # All masked out
    y_true = np.ones((10, 5))
    y_pred = np.ones((10, 5))
    sigma = np.ones((10, 5))
    mask = np.zeros((10, 5))

    calibrator = fit_conformal_calibrator(y_true, y_pred, sigma, mask=mask)
    assert calibrator.scale_factor == pytest.approx(1.645)
    assert calibrator.n_calibration_samples == 0
