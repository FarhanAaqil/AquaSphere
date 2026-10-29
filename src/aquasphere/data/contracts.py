"""
Pandera data contracts (blueprint §15: "pandera data contracts").

ARGO_PROFILES is the schema of the processed Argo table (data/processed/argo_profiles.parquet):
one row per profile, 15 standard-depth temperatures t_<d> and observation masks m_<d>.
"""

from __future__ import annotations

import pandas as pd
import pandera.pandas as pa

from aquasphere.constants import LAT_MAX, LAT_MIN, LON_MAX, LON_MIN, STANDARD_DEPTHS

# Physically plausible seawater temperatures for 0-1000 m in the North Indian Ocean (°C)
T_MIN, T_MAX = 1.0, 35.0


def _observed_depths_are_finite(df: pd.DataFrame) -> pd.Series:
    """Row-wise: every depth flagged as observed (m_d == 1) has a finite temperature."""
    ok = pd.Series(True, index=df.index)
    for d in STANDARD_DEPTHS:
        ok &= ~((df[f"m_{d}"] == 1) & df[f"t_{d}"].isna())
    return ok


def _has_an_observation(df: pd.DataFrame) -> pd.Series:
    return df[[f"m_{d}" for d in STANDARD_DEPTHS]].sum(axis=1) > 0


_columns: dict[str, pa.Column] = {
    "profile_id": pa.Column(str, unique=True),
    "float_id": pa.Column(str, nullable=False),
    "cycle": pa.Column(int, pa.Check.ge(0)),
    "lat": pa.Column(float, pa.Check.in_range(LAT_MIN, LAT_MAX)),
    "lon": pa.Column(float, pa.Check.in_range(LON_MIN, LON_MAX)),
    "date": pa.Column(
        str,
        pa.Check.str_matches(r"^\d{4}-\d{2}-\d{2}"),
        description="Profile date, ISO YYYY-MM-DD",
    ),
    "sst": pa.Column(float, pa.Check.in_range(10.0, 35.0), nullable=True),
    # Optional (older tables predate it): R real-time, A real-time adjusted, D delayed mode
    "data_mode": pa.Column(str, pa.Check.isin(["R", "A", "D"]), required=False),
}
for _d in STANDARD_DEPTHS:
    _columns[f"t_{_d}"] = pa.Column(float, pa.Check.in_range(T_MIN, T_MAX), nullable=True)
    _columns[f"m_{_d}"] = pa.Column(int, pa.Check.isin([0, 1]))

ARGO_PROFILES = pa.DataFrameSchema(
    _columns,
    checks=[
        pa.Check(
            _observed_depths_are_finite, error="observed depth (m_d == 1) has NaN temperature"
        ),
        pa.Check(_has_an_observation, error="profile has no observed depth"),
    ],
    strict=False,  # extra columns (e.g. collocated SLA/SSS) are allowed
    coerce=False,
    name="argo_profiles",
)


def validate_argo_profiles(df: pd.DataFrame) -> pd.DataFrame:
    """Validate the processed Argo table, reporting every failure at once."""
    return ARGO_PROFILES.validate(df, lazy=True)
