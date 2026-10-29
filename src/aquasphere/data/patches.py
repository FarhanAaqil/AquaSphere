"""
Satellite patch stacks for Tier B and Tier C (blueprint §9.1).

    x in R^(L x C x 9 x 9),  L = 4 lags (t, t-7, t-14, t-28 days),
    C = 7 channels: SST anomaly, SLA, SSS, geostrophic u/v, wind u/v

plus a static land channel. Missing pixels (no product that day, or land) stay NaN; the training
code standardises, zero-fills and passes the land channel, so the loss never sees land values.

The SST anomaly is taken against a per-cell monthly SST climatology fitted on the
training years (2015-2022) of the store only, so nothing from validation or test leaks into it.

    python -m aquasphere.data.patches            # labelled patches for the collocated table
    python -m aquasphere.data.patches --ssl      # + unlabelled training-year patches for Tier C
"""

from __future__ import annotations

import argparse
import logging
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import zarr

from aquasphere.data.collocate_nio import OUTPUT as TABLE
from aquasphere.eval.protocol import PERIODS

logger = logging.getLogger(__name__)

STORE = Path("data/store/surface_nio.zarr")
LABELLED = Path("data/processed/patches_nio.npz")
UNLABELLED = Path("data/processed/ssl_patches_train_years.npz")

LAGS = (0, 7, 14, 28)  # days before the profile date
CHANNELS = ("sst_anom", "sla", "sss", "ug", "vg", "u10", "v10")
PATCH = 9
HALF = PATCH // 2


class PatchSource:
    """The surface store held as padded arrays, so patches come out by fancy indexing."""

    def __init__(self, store: Path = STORE) -> None:
        self.root = zarr.open_group(str(store), mode="r")
        self.dates = pd.to_datetime(list(self.root.attrs["dates"]))
        self.index = {d.strftime("%Y-%m-%d"): i for i, d in enumerate(self.dates)}
        self.lat = np.asarray(self.root["lat"][:], dtype=np.float64)
        self.lon = np.asarray(self.root["lon"][:], dtype=np.float64)
        train_end = pd.Timestamp(PERIODS["train"][1])
        self.n_train_days = int((self.dates <= train_end).sum())
        sst = np.asarray(self.root["sst"][: self.n_train_days], dtype=np.float32)
        months = self.dates[: self.n_train_days].month.to_numpy()
        # Training-years monthly SST climatology per cell: [12, lat, lon]
        with warnings.catch_warnings():  # land cells and months without training days stay NaN
            warnings.simplefilter("ignore", RuntimeWarning)
            self.sst_clim = np.stack([np.nanmean(sst[months == m], axis=0) for m in range(1, 13)])
        # Land: no SST on any training day
        self.land = np.all(np.isnan(sst), axis=0)
        del sst

    def cells(self, lat: np.ndarray, lon: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        r = np.clip(
            np.rint((lat - self.lat[0]) / (self.lat[1] - self.lat[0])), 0, len(self.lat) - 1
        )
        c = np.clip(
            np.rint((lon - self.lon[0]) / (self.lon[1] - self.lon[0])), 0, len(self.lon) - 1
        )
        return r.astype(int), c.astype(int)

    def extract(
        self, day: np.ndarray, row: np.ndarray, col: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """Patches [N, L, C, 9, 9] (float16, NaN = missing) and land [N, 9, 9] for store indices."""
        n = len(day)
        out = np.full((n, len(LAGS), len(CHANNELS), PATCH, PATCH), np.nan, dtype=np.float16)
        offs = np.arange(-HALF, HALF + 1)
        rr = row[:, None] + offs[None, :]  # [N, 9]
        cc = col[:, None] + offs[None, :]
        r_ok = (rr >= 0) & (rr < len(self.lat))
        c_ok = (cc >= 0) & (cc < len(self.lon))
        rr_c = np.clip(rr, 0, len(self.lat) - 1)
        cc_c = np.clip(cc, 0, len(self.lon) - 1)
        inside = r_ok[:, :, None] & c_ok[:, None, :]  # [N, 9, 9]
        land = np.where(inside, self.land[rr_c[:, :, None], cc_c[:, None, :]], True)
        t = day[:, None] - np.asarray(LAGS)[None, :]  # [N, L]
        t_ok = t >= 0
        t_c = np.clip(t, 0, None)
        ok = t_ok[:, :, None, None] & inside[:, None, :, :]
        for k, name in enumerate(CHANNELS):
            var = "sst" if name == "sst_anom" else name
            arr = np.asarray(self.root[var][:], dtype=np.float32)
            vals = arr[t_c[:, :, None, None], rr_c[:, None, :, None], cc_c[:, None, None, :]]
            if name == "sst_anom":
                month = self.dates[t_c.ravel()].month.to_numpy().reshape(t_c.shape) - 1
                vals = (
                    vals
                    - self.sst_clim[
                        month[:, :, None, None], rr_c[:, None, :, None], cc_c[:, None, None, :]
                    ]
                )
            out[:, :, k] = np.where(ok, vals, np.nan).astype(np.float16)
            del arr
            logger.info("patches: %s done", name)
        return out, land


def labelled(table: Path = TABLE, out: Path = LABELLED, store: Path = STORE) -> Path:
    df = pd.read_parquet(table, columns=["profile_id", "lat", "lon", "date"])
    src = PatchSource(store)
    day = np.array([src.index.get(str(d)[:10], -1) for d in df["date"]])
    if (day < 0).any():
        raise ValueError(f"{int((day < 0).sum())} profile dates are not in the store")
    row, col = src.cells(df["lat"].to_numpy(), df["lon"].to_numpy())
    patches, land = src.extract(day, row, col)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out,
        profile_id=np.asarray(df["profile_id"].astype(str), dtype=str),
        patches=patches,
        land=land,
        lags=np.asarray(LAGS),
        channels=np.asarray(CHANNELS),
    )
    logger.info("wrote %s: %s", out, patches.shape)
    return out


def unlabelled(n: int = 60000, seed: int = 0, out: Path = UNLABELLED, store: Path = STORE) -> Path:
    """Random ocean cells on training-year days only (blueprint §9.2: no transductive data)."""
    src = PatchSource(store)
    rng = np.random.default_rng(seed)
    ocean_r, ocean_c = np.nonzero(~src.land)
    pick = rng.integers(0, len(ocean_r), size=n)
    # Start at day 28 so every lag exists; stay inside the training years
    day = rng.integers(max(LAGS), src.n_train_days, size=n)
    patches, land = src.extract(day, ocean_r[pick], ocean_c[pick])
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out,
        patches=patches,
        land=land,
        day=np.asarray(src.dates[day].strftime("%Y-%m-%d"), dtype=str),
        lat=src.lat[ocean_r[pick]],
        lon=src.lon[ocean_c[pick]],
    )
    logger.info("wrote %s: %s", out, patches.shape)
    return out


def load(path: Path = LABELLED) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--ssl", action="store_true", help="also write unlabelled training-year patches")
    p.add_argument("--n-ssl", type=int, default=60000)
    a = p.parse_args()
    labelled()
    if a.ssl:
        unlabelled(n=a.n_ssl)


if __name__ == "__main__":
    main()
