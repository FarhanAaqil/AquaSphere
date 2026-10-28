"""
Write the small static JSON files the web frontend reads alongside the API.

    python scripts/build_web_data.py

Outputs (all derived from real artefacts, nothing simulated):
    web/data/build_info.json   git SHA, branch, data manifest hashes, model/data versions
    web/data/floats.json       last known position of every Argo float in the processed archive
    web/data/heldout.json      positions of the profiles in the validation lookup store
    web/data/dates.json        dates present in the local surface store (/meta only gives a range)
    web/data/index.json        names of every results file present, so the UI can show "Pending"
                               for missing ones without probing for 404s
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "web" / "data"

ARCHIVE_CANDIDATES = [
    ROOT / "data" / "processed" / "argo_profiles.parquet",
    ROOT / "data" / "argo_sst_training.csv",
]
HELDOUT_STORE = ROOT / "tests" / "fixtures" / "argo_200.parquet"

# Rough basin split used for the AS / BoB filters (Indian subcontinent tip ~78°E).
BOB_LON = 78.0


def region(lat: float, lon: float) -> str:
    if lat < 5.0:
        return "Equatorial"
    return "Bay of Bengal" if lon >= BOB_LON else "Arabian Sea"


def git(*args: str) -> str | None:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_table(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
    if "float_id" not in df.columns:
        df["float_id"] = df["profile_id"].astype(str).str.split("_").str[0]
    return df


def build_info() -> dict:
    manifest_path = ROOT / "data" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    metrics_path = ROOT / "docs" / "results" / "metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else {}

    artifacts = []
    for key, art in manifest.get("artifacts", {}).items():
        path = ROOT / art["path"]
        actual = sha256(path) if path.exists() else None
        artifacts.append(
            {
                "key": key,
                "path": art["path"],
                "description": art.get("description"),
                "source_url": art.get("source_url"),
                "date_range": art.get("date_range"),
                "row_count": art.get("row_count"),
                "sha256": art.get("sha256"),
                "verified": actual == art.get("sha256") if actual else None,
            }
        )
    if HELDOUT_STORE.exists():
        artifacts.append(
            {
                "key": "heldout_store",
                "path": str(HELDOUT_STORE.relative_to(ROOT)).replace("\\", "/"),
                "description": "Profiles the serving API uses for /validation/profile lookups.",
                "sha256": sha256(HELDOUT_STORE),
                "verified": None,
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_sha": git("rev-parse", "HEAD"),
        "git_branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "git_dirty": bool(git("status", "--porcelain")),
        "metrics_model_version": metrics.get("model_version"),
        "metrics_data_version": metrics.get("data_version"),
        "metrics_split": metrics.get("split"),
        "artifacts": artifacts,
    }


def floats() -> dict:
    src = next((p for p in ARCHIVE_CANDIDATES if p.exists()), None)
    if src is None:
        return {"source": None, "floats": []}
    df = load_table(src).sort_values("date")
    last = df.groupby("float_id").agg(
        lat=("lat", "last"), lon=("lon", "last"), date=("date", "last"), n=("lat", "size")
    )
    rows = [
        {
            "id": str(fid),
            "lat": round(float(r.lat), 3),
            "lon": round(float(r.lon), 3),
            "date": str(r.date)[:10],
            "n_profiles": int(r.n),
            "region": region(float(r.lat), float(r.lon)),
        }
        for fid, r in last.iterrows()
    ]
    return {
        "source": str(src.relative_to(ROOT)).replace("\\", "/"),
        "n_profiles": int(len(df)),
        "floats": rows,
    }


def split_membership() -> dict[str, str]:
    """Float -> partition, reproducing the split used by aquasphere.eval.report."""
    from aquasphere.data.splits import make_float_grouped_split

    csv = ROOT / "data" / "argo_sst_training.csv"
    if not csv.exists():
        return {}
    train, val, test = make_float_grouped_split(
        load_table(csv), train_ratio=0.70, val_ratio=0.15, test_ratio=0.15, seed=42
    )
    out: dict[str, str] = {}
    for name, part in (("train", train), ("val", val), ("test", test)):
        out.update({str(f): name for f in part["float_id"].unique()})
    return out


def heldout() -> dict:
    if not HELDOUT_STORE.exists():
        return {"source": None, "profiles": []}
    df = load_table(HELDOUT_STORE)
    membership = split_membership()
    rows = [
        {
            "profile_id": str(r.profile_id),
            "float_id": str(r.float_id),
            "lat": round(float(r.lat), 3),
            "lon": round(float(r.lon), 3),
            "date": str(r.date)[:10],
            "region": region(float(r.lat), float(r.lon)),
            "split": membership.get(str(r.float_id), "unknown"),
        }
        for r in df.itertuples()
    ]
    return {
        "source": str(HELDOUT_STORE.relative_to(ROOT)).replace("\\", "/"),
        "split_rule": "float-grouped 70/15/15, seed 42 (same as aquasphere.eval.report)",
        "profiles": rows,
    }


def store_dates() -> dict:
    """Read the date index straight from the Zarr v3 group metadata (no zarr import needed)."""
    meta = ROOT / "data" / "store" / "surface.zarr" / "zarr.json"
    if not meta.exists():
        return {"source": None, "dates": []}
    attrs = json.loads(meta.read_text(encoding="utf-8")).get("attributes", {})
    return {"source": "data/store/surface.zarr", "dates": sorted(attrs.get("dates", []))}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, payload in (
        ("build_info.json", build_info()),
        ("floats.json", floats()),
        ("heldout.json", heldout()),
        ("dates.json", store_dates()),
    ):
        (OUT / name).write_text(json.dumps(payload, indent=1), encoding="utf-8")
        print(f"wrote web/data/{name}")
    present = sorted(p.stem for p in OUT.glob("*.json") if p.name != "index.json")
    (OUT / "index.json").write_text(json.dumps({"files": present}, indent=1), encoding="utf-8")
    print(f"wrote web/data/index.json ({len(present)} files)")


if __name__ == "__main__":
    main()
