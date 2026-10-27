"""
Unit tests for Experiment E1 Leakage Gap Analysis (aquasphere.eval.leakage).
"""

from pathlib import Path

import pandas as pd
import pytest

from aquasphere.eval.leakage import (
    format_leakage_markdown,
    make_random_split,
    make_time_blocked_split,
    run_experiment_e1,
)

FIXTURE_PATH = Path("tests/fixtures/argo_200.parquet")


def test_make_random_split() -> None:
    df = pd.read_parquet(FIXTURE_PATH)
    train_df, eval_df = make_random_split(df, train_ratio=0.70, seed=42)

    assert len(train_df) + len(eval_df) == len(df)
    assert len(train_df) == int(len(df) * 0.70)
    assert len(eval_df) == len(df) - int(len(df) * 0.70)


def test_make_time_blocked_split() -> None:
    df = pd.read_parquet(FIXTURE_PATH)
    train_df, eval_df = make_time_blocked_split(df, date_col="date", train_ratio=0.75)

    assert len(train_df) + len(eval_df) == len(df)
    assert train_df["date"].max() <= eval_df["date"].min()


def test_run_experiment_e1() -> None:
    df = pd.read_parquet(FIXTURE_PATH)
    res = run_experiment_e1(df, train_ratio=0.80, seed=42)

    assert "_experiment" in res
    assert "protocols" in res
    assert "random" in res["protocols"]
    assert "float_grouped" in res["protocols"]
    assert "time_blocked" in res["protocols"]
    assert "leakage_gaps" in res

    gaps = res["leakage_gaps"]
    assert "Climatology" in gaps
    assert "Gradient Boosted Trees (HistGBDT)" in gaps

    gbdt = gaps["Gradient Boosted Trees (HistGBDT)"]
    assert "rand_thermo_rmse" in gbdt
    assert "flt_thermo_rmse" in gbdt
    assert "delta_float_leakage" in gbdt

    md = format_leakage_markdown(res)
    assert "Experiment E1: Generalization & Leakage Gap Analysis" in md
    assert "Float Leakage Gap" in md


def test_main_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from aquasphere.eval.leakage import main

    out_json = tmp_path / "e1.json"
    out_md = tmp_path / "e1.md"
    monkeypatch.setattr(
        "sys.argv",
        [
            "aquasphere-e1-leakage",
            "--data",
            str(FIXTURE_PATH),
            "--json",
            str(out_json),
            "--md",
            str(out_md),
            "--seed",
            "42",
        ],
    )
    main()
    assert out_json.exists()
    assert out_md.exists()
