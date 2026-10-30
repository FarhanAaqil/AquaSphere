"""
Regression gate (roadmap Phase 6): the served checkpoint must still reproduce the validation
numbers recorded in docs/results/phase4.json.

    python scripts/regression_check.py          # exit 1 if anything drifted

Re-scores checkpoints/tier_a_v2/model.pt on the 2023 validation partition (never the test
period) and compares thermocline RMSE, skill and Mondrian coverage with the frozen values.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aquasphere.data.collocate_nio import OUTPUT as TABLE  # noqa: E402
from aquasphere.eval import metrics_v2 as m  # noqa: E402
from aquasphere.eval.baselines_v2 import B0Climatology, targets  # noqa: E402
from aquasphere.eval.protocol import assign, partition  # noqa: E402
from aquasphere.train.v2 import ProfileModel  # noqa: E402

CHECKPOINT = ROOT / "checkpoints" / "tier_a_v2" / "model.pt"
FROZEN = ROOT / "docs" / "results" / "phase4.json"
TOL_RMSE = 1e-3  # °C
TOL_SKILL = 1e-3


def main() -> int:
    if not CHECKPOINT.exists():
        print(f"skip: {CHECKPOINT.relative_to(ROOT)} not present (fresh clone)")
        return 0
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))["e7"]["delayed"]
    df = assign(pd.read_parquet(ROOT / TABLE))
    train, val = partition(df, "train"), partition(df, "val")
    model = ProfileModel.from_state(torch.load(CHECKPOINT, map_location="cpu", weights_only=True))
    pred, _, _ = model.predict(val)
    y, mask = targets(val)
    err = np.where(mask, pred - y, 0.0)
    b0 = np.where(mask, B0Climatology().fit(train).predict(val) - y, 0.0)
    got = {
        "thermocline_rmse": m.rmse(err, mask, m.THERMOCLINE),
        "skill_thermocline": m.skill(err, b0, mask, m.THERMOCLINE),
    }
    failures = []
    for key, tol in (("thermocline_rmse", TOL_RMSE), ("skill_thermocline", TOL_SKILL)):
        diff = abs(got[key] - frozen[key])
        status = "ok" if diff <= tol else "DRIFT"
        print(f"{key}: frozen {frozen[key]:.4f}, now {got[key]:.4f} ({status})")
        if diff > tol:
            failures.append(key)
    if failures:
        print("Regression: the served checkpoint no longer reproduces phase4.json")
        return 1
    print("Regression gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
