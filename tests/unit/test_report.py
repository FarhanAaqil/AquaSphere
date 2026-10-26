"""
Unit tests for the evaluation reporting pipeline (SIH 26066).
"""

import json
from pathlib import Path

import pytest

from aquasphere.eval.report import generate_baseline_markdown, run_evaluation, update_markdown_file


def test_generate_baseline_markdown():
    mock_results = [
        {
            "name": "Climatology",
            "overall_rmse": 1.25,
            "thermocline_rmse": 1.85,
            "thermocline_ci_95": [1.60, 2.10],
            "skill_score_overall": 0.0,
            "mld_rmse": 18.5,
            "d20_rmse": 24.2,
        }
    ]

    md = generate_baseline_markdown(mock_results, n_val=300, n_floats=15)
    assert "Honest Baseline Ladder" in md
    assert "Climatology" in md
    assert "1.250" in md
    assert "[1.60, 2.10]" in md


def test_update_markdown_file(tmp_path: Path):
    test_md = tmp_path / "TEST.md"
    test_md.write_text("Header\n<!-- METRICS:START -->\nOld text\n<!-- METRICS:END -->\nFooter\n")

    success = update_markdown_file(test_md, "New generated table")
    assert success
    content = test_md.read_text()
    assert "New generated table" in content
    assert "Old text" not in content
    assert "Header" in content
    assert "Footer" in content


def test_run_evaluation_creates_artifacts(tmp_path: Path):
    data_csv = Path("data/argo_sst_training.csv")
    if not data_csv.exists():
        pytest.skip("Training CSV not present.")

    out_json = tmp_path / "metrics.json"
    out_md = tmp_path / "baseline_table.md"

    run_evaluation(csv_path=data_csv, output_json=out_json, output_md=out_md, seed=42)

    assert out_json.exists()
    assert out_md.exists()

    with open(out_json, encoding="utf-8") as f:
        data = json.load(f)
    assert "baselines" in data
    assert "Climatology" in data["baselines"]
    assert "v1 OceanEmbedNet (Re-evaluated)" in data["baselines"]
