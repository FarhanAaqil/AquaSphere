"""
Package release assets (roadmap Phase 6): model weights and data stores as archives with a
SHA-256 manifest, ready to attach to a GitHub release. Raw data is never committed to git.

    python scripts/package_release.py            # writes dist/release/
    python scripts/package_release.py --verify   # re-checks dist/release/SHA256SUMS

Assets:
    aquasphere-model-tier_a_v2.tar.gz    checkpoints/tier_a_v2 (weights, ONNX export)
    aquasphere-demo-store.tar.gz         data/store/surface.zarr (13-date synthetic demo store)
    aquasphere-nio-store-2015-2025.tar.gz data/store/surface_nio.zarr (real open-data store)
    aquasphere-argo-nio.tar.gz           data/processed/argo_nio_*.parquet
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist" / "release"
ASSETS = {
    "aquasphere-model-tier_a_v2.tar.gz": ["checkpoints/tier_a_v2"],
    "aquasphere-demo-store.tar.gz": ["data/store/surface.zarr"],
    "aquasphere-nio-store-2015-2025.tar.gz": ["data/store/surface_nio.zarr"],
    "aquasphere-argo-nio.tar.gz": [
        "data/processed/argo_nio_2015_2025.parquet",
        "data/processed/argo_nio_collocated.parquet",
    ],
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build() -> None:
    DIST.mkdir(parents=True, exist_ok=True)
    sums, manifest = [], {}
    for name, parts in ASSETS.items():
        present = [p for p in parts if (ROOT / p).exists()]
        if not present:
            print(f"skip {name}: nothing to package")
            continue
        out = DIST / name
        with tarfile.open(out, "w:gz") as tar:
            for p in present:
                tar.add(ROOT / p, arcname=p)
        digest = sha256(out)
        sums.append(f"{digest}  {name}")
        manifest[name] = {"sha256": digest, "bytes": out.stat().st_size, "contains": present}
        print(f"{name}: {out.stat().st_size / 1e6:.1f} MB")
    (DIST / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    (DIST / "release.json").write_text(
        json.dumps(
            {"built_at": datetime.now(UTC).isoformat(timespec="seconds"), "assets": manifest},
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"wrote {DIST.relative_to(ROOT)}/SHA256SUMS and release.json")


def verify() -> int:
    bad = 0
    for line in (DIST / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split(maxsplit=1)
        ok = sha256(DIST / name) == digest
        bad += not ok
        print(f"{'ok ' if ok else 'BAD'} {name}")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    if a.verify:
        return verify()
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
