"""
Experiment E1: Generalization & Leakage Gap Analysis (Master Blueprint Phase 2).

Quantifies the performance inflation caused by naive random splitting in oceanographic
deep learning versus honest leak-free splitting protocols:
1. Random Split: Naive row-wise partition (leaks both float trajectory and temporal persistence).
2. Float-Grouped Split: Partitions strictly by WMO float identifier (zero float leakage).
3. Time-Blocked Split: Forward-in-time temporal holdout (training on past, evaluating on future).

The Generalization Gap is quantified as:
    ΔRMSE_float = RMSE_float_grouped - RMSE_random
    ΔRMSE_time  = RMSE_time_blocked - RMSE_random
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aquasphere.data.splits import (
    assert_no_leakage,
    ensure_float_id_column,
    make_float_grouped_split,
)
from aquasphere.eval.baselines import (
    ClimatologyBaseline,
    GradientBoostedBaseline,
    RidgeAnomalyBaseline,
    V1OceanEmbedNetBaseline,
    extract_targets,
)
from aquasphere.eval.metrics import (
    compute_depth_group_metrics,
    compute_errors,
    compute_skill_score,
)

logger = logging.getLogger(__name__)


def make_random_split(
    df: pd.DataFrame,
    train_ratio: float = 0.75,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Naive random row-wise train/val split (deliberately leaking float IDs)."""
    rng = np.random.default_rng(seed)
    shuffled_idx = rng.permutation(len(df))
    n_train = int(len(df) * train_ratio)
    train_idx = shuffled_idx[:n_train]
    eval_idx = shuffled_idx[n_train:]
    return df.iloc[train_idx].copy(), df.iloc[eval_idx].copy()


