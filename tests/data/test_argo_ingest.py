"""Argo ingest: QC filtering, data mode, pressure-to-depth and windowing, with no network access."""

from __future__ import annotations

from datetime import date, timedelta
from itertools import pairwise
from typing import Any

import numpy as np
import pytest

from aquasphere.data.argo_ingest import (
    data_mode,
    parse_record,
    pressure_to_depth,
    weekly_windows,
)


def _record(**over: Any) -> dict[str, Any]:
    pres = [5.0, 10, 20, 40, 60, 80, 100, 150, 200, 300, 500, 700, 1000, 1050]
    temp = [29.0, 28.9, 28.5, 27.0, 25.0, 23.0, 21.0, 18.0, 15.0, 13.0, 11.0, 9.5, 8.0, 7.8]
    rec: dict[str, Any] = {
        "_id": "2902599_066",
        "geolocation": {"type": "Point", "coordinates": [70.5, 15.25]},
        "timestamp": "2016-03-04T06:12:00.000Z",
        "cycle_number": 66,
        "geolocation_argoqc": 1,
        "timestamp_argoqc": 1,
        "source": [{"url": "ftp://x/D2902599_066.nc"}],
        "data_info": [
            ["temperature", "pressure", "temperature_argoqc", "pressure_argoqc"],
            ["units", "data_keys_mode"],
            [["degree_Celsius", "D"], ["decibar", "D"], [None, None], [None, None]],
        ],
        "data": [temp, pres, [1] * len(pres), [1] * len(pres)],
    }
    rec.update(over)
    return rec


def test_pressure_to_depth_matches_unesco_check_value() -> None:
    # UNESCO 1983 check value: 10000 dbar at 30° latitude -> 9712.653 m
    assert pressure_to_depth(np.array([10000.0]), 30.0)[0] == pytest.approx(9712.653, abs=1e-3)
    assert pressure_to_depth(np.array([0.0]), 15.0)[0] == 0.0


def test_parse_good_profile() -> None:
    row = parse_record(_record())
    assert row is not None
    assert row["profile_id"] == "2902599_066"
    assert row["float_id"] == "2902599"
    assert row["date"] == "2016-03-04"
    assert row["data_mode"] == "D"
    assert row["m_0"] == 1 and row["m_1000"] == 1  # 5 dbar extrapolates to 0 m; 1050 dbar > 1000 m
    assert row["t_0"] == pytest.approx(29.0)
    assert 20.0 < row["t_100"] < 21.5
    assert np.isnan(row["sst"])


@pytest.mark.parametrize(
    "over",
    [
        {"geolocation_argoqc": 4},
        {"timestamp_argoqc": 3},
        {"geolocation": {"type": "Point", "coordinates": [40.0, 15.0]}},  # outside the domain
    ],
)
def test_profile_level_qc_rejects(over: dict[str, Any]) -> None:
    assert parse_record(_record(**over)) is None


def test_bad_level_qc_flags_are_dropped() -> None:
    rec = _record()
    # Flag temperature below 150 dbar as bad. 150 dbar is ~149 m deep, so the deepest good level
    # sits just above the 150 m standard depth: 125 m stays observed, 150 m and below are masked.
    rec["data"][2] = [1 if p <= 150 else 4 for p in rec["data"][1]]
    row = parse_record(rec)
    assert row is not None
    assert row["m_125"] == 1
    assert row["m_150"] == 0 and row["m_1000"] == 0
    assert np.isnan(row["t_1000"])


def test_too_few_good_levels_rejected() -> None:
    rec = _record()
    rec["data"][3] = [1, 1, 1, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4]  # pressure QC bad below 20 dbar
    assert parse_record(rec) is None


def test_data_mode_falls_back_to_file_prefix() -> None:
    rec = _record()
    rec["data_info"][2][0] = ["degree_Celsius", None]
    rec["source"] = [{"url": "ftp://x/R2902599_066.nc"}]
    assert data_mode(rec) == "R"
    rec["source"] = []
    assert data_mode(rec) == "R"  # unknown is treated as least trusted


def test_weekly_windows_tile_the_range_without_gaps() -> None:
    start, end = date(2015, 1, 1), date(2015, 3, 3)
    wins = list(weekly_windows(start, end))
    assert wins[0][0] == start and wins[-1][1] == end
    for (_, a_end), (b_start, _) in pairwise(wins):
        assert b_start == a_end + timedelta(days=1)
    assert all((b - a).days <= 6 for a, b in wins)
