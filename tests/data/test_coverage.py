"""Coverage report: counts per variable, year, region, season and depth."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from aquasphere.constants import STANDARD_DEPTHS
from aquasphere.data.coverage import argo_coverage, monsoon_season, store_coverage, to_markdown
from aquasphere.data.store import (
    DEFAULT_LAT_GRID,
    DEFAULT_LON_GRID,
    SATELLITE_VARS,
    SurfaceZarrStore,
)


def test_monsoon_seasons() -> None:
    assert monsoon_season(7).startswith("SW")
    assert monsoon_season(1).startswith("NE")
    assert monsoon_season(4).startswith("Inter")


def test_store_and_argo_coverage(tmp_path: Path) -> None:
    dates = ["2016-12-31", "2017-01-01", "2017-01-02"]
    store = SurfaceZarrStore.create(tmp_path / "s.zarr", dates)
    shape = (len(DEFAULT_LAT_GRID), len(DEFAULT_LON_GRID))
    for i, d in enumerate(dates):
        fields = {v: np.full(shape, 1.0, np.float32) for v in SATELLITE_VARS}
        if i == 0:
            for v in ("sla", "ug", "vg"):  # altimetry missing on the first day
                fields[v][:] = np.nan
        store.write_day(d, fields)

    cov = store_coverage(store)
    assert cov["n_dates"] == 3
    assert cov["variables"]["sst"]["days_with_data"] == 3
    assert cov["variables"]["sla"]["days_with_data"] == 2
    assert cov["variables"]["sla"]["first_day"] == "2017-01-01"
    assert cov["variables"]["sla"]["by_year"][2016]["days"] == 0

    rows = []
    for k, (lat, lon, date, mode) in enumerate(
        [(10, 60, "2017-07-01", "D"), (15, 88, "2017-01-15", "D"), (20, 90, "2018-04-02", "R")]
    ):
        r = {
            "profile_id": f"{k}_1",
            "float_id": str(k),
            "lat": lat,
            "lon": lon,
            "date": date,
            "data_mode": mode,
            "sst_avail": k % 2,
        }
        r.update({f"m_{z}": int(z <= 500) for z in STANDARD_DEPTHS})
        rows.append(r)
    a = argo_coverage(pd.DataFrame(rows))
    assert a["profiles"] == 3 and a["floats"] == 3
    assert a["by_year"] == {2017: 2, 2018: 1}
    assert a["by_region"] == {"Bay of Bengal": 2, "Arabian Sea": 1}
    assert a["by_data_mode"] == {"D": 2, "R": 1}
    assert a["observed_by_depth"][500] == 3 and a["observed_by_depth"][700] == 0
    assert a["channel_availability"]["sst"] == round(1 / 3, 3)

    md = to_markdown({"generated_at": "now", "store": cov, "argo": a})
    assert "| sla | nesdisSSH1day | 2 | 2017-01-01 |" in md
    assert "| Bay of Bengal · NE monsoon (Dec-Feb) |" in md
