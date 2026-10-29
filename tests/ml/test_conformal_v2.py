"""Mondrian conformal intervals and the embedding-space dissimilarity index."""

from __future__ import annotations

import numpy as np
import pandas as pd

from aquasphere.eval.applicability import DissimilarityIndex
from aquasphere.train import conformal_v2 as c


def _scores(seed: int = 0) -> tuple[np.ndarray, ...]:
    """Two regions whose normalised errors differ in scale: one global q cannot fit both."""
    rng = np.random.default_rng(seed)
    n, d = 4000, 3
    reg = np.where(rng.random(n) < 0.5, "Arabian Sea", "Bay of Bengal")
    sea = rng.choice(["SW monsoon", "NE monsoon", "Inter-monsoon"], n)
    scale = np.where(reg == "Bay of Bengal", 2.0, 1.0)[:, None]
    scores = np.abs(rng.normal(size=(n, d))) * scale
    mask = rng.random((n, d)) < 0.9
    floats = rng.integers(0, 200, n).astype(str)
    return scores, mask, reg, sea, floats


def test_quantile_is_the_finite_sample_one() -> None:
    s = np.arange(1, 11, dtype=float)  # n = 10, alpha = 0.1 -> ceil(11 * 0.9) / 10 = 1.0
    assert c.conformal_quantile(s, 0.10) == 10.0
    s = np.arange(1, 101, dtype=float)  # ceil(101 * 0.9) = 91 -> the 91st smallest
    assert c.conformal_quantile(s, 0.10) == 91.0


def test_mondrian_covers_each_stratum_where_global_does_not() -> None:
    scores, mask, reg, sea, floats = _scores()
    q_m = c.cross_conformal(scores, mask, reg, sea, floats, mondrian=True)
    q_g = c.cross_conformal(scores, mask, reg, sea, floats, mondrian=False)
    for q, ok in ((q_m, True), (q_g, False)):
        inside = scores <= q
        rows = c.coverage_by_stratum(inside, mask, reg, sea, floats, n_boot=200)
        overall = next(r for r in rows if r["region"] == "All")
        assert 0.88 <= overall["coverage"] <= 0.92  # both are fine on average
        bob = [r for r in rows if r["region"] == "Bay of Bengal"]
        assert all((0.85 <= r["coverage"] <= 0.95) == ok for r in bob)
        assert all(r["ci_low"] <= r["coverage"] <= r["ci_high"] for r in rows)


def test_small_strata_fall_back_and_round_trip() -> None:
    scores, mask, reg, sea, _ = _scores()
    reg = reg.copy()
    reg[:20] = "Lakshadweep"  # 20 rows: below MIN_N at every depth
    sea = sea.copy()
    mc = c.MondrianConformal().fit(scores, mask, reg, sea)
    q, level = mc.scale(np.array(["Lakshadweep", "Arabian Sea"]), np.array([sea[0], "SW monsoon"]))
    assert (level[0] == 2).all() and (level[1] == 0).all()
    assert np.allclose(q[0], mc.q["*|*"])
    again = c.MondrianConformal.from_dict(mc.to_dict())
    lo, hi = again.interval(
        np.zeros((1, 3)), np.ones((1, 3)), np.array(["Arabian Sea"]), np.array(["SW monsoon"])
    )
    assert np.allclose(hi, -lo) and np.allclose(hi[0], mc.q["Arabian Sea|SW monsoon"])
    # Unknown strata with no data at all use the global quantile, never an invented one
    assert np.allclose(mc.scale(np.array(["Gulf"]), np.array(["x"]))[0][0], mc.q["*|*"])


def test_dissimilarity_index_flags_far_embeddings() -> None:
    rng = np.random.default_rng(0)
    emb = rng.normal(size=(3000, 4))
    floats = rng.integers(0, 300, 3000).astype(str)
    di = DissimilarityIndex().fit(emb, floats)
    assert di.threshold > 0 and di.fold_di is not None
    # Most training-fold points are inside by construction of the whisker rule
    assert np.mean(di.fold_di <= di.threshold) > 0.9
    near = emb[:5] + 1e-3
    far = np.full((5, 4), 8.0)
    d_near, in_near = di.in_domain(near)
    d_far, in_far = di.in_domain(far)
    assert in_near.all() and not in_far.any() and (d_far > d_near).all()
    again = DissimilarityIndex.from_dict(di.to_dict())
    assert np.allclose(again(far), di(far), rtol=1e-5)


def test_strata_labels_follow_the_protocol() -> None:
    df = pd.DataFrame({"lon": [60.0, 85.0], "date": ["2023-07-01", "2023-01-15"]})
    reg, sea = c.strata(df)
    assert list(reg) == ["Arabian Sea", "Bay of Bengal"]
    assert list(sea) == ["SW monsoon", "NE monsoon"]
