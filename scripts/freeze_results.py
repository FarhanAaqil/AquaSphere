"""
Freeze the results files (roadmap Phase 6): record the SHA-256 of every file in docs/results so
CI notices if a number changes without being re-frozen on purpose.

    python scripts/freeze_results.py    # writes docs/results/frozen_results.json

Hashes are taken over newline-normalised bytes so Windows and Linux checkouts agree.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "docs" / "results"
OUT = RESULTS / "frozen_results.json"
SKIP = {"frozen_results.json"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def current() -> dict[str, str]:
    return {
        p.name: digest(p)
        for p in sorted(RESULTS.iterdir())
        if p.is_file() and p.name not in SKIP and p.suffix in (".json", ".md", ".log")
    }


def main() -> None:
    OUT.write_text(
        json.dumps(
            {"frozen_at": datetime.now(UTC).isoformat(timespec="seconds"), "sha256": current()},
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
