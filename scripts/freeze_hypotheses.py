"""
Write docs/hypotheses.yaml: the confirmatory hypotheses, frozen before any tuned model touches the
2024-2025 test period (blueprint §5, §11). Then commit it and tag the commit:

    python scripts/freeze_hypotheses.py
    git add docs/hypotheses.yaml && git commit -m "..." && git tag -a hypotheses-v1-<date> -m "..."

Thresholds are the blueprint v1.1 values word for word. The pilot block is generated from the
Phase 3 results files (train/validation only) and records what was known at freezing time; it
was NOT used to choose any threshold. Changes after the tag must be logged as deviations.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "docs" / "results"
OUT = ROOT / "docs" / "hypotheses.yaml"

HYPOTHESES: dict[str, dict[str, Any]] = {
    "H1a": {
        "question": "RQ1: how much does each surface sensor add to subsurface skill?",
        "claim": "Adding SLA to SST lowers 50-150 m RMSE by at least 15%.",
        "comparison": "Same model trained on SST + SLA vs SST only (E3), test period.",
        "metric": "thermocline_rmse_50_150m",
        "threshold": {"relative_reduction_min": 0.15},
        "falsified_if": "The 95% block-bootstrap CI of the RMSE difference includes zero, or the reduction is below 15%.",
        "experiment": "E3",
    },
    "H1b": {
        "question": "RQ1: how much skill is kept in real-time (nowcast) mode?",
        "claim": "Nowcast mode (SST + SLA) keeps at least 85% of the full-mode thermocline skill score.",
        "comparison": "Nowcast vs delayed (all sensors) through availability masks (E7), test period.",
        "metric": "skill_ratio_nowcast_over_delayed_thermocline",
        "threshold": {"ratio_min": 0.85},
        "falsified_if": "The ratio falls below 0.85.",
        "experiment": "E7",
    },
    "H2": {
        "question": "RQ2: does self-supervised pre-training help, especially with few labels?",
        "claim": "Pre-trained encoders reduce test thermocline RMSE by at least 5% at full labels and at least 10% with 10% of labels, relative to training from scratch with the same architecture, data and tuning budget.",
        "comparison": "Scratch vs pre-trained at 10/25/50/100% of labels (E5), test period.",
        "metric": "thermocline_rmse_50_150m",
        "threshold": {
            "relative_reduction_full_labels_min": 0.05,
            "relative_reduction_10pct_labels_min": 0.10,
        },
        "falsified_if": "Either reduction is below its threshold. A negative result is reported and Tier B remains the shipped model.",
        "experiment": "E5",
    },
    "H3": {
        "question": "RQ3: are the uncertainties calibrated, and can out-of-domain cases be flagged?",
        "claim": "Nominal 90% intervals reach 87-93% empirical coverage on the test period overall and within 5 points in each region and monsoon season; errors inside the applicability domain are lower than outside it.",
        "comparison": "Conformal intervals of the shipped model (E6), test period.",
        "metric": "coverage_90",
        "threshold": {"overall_band": [0.87, 0.93], "per_stratum_band": [0.85, 0.95]},
        "falsified_if": "Coverage falls outside the stated band.",
        "strata_rule": "Per-stratum coverage is confirmatory only for strata the Phase 3 power analysis marked confirmatory; others are reported descriptively.",
        "experiment": "E6",
    },
    "H4": {
        "question": "RQ4: how optimistic is a random profile-level split?",
        "claim": "The random-split RMSE of the current baseline is at least 20% lower than its blocked-split RMSE at 50-150 m.",
        "comparison": "B3 (v1 network) under a random profile split vs the time-blocked, float-grouped protocol split; rerun in the final evaluation so the test period decides.",
        "metric": "thermocline_rmse_50_150m",
        "threshold": {"relative_gap_min": 0.20},
        "falsified_if": "The gap is below 20%. Reported either way: this is a methodological contribution regardless of outcome.",
        "experiment": "E1",
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pilot() -> dict[str, Any]:
    m = json.loads((RESULTS / "metrics_v2.json").read_text(encoding="utf-8"))
    e1 = json.loads((RESULTS / "e1_leakage_v2.json").read_text(encoding="utf-8"))
    b4 = m["e2"]["B4"].get("probabilistic", {})
    return {
        "note": "Measured on train (2015-2022) and validation (2023) only, before freezing. Exploratory context; no threshold above was changed because of it.",
        "split": m["split"],
        "e2_thermocline_rmse_validation": {k: v["thermocline_rmse"] for k, v in m["e2"].items()},
        "e2_skill_vs_b0_validation": {k: v["skill_thermocline"] for k, v in m["e2"].items()},
        "b4_coverage_90_validation": b4.get("coverage_90"),
        "e1_random_vs_blocked_pct_2015_2023": {
            k: v["random_vs_blocked_pct"] for k, v in e1["models"].items()
        },
        "power": [
            {
                "stratum": f"{s['region']} / {s['season']}",
                "floats": s["floats"],
                "mde_c": s.get("mde_thermocline_c"),
                "claim_effect_c": s.get("claim_effect_c"),
                "status": s["status"],
            }
            for s in m["strata"]
        ],
        "evidence_sha256": {
            "docs/results/metrics_v2.json": sha256(RESULTS / "metrics_v2.json"),
            "docs/results/e1_leakage_v2.json": sha256(RESULTS / "e1_leakage_v2.json"),
        },
    }


def main() -> None:
    doc = {
        "title": "AquaSphere confirmatory hypotheses",
        "version": 1,
        "status": "frozen",
        "frozen_at": datetime.now(UTC).date().isoformat(),
        "source": "Blueprint v1.1 §5 (thresholds verbatim) and §11 (protocol)",
        "rules": [
            "Thresholds are the blueprint v1.1 values, unchanged after the pilot below.",
            "Confirmatory tests run once, on the 2024-01-01 to 2025-12-31 test period, in the final evaluation (roadmap Phase 6).",
            "Any later change is a deviation and must be logged in docs/hypotheses_deviations.md with its reason.",
            "Every comparison not listed under confirmatory is exploratory.",
        ],
        "protocol": {
            "periods": {
                "train": ["2015-01-01", "2022-12-31"],
                "validation": ["2023-01-01", "2023-12-31"],
                "test": ["2024-01-01", "2025-12-31"],
            },
            "float_rule": "Each float belongs to the first period it appears in; its later profiles are excluded.",
            "primary_metric": "RMSE at 50-150 m (thermocline); headline depths 20 m and below, 0-10 m reported separately (OISST ingests Argo).",
            "statistics": "Block bootstrap over floats (2000 resamples), 3 seeds per configuration (mean and std).",
            "alpha": 0.05,
            "multiple_testing": {"method": "holm", "family": list(HYPOTHESES)},
        },
        "confirmatory": HYPOTHESES,
        "pilot": pilot(),
    }
    OUT.write_text(
        "# Frozen before any tuned model touches the test period. Generated by scripts/freeze_hypotheses.py.\n"
        + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
