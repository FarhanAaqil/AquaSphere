"""
Oceanographic and statistical evaluation metrics for AquaSphere (SIH 26066).

Includes:
- Statistical errors: RMSE, MAE, Bias per depth and overall.
- Climatology skill score (SS = 1 - MSE_model / MSE_clim) and anomaly correlation.
- Derived oceanographic variables:
    * Mixed Layer Depth (MLD) via delta-T = 0.2 deg C threshold from 10 m reference.
    * D20: 20 deg C isotherm depth (thermocline proxy).
    * OHC-300: Depth-integrated upper 300 m thermal index.
- Uncertainty calibration: empirical coverage, sharpness, reliability diagram bins.
- Block bootstrap confidence intervals over floats (not profiles).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
from scipy import integrate, interpolate

from aquasphere.constants import DEPTH_GROUPS, STANDARD_DEPTHS

logger = logging.getLogger(__name__)


def compute_errors(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    mask: np.ndarray | None = None,
) -> dict[str, Any]:
    """Compute RMSE, MAE, and Bias per depth and overall.

    Args:
        y_true: Ground truth temperatures [N, n_depths].
        y_pred: Predicted temperatures [N, n_depths].
        mask: Optional boolean or 0/1 mask [N, n_depths] where 1/True is valid.

    Returns:
        Dictionary with 'overall' and 'per_depth' metrics.
    """
    y_true = np.asarray(y_true, dtype=np.float64)
    y_pred = np.asarray(y_pred, dtype=np.float64)

    if y_true.shape != y_pred.shape:
        raise ValueError(f"Shape mismatch: y_true {y_true.shape} vs y_pred {y_pred.shape}")

    if mask is not None:
        mask = np.asarray(mask, dtype=bool)
        if mask.shape != y_true.shape:
            raise ValueError(f"Mask shape {mask.shape} does not match y_true {y_true.shape}")
    else:
        mask = ~np.isnan(y_true) & ~np.isnan(y_pred)

    n_depths = y_true.shape[1]
    per_depth: list[dict[str, Any]] = []

    for i in range(n_depths):
        m = mask[:, i]
        d = STANDARD_DEPTHS[i] if i < len(STANDARD_DEPTHS) else i
        if not np.any(m):
            per_depth.append(
                {
                    "depth_m": d,
                    "rmse": float("nan"),
                    "mae": float("nan"),
                    "bias": float("nan"),
                    "n_samples": 0,
                }
            )
            continue

        yt = y_true[m, i]
        yp = y_pred[m, i]
        diff = yp - yt

        rmse = float(np.sqrt(np.mean(diff**2)))
        mae = float(np.mean(np.abs(diff)))
        bias = float(np.mean(diff))

        per_depth.append(
            {
                "depth_m": d,
                "rmse": round(rmse, 4),
                "mae": round(mae, 4),
                "bias": round(bias, 4),
                "n_samples": int(np.sum(m)),
            }
        )

    # Overall masked
    all_diff = (y_pred - y_true)[mask]
    if len(all_diff) > 0:
        overall_rmse = float(np.sqrt(np.mean(all_diff**2)))
        overall_mae = float(np.mean(np.abs(all_diff)))
        overall_bias = float(np.mean(all_diff))
    else:
        overall_rmse = overall_mae = overall_bias = float("nan")

    return {
        "overall": {
            "rmse": round(overall_rmse, 4),
            "mae": round(overall_mae, 4),
            "bias": round(overall_bias, 4),
            "n_total": int(np.sum(mask)),
        },
        "per_depth": per_depth,
    }


def compute_skill_score(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_clim: np.ndarray,
    mask: np.ndarray | None = None,
) -> dict[str, Any]:
    """Compute Skill Score: SS = 1 - (MSE_model / MSE_clim).

    SS > 0 means the model is superior to climatology.
    SS = 1 is perfect prediction.
    SS <= 0 indicates no skill beyond baseline climatology.
    """
    y_true = np.asarray(y_true, dtype=np.float64)
    y_pred = np.asarray(y_pred, dtype=np.float64)
    y_clim = np.asarray(y_clim, dtype=np.float64)

    if mask is None:
        mask = ~np.isnan(y_true) & ~np.isnan(y_pred) & ~np.isnan(y_clim)
    else:
        mask = np.asarray(mask, dtype=bool)

    n_depths = y_true.shape[1]
    per_depth_ss: list[dict[str, Any]] = []

    for i in range(n_depths):
        m = mask[:, i]
        d = STANDARD_DEPTHS[i] if i < len(STANDARD_DEPTHS) else i
        if not np.any(m):
            per_depth_ss.append({"depth_m": d, "skill_score": float("nan")})
            continue

        mse_model = float(np.mean((y_pred[m, i] - y_true[m, i]) ** 2))
        mse_clim = float(np.mean((y_clim[m, i] - y_true[m, i]) ** 2))

        ss = 1.0 - (mse_model / (mse_clim + 1e-12)) if mse_clim > 1e-8 else 0.0
        per_depth_ss.append(
            {
                "depth_m": d,
                "skill_score": round(ss, 4),
                "mse_model": round(mse_model, 4),
                "mse_clim": round(mse_clim, 4),
            }
        )

    # Overall SS
    valid_diff_model = (y_pred - y_true)[mask]
    valid_diff_clim = (y_clim - y_true)[mask]

    if len(valid_diff_model) > 0:
        tot_mse_m = float(np.mean(valid_diff_model**2))
        tot_mse_c = float(np.mean(valid_diff_clim**2))
        overall_ss = 1.0 - (tot_mse_m / (tot_mse_c + 1e-12)) if tot_mse_c > 1e-8 else 0.0
    else:
        overall_ss = float("nan")

    return {
        "overall_skill_score": round(overall_ss, 4),
        "per_depth": per_depth_ss,
    }


def compute_anomaly_correlation(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_clim: np.ndarray,
    mask: np.ndarray | None = None,
) -> list[dict[str, Any]]:
    """Compute Pearson anomaly correlation: corr(y_true - y_clim, y_pred - y_clim)."""
    y_true = np.asarray(y_true, dtype=np.float64)
    y_pred = np.asarray(y_pred, dtype=np.float64)
    y_clim = np.asarray(y_clim, dtype=np.float64)

    if mask is None:
        mask = ~np.isnan(y_true) & ~np.isnan(y_pred) & ~np.isnan(y_clim)
    else:
        mask = np.asarray(mask, dtype=bool)

    n_depths = y_true.shape[1]
    results: list[dict[str, Any]] = []

    for i in range(n_depths):
        m = mask[:, i]
        d = STANDARD_DEPTHS[i] if i < len(STANDARD_DEPTHS) else i
        if np.sum(m) < 3:
            results.append({"depth_m": d, "anomaly_corr": float("nan")})
            continue

        true_anom = y_true[m, i] - y_clim[m, i]
        pred_anom = y_pred[m, i] - y_clim[m, i]

        std_t = np.std(true_anom)
        std_p = np.std(pred_anom)

        if std_t > 1e-8 and std_p > 1e-8:
            r = float(np.corrcoef(true_anom, pred_anom)[0, 1])
        else:
            r = 0.0

        results.append({"depth_m": d, "anomaly_corr": round(r, 4)})

    return results


def compute_mld(
    temperatures: np.ndarray,
    depths: Sequence[float] = STANDARD_DEPTHS,
    delta_t: float = 0.2,
    ref_depth: float = 10.0,
) -> float:
    """Calculate Mixed Layer Depth (MLD) in meters.

    Uses the standard de Boyer Montegut et al. (2004) oceanographic criterion:
    the depth where T = T(ref_depth) - delta_t (default: 0.2 deg C from 10 m).
    Linearly interpolates between standard depth levels.
    """
    temps = np.asarray(temperatures, dtype=np.float64)
    d_arr = np.asarray(depths, dtype=np.float64)

    # Clean out NaNs
    valid = ~np.isnan(temps)
    if np.sum(valid) < 3:
        return float("nan")

    temps = temps[valid]
    d_arr = d_arr[valid]

    # Find reference temperature at ref_depth (e.g. 10 m)
    if ref_depth in d_arr:
        ref_temp = float(temps[d_arr == ref_depth][0])
    else:
        ref_temp = float(interpolate.interp1d(d_arr, temps, fill_value="extrapolate")(ref_depth))

    target_temp = ref_temp - delta_t

    # Search downward below reference depth
    below_ref = d_arr >= ref_depth
    d_sub = d_arr[below_ref]
    t_sub = temps[below_ref]

    # Check if threshold crossed
    for j in range(len(t_sub) - 1):
        t1, t2 = t_sub[j], t_sub[j + 1]
        z1, z2 = d_sub[j], d_sub[j + 1]
        # Temperature decreases with depth across target
        if (t1 >= target_temp >= t2) or (t1 <= target_temp <= t2):
            if np.isclose(t1, t2):
                return float(z1)
            frac = (target_temp - t1) / (t2 - t1)
            return float(z1 + frac * (z2 - z1))

    # If temperature never drops by delta_t, MLD is >= maximum observed depth
    return float(d_sub[-1])


def compute_d20(
    temperatures: np.ndarray,
    depths: Sequence[float] = STANDARD_DEPTHS,
    isotherm: float = 20.0,
) -> float:
    """Calculate D20 (depth in meters of the 20 deg C isotherm).

    A primary proxy for thermocline depth in the North Indian Ocean.
    Uses linear interpolation across standard depths.
    """
    temps = np.asarray(temperatures, dtype=np.float64)
    d_arr = np.asarray(depths, dtype=np.float64)

    valid = ~np.isnan(temps)
    if np.sum(valid) < 3:
        return float("nan")

    temps = temps[valid]
    d_arr = d_arr[valid]

    if temps[0] < isotherm:
        # Water column is colder than 20 deg C from surface
        return float(d_arr[0])

    for j in range(len(temps) - 1):
        t1, t2 = temps[j], temps[j + 1]
        z1, z2 = d_arr[j], d_arr[j + 1]
        if (t1 >= isotherm >= t2) or (t1 <= isotherm <= t2):
            if np.isclose(t1, t2):
                return float(z1)
            frac = (isotherm - t1) / (t2 - t1)
            return float(z1 + frac * (z2 - z1))

    # If never crosses 20 deg C
    return float("nan")


def compute_ohc300(
    temperatures: np.ndarray,
    depths: Sequence[float] = STANDARD_DEPTHS,
    max_depth: float = 300.0,
) -> float:
    """Calculate depth-averaged temperature index for the upper 300 m.

    Index = (1 / max_depth) * integral_{0}^{max_depth} T(z) dz.
    """
    temps = np.asarray(temperatures, dtype=np.float64)
    d_arr = np.asarray(depths, dtype=np.float64)

    valid = ~np.isnan(temps)
    if np.sum(valid) < 3:
        return float("nan")

    temps = temps[valid]
    d_arr = d_arr[valid]

    # Restrict to upper max_depth meters
    in_range = d_arr <= max_depth
    if not np.any(in_range):
        return float("nan")

    z_sub = list(d_arr[in_range])
    t_sub = list(temps[in_range])

    # If highest depth in range < max_depth, interpolate to max_depth
    if z_sub[-1] < max_depth and d_arr[-1] >= max_depth:
        t_interp = float(interpolate.interp1d(d_arr, temps)(max_depth))
        z_sub.append(max_depth)
        t_sub.append(t_interp)

    integral = integrate.trapezoid(t_sub, z_sub)
    span = z_sub[-1] - z_sub[0]
    return float(integral / span) if span > 0 else float("nan")


def compute_oceanographic_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    depths: Sequence[float] = STANDARD_DEPTHS,
) -> dict[str, Any]:
    """Compute MLD, D20, and OHC-300 metrics across all profiles."""
    y_true = np.asarray(y_true, dtype=np.float64)
    y_pred = np.asarray(y_pred, dtype=np.float64)
    n = y_true.shape[0]

    mld_true, mld_pred = [], []
    d20_true, d20_pred = [], []
    ohc_true, ohc_pred = [], []

    for i in range(n):
        mt = compute_mld(y_true[i], depths=depths)
        mp = compute_mld(y_pred[i], depths=depths)
        if not np.isnan(mt) and not np.isnan(mp):
            mld_true.append(mt)
            mld_pred.append(mp)

        dt = compute_d20(y_true[i], depths=depths)
        dp = compute_d20(y_pred[i], depths=depths)
        if not np.isnan(dt) and not np.isnan(dp):
            d20_true.append(dt)
            d20_pred.append(dp)

        ot = compute_ohc300(y_true[i], depths=depths)
        op = compute_ohc300(y_pred[i], depths=depths)
        if not np.isnan(ot) and not np.isnan(op):
            ohc_true.append(ot)
            ohc_pred.append(op)

    def _summary(true_vals: list[float], pred_vals: list[float]) -> dict[str, float]:
        if not true_vals:
            return {"rmse": float("nan"), "mae": float("nan"), "bias": float("nan")}
        diff = np.array(pred_vals) - np.array(true_vals)
        return {
            "rmse": round(float(np.sqrt(np.mean(diff**2))), 2),
            "mae": round(float(np.mean(np.abs(diff))), 2),
            "bias": round(float(np.mean(diff)), 2),
        }

    return {
        "mld": _summary(mld_true, mld_pred),
        "d20": _summary(d20_true, d20_pred),
        "ohc300": _summary(ohc_true, ohc_pred),
    }


def compute_coverage(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_sigma: np.ndarray,
    nominal_coverage: float = 0.90,
) -> dict[str, Any]:
    """Compute uncertainty calibration metrics (empirical coverage and sharpness).

    Args:
        y_true: True temperatures [N, n_depths].
        y_pred: Predicted mean temperatures [N, n_depths].
        y_sigma: Predicted standard deviation (uncertainty) [N, n_depths].
        nominal_coverage: Nominal interval target (default: 0.90 -> 90%).
    """
    # z critical value for normal distribution: for 0.90 -> 1.64485
    from scipy.stats import norm

    alpha = 1.0 - nominal_coverage
    z_crit = float(norm.ppf(1.0 - alpha / 2.0))

    lower = y_pred - z_crit * y_sigma
    upper = y_pred + z_crit * y_sigma

    valid = ~np.isnan(y_true) & ~np.isnan(y_pred) & ~np.isnan(y_sigma) & (y_sigma > 0)
    if not np.any(valid):
        return {"empirical_coverage": float("nan"), "sharpness": float("nan")}

    in_interval = (y_true[valid] >= lower[valid]) & (y_true[valid] <= upper[valid])
    empirical_cov = float(np.mean(in_interval))
    sharpness = float(np.mean(upper[valid] - lower[valid]))

    return {
        "nominal_coverage": nominal_coverage,
        "empirical_coverage": round(empirical_cov, 4),
        "sharpness": round(sharpness, 4),
    }


def compute_depth_group_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    mask: np.ndarray | None = None,
) -> list[dict[str, Any]]:
    """Aggregate RMSE, MAE, Bias and Pearson correlation by standard DEPTH_GROUPS."""
    y_true = np.asarray(y_true, dtype=np.float64)
    y_pred = np.asarray(y_pred, dtype=np.float64)

    if mask is None:
        mask = ~np.isnan(y_true) & ~np.isnan(y_pred)

    grouped_results: list[dict[str, Any]] = []

    for label, depths in DEPTH_GROUPS.items():
        idxs = [STANDARD_DEPTHS.index(d) for d in depths if d in STANDARD_DEPTHS]
        if not idxs:
            continue

        group_true = y_true[:, idxs].ravel()
        group_pred = y_pred[:, idxs].ravel()
        group_mask = mask[:, idxs].ravel()

        if not np.any(group_mask):
            continue

        yt = group_true[group_mask]
        yp = group_pred[group_mask]
        diff = yp - yt

        rmse = float(np.sqrt(np.mean(diff**2)))
        mae = float(np.mean(np.abs(diff)))
        bias = float(np.mean(diff))
        corr = float(np.corrcoef(yt, yp)[0, 1]) if yt.std() > 1e-8 and yp.std() > 1e-8 else 0.0

        grouped_results.append(
            {
                "depth_group": label,
                "rmse": round(rmse, 4),
                "mae": round(mae, 4),
                "bias": round(bias, 4),
                "corr": round(corr, 4),
                "n_samples": int(np.sum(group_mask)),
            }
        )

    return grouped_results


def block_bootstrap_ci(
    df: pd.DataFrame,
    y_true_cols: Sequence[str],
    y_pred: np.ndarray,
    group_col: str = "float_id",
    depth_slice: Sequence[int] | None = None,
    n_boot: int = 500,
    ci: float = 0.95,
    seed: int = 42,
) -> dict[str, float]:
    """Compute block bootstrap confidence interval over floats (not profiles).

    Specifically used for thermocline (50-150 m) RMSE to provide honest CIs.
    """
    df = df.reset_index(drop=True)
    y_true = df[list(y_true_cols)].to_numpy(dtype=np.float64)

    if depth_slice is not None:
        idxs = [STANDARD_DEPTHS.index(d) for d in depth_slice if d in STANDARD_DEPTHS]
        y_true = y_true[:, idxs]
        y_pred = y_pred[:, idxs]

    unique_floats = df[group_col].unique()
    n_floats = len(unique_floats)
    float_to_indices = {flt: df.index[df[group_col] == flt].to_numpy() for flt in unique_floats}

    rng = np.random.default_rng(seed)
    boot_rmse: list[float] = []

    for _ in range(n_boot):
        sample_floats = rng.choice(unique_floats, size=n_floats, replace=True)
        sample_indices = np.concatenate([float_to_indices[flt] for flt in sample_floats])

        diff = (y_pred[sample_indices] - y_true[sample_indices]).ravel()
        diff = diff[~np.isnan(diff)]
        if len(diff) > 0:
            boot_rmse.append(float(np.sqrt(np.mean(diff**2))))

    alpha = (1.0 - ci) / 2.0
    lower = float(np.percentile(boot_rmse, 100 * alpha))
    upper = float(np.percentile(boot_rmse, 100 * (1.0 - alpha)))
    mean_val = float(np.mean(boot_rmse))

    return {
        "mean": round(mean_val, 4),
        "ci_lower": round(lower, 4),
        "ci_upper": round(upper, 4),
        "ci_nominal": ci,
    }
