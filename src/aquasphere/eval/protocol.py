"""
Evaluation protocol v2 (blueprint §11): time-blocked AND float-grouped splits, test period locked.

Periods: train 2015-2022, validation/calibration 2023, test 2024-2025.
Every float belongs to exactly one partition: the first period it appears in. Profiles a float
contributes to a later period are dropped, because the model would already have seen that float.

The test partition can only be read through ``partition(df, "test", unlock=...)`` with the exact
unlock phrase, and every read is appended to docs/results/test_access.log. Phase 6 evaluates on it
once; everything before that (baselines, tuning, calibration) uses train and validation only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aquasphere.data.splits import ensure_float_id_column

PERIODS: dict[str, tuple[str, str]] = {
    "train": ("2015-01-01", "2022-12-31"),
    "val": ("2023-01-01", "2023-12-31"),
    "test": ("2024-01-01", "2025-12-31"),
}
ORDER = ("train", "val", "test")
UNLOCK_PHRASE = "final-evaluation-once"
ACCESS_LOG = Path("docs/results/test_access.log")
BOB_LON = 78.0


class TestPeriodLocked(PermissionError):  # noqa: N818 (reads better at the raise site)
    """Raised when code that must not see 2024-25 tries to read the test partition."""

    __test__ = False  # not a pytest test class, despite the name


@dataclass(frozen=True)
class SplitSummary:
    profiles: dict[str, int]
    floats: dict[str, int]
    dropped_profiles: dict[str, int]  # later-period profiles of floats owned by an earlier period

    def as_dict(self) -> dict[str, Any]:
        return {
            "profiles": self.profiles,
            "floats": self.floats,
            "dropped_profiles": self.dropped_profiles,
        }


def period_of(dates: pd.Series) -> pd.Series:
    """'train' / 'val' / 'test' for each date; NaN outside 2015-2025."""
    d = pd.to_datetime(dates)
    out = pd.Series(np.nan, index=d.index, dtype=object)
    for name, (lo, hi) in PERIODS.items():
        out[(d >= lo) & (d <= hi)] = name
    return out


def assign(df: pd.DataFrame) -> pd.DataFrame:
    """Add 'period' and 'partition' columns. partition is NaN for dropped profiles."""
    df = ensure_float_id_column(df).copy()
    df["float_id"] = df["float_id"].astype(str)
    df["period"] = period_of(df["date"])
    rank = df["period"].map({p: i for i, p in enumerate(ORDER)})
    owner_rank = rank.groupby(df["float_id"]).transform("min")
    owned = rank == owner_rank
    df["partition"] = df["period"].where(owned)
    return df


def summarise(df: pd.DataFrame) -> SplitSummary:
    a = df if "partition" in df.columns else assign(df)
    return SplitSummary(
        profiles={p: int((a["partition"] == p).sum()) for p in ORDER},
        floats={p: int(a.loc[a["partition"] == p, "float_id"].nunique()) for p in ORDER},
        dropped_profiles={
            p: int(((a["period"] == p) & a["partition"].isna()).sum()) for p in ORDER
        },
    )


def partition(
    df: pd.DataFrame, name: str, *, unlock: str | None = None, purpose: str = ""
) -> pd.DataFrame:
    """One partition of the protocol. Reading 'test' needs the unlock phrase and is logged."""
    if name not in ORDER:
        raise ValueError(f"unknown partition {name!r}; expected one of {ORDER}")
    if name == "test":
        if unlock != UNLOCK_PHRASE:
            raise TestPeriodLocked(
                "The 2024-2025 test period is locked until the final evaluation (roadmap Phase 6). "
                "Tune, calibrate and compare on 'train' and 'val'."
            )
        ACCESS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with ACCESS_LOG.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {"at": datetime.now(UTC).isoformat(timespec="seconds"), "purpose": purpose}
                )
                + "\n"
            )
    a = df if "partition" in df.columns else assign(df)
    return a[a["partition"] == name].copy()


def region(lon: pd.Series) -> pd.Series:
    return pd.Series(np.where(lon >= BOB_LON, "Bay of Bengal", "Arabian Sea"), index=lon.index)


def season(dates: pd.Series) -> pd.Series:
    m = pd.to_datetime(dates).dt.month
    return pd.Series(
        np.select(
            [m.isin([6, 7, 8, 9]), m.isin([12, 1, 2])],
            ["SW monsoon", "NE monsoon"],
            default="Inter-monsoon",
        ),
        index=dates.index,
    )
