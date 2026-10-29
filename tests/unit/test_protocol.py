"""Evaluation protocol v2: periods, one float per partition, and a locked test period."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from aquasphere.eval import protocol
from aquasphere.eval.protocol import TestPeriodLocked, assign, partition, summarise


def _table() -> pd.DataFrame:
    rows = [
        # float A: train only
        ("A_1", "2016-05-01"),
        ("A_2", "2021-12-31"),
        # float B: starts in train, continues into val and test -> owned by train
        ("B_1", "2022-11-01"),
        ("B_2", "2023-02-01"),
        ("B_3", "2024-03-01"),
        # float C: starts in val, continues into test -> owned by val
        ("C_1", "2023-06-01"),
        ("C_2", "2025-01-01"),
        # float D: test only
        ("D_1", "2024-07-01"),
        ("D_2", "2025-12-31"),
        # outside the protocol window
        ("E_1", "2014-12-31"),
    ]
    return pd.DataFrame(
        {"profile_id": [p for p, _ in rows], "date": [d for _, d in rows], "lon": 70.0, "lat": 15.0}
    )


def test_every_float_lives_in_exactly_one_partition() -> None:
    a = assign(_table())
    owners = a.dropna(subset=["partition"]).groupby("float_id")["partition"].nunique()
    assert (owners == 1).all()
    assert dict(a.set_index("profile_id")["partition"].dropna()) == {
        "A_1": "train",
        "A_2": "train",
        "B_1": "train",
        "C_1": "val",
        "D_1": "test",
        "D_2": "test",
    }


def test_partitions_are_time_ordered_with_no_overlap() -> None:
    a = assign(_table())
    for name, (lo, hi) in protocol.PERIODS.items():
        dates = pd.to_datetime(a.loc[a["partition"] == name, "date"])
        assert dates.min() >= pd.Timestamp(lo) and dates.max() <= pd.Timestamp(hi)


def test_summary_counts_dropped_profiles() -> None:
    s = summarise(_table())
    assert s.profiles == {"train": 3, "val": 1, "test": 2}
    assert s.floats == {"train": 2, "val": 1, "test": 1}
    # B_2 (val, owned by train); B_3 and C_2 (test, owned by earlier partitions)
    assert s.dropped_profiles == {"train": 0, "val": 1, "test": 2}


def test_test_partition_is_locked_without_the_phrase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(protocol, "ACCESS_LOG", tmp_path / "access.log")
    df = _table()
    with pytest.raises(TestPeriodLocked):
        partition(df, "test")
    with pytest.raises(TestPeriodLocked):
        partition(df, "test", unlock="please")
    assert not (tmp_path / "access.log").exists()
    assert len(partition(df, "val")) == 1


def test_unlocked_test_reads_are_logged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = tmp_path / "access.log"
    monkeypatch.setattr(protocol, "ACCESS_LOG", log)
    out = partition(_table(), "test", unlock=protocol.UNLOCK_PHRASE, purpose="unit test")
    assert set(out["profile_id"]) == {"D_1", "D_2"}
    assert "unit test" in log.read_text(encoding="utf-8")


def test_regions_and_seasons() -> None:
    df = pd.DataFrame(
        {"lon": [60.0, 88.0, 78.0], "date": ["2023-07-01", "2023-01-10", "2023-04-01"]}
    )
    assert list(protocol.region(df["lon"])) == ["Arabian Sea", "Bay of Bengal", "Bay of Bengal"]
    assert list(protocol.season(df["date"])) == ["SW monsoon", "NE monsoon", "Inter-monsoon"]
