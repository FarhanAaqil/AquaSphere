"""
Derived ocean products and export formats (roadmap Phase 5).

    Tropical cyclone heat potential (Leipper & Volgenau 1972, as computed by NOAA AOML):
        TCHP = rho * cp * integral_0^D26 (T(z) - 26) dz       [kJ/cm^2]
    with rho = 1026 kg/m^3 and cp = 4178 J/(kg K), integrated on a 1 m grid after linear
    interpolation between the 15 standard depths. TCHP is 0 when the surface is below 26 °C.

Every value here is computed from a predicted profile; nothing is filled in when the profile is
missing.
"""

from __future__ import annotations

import io
import math
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from aquasphere.constants import STANDARD_DEPTHS

RHO = 1026.0
CP = 4178.0
J_PER_M2_TO_KJ_PER_CM2 = 1e-7
_FINE = np.arange(0.0, float(STANDARD_DEPTHS[-1]) + 1.0, 1.0)


def isotherm_depth(temps: np.ndarray, iso: float) -> float | None:
    """Depth (m) where the profile first crosses `iso` going down.

    0 when the surface is already colder; None when the profile never cools to `iso`
    within 1000 m or has fewer than 3 values.
    """
    t = np.asarray(temps, dtype=np.float64)
    z = np.asarray(STANDARD_DEPTHS, dtype=np.float64)
    ok = np.isfinite(t)
    if ok.sum() < 3:
        return None
    t, z = t[ok], z[ok]
    if t[0] < iso:
        return 0.0
    for j in range(len(t) - 1):
        if t[j] >= iso > t[j + 1]:
            return float(z[j] + (t[j] - iso) * (z[j + 1] - z[j]) / (t[j] - t[j + 1]))
    return None


def tchp(temps: np.ndarray) -> float | None:
    """Tropical cyclone heat potential (kJ/cm^2) of one profile."""
    t = np.asarray(temps, dtype=np.float64)
    z = np.asarray(STANDARD_DEPTHS, dtype=np.float64)
    ok = np.isfinite(t)
    if ok.sum() < 3:
        return None
    fine = np.interp(_FINE, z[ok], t[ok])
    d26 = isotherm_depth(t, 26.0)
    if d26 is None:  # warmer than 26 °C all the way down: not a credible profile to integrate
        return None
    excess = np.clip(fine - 26.0, 0.0, None) * (_FINE <= d26)
    return float(RHO * CP * float(np.trapezoid(excess, _FINE)) * J_PER_M2_TO_KJ_PER_CM2)


def great_circle(
    lat1: float, lon1: float, lat2: float, lon2: float, n: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """n points from (lat1, lon1) to (lat2, lon2) along the great circle, and distance (km)."""
    p1, l1, p2, l2 = map(math.radians, (lat1, lon1, lat2, lon2))
    d = 2 * math.asin(
        math.sqrt(
            math.sin((p2 - p1) / 2) ** 2
            + math.cos(p1) * math.cos(p2) * math.sin((l2 - l1) / 2) ** 2
        )
    )
    f = np.linspace(0.0, 1.0, n)
    if d < 1e-12:
        return np.full(n, lat1), np.full(n, lon1), np.zeros(n)
    a = np.sin((1 - f) * d) / math.sin(d)
    b = np.sin(f * d) / math.sin(d)
    x = a * math.cos(p1) * math.cos(l1) + b * math.cos(p2) * math.cos(l2)
    y = a * math.cos(p1) * math.sin(l1) + b * math.cos(p2) * math.sin(l2)
    zz = a * math.sin(p1) + b * math.sin(p2)
    lat = np.degrees(np.arctan2(zz, np.sqrt(x**2 + y**2)))
    lon = np.degrees(np.arctan2(y, x))
    return lat, lon, f * d * 6371.0


def provenance_lines(meta: dict[str, Any]) -> list[str]:
    stamp = {"generated_at": datetime.now(UTC).isoformat(timespec="seconds"), **meta}
    return [f"{k}={v}" for k, v in stamp.items() if v is not None]


def to_csv(rows: list[dict[str, Any]], meta: dict[str, Any]) -> str:
    """Long-format CSV: one row per (point, depth), provenance as leading '#' comment lines."""
    cols = [
        "lat",
        "lon",
        "date",
        "depth_m",
        "temperature_c",
        "sigma_c",
        "lower_90_c",
        "upper_90_c",
        "data_source",
        "mode",
    ]
    out = io.StringIO()
    out.write("# AquaSphere subsurface temperature export\n")
    for line in provenance_lines(meta):
        out.write(f"# {line}\n")
    out.write(",".join(cols) + "\n")
    for r in rows:
        for k, z in enumerate(r["depths"]):
            vals = [
                f"{r['lat']:.4f}",
                f"{r['lon']:.4f}",
                r["date"],
                str(z),
                f"{r['temperatures'][k]:.4f}",
                f"{r['uncertainties'][k]:.4f}",
                f"{r['interval_lower'][k]:.4f}",
                f"{r['interval_upper'][k]:.4f}",
                r.get("data_source", ""),
                r.get("mode", ""),
            ]
            out.write(",".join(vals) + "\n")
    return out.getvalue()


def to_netcdf(rows: list[dict[str, Any]], meta: dict[str, Any]) -> bytes:
    """NetCDF3 (scipy engine, no HDF5) with dims (point, depth) and provenance in attributes."""
    import xarray as xr

    depth = np.asarray(rows[0]["depths"], dtype=np.int32)

    def arr(key: str) -> np.ndarray:
        return np.asarray([r[key] for r in rows], dtype=np.float32)

    ds = xr.Dataset(
        {
            "temperature": (("point", "depth"), arr("temperatures"), {"units": "degC"}),
            "sigma": (("point", "depth"), arr("uncertainties"), {"units": "degC"}),
            "lower_90": (("point", "depth"), arr("interval_lower"), {"units": "degC"}),
            "upper_90": (("point", "depth"), arr("interval_upper"), {"units": "degC"}),
            "lat": (("point",), np.asarray([r["lat"] for r in rows], dtype=np.float32)),
            "lon": (("point",), np.asarray([r["lon"] for r in rows], dtype=np.float32)),
            "date": (("point",), np.asarray([r["date"] for r in rows], dtype="S10")),
            "data_source": (
                ("point",),
                np.asarray([r.get("data_source", "") for r in rows], dtype="S24"),
            ),
        },
        coords={"depth": ("depth", depth, {"units": "m", "positive": "down"})},
        # scipy keeps global attributes as Python attributes of the file object, so names like
        # "mode" would clobber its own fields: prefix them
        attrs={
            "title": "AquaSphere subsurface temperature export",
            **{
                f"aquasphere_{k}": str(v)
                for k, v in (ln.split("=", 1) for ln in provenance_lines(meta))
            },
        },
    )
    # Through a temporary file: the in-memory scipy writer is unreliable across versions
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "export.nc"
        ds.to_netcdf(path, engine="scipy")
        return path.read_bytes()
