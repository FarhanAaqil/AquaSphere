"""
E8: independent check against RAMA moorings (blueprint E8, roadmap Phase 6).

RAMA buoys measure temperature at fixed depths and are never used anywhere in training,
tuning or calibration, and they are not Argo, so this is the most independent test available.
The served Tier A v2 model is driven by the satellite inputs in the local store for each
mooring day; its profile is interpolated to the mooring's sensor depths and compared with the
daily mean temperature (quality flags 1-3 only, PMEL's "probably valid" rule). The training-years
climatology (B0) is scored the same way for reference.

ARMOR3D (blueprint B5) is not compared: it needs a Copernicus Marine account, and it
assimilates Argo, so it would only be a labelled upper reference.

    python -m aquasphere.eval.e8_rama        # downloads ~1 MB per mooring once (cached)
"""

from __future__ import annotations

import argparse
import json
import logging
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch

from aquasphere.constants import STANDARD_DEPTHS
from aquasphere.data.collocate_nio import OUTPUT as TABLE
from aquasphere.eval.baselines_v2 import Climatology, targets
from aquasphere.eval.protocol import assign, partition
from aquasphere.serve.resolver import SurfaceResolver
from aquasphere.train.v2 import ProfileModel

logger = logging.getLogger(__name__)

ERDDAP = "https://data.pmel.noaa.gov/pmel/erddap/tabledap/pmelTaoDyT.csv"
CACHE = Path("data/cache/rama")
STORE = Path("data/store/surface_nio.zarr")
CHECKPOINT = Path("checkpoints/tier_a_v2/model.pt")
OUT = Path("docs/results")
# RAMA sites inside the 5-30N, 45-105E domain with data in 2024-2025
MOORINGS = {
    "15n90e": (15.0, 90.0),
    "12n90e": (12.0, 90.0),
    "8n90e": (8.0, 90.0),
    "8n67e": (8.0, 67.0),
}
PERIOD = ("2024-01-01", "2025-12-31")
BLOCK_DAYS = 30  # bootstrap blocks: days within a month are correlated


def fetch(station: str) -> pd.DataFrame:
    """Daily temperature at every sensor depth, quality 1-3 only, cached as CSV."""
    path = CACHE / f"{station}_{PERIOD[0]}_{PERIOD[1]}.csv"
    if not path.exists():
        q = (
            f"?time,depth,T_20,QT_5020&station=%22{station}%22"
            f"&time%3E={PERIOD[0]}T00:00:00Z&time%3C={PERIOD[1]}T23:59:59Z"
            "&T_20!=NaN&QT_5020%3E=1&QT_5020%3C=3"
        )
        with urllib.request.urlopen(ERDDAP + q, timeout=300) as r:
            text = r.read().decode("utf-8")
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    df = pd.read_csv(path, skiprows=[1])
    df["date"] = df["time"].str[:10]
    return df.rename(columns={"T_20": "temp"})[["date", "depth", "temp"]]


def interp(profile: np.ndarray, depths: np.ndarray) -> np.ndarray:
    return np.asarray(
        np.interp(depths, np.asarray(STANDARD_DEPTHS, dtype=float), profile, right=np.nan)
    )


def score(err: np.ndarray, days: np.ndarray, n_boot: int = 1000, seed: int = 0) -> dict[str, Any]:
    """RMSE, bias and a 95% CI from resampling 30-day blocks."""
    if err.size == 0:
        return {"rmse": None, "bias": None, "n": 0}
    block = (pd.to_datetime(days) - pd.Timestamp(PERIOD[0])).days.to_numpy() // BLOCK_DAYS
    uniq, inv = np.unique(block, return_inverse=True)
    sq = np.bincount(inv, weights=err**2, minlength=len(uniq))
    n = np.bincount(inv, minlength=len(uniq)).astype(float)
    draws = np.random.default_rng(seed).integers(0, len(uniq), size=(n_boot, len(uniq)))
    reps = np.sqrt(sq[draws].sum(axis=1) / np.maximum(n[draws].sum(axis=1), 1))
    return {
        "rmse": round(float(np.sqrt(np.mean(err**2))), 4),
        "ci": [
            round(float(np.percentile(reps, 2.5)), 4),
            round(float(np.percentile(reps, 97.5)), 4),
        ],
        "bias": round(float(np.mean(err)), 4),
        "n": int(err.size),
    }


