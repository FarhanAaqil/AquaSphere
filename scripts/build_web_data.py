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
from contextlib import chdir
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from aquasphere.serve.membership import TrainingMembership

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "web" / "data"
CHECKPOINT = ROOT / "checkpoints" / "tier_a" / "model_a.pt"

V2_TABLE = ROOT / "data" / "processed" / "argo_nio_collocated.parquet"
V2_CHECKPOINT = ROOT / "checkpoints" / "tier_a_v2" / "model.pt"
ARCHIVE_CANDIDATES = [
    V2_TABLE,
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
    """Same digest the manifest records (files, or directory trees such as Zarr stores)."""
    from aquasphere.data.manifest import compute_file_sha256

    return compute_file_sha256(path)


def load_table(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
    if "float_id" not in df.columns:
        df["float_id"] = df["profile_id"].astype(str).str.split("_").str[0]
    return df


def build_info() -> dict:
    manifest_path = ROOT / "data" / "manifest.json"
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    )
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
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
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
        "n_profiles": len(df),
        "floats": rows,
    }


def served_membership() -> TrainingMembership:
    """Training membership of the served model, exactly as the API computes it."""
    from aquasphere.serve.membership import ARGO_TABLES, TrainingMembership

    checkpoint = None
    path = V2_CHECKPOINT if V2_CHECKPOINT.exists() else CHECKPOINT
    if path.exists():
        try:
            import torch

            checkpoint = torch.load(path, map_location="cpu", weights_only=False)
        except Exception as e:  # unreadable checkpoint: fall back to reconstructing the split
            print(f"warning: could not read {path}: {e}")
    tables = (V2_TABLE.relative_to(ROOT), *ARGO_TABLES) if path == V2_CHECKPOINT else ARGO_TABLES
    with chdir(ROOT):
        return TrainingMembership.resolve(checkpoint, tables=tables)


def heldout() -> dict:
    # With the protocol v2 model served, lookups come from the 2023 validation year
    v2 = V2_CHECKPOINT.exists() and V2_TABLE.exists()
    source = V2_TABLE if v2 else HELDOUT_STORE
    if not source.exists():
        return {"source": None, "profiles": []}
    if v2:
        from aquasphere.eval.protocol import assign

        df = assign(pd.read_parquet(V2_TABLE))
        df = df[df["partition"] == "val"]
    else:
        df = load_table(HELDOUT_STORE)
    membership = served_membership()

    def split_of(float_id: str) -> str:
        inside = membership.float_in_training(float_id)
        return "unknown" if inside is None else "train" if inside else "held_out"

    rows = [
        {
            "profile_id": str(r.profile_id),
            "float_id": str(r.float_id),
            "lat": round(float(r.lat), 3),
            "lon": round(float(r.lon), 3),
            "date": str(r.date)[:10],
            "region": region(float(r.lat), float(r.lon)),
            "split": split_of(str(r.float_id)),
        }
        for r in df.itertuples()
    ]
    return {
        "source": str(source.relative_to(ROOT)).replace("\\", "/")
        + (" (validation 2023)" if v2 else ""),
        "split_rule": f"served model's training split ({membership.source})",
        "profiles": rows,
    }


def store_dates() -> dict:
    """Read the date index straight from the Zarr v3 group metadata (no zarr import needed)."""
    with chdir(ROOT):
        from aquasphere.serve.resolver import default_store

        store = default_store()
    meta = ROOT / store / "zarr.json"
    if not meta.exists():
        return {"source": None, "dates": []}
    attrs = json.loads(meta.read_text(encoding="utf-8")).get("attributes", {})
    return {"source": store.as_posix(), "dates": sorted(attrs.get("dates", []))}


def input_audit() -> dict:
    """Prove which tables carry synthetic satellite columns (see aquasphere.data.audit)."""
    from aquasphere.data.audit import synthetic_channel_audit

    used_by = {
        "tests/fixtures/argo_200.parquet": "E3/E7 ablation runs (ablation.json) and /validation lookups",
        "data/processed/argo_profiles.parquet": "training data of the served model",
        "data/argo_sst_training.csv": "evaluation ladder (metrics.json) and E1 leakage runs",
    }
    with chdir(ROOT):
        tables = [
            {**synthetic_channel_audit(t, "data/store/surface.zarr"), "used_by": use}
            for t, use in used_by.items()
        ]
    return {"generated_at": datetime.now(UTC).isoformat(timespec="seconds"), "tables": tables}


TEXT_SUFFIXES = {".js", ".css", ".html", ".json", ".svg", ".webmanifest", ".txt", ".md"}


def precache() -> dict[str, Any]:
    """App shell for the service worker (web/sw.js): every static file, versioned by content."""
    web = OUT.parent
    files = sorted(
        p.relative_to(web).as_posix()
        for p in web.rglob("*")
        if p.is_file() and p.name not in ("sw.js", "precache.json") and not p.name.startswith(".")
    )
    digest = hashlib.sha256()
    for f in files:
        digest.update(f.encode())
        body = (web / f).read_bytes()
        if Path(f).suffix in TEXT_SUFFIXES:  # Windows and Linux checkouts must agree
            body = body.replace(b"\r\n", b"\n")
        digest.update(hashlib.sha256(body).digest())
    return {
        "version": digest.hexdigest()[:16],
        "files": ["index.html", *[f for f in files if f != "index.html"]],
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, payload in (
        ("build_info.json", build_info()),
        ("floats.json", floats()),
        ("heldout.json", heldout()),
        ("dates.json", store_dates()),
        ("input_audit.json", input_audit()),
    ):
        (OUT / name).write_text(json.dumps(payload, indent=1), encoding="utf-8")
        print(f"wrote web/data/{name}")
    (OUT / "precache.json").write_text(json.dumps(precache(), indent=1), encoding="utf-8")
    print("wrote web/data/precache.json")
    present = sorted(
        p.stem for p in OUT.glob("*.json") if p.name not in ("index.json", "precache.json")
    )
    (OUT / "index.json").write_text(json.dumps({"files": present}, indent=1), encoding="utf-8")
    print(f"wrote web/data/index.json ({len(present)} files)")


if __name__ == "__main__":
    main()
