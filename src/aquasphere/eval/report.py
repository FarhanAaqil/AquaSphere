"""
Evaluation reporting and honest baseline comparison runner for AquaSphere (SIH 26066).

Executes:
1. Leak-free float-grouped train / val / test partitioning.
2. Baseline ladder evaluation (Climatology, Ridge, GBDT, and v1 OceanEmbedNet).
3. Metric calculations: Overall RMSE, Thermocline (50-150m) RMSE, Skill Scores,
   MLD error, D20 error, and block-bootstrap 95% CIs.
4. Generates docs/results/metrics.json, docs/results/baseline_table.md, and
   updates docs/MODEL_CARD.md between <!-- METRICS:START --> markers.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aquasphere.constants import DEPTH_COLS
from aquasphere.data.splits import assert_no_leakage, make_float_grouped_split
from aquasphere.eval.baselines import (
    ClimatologyBaseline,
    GradientBoostedBaseline,
    RidgeAnomalyBaseline,
    V1OceanEmbedNetBaseline,
    extract_targets,
)
from aquasphere.eval.metrics import (
    block_bootstrap_ci,
    compute_depth_group_metrics,
    compute_errors,
    compute_oceanographic_metrics,
    compute_skill_score,
)

logger = logging.getLogger(__name__)


def evaluate_model(
    name: str,
    model: Any,
    train_df: pd.DataFrame,
    eval_df: pd.DataFrame,
    clim_preds: np.ndarray,
) -> dict[str, Any]:
    """Fit model on train_df (if needed), predict on eval_df, and compute metrics."""
    logger.info("Evaluating baseline: %s ...", name)
    model.fit(train_df)
    preds = model.predict(eval_df)
    y_true = extract_targets(eval_df)

    errors = compute_errors(y_true, preds)
    skills = compute_skill_score(y_true, preds, clim_preds)
    ocean = compute_oceanographic_metrics(y_true, preds)
    grouped = compute_depth_group_metrics(y_true, preds)

    # Thermocline group is 50-150 m
    thermo_group = next(
        (g for g in grouped if "50" in g["depth_group"] and "150" in g["depth_group"]),
        None,
    )
    thermo_rmse = thermo_group["rmse"] if thermo_group else float("nan")

    # Block bootstrap 95% CI on thermocline RMSE
    thermo_ci = block_bootstrap_ci(
        eval_df,
        y_true_cols=DEPTH_COLS,
        y_pred=preds,
        group_col="float_id",
        depth_slice=[50, 75, 100, 125, 150],
        n_boot=300,
        ci=0.95,
        seed=42,
    )

    return {
        "name": name,
        "overall_rmse": errors["overall"]["rmse"],
        "overall_mae": errors["overall"]["mae"],
        "overall_bias": errors["overall"]["bias"],
        "thermocline_rmse": thermo_rmse,
        "thermocline_ci_95": [thermo_ci["ci_lower"], thermo_ci["ci_upper"]],
        "skill_score_overall": skills["overall_skill_score"],
        "mld_rmse": ocean["mld"]["rmse"],
        "d20_rmse": ocean["d20"]["rmse"],
        "ohc300_rmse": ocean["ohc300"]["rmse"],
        "grouped": grouped,
        "per_depth": errors["per_depth"],
        "predictions": preds,
    }


def generate_baseline_markdown(results: list[dict[str, Any]], n_val: int, n_floats: int) -> str:
    """Format evaluation results into a clean markdown table."""
    lines = [
        "### Honest Baseline Ladder (Float-Grouped Hold-Out Evaluation)",
        "",
        f"> **Evaluation Set:** {n_val} held-out profiles across {n_floats} unique Argo floats.",
        "> **Hold-Out Rule:** Zero float ID overlap with training (leak-free guaranteed).",
        "",
        "| Model | Overall RMSE (°C) | Thermocline RMSE (50-150m) | 95% CI (Thermo) | Skill Score (SS) | D20 Error (m) | MLD Error (m) |",
        "|---|---|---|---|---|---|---|",
    ]

    for r in results:
        ci_str = f"[{r['thermocline_ci_95'][0]:.2f}, {r['thermocline_ci_95'][1]:.2f}]"
        ss_str = f"{r['skill_score_overall']:+.3f}"
        d20_str = f"{r['d20_rmse']:.1f}" if not np.isnan(r["d20_rmse"]) else "N/A"
        mld_str = f"{r['mld_rmse']:.1f}" if not np.isnan(r["mld_rmse"]) else "N/A"
        lines.append(
            f"| **{r['name']}** | {r['overall_rmse']:.3f} | {r['thermocline_rmse']:.3f} | {ci_str} | {ss_str} | {d20_str} | {mld_str} |"
        )

    lines.extend(
        [
            "",
            "*Note: v1 OceanEmbedNet numbers reflect honest float-grouped hold-out splits (unlike the random split reported in v1 prototypes).*",
        ]
    )
    return "\n".join(lines)


def update_markdown_file(file_path: Path, new_content: str, marker: str = "METRICS") -> bool:
    """Update file section between <!-- {marker}:START --> and <!-- {marker}:END -->."""
    if not file_path.exists():
        return False

    content = file_path.read_text(encoding="utf-8")
    pattern = rf"(<!-- {marker}:START -->)(.*?)(<!-- {marker}:END -->)"
    replacement = rf"\1\n{new_content}\n\3"

    new_full, count = re.subn(pattern, replacement, content, flags=re.DOTALL)
    if count > 0:
        file_path.write_text(new_full, encoding="utf-8")
        return True
    return False


def run_evaluation(
    csv_path: str | Path = "data/argo_sst_training.csv",
    output_json: str | Path = "docs/results/metrics.json",
    output_md: str | Path = "docs/results/baseline_table.md",
    seed: int = 42,
    split: str = "val",
) -> dict[str, Any]:
    """Execute complete evaluation protocol and output artifacts."""
    csv_file = Path(csv_path)
    if not csv_file.exists():
        raise FileNotFoundError(f"Training data not found at {csv_file}")

    logger.info("Loading Argo profiles from %s ...", csv_file)
    df = pd.read_csv(csv_file)

    # 1. Create leak-free float-grouped split
    train_df, val_df, test_df = make_float_grouped_split(
        df, train_ratio=0.70, val_ratio=0.15, test_ratio=0.15, seed=seed
    )
    assert_no_leakage(train_df, val_df, test_df, group_col="float_id")

    eval_df = test_df if split == "test" else val_df
    n_eval_floats = eval_df["float_id"].nunique()
    logger.info(
        "Evaluation set (%s): %d profiles from %d floats", split, len(eval_df), n_eval_floats
    )

    # 2. Evaluate Climatology first (required for Skill Score)
    clim = ClimatologyBaseline()
    clim.fit(train_df)
    clim_eval_preds = clim.predict(eval_df)

    # 3. Evaluate Ladder
    models: list[tuple[str, Any]] = [
        ("Climatology", clim),
        ("Climatology + Ridge", RidgeAnomalyBaseline(alpha=1.0)),
        ("Gradient Boosted Trees (HistGBDT)", GradientBoostedBaseline(max_iter=100, max_depth=6)),
        ("v1 OceanEmbedNet (Re-evaluated)", V1OceanEmbedNetBaseline()),
    ]

    eval_results: list[dict[str, Any]] = []
    for name, mdl in models:
        res = evaluate_model(name, mdl, train_df, eval_df, clim_eval_preds)
        eval_results.append(res)

    # 4. Generate JSON artifact
    json_payload: dict[str, Any] = {
        "_note": "This file is auto-generated by aquasphere.eval.report. Do not edit by hand.",
        "_generated_at": datetime.now(UTC).isoformat(),
        "model_version": "v0.2-baseline",
        "data_version": "argo-2025-snapshot",
        "split": f"{split}_float_grouped",
        "n_train_profiles": len(train_df),
        "n_eval_profiles": len(eval_df),
        "n_eval_floats": n_eval_floats,
        "baselines": {
            r["name"]: {
                "overall_rmse": r["overall_rmse"],
                "overall_mae": r["overall_mae"],
                "overall_bias": r["overall_bias"],
                "thermocline_rmse": r["thermocline_rmse"],
                "thermocline_ci_95": r["thermocline_ci_95"],
                "skill_score_overall": r["skill_score_overall"],
                "mld_rmse": r["mld_rmse"],
                "d20_rmse": r["d20_rmse"],
                "ohc300_rmse": r["ohc300_rmse"],
                "grouped": r["grouped"],
            }
            for r in eval_results
        },
    }

    out_json = Path(output_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(json_payload, indent=2), encoding="utf-8")
    logger.info("Wrote metrics payload to %s", out_json)

    # 5. Generate Markdown Table artifact
    md_content = generate_baseline_markdown(eval_results, len(eval_df), n_eval_floats)
    out_md = Path(output_md)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(md_content, encoding="utf-8")
    logger.info("Wrote baseline table to %s", out_md)

    # 6. Update markdown documents with METRICS table
    for md_doc in [Path("docs/MODEL_CARD.md"), Path("README.md"), Path("walkthrough.md")]:
        if update_markdown_file(md_doc, md_content, marker="METRICS"):
            logger.info("Updated METRICS section in %s", md_doc)

    # 7. Update markdown documents with ABLATION table if present
    ablation_file = Path("docs/results/ablation_table.md")
    if ablation_file.exists():
        ablation_md = ablation_file.read_text(encoding="utf-8")
        for md_doc in [Path("docs/MODEL_CARD.md"), Path("README.md")]:
            if update_markdown_file(md_doc, ablation_md, marker="ABLATION"):
                logger.info("Updated ABLATION section in %s", md_doc)

    return json_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="AquaSphere Evaluation and Baseline Reporter")
    parser.add_argument("--data", default="data/argo_sst_training.csv", help="Path to Argo CSV")
    parser.add_argument("--json", default="docs/results/metrics.json", help="Output JSON path")
    parser.add_argument("--md", default="docs/results/baseline_table.md", help="Output MD path")
    parser.add_argument(
        "--split", choices=["val", "test"], default="val", help="Partition to evaluate on"
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed for splitting")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    run_evaluation(
        csv_path=args.data,
        output_json=args.json,
        output_md=args.md,
        seed=args.seed,
        split=args.split,
    )

    print("\n" + "=" * 78)
    print("  AQUASPHERE EVALUATION FRAMEWORK — HONEST BASELINE LADDER")
    print("=" * 78)
    table_md = Path(args.md).read_text(encoding="utf-8")
    print(table_md)
    print("=" * 78 + "\n")


if __name__ == "__main__":
    main()
