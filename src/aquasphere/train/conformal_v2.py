"""
Mondrian split-conformal intervals by region and monsoon season (blueprint §9.4).

    s_ik = |a_ik - mu_ik| / sigma_ik
    q_k  = Quantile_{ceil((n+1)(1-alpha))/n}(s_1k ... s_nk)      within each stratum
    interval_k = mu_k +- q_k * sigma_k

Calibration uses the validation year (2023). Residuals from one float are correlated, so the
coverage of this procedure on 2023 is estimated by cross-conformal folds split by float: each
fold is calibrated on the other floats and scored on its own, and the result is checked with a
block bootstrap over floats. A stratum with fewer than MIN_N calibration scores at a depth falls
back to its region, then to all strata, and the fallback used is recorded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from aquasphere.eval.protocol import region, season

MIN_N = 30
ALL = "*"


def strata(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    return region(df["lon"]).to_numpy(), season(df["date"]).to_numpy()


def conformal_quantile(scores: np.ndarray, alpha: float) -> float:
    """The ceil((n+1)(1-alpha))-th smallest score; the largest one if that rank exceeds n."""
    n = len(scores)
    k = min(int(np.ceil((n + 1) * (1 - alpha))), n)
    return float(np.partition(scores, k - 1)[k - 1])


@dataclass
class MondrianConformal:
    alpha: float = 0.10
    min_n: int = MIN_N
    q: dict[str, list[float | None]] = field(default_factory=dict)
    n: dict[str, list[int]] = field(default_factory=dict)

    @staticmethod
    def key(reg: str, sea: str) -> str:
        return f"{reg}|{sea}"

    def fit(
        self,
        scores: np.ndarray,
        mask: np.ndarray,
        reg: np.ndarray,
        sea: np.ndarray,
    ) -> MondrianConformal:
        """scores: |error| / sigma [N, D]; mask: observed [N, D]; reg/sea: stratum labels [N]."""
        groups: dict[str, np.ndarray] = {self.key(ALL, ALL): np.ones(len(scores), dtype=bool)}
        for r in np.unique(reg):
            groups[self.key(r, ALL)] = reg == r
            for s in np.unique(sea):
                groups[self.key(r, s)] = (reg == r) & (sea == s)
        self.q, self.n = {}, {}
        for k, sel in groups.items():
            qs: list[float | None] = []
            ns: list[int] = []
            for d in range(scores.shape[1]):
                sc = scores[sel & mask[:, d], d]
                sc = sc[np.isfinite(sc)]
                ns.append(len(sc))
                qs.append(conformal_quantile(sc, self.alpha) if len(sc) >= self.min_n else None)
            self.q[k], self.n[k] = qs, ns
        return self

    def scale(self, reg: np.ndarray, sea: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """q [N, D] for each row, and the level used: 0 stratum, 1 region, 2 all, 3 none (1.645)."""
        n_d = len(next(iter(self.q.values())))
        out = np.full((len(reg), n_d), 1.645)
        level = np.full((len(reg), n_d), 3, dtype=int)
        cache: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]] = {}
        for i, (r, s) in enumerate(zip(reg, sea, strict=True)):
            if (r, s) not in cache:
                q_row = np.full(n_d, 1.645)
                l_row = np.full(n_d, 3, dtype=int)
                for d in range(n_d):
                    for lv, k in enumerate((self.key(r, s), self.key(r, ALL), self.key(ALL, ALL))):
                        v = self.q.get(k, [None] * n_d)[d]
                        if v is not None:
                            q_row[d], l_row[d] = v, lv
                            break
                cache[(r, s)] = (q_row, l_row)
            out[i], level[i] = cache[(r, s)]
        return out, level

    def interval(
        self, mean: np.ndarray, sigma: np.ndarray, reg: np.ndarray, sea: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        q, _ = self.scale(reg, sea)
        return mean - q * sigma, mean + q * sigma

    def to_dict(self) -> dict[str, Any]:
        return {"alpha": self.alpha, "min_n": self.min_n, "q": self.q, "n": self.n}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MondrianConformal:
        return cls(alpha=d["alpha"], min_n=d["min_n"], q=d["q"], n=d["n"])


def global_conformal(scores: np.ndarray, mask: np.ndarray, alpha: float = 0.10) -> np.ndarray:
    """Per-depth split-conformal q without strata (the comparison in E6)."""
    return np.array(
        [conformal_quantile(scores[mask[:, d], d], alpha) for d in range(scores.shape[1])]
    )


def cross_conformal(
    scores: np.ndarray,
    mask: np.ndarray,
    reg: np.ndarray,
    sea: np.ndarray,
    floats: np.ndarray,
    folds: int = 5,
    alpha: float = 0.10,
    mondrian: bool = True,
    seed: int = 0,
) -> np.ndarray:
    """Out-of-fold q [N, D]: each float's rows are scaled by a calibrator that never saw it."""
    rng = np.random.default_rng(seed)
    uniq = np.unique(floats)
    fold_of = dict(zip(rng.permutation(uniq), np.arange(len(uniq)) % folds, strict=True))
    fold = np.array([fold_of[f] for f in floats])
    q = np.full(scores.shape, np.nan)
    for k in range(folds):
        cal, held = fold != k, fold == k
        if mondrian:
            mc = MondrianConformal(alpha=alpha).fit(scores[cal], mask[cal], reg[cal], sea[cal])
            q[held] = mc.scale(reg[held], sea[held])[0]
        else:
            q[held] = global_conformal(scores[cal], mask[cal], alpha)[None, :]
    return q


def coverage_by_stratum(
    inside: np.ndarray,
    mask: np.ndarray,
    reg: np.ndarray,
    sea: np.ndarray,
    floats: np.ndarray,
    n_boot: int = 2000,
    seed: int = 0,
) -> list[dict[str, Any]]:
    """Coverage overall and per region x season, with a 95% CI from resampling whole floats."""
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    cells = [(ALL, ALL)] + [(r, s) for r in np.unique(reg) for s in np.unique(sea)]
    for r, s in cells:
        sel = np.ones(len(reg), dtype=bool)
        if r != ALL:
            sel = (reg == r) & (sea == s)
        if not sel.any():
            continue
        f = floats[sel]
        uniq, inv = np.unique(f, return_inverse=True)
        hit = np.bincount(inv, weights=(inside[sel] & mask[sel]).sum(axis=1), minlength=len(uniq))
        tot = np.bincount(inv, weights=mask[sel].sum(axis=1), minlength=len(uniq))
        draws = rng.integers(0, len(uniq), size=(n_boot, len(uniq)))
        reps = hit[draws].sum(axis=1) / np.maximum(tot[draws].sum(axis=1), 1)
        rows.append(
            {
                "region": "All" if r == ALL else r,
                "season": "All" if s == ALL else s,
                "profiles": int(sel.sum()),
                "floats": len(uniq),
                "coverage": float(hit.sum() / max(tot.sum(), 1)),
                "ci_low": float(np.percentile(reps, 2.5)),
                "ci_high": float(np.percentile(reps, 97.5)),
            }
        )
    return rows
