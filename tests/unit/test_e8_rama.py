"""E8 helpers: depth interpolation never extrapolates, block-bootstrap scores are sane."""

from __future__ import annotations

import numpy as np

from aquasphere.constants import STANDARD_DEPTHS
from aquasphere.eval.e8_rama import interp, markdown, score


def test_interp_matches_profile_and_refuses_to_extrapolate() -> None:
    prof = np.asarray(STANDARD_DEPTHS, dtype=float) * -0.01 + 28
    got = interp(prof, np.array([0.0, 40.0, 1000.0, 1200.0]))
    assert np.allclose(got[:3], [28.0, 27.6, 18.0]) and np.isnan(got[3])


def test_score_rmse_bias_and_ci() -> None:
    days = np.array([f"2024-{m:02d}-15" for m in range(1, 13)] * 5)
    err = np.tile(np.array([0.5, -0.5]), 30)
    s = score(err, days, n_boot=200)
    assert s["rmse"] == 0.5 and s["bias"] == 0.0 and s["n"] == 60
    assert s["ci"][0] <= 0.5 <= s["ci"][1]
    assert score(np.array([]), np.array([]))["rmse"] is None


def test_markdown_reports_surface_only_moorings() -> None:
    r = {
        "generated_at": "t",
        "model_version": "v",
        "source": "s",
        "armor3d": "a",
        "moorings": [
            {"id": "8n90e", "n": 0, "days": 10, "note": "only sensors shallower than 20 m"}
        ],
    }
    assert "only sensors shallower than 20 m" in markdown(r)
