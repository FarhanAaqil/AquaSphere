"""Final evaluation helpers and guards (the run itself reads the test period once and is not
repeated in tests)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from aquasphere.eval import final_eval as fe

RESULTS = Path(__file__).resolve().parents[2] / "docs" / "results" / "final_eval.json"


def test_blocks_resample_whole_floats() -> None:
    floats = np.array(["a", "a", "b", "c", "c", "c"])
    b = fe.Blocks(floats, n_boot=500, seed=0)
    point, reps = b.sums(np.ones(6))
    assert point == 6.0 and reps.shape == (500,)
    # Each replicate is a sum of whole floats (sizes 1, 2, 3) over three draws
    assert set(np.unique(reps)) <= {3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0}


def test_holm_adjusts_and_needs_the_threshold_too() -> None:
    res = {
        "A": {"p": 0.01, "meets_threshold": True},
        "B": {"p": 0.02, "meets_threshold": False},
        "C": {"p": 0.04, "meets_threshold": True},
    }
    fe.holm(res)
    assert res["A"]["p_holm"] == 0.03 and res["A"]["supported"]
    assert res["B"]["p_holm"] == 0.04 and not res["B"]["supported"]  # threshold not met
    assert res["C"]["p_holm"] == 0.04 and res["C"]["supported"]  # monotone: max(prev, 1 x 0.04)


def test_markdown_renders_the_committed_results() -> None:
    r = json.loads(RESULTS.read_text(encoding="utf-8"))
    md = fe.markdown(r)
    assert "H1a SLA adds to SST" in md and "Test-period ladder" in md
    assert md.count("supported") >= 5


def test_refuses_without_the_phrase_and_refuses_a_second_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("sys.argv", ["final_eval"])
    with pytest.raises(SystemExit, match="read once"):
        fe.main()
    (tmp_path / "final_eval.json").write_text("{}")
    monkeypatch.setattr(fe, "OUT", tmp_path)
    monkeypatch.setattr("sys.argv", ["final_eval", "--confirm", "final-evaluation-once"])
    with pytest.raises(SystemExit, match="already evaluated"):
        fe.main()
    monkeypatch.setattr("sys.argv", ["final_eval", "--confirm", "final-evaluation-once", "--quick"])
    (tmp_path / "final_eval.json").unlink()
    with pytest.raises(SystemExit, match="only for dry runs"):
        fe.main()


def test_the_test_period_was_read_exactly_once() -> None:
    log = RESULTS.parent / "test_access.log"
    lines = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1 and "Phase 6 final evaluation" in json.loads(lines[0])["purpose"]
