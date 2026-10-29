"""
Checkpoint provenance (blueprint §8.1: checkpoints carry config + git SHA + data hash).

Training records where a model came from; serving verifies that record before it reports ready.
"""

from __future__ import annotations

import hashlib
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Status values reported by /ready
VERIFIED = "verified"  # data file present and its hash matches the checkpoint
NOT_RECORDED = "not_recorded"  # checkpoint predates provenance; nothing to check
DATA_UNAVAILABLE = "data_unavailable"  # recorded, but the training data file is not on this machine
MISMATCH = "mismatch"  # recorded data hash differs from the file on disk: refuse to serve


def file_sha256(path: Path | str) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_info(cwd: Path | str = ".") -> dict[str, Any]:
    """Current commit and whether the tree has uncommitted changes; None values if git is absent."""

    def run(*args: str) -> str | None:
        try:
            return subprocess.check_output(
                ["git", *args], cwd=cwd, text=True, stderr=subprocess.DEVNULL
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            return None

    sha = run("rev-parse", "HEAD")
    status = run("status", "--porcelain")
    return {"git_sha": sha, "git_dirty": None if status is None else bool(status)}


def build_provenance(data_path: Path | str, seed: int, cwd: Path | str = ".") -> dict[str, Any]:
    """Provenance block stored in a checkpoint at training time."""
    data_path = Path(data_path)
    return {
        **git_info(cwd),
        "data_path": data_path.as_posix(),
        "data_sha256": file_sha256(data_path),
        "seed": seed,
        "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def verify_provenance(provenance: dict[str, Any] | None) -> tuple[str, str]:
    """Check a checkpoint's provenance against the data on disk. Returns (status, detail)."""
    if not provenance or not provenance.get("data_sha256"):
        return NOT_RECORDED, "Checkpoint has no provenance block (trained before it was recorded)."
    path = Path(provenance.get("data_path", ""))
    if not path.is_file():
        return DATA_UNAVAILABLE, f"Training data {path.as_posix()} is not on this machine."
    actual = file_sha256(path)
    if actual != provenance["data_sha256"]:
        return (
            MISMATCH,
            f"{path.as_posix()} has changed since training "
            f"(recorded {provenance['data_sha256'][:12]}, found {actual[:12]}).",
        )
    return VERIFIED, f"{path.as_posix()} matches the hash recorded at training time."