def run(n_boot: int = 1000) -> dict[str, Any]:
    ck = torch.load(CHECKPOINT, map_location="cpu", weights_only=True)
    model = ProfileModel.from_state(ck)
    resolver = SurfaceResolver(store_path=STORE, enable_network=False)
    train = partition(assign(pd.read_parquet(TABLE)), "train")
    y, _ = targets(train)
    clim = Climatology().fit(train, y)

    out: dict[str, Any] = {"moorings": [], "by_depth": {}}
    pooled: dict[str, list[np.ndarray]] = {"model": [], "b0": [], "depth": [], "day": []}
    for station, (lat, lon) in MOORINGS.items():
        obs = fetch(station)
        obs = obs[obs["depth"] <= 500]
        dates = sorted(obs["date"].unique())
        inputs = resolver.store_series(lat, lon, dates)
        have = [(d, x[0]) for d, x in zip(dates, inputs, strict=True) if x is not None]
        if not have:
            out["moorings"].append(
                {"id": station, "lat": lat, "lon": lon, "n": 0, "note": "no satellite inputs"}
            )
            continue
        frame = pd.DataFrame(
            {"lat": lat, "lon": lon, "date": [d for d, _ in have]}
            | {
                c: [f.get(c, np.nan) for _, f in have]
                for c in ("sst", "sss", "sla", "ug", "vg", "u10", "v10")
            }
        )
        pred, _, _ = model.predict(frame)
        base = clim.predict(frame)
        by_date = {d: i for i, (d, _) in enumerate(have)}
        o = obs[obs["date"].isin(by_date)]
        rows = o["date"].map(by_date).to_numpy()
        z = o["depth"].to_numpy(dtype=float)
        pm = np.array([interp(pred[r], np.array([dz]))[0] for r, dz in zip(rows, z, strict=True)])
        pb = np.array([interp(base[r], np.array([dz]))[0] for r, dz in zip(rows, z, strict=True)])
        t = o["temp"].to_numpy(dtype=float)
        days = o["date"].to_numpy()
        ok = np.isfinite(pm) & np.isfinite(pb)
        em, eb = (pm - t)[ok], (pb - t)[ok]
        zz, dd = z[ok], days[ok]
        head = zz >= 20
        thermo = (zz >= 50) & (zz <= 150)
        if not head.any():
            note = f"only sensors shallower than 20 m in {PERIOD[0][:4]}-{PERIOD[1][:4]}"
            surface = score(em[zz <= 10], dd[zz <= 10], n_boot)
            out["moorings"].append(
                {
                    "id": station,
                    "lat": lat,
                    "lon": lon,
                    "days": len(have),
                    "n": 0,
                    "note": note,
                    "surface_0_10m": surface,
                }
            )
            continue
        m_all, b_all = score(em[head], dd[head], n_boot), score(eb[head], dd[head], n_boot)
        out["moorings"].append(
            {
                "id": station,
                "lat": lat,
                "lon": lon,
                "region": "Bay of Bengal" if lon >= 78 else "Arabian Sea",
                "days": len(have),
                "days_without_inputs": len(dates) - len(have),
                "n": m_all["n"],
                "rmse": m_all["rmse"],
                "headline": m_all,
                "headline_b0": b_all,
                "thermocline": score(em[thermo], dd[thermo], n_boot),
                "thermocline_b0": score(eb[thermo], dd[thermo], n_boot),
                "surface_0_10m": score(em[zz <= 10], dd[zz <= 10], n_boot),
                "skill_headline": (
                    round(1 - (m_all["rmse"] / b_all["rmse"]) ** 2, 4) if b_all["rmse"] else None
                ),
            }
        )
        for key, arr in (("model", em), ("b0", eb), ("depth", zz), ("day", dd)):
            pooled[key].append(arr)
        logger.info(
            "%s: %d days, headline RMSE %s (B0 %s)",
            station,
            len(have),
            m_all["rmse"],
            b_all["rmse"],
        )

    if pooled["model"]:
        em, eb = np.concatenate(pooled["model"]), np.concatenate(pooled["b0"])
        zz, dd = np.concatenate(pooled["depth"]), np.concatenate(pooled["day"])
        for d in sorted(set(zz.tolist())):
            sel = zz == d
            out["by_depth"][str(int(d))] = {
                "model": round(float(np.sqrt(np.mean(em[sel] ** 2))), 4),
                "b0": round(float(np.sqrt(np.mean(eb[sel] ** 2))), 4),
                "n": int(sel.sum()),
            }
        head = zz >= 20
        out["pooled_headline"] = score(em[head], dd[head], n_boot)
        out["pooled_headline_b0"] = score(eb[head], dd[head], n_boot)
    out.update(
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        model_version=ck.get("model_version"),
        source="NOAA PMEL GTMBA daily temperature (pmelTaoDyT), RAMA array, quality 1-3",
        period=list(PERIOD),
        armor3d="Not compared: needs a Copernicus Marine account; it assimilates Argo, so it would be an upper reference only.",
    )
    return out


def markdown(r: dict[str, Any]) -> str:
    lines = [
        "# E8: RAMA mooring comparison (2024-2025)",
        "",
        f"Generated {r['generated_at']} with {r['model_version']}. {r['source']}. Headline = sensors at 20 m and deeper; "
        "95% CIs from 30-day block bootstrap. Moorings were never used for training, tuning or calibration.",
        "",
        "| Mooring | Region | Days | Obs | RMSE >= 20 m | 95% CI | B0 climatology | Skill | Thermocline RMSE | Bias |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for mo in r["moorings"]:
        if not mo.get("n"):
            lines.append(
                f"| {mo['id']} | {mo.get('note', 'no data')} | {mo.get('days', 0)} | 0 | - | - | - | - | - | - |"
            )
            continue
        h, b, t = mo["headline"], mo["headline_b0"], mo["thermocline"]
        lines.append(
            f"| {mo['id']} | {mo['region']} | {mo['days']} | {mo['n']} | {h['rmse']:.3f} | {h['ci'][0]:.3f}-{h['ci'][1]:.3f} | "
            f"{b['rmse']:.3f} | {mo['skill_headline']:+.3f} | {t['rmse'] if t['rmse'] is not None else '-'} | {h['bias']:+.3f} |"
        )
    if "pooled_headline" in r:
        p, b = r["pooled_headline"], r["pooled_headline_b0"]
        lines += [
            "",
            f"Pooled: RMSE {p['rmse']:.3f} °C (95% CI {p['ci'][0]:.3f}-{p['ci'][1]:.3f}) vs climatology {b['rmse']:.3f} °C over {p['n']} observations.",
        ]
    lines += ["", r["armor3d"]]
    return "\n".join(lines) + "\n"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-boot", type=int, default=1000)
    a = ap.parse_args()
    r = run(a.n_boot)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "e8_rama.json").write_text(json.dumps(r, indent=1), encoding="utf-8")
    (OUT / "e8_rama.md").write_text(markdown(r), encoding="utf-8")
    logger.info("wrote docs/results/e8_rama.json and e8_rama.md")


if __name__ == "__main__":
    main()
