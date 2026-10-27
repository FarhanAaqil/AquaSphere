"""
Conformal calibration for uncertainty-aware subsurface ocean temperature predictions (SIH 26066).

Provides distribution-free, finite-sample calibrated prediction intervals
so that nominal 90% confidence bands achieve target 85-95% empirical coverage.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ConformalCalibrator:
    """Stores conformal scale factors for calibrated prediction intervals."""

    scale_factor: float
    nominal_coverage: float
    n_calibration_samples: int
    empirical_val_coverage: float
    scale_factors: np.ndarray | None = None

    def predict_interval(
        self,
        y_pred: np.ndarray,
        sigma: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Compute calibrated lower and upper prediction bounds.

        Args:
            y_pred: Predicted temperature profile [N, D] (°C)
            sigma: Predicted standard deviations [N, D] (°C)

        Returns:
            lower, upper prediction bounds of shape [N, D] (°C)
        """
        if self.scale_factors is not None and self.scale_factors.shape == (sigma.shape[-1],):
            half_width = self.scale_factors * sigma
        else:
            half_width = self.scale_factor * sigma
        lower = y_pred - half_width
        upper = y_pred + half_width
        return lower, upper

    def to_dict(self) -> dict[str, Any]:
        """Serialize calibrator parameters to dictionary."""
        return {
            "scale_factor": float(self.scale_factor),
            "scale_factors": self.scale_factors.tolist()
            if self.scale_factors is not None
            else None,
            "nominal_coverage": float(self.nominal_coverage),
            "n_calibration_samples": int(self.n_calibration_samples),
            "empirical_val_coverage": float(self.empirical_val_coverage),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConformalCalibrator:
        """Load calibrator from dictionary."""
        scale_factors = (
            np.array(data["scale_factors"], dtype=np.float64)
            if data.get("scale_factors") is not None
            else None
        )
        return cls(
            scale_factor=float(data["scale_factor"]),
            nominal_coverage=float(data.get("nominal_coverage", 0.90)),
            n_calibration_samples=int(data.get("n_calibration_samples", 0)),
            empirical_val_coverage=float(data.get("empirical_val_coverage", 0.90)),
            scale_factors=scale_factors,
        )


def fit_conformal_calibrator(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    sigma: np.ndarray,
    mask: np.ndarray | None = None,
    alpha: float = 0.10,
) -> ConformalCalibrator:
    r"""Fit a split-conformal calibrator using validation non-conformity scores.

    Non-conformity score for profile i:
        R_i = max_{k: m_k=1} |T_{i, k} - \hat{T}_{i, k}| / \sigma_{i, k}

    The scale factor is the (1 - alpha) conformal quantile of R:
        q = ceil((n + 1) * (1 - alpha)) / n

    Args:
        y_true: Ground truth observed temperatures [N, D] (°C)
        y_pred: Model predicted temperatures [N, D] (°C)
        sigma: Predicted standard deviations [N, D] (°C)
        mask: Observation availability mask [N, D] (1 for observed, 0 for missing)
        alpha: Target error rate (alpha=0.10 corresponds to 90% nominal coverage)

    Returns:
        ConformalCalibrator instance with computed scale factor.
    """
    if y_true.shape != y_pred.shape or y_true.shape != sigma.shape:
        raise ValueError(
            f"Shape mismatch: y_true {y_true.shape}, y_pred {y_pred.shape}, sigma {sigma.shape}"
        )

    _n_samples, n_depths = y_true.shape
    if mask is None:
        mask = (~np.isnan(y_true)).astype(np.float32)

    # Avoid zero division
    safe_sigma = np.clip(sigma, 1e-4, 50.0)
    residuals = np.abs(y_true - y_pred)
    normalized_errors = residuals / safe_sigma

    # Compute depth-stratified non-conformity quantiles (per-depth conformal calibration)
    scale_factors = np.zeros(n_depths, dtype=np.float64)
    for k in range(n_depths):
        valid_k = (mask[:, k] > 0) & np.isfinite(normalized_errors[:, k])
        scores_k = normalized_errors[valid_k, k]
        if len(scores_k) > 5:
            q_level = min(1.0, np.ceil((len(scores_k) + 1) * (1.0 - alpha)) / len(scores_k))
            scale_factors[k] = float(np.quantile(scores_k, q_level))
        else:
            scale_factors[k] = 1.645

    mean_scale_factor = float(np.mean(scale_factors))

    # Measure empirical coverage on calibration set
    lower = y_pred - scale_factors * safe_sigma
    upper = y_pred + scale_factors * safe_sigma

    valid_mask = mask > 0
    total_valid_obs = int(np.sum(valid_mask))
    valid_samples = int(np.sum(np.any(valid_mask, axis=1)))

    if total_valid_obs == 0:
        logger.warning("No valid observations to fit conformal calibrator. Defaulting to 1.645.")
        return ConformalCalibrator(
            scale_factor=1.645,
            nominal_coverage=1.0 - alpha,
            n_calibration_samples=0,
            empirical_val_coverage=round(1.0 - alpha, 4),
            scale_factors=np.full(n_depths, 1.645),
        )

    inside = (y_true >= lower) & (y_true <= upper)
    emp_covered = int(np.sum(inside[valid_mask]))
    empirical_coverage = float(emp_covered / total_valid_obs)

    logger.info(
        "Fitted Per-Depth Conformal Calibrator: mean_scale=%.3f, empirical_coverage=%.2f%% (nominal %.1f%%)",
        mean_scale_factor,
        empirical_coverage * 100.0,
        (1.0 - alpha) * 100.0,
    )

    return ConformalCalibrator(
        scale_factor=mean_scale_factor,
        nominal_coverage=1.0 - alpha,
        n_calibration_samples=valid_samples,
        empirical_val_coverage=round(empirical_coverage, 4),
        scale_factors=scale_factors,
    )
