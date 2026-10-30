"""
Run `make reproduce` without make (Windows, minimal shells): the steps are read from the Makefile
itself, with every `$(MAKE) target` expanded to that target's recipe, so this can never drift
from what `make reproduce` does.

    python scripts/reproduce.py            # run every step, stop at the first failure
    python scripts/reproduce.py --list     # print the commands only
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def targets(makefile: Path) -> dict[str, tuple[list[str], list[str]]]:
    """target -> (prerequisites, recipe lines)."""
    out: dict[str, tuple[list[str], list[str]]] = {}
    current = None
    for line in makefile.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Za-z0-9_.-]+):(?!=)\s*(.*)$", line)
        if m and not line.startswith("\t"):
            current = m.group(1)
            out[current] = (m.group(2).split(), [])
        elif line.startswith("\t") and current:
            out[current][1].append(line[1:])
        elif not line.strip():
            current = None
    return out


def expand(name: str, table: dict[str, tuple[list[str], list[str]]]) -> list[str]:
    prereqs, recipe = table[name]
    cmds: list[str] = []
    for p in prereqs:
        if p in table:
            cmds += expand(p, table)
    for line in recipe:
        m = re.match(r"^\$\(MAKE\)\s+(\S+)$", line.strip())
        if m:
            cmds += expand(m.group(1), table)
        elif line.strip().startswith("@echo"):
            continue
        else:
            cmds.append(line.strip())
    return cmds


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--target", default="reproduce")
    a = ap.parse_args()
    cmds = expand(a.target, targets(ROOT / "Makefile"))
    for i, cmd in enumerate(cmds, 1):
        print(f"[{i}/{len(cmds)}] {cmd}", flush=True)
        if a.list:
            continue
        t0 = time.time()
        rc = subprocess.run(cmd, shell=True, cwd=ROOT).returncode
        print(f"      exit {rc} after {time.time() - t0:.0f}s", flush=True)
        if rc != 0:
            return rc
    return 0


if __name__ == "__main__":
    sys.exit(main())
