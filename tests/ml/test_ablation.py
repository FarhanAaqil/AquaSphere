"""
Unit tests for AquaSphere multi-seed ablation runner (SIH 26066).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from aquasphere.eval.ablation import (
    evaluate_ablation_rung,
    format_ablation_markdown,
    main,
    mask_input_features,
    run_ablation_ladder,
)

FIXTURE_PATH = Path("tests/fixtures/argo_200.parquet")


def test_mask_input_features() -> None:
    x = np.ones((5, 18), dtype=np.float32)
    # Mask out SLA
    x_no_sla = mask_input_features(x, keep_sla=False, keep_sss=True, keep_wind=True)
    assert x_no_sla[:, 6].tolist() == [0.0] * 5
    assert x_no_sla[:, 12].tolist() == [0.0] * 5
    assert x_no_sla[:, 5].tolist() == [1.0] * 5

    # Mask out SSS
    x_no_sss = mask_input_features(x, keep_sla=True, keep_sss=False, keep_wind=True)
    assert x_no_sss[:, 5].tolist() == [35.0] * 5
    assert x_no_sss[:, 11].tolist() == [0.0] * 5

    # Mask out Wind
    x_no_wind = mask_input_features(x, keep_sla=True, keep_sss=True, keep_wind=False)
    for idx in [7, 8, 9, 10, 13, 14, 15, 16]:
        assert x_no_wind[:, idx].tolist() == [0.0] * 5


def test_evaluate_ablation_rung() -> None:
    df = pd.read_parquet(FIXTURE_PATH)
    clim = np.ones((12, 15), dtype=np.float32) * 20.0
    res = evaluate_ablation_rung(
        name="A1 (SST only)",
        df_train=df.iloc[:100],
        df_val=df.iloc[100:],
        clim_matrix=clim,
        keep_sla=False,
        keep_sss=False,
        keep_wind=False,
        use_patch=False,
        use_ssl=False,
        epochs=1,
        seed=42,
    )
    assert "overall_rmse" in res
    assert "thermo_rmse" in res
    assert "skill_score" in res
    assert "coverage" in res
    assert res["overall_rmse"] > 0.0


def test_run_ablation_ladder_smoke() -> None:
    df = pd.read_parquet(FIXTURE_PATH).iloc[:50]
    summary = run_ablation_ladder(df, seeds=[42], epochs=1)

    assert "results" in summary
    assert len(summary["results"]) == 6
    md = format_ablation_markdown(summary)
    assert "| Run |" in md
    assert "A1 (SST only)" in md
    assert "C (+ SSL Pretrain)" in md


def test_ablation_cli_main_smoke(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    out_table = tmp_path / "test_ablation.md"
    test_args = [
        "aquasphere-ablate",
        "--fixture",
        str(FIXTURE_PATH),
        "--epochs",
        "1",
        "--output",
        str(out_table),
    ]
    monkeypatch.setattr(sys, "argv", test_args)
    main()
    assert out_table.exists()
    assert len(out_table.read_text(encoding="utf-8")) > 100