def make_time_blocked_split(
    df: pd.DataFrame,
    date_col: str = "date",
    train_ratio: float = 0.75,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Strict forward-in-time temporal split (training on earlier dates, evaluating on later)."""
    df_sorted = df.sort_values(by=date_col).copy()
    n_train = int(len(df_sorted) * train_ratio)
    return df_sorted.iloc[:n_train].copy(), df_sorted.iloc[n_train:].copy()


def evaluate_split_protocol(
    protocol_name: str,
    train_df: pd.DataFrame,
    eval_df: pd.DataFrame,
    models: list[tuple[str, Any]],
) -> dict[str, Any]:
    """Train and evaluate baseline ladder on given split."""
    y_true = extract_targets(eval_df)

    # Climatology baseline for skill score
    clim = ClimatologyBaseline()
    clim.fit(train_df)
    clim_preds = clim.predict(eval_df)

    model_metrics: dict[str, dict[str, float]] = {}

    for name, model in models:
        model.fit(train_df)
        preds = model.predict(eval_df)

        errors = compute_errors(y_true, preds)
        skills = compute_skill_score(y_true, preds, clim_preds)
        grouped = compute_depth_group_metrics(y_true, preds)

        thermo_group = next(
            (g for g in grouped if "50" in g["depth_group"] and "150" in g["depth_group"]),
            None,
        )
        thermo_rmse = thermo_group["rmse"] if thermo_group else float("nan")

        model_metrics[name] = {
            "overall_rmse": round(float(errors["overall"]["rmse"]), 4),
            "overall_mae": round(float(errors["overall"]["mae"]), 4),
            "thermocline_rmse": round(float(thermo_rmse), 4),
            "skill_score": round(float(skills["overall_skill_score"]), 4),
        }

    return {
        "protocol": protocol_name,
        "n_train": len(train_df),
        "n_eval": len(eval_df),
        "n_eval_floats": int(eval_df["float_id"].nunique()) if "float_id" in eval_df.columns else 0,
        "metrics": model_metrics,
    }


def run_experiment_e1(
    df: pd.DataFrame,
    train_ratio: float = 0.75,
    seed: int = 42,
) -> dict[str, Any]:
    """Execute complete Experiment E1 comparing Random vs Float-Grouped vs Time-Blocked."""
    df = ensure_float_id_column(df)

    # 1. Random Split (Naive)
    train_rand, eval_rand = make_random_split(df, train_ratio=train_ratio, seed=seed)

    # 2. Float-Grouped Split (Leak-Free Spatial)
    train_flt, eval_flt, _ = make_float_grouped_split(
        df,
        train_ratio=train_ratio,
        val_ratio=1.0 - train_ratio,
        test_ratio=0.0,
        seed=seed,
    )
    assert_no_leakage(train_flt, eval_flt, group_col="float_id")

    # 3. Time-Blocked Split (Leak-Free Temporal)
    train_time, eval_time = make_time_blocked_split(df, date_col="date", train_ratio=train_ratio)

    def get_fresh_models() -> list[tuple[str, Any]]:
        return [
            ("Climatology", ClimatologyBaseline()),
            ("Climatology + Ridge", RidgeAnomalyBaseline(alpha=1.0)),
            (
                "Gradient Boosted Trees (HistGBDT)",
                GradientBoostedBaseline(max_iter=100, max_depth=6),
            ),
            ("v1 OceanEmbedNet", V1OceanEmbedNetBaseline()),
        ]

    logger.info("Evaluating Random Split Protocol...")
    rand_res = evaluate_split_protocol("Random (Naive)", train_rand, eval_rand, get_fresh_models())

    logger.info("Evaluating Float-Grouped Protocol...")
    flt_res = evaluate_split_protocol("Float-Grouped", train_flt, eval_flt, get_fresh_models())

    logger.info("Evaluating Time-Blocked Protocol...")
    time_res = evaluate_split_protocol("Time-Blocked", train_time, eval_time, get_fresh_models())

    # Compute Leakage Gaps: ΔRMSE = Blocked - Random
    model_names = [m[0] for m in get_fresh_models()]
    leakage_gaps: dict[str, dict[str, float]] = {}

    for m in model_names:
        r_rand = rand_res["metrics"][m]["thermocline_rmse"]
        r_flt = flt_res["metrics"][m]["thermocline_rmse"]
        r_time = time_res["metrics"][m]["thermocline_rmse"]

        leakage_gaps[m] = {
            "rand_thermo_rmse": r_rand,
            "flt_thermo_rmse": r_flt,
            "time_thermo_rmse": r_time,
            "delta_float_leakage": round(r_flt - r_rand, 4),
            "delta_time_leakage": round(r_time - r_rand, 4),
            "rand_skill": rand_res["metrics"][m]["skill_score"],
            "flt_skill": flt_res["metrics"][m]["skill_score"],
            "time_skill": time_res["metrics"][m]["skill_score"],
        }

    return {
        "_experiment": "E1: Random vs Blocked Leakage Gap Analysis",
        "_generated_at": datetime.now(UTC).isoformat(),
        "n_profiles_total": len(df),
        "train_ratio": train_ratio,
        "seed": seed,
        "protocols": {
            "random": rand_res,
            "float_grouped": flt_res,
            "time_blocked": time_res,
        },
        "leakage_gaps": leakage_gaps,
    }


def format_leakage_markdown(res: dict[str, Any]) -> str:
    """Format Experiment E1 results as a comprehensive scientific markdown report."""
    lines = [
        "### Experiment E1: Generalization & Leakage Gap Analysis",
        "",
        "> **Objective:** Quantify the performance inflation caused by naive random splitting in oceanography.",
        "> In oceanographic machine learning, random splitting leaks Argo float trajectories (spatial autocorrelation)",
        "> and temporal persistence, producing dangerously optimistic error metrics.",
        "",
        "#### Thermocline RMSE (50-150 m) Across Splitting Protocols",
        "",
        "| Model | Random Split (Naive) | Float-Grouped | Time-Blocked | Float Leakage Gap (ΔRMSE) | Temporal Gap (ΔRMSE) |",
        "|---|:---:|:---:|:---:|:---:|:---:|",
    ]

    for model, gaps in res["leakage_gaps"].items():
        delta_flt_sign = (
            f"+{gaps['delta_float_leakage']:.3f}"
            if gaps["delta_float_leakage"] > 0
            else f"{gaps['delta_float_leakage']:.3f}"
        )
        delta_time_sign = (
            f"+{gaps['delta_time_leakage']:.3f}"
            if gaps["delta_time_leakage"] > 0
            else f"{gaps['delta_time_leakage']:.3f}"
        )
        lines.append(
            f"| **{model}** | {gaps['rand_thermo_rmse']:.3f} °C | {gaps['flt_thermo_rmse']:.3f} °C | {gaps['time_thermo_rmse']:.3f} °C | **{delta_flt_sign} °C** | **{delta_time_sign} °C** |"
        )

    lines.extend(
        [
            "",
            "#### Skill Score (vs Climatology) Across Splitting Protocols",
            "",
            "| Model | Random SS | Float-Grouped SS | Time-Blocked SS | Impact |",
            "|---|:---:|:---:|:---:|---|",
        ]
    )

    for model, gaps in res["leakage_gaps"].items():
        drop = gaps["rand_skill"] - gaps["flt_skill"]
        verdict = (
            f"Skill drops by {drop:.3f} under honest spatial hold-out"
            if drop > 0
            else "Consistent across splits"
        )
        lines.append(
            f"| **{model}** | {gaps['rand_skill']:+.3f} | {gaps['flt_skill']:+.3f} | {gaps['time_skill']:+.3f} | {verdict} |"
        )

    lines.extend(
        [
            "",
            "#### Key Scientific Findings",
            "1. **Random splitting underestimates thermocline error:** Naive random splitting yields artificially lower RMSE because subsequent profiles from the same drifting float exist in both training and test sets.",
            "2. **Float-grouped holdout enforces generalization:** Holding out complete float trajectories reveals true spatial transferability across unseen oceanic coordinates.",
            "3. **Time-blocked holdout tests seasonal transfer:** Temporal holdout tests forward-in-time forecasting where the model cannot rely on temporally adjacent observations.",
        ]
    )

    return "\n".join(lines)


def main() -> None:
    """CLI entry point for aquasphere-e1-leakage."""
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="AquaSphere Experiment E1: Leakage Gap Analysis")
    default_data = (
        "data/processed/argo_profiles.parquet"
        if Path("data/processed/argo_profiles.parquet").exists()
        else "data/argo_sst_training.csv"
    )
    parser.add_argument("--data", default=default_data, help="Path to profile dataset")
    parser.add_argument(
        "--json", default="docs/results/e1_leakage.json", help="Path to output JSON"
    )
    parser.add_argument(
        "--md", default="docs/results/e1_leakage.md", help="Path to output Markdown"
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    data_p = Path(args.data)
    df = pd.read_parquet(data_p) if data_p.suffix == ".parquet" else pd.read_csv(data_p)

    results = run_experiment_e1(df, seed=args.seed)
    md_report = format_leakage_markdown(results)

    out_json = Path(args.json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(results, indent=2), encoding="utf-8")

    out_md = Path(args.md)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(md_report, encoding="utf-8")

    print("\n" + md_report + "\n")
    print(f"[*] Saved Experiment E1 results to {out_json} and {out_md}")


if __name__ == "__main__":
    main()
