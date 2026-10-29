"""
Metrics for evaluation protocol v2 (blueprint §11, §13).

Everything works on [N, 15] arrays with a boolean observation mask (depths a float did not reach
are excluded, never filled). Adds what v1 lacked: CRPS, reliability data, the 0-10 m / 20 m-and-
below split required by the input-independence audit, float-level bootstrap intervals, paired
model comparisons with Holm correction, and minimum detectable differences for power analysis.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
from scipy.stats import norm

from aquasphere.constants import STANDARD_DEPTHS

DEPTHS = np.asarray(STANDARD_DEPTHS)
# OISST contains Argo near-surface values (blueprint §10.1): 0-10 m is reported separately and
# headline skill uses 20 m and below.
DEPTH_BANDS: dict[str, list[int]] = {
    "0-10 m (OISST-dependent)": [0, 5, 10],
    "20-30 m": [20, 30],
    "50-150 m (thermocline)": [50, 75, 100, 125, 150],
    "200-300 m": [200, 300],
    "500-1000 m": [500, 700, 1000],
}
HEADLINE = [d for d in STANDARD_DEPTHS if d >= 20]
THERMOCLINE = DEPTH_BANDS["50-150 m (thermocline)"]
RELIABILITY_LEVELS = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)


def cols(depths: Sequence[int]) -> np.ndarray:
    return np.array([STANDARD_DEPTHS.index(d) for d in depths])


def rmse(err: np.ndarray, mask: np.ndarray, depths: Sequence[int] | None = None) -> float:
    """RMSE over observed cells, optionally restricted to some standard depths."""
    if depths is not None:
        idx = cols(depths)
        err, mask = err[:, idx], mask[:, idx]
    e = err[mask]
    return float(np.sqrt(np.mean(e**2))) if e.size else float("nan")


def skill(
    err_model: np.ndarray,
    err_clim: np.ndarray,
    mask: np.ndarray,
    depths: Sequence[int] | None = None,
) -> float:
    """1 - MSE(model) / MSE(climatology) over the same observed cells."""
    m, c = rmse(err_model, mask, depths), rmse(err_clim, mask, depths)
    return float(1.0 - (m / c) ** 2) if c > 0 else float("nan")


def crps_gaussian(y: np.ndarray, mu: np.ndarray, sigma: np.ndarray) -> np.ndarray:
    """Closed-form CRPS of N(mu, sigma²) at y (Gneiting & Raftery 2007). Same units as y."""
    s = np.maximum(sigma, 1e-9)
    z = (y - mu) / s
    crps: np.ndarray = s * (z * (2 * norm.cdf(z) - 1) + 2 * norm.pdf(z) - 1 / np.sqrt(np.pi))
    return crps


def reliability(
    y: np.ndarray,
    mu: np.ndarray,
    sigma: np.ndarray,
    mask: np.ndarray,
    levels: Sequence[float] = RELIABILITY_LEVELS,
) -> dict[str, Any]:
    """Empirical coverage of central Gaussian intervals at several nominal levels."""
    z = np.abs(y - mu) / np.maximum(sigma, 1e-9)
    emp = [float(np.mean(z[mask] <= norm.ppf(0.5 + p / 2))) for p in levels]
    return {"nominal": list(levels), "empirical": emp, "n": int(mask.sum())}


def interval_scores(
    y: np.ndarray, lower: np.ndarray, upper: np.ndarray, mask: np.ndarray
) -> dict[str, float]:
    inside = (y >= lower) & (y <= upper)
    return {
        "coverage": float(np.mean(inside[mask])),
        "mean_width": float(np.mean((upper - lower)[mask])),
    }


def band_table(err: np.ndarray, mask: np.ndarray) -> list[dict[str, Any]]:
    out = []
    for label, depths in DEPTH_BANDS.items():
        idx = cols(depths)
        e = err[:, idx][mask[:, idx]]
        out.append(
            {
                "band": label,
                "rmse": round(float(np.sqrt(np.mean(e**2))), 4) if e.size else None,
                "bias": round(float(np.mean(e)), 4) if e.size else None,
                "n": int(e.size),
            }
        )
    return out


def anomaly_correlation(
    y: np.ndarray, pred: np.ndarray, clim: np.ndarray, mask: np.ndarray, depths: Sequence[int]
) -> float:
    idx = cols(depths)
    a = (y - clim)[:, idx][mask[:, idx]]
    b = (pred - clim)[:, idx][mask[:, idx]]
    if a.size < 3 or a.std() < 1e-9 or b.std() < 1e-9:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


# ── Float-level bootstrap ─────────────────────────────────────────────────────


def _float_blocks(groups: np.ndarray) -> list[np.ndarray]:
    _, inverse = np.unique(groups, return_inverse=True)
    return [np.flatnonzero(inverse == k) for k in range(inverse.max() + 1)]


def bootstrap_rmse(
    err: np.ndarray,
    mask: np.ndarray,
    groups: np.ndarray,
    depths: Sequence[int],
    n_boot: int = 1000,
    seed: int = 0,
) -> dict[str, float]:
    """RMSE with a 95% CI from resampling whole floats (profiles of one float are correlated)."""
    idx = cols(depths)
    sq = np.where(mask[:, idx], err[:, idx] ** 2, 0.0).sum(axis=1)
    cnt = mask[:, idx].sum(axis=1)
    blocks = _float_blocks(groups)
    b_sq = np.array([sq[b].sum() for b in blocks])
    b_n = np.array([cnt[b].sum() for b in blocks])
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(blocks), size=(n_boot, len(blocks)))
    reps = np.sqrt(b_sq[draws].sum(axis=1) / np.maximum(b_n[draws].sum(axis=1), 1))
    point = float(np.sqrt(b_sq.sum() / max(b_n.sum(), 1)))
    return {
        "rmse": point,
        "ci_low": float(np.percentile(reps, 2.5)),
        "ci_high": float(np.percentile(reps, 97.5)),
        "se": float(reps.std(ddof=1)),
    }


def paired_rmse_difference(
    err_a: np.ndarray,
    err_b: np.ndarray,
    mask: np.ndarray,
    groups: np.ndarray,
    depths: Sequence[int],
    n_boot: int = 2000,
    seed: int = 0,
) -> dict[str, float]:
    """RMSE(a) - RMSE(b) on the same cells, with a float-block bootstrap CI and two-sided p."""
    idx = cols(depths)
    m = mask[:, idx]
    sa = np.where(m, err_a[:, idx] ** 2, 0.0).sum(axis=1)
    sb = np.where(m, err_b[:, idx] ** 2, 0.0).sum(axis=1)
    cnt = m.sum(axis=1)
    blocks = _float_blocks(groups)
    ba = np.array([sa[b].sum() for b in blocks])
    bb = np.array([sb[b].sum() for b in blocks])
    bn = np.array([cnt[b].sum() for b in blocks])
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(blocks), size=(n_boot, len(blocks)))
    n = np.maximum(bn[draws].sum(axis=1), 1)
    diffs = np.sqrt(ba[draws].sum(axis=1) / n) - np.sqrt(bb[draws].sum(axis=1) / n)
    point = float(np.sqrt(ba.sum() / max(bn.sum(), 1)) - np.sqrt(bb.sum() / max(bn.sum(), 1)))
    # two-sided percentile p-value for H0: difference = 0
    p = float(min(1.0, 2 * min(np.mean(diffs <= 0), np.mean(diffs >= 0))))
    return {
        "diff": point,
        "ci_low": float(np.percentile(diffs, 2.5)),
        "ci_high": float(np.percentile(diffs, 97.5)),
        "se": float(diffs.std(ddof=1)),
        "p": p,
    }


def holm(pvalues: dict[str, float]) -> dict[str, float]:
    """Holm-Bonferroni adjusted p-values (monotone, capped at 1)."""
    order = sorted(pvalues, key=lambda k: pvalues[k])
    m = len(order)
    out: dict[str, float] = {}
    running = 0.0
    for i, k in enumerate(order):
        running = max(running, min(1.0, (m - i) * pvalues[k]))
        out[k] = running
    return out


def minimum_detectable_difference(se: float, alpha: float = 0.05, power: float = 0.8) -> float:
    """Smallest true difference detectable with the given power, two-sided test."""
    return float((norm.ppf(1 - alpha / 2) + norm.ppf(power)) * se)
