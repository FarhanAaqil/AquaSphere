"""End-to-end report on a small synthetic archive: outputs written, test period never touched."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from aquasphere.constants import STANDARD_DEPTHS
from aquasphere.eval import baselines_v2, protocol, report_v2


def _archive(path: Path) -> None:
    """60 floats spread over 2015-2025, 25 profiles each, anomaly driven by SST."""
    rng = np.random.default_rng(0)
    rows = []
    for f in range(60):
        start = pd.Timestamp("2015-01-01") + pd.Timedelta(days=int(rng.integers(0, 3800)))
        lat0, lon0 = rng.uniform(7, 27), rng.uniform(50, 100)
        for c in range(25):
            date = start + pd.Timedelta(days=10 * c)
            if date > pd.Timestamp("2025-12-31"):
                break
            sst_anom = rng.normal(0, 0.6)
            row = {
                "profile_id": f"{f}_{c:03d}",
                "lat": lat0 + rng.normal(0, 0.3),
                "lon": lon0 + rng.normal(0, 0.3),
                "date": date.strftime("%Y-%m-%d"),
                "sst": 28.5 + sst_anom,
            }
            for ch in ("sss", "sla", "ug", "vg", "u10", "v10"):
                row[ch] = rng.normal()
            for d in STANDARD_DEPTHS:
                row[f"t_{d}"] = (
                    28 - 0.02 * d + 1.5 * sst_anom * np.exp(-d / 150) + rng.normal(0, 0.1)
                )
                row[f"m_{d}"] = 1
            rows.append(row)
    pd.DataFrame(rows).to_parquet(path, index=False)


def test_report_writes_everything_without_reading_the_test_period(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    table = tmp_path / "archive.parquet"
    _archive(table)
    monkeypatch.setattr(baselines_v2.B3V1Net, "EPOCHS", 2)
    monkeypatch.setattr(baselines_v2.B4DeepEnsemble, "EPOCHS", 3)
    monkeypatch.setattr(baselines_v2.B4DeepEnsemble, "WARMUP", 1)
    monkeypatch.setattr(baselines_v2.B4DeepEnsemble, "MEMBERS", 2)

    # Any attempt to read the locked test period fails the run outright
    real_partition = protocol.partition

    def guarded(df: pd.DataFrame, name: str, **kw: object) -> pd.DataFrame:
        assert name != "test", "evaluation tried to read the test period"
        return real_partition(df, name)

    monkeypatch.setattr(report_v2, "partition", guarded)

    out = tmp_path / "results"
    report_v2.run(table, out, seeds=(0, 1), n_boot=50)

    metrics = json.loads((out / "metrics_v2.json").read_text(encoding="utf-8"))
    assert set(metrics["e2"]) == {"B0", "B1", "B2", "B3", "B4"}
    assert metrics["protocol"]["test_locked"] is True
    assert metrics["e2"]["B0"]["skill_thermocline"] == 0.0
    assert metrics["e2"]["B2"]["thermocline_rmse"] < metrics["e2"]["B0"]["thermocline_rmse"]
    assert "p_holm" in metrics["e2"]["B2"]["vs_B0_thermocline"]
    assert "reliability" in metrics["e2"]["B4"]["probabilistic"]
    assert {s["status"] for s in metrics["strata"]} <= {"confirmatory", "descriptive only", "empty"}

    e1 = json.loads((out / "e1_leakage_v2.json").read_text(encoding="utf-8"))
    assert set(e1["models"]) == {"B0", "B1", "B2", "B3"}
    for name in ("baseline_table_v2.md", "e1_leakage_v2.md"):
        assert "do not edit" in (out / name).read_text(encoding="utf-8")
