"""The pandera contract accepts the real Argo tables and rejects each kind of bad row."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd
import pandera.errors
import pytest

from aquasphere.data.contracts import validate_argo_profiles

FIXTURE = Path("tests/fixtures/argo_200.parquet")


@pytest.fixture()
def table() -> pd.DataFrame:
    return pd.read_parquet(FIXTURE).copy()


def test_fixture_table_satisfies_contract(table: pd.DataFrame) -> None:
    validate_argo_profiles(table)


def _set(col: str, value: object) -> Callable[[pd.DataFrame], None]:
    def mutate(df: pd.DataFrame) -> None:
        df.loc[df.index[0], col] = value

    return mutate


def _observed_nan(df: pd.DataFrame) -> None:
    df.loc[df.index[0], "m_100"] = 1
    df.loc[df.index[0], "t_100"] = np.nan


def _duplicate_id(df: pd.DataFrame) -> None:
    df.loc[df.index[1], "profile_id"] = df.loc[df.index[0], "profile_id"]


def _no_observations(df: pd.DataFrame) -> None:
    for c in [c for c in df.columns if c.startswith("m_")]:
        df.loc[df.index[0], c] = 0


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (_set("lat", 31.5), "latitude outside 5-30N"),
        (_set("lon", 40.0), "longitude outside 45-105E"),
        (_set("t_50", 41.0), "non-physical temperature"),
        (_set("m_20", 2), "mask must be 0 or 1"),
        (_set("date", "31/03/2025"), "date not ISO"),
        (_observed_nan, "observed depth with NaN temperature"),
        (_duplicate_id, "duplicate profile_id"),
        (_no_observations, "profile with no observed depth"),
    ],
)
def test_contract_rejects_bad_rows(
    table: pd.DataFrame, mutate: Callable[[pd.DataFrame], None], reason: str
) -> None:
    mutate(table)
    with pytest.raises(pandera.errors.SchemaErrors):
        validate_argo_profiles(table)
