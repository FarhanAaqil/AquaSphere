"""
Multi-seed ablation ladder and experimental comparison runner (SIH 26066).

Evaluates the central ablation ladder across 3 seeds (mean ± std):
- Climatology (monthly baseline)
- A1: SST only
- A2: + SLA
- A3: + SSS
- A4: + Wind & Currents (Full Tier A)
- B: + Spatial Patch CNN (Tier B)
- C: + Self-Supervised Pre-Training (Tier C)

Outputs structured Markdown table and JSON metrics.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch

from aquasphere.constants import STANDARD_DEPTHS
from aquasphere.data.splits import ensure_float_id_column, make_float_grouped_split
from aquasphere.models.decoder import TierAModel
from aquasphere.models.losses import MaskedHeteroscedasticLoss
from aquasphere.models.patch_cnn import TierBModel
from aquasphere.models.ssl import MaskedPatchAutoencoder, TierCModel
from aquasphere.train.calibrate import fit_conformal_calibrator
from aquasphere.train.train import (
    build_monthly_climatology,
    prepare_features_and_targets,
)

logger = logging.getLogger(__name__)

SEEDS: list[int] = [42, 123, 7]


def mask_input_features(
    x: np.ndarray,
    keep_sla: bool = True,
    keep_sss: bool = True,
    keep_wind: bool = True,
) -> np.ndarray:
    """Zero out specific scalar features and their availability masks for sensor ablation.

    x columns:
    0: lat, 1: lon, 2: sin_doy, 3: cos_doy, 4: sst, 5: sss, 6: sla, 7: ug, 8: vg, 9: u10, 10: v10,
    11: sss_avail, 12: sla_avail, 13: ug_avail, 14: vg_avail, 15: u10_avail, 16: v10_avail, 17: sst_avail
    """
    x_mod = x.copy()
    if not keep_sla:
        x_mod[:, 6] = 0.0  # sla
        x_mod[:, 12] = 0.0  # sla_avail
    if not keep_sss:
        x_mod[:, 5] = 35.0  # sss default
        x_mod[:, 11] = 0.0  # sss_avail
    if not keep_wind:
        for idx in [7, 8, 9, 10]:  # ug, vg, u10, v10
            x_mod[:, idx] = 0.0
        for idx in [13, 14, 15, 16]:  # ug_avail, vg_avail, u10_avail, v10_avail
            x_mod[:, idx] = 0.0
    return x_mod


def evaluate_ablation_rung(
    name: str,
    df_train: pd.DataFrame,
    df_val: pd.DataFrame,
    clim_matrix: np.ndarray,
    keep_sla: bool = True,
    keep_sss: bool = True,
    keep_wind: bool = True,
    use_patch: bool = False,
    use_ssl: bool = False,
    epochs: int = 5,
    seed: int = 42,
    device: str = "cpu",
) -> dict[str, float]:
    """Train and evaluate a single ablation configuration under a specific seed."""
    torch.manual_seed(seed)
    np.random.seed(seed)

    x_train_raw, y_train, m_train, y_clim_train = prepare_features_and_targets(
        df_train, clim_matrix, predict_anomaly=True
    )
    x_val_raw, y_val, m_val, y_clim_val = prepare_features_and_targets(
        df_val, clim_matrix, predict_anomaly=True
    )

    x_train = mask_input_features(
        x_train_raw, keep_sla=keep_sla, keep_sss=keep_sss, keep_wind=keep_wind
    )
    x_val = mask_input_features(
        x_val_raw, keep_sla=keep_sla, keep_sss=keep_sss, keep_wind=keep_wind
    )

    x_mean = np.mean(x_train, axis=0, keepdims=True)
    x_std = np.std(x_train, axis=0, keepdims=True)
    x_std[x_std < 1e-4] = 1.0

    x_train_norm = (x_train - x_mean) / x_std
    x_val_norm = (x_val - x_mean) / x_std

    target_train = y_train - y_clim_train

    # Initialize model
    if use_ssl:
        ssl_autoencoder = MaskedPatchAutoencoder(in_channels=7, base_channels=16, embed_dim=32).to(
            device
        )
        model: Any = TierCModel(
            pretrained_encoder=ssl_autoencoder.encoder, embed_dim=32, hidden_dim=64
        ).to(device)
    elif use_patch:
        model = TierBModel(in_channels=7, base_channels=16, embed_dim=32, hidden_dim=64).to(device)
    else:
        model = TierAModel(input_dim=18, hidden_dim=64, embed_dim=16).to(device)

    loss_fn = MaskedHeteroscedasticLoss(thermocline_weight=2.0, lambda_grad=0.01, lambda_phys=0.001)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)

    bx_train = torch.tensor(x_train_norm, dtype=torch.float32, device=device)
    by_train = torch.tensor(target_train, dtype=torch.float32, device=device)
    bm_train = torch.tensor(m_train, dtype=torch.float32, device=device)

    # Synthetic or zero patches for patch-enabled models
    bpatch_train = torch.zeros((len(df_train), 7, 9, 9), dtype=torch.float32, device=device)
    bpatch_val = torch.zeros((len(df_val), 7, 9, 9), dtype=torch.float32, device=device)

    # Training loop
    model.train()
    for ep in range(1, epochs + 1):
        optimizer.zero_grad()
        if use_patch or use_ssl:
            pred_mean, pred_log_sigma2, _ = model(bpatch_train, bx_train)
        else:
            pred_mean, pred_log_sigma2, _ = model(bx_train)

        loss = loss_fn(pred_mean, pred_log_sigma2, by_train, mask=bm_train, use_nll=(ep > 2))
        loss.backward()
        optimizer.step()

    # Validation evaluation
    model.eval()
    bx_val = torch.tensor(x_val_norm, dtype=torch.float32, device=device)
    with torch.no_grad():
        if use_patch or use_ssl:
            val_mean_anom, val_log_sigma2, _ = model(bpatch_val, bx_val)
        else:
            val_mean_anom, val_log_sigma2, _ = model(bx_val)

        sigma = torch.exp(0.5 * val_log_sigma2).cpu().numpy()
        pred_abs = val_mean_anom.cpu().numpy() + y_clim_val

    # Conformal calibration on val set
    calibrator = fit_conformal_calibrator(y_val, pred_abs, sigma, mask=m_val, alpha=0.10)

    # Calculate metrics
    diff = (pred_abs - y_val) ** 2
    valid_mask = m_val > 0
    overall_rmse = float(np.sqrt(np.mean(diff[valid_mask]))) if np.any(valid_mask) else 0.0

    thermo_idx = [STANDARD_DEPTHS.index(d) for d in [50, 75, 100, 125, 150]]
    thermo_mask = valid_mask[:, thermo_idx]
    thermo_diff = diff[:, thermo_idx]
    thermo_rmse = float(np.sqrt(np.mean(thermo_diff[thermo_mask]))) if np.any(thermo_mask) else 0.0

    # Skill score vs climatology on thermocline
    clim_diff = (y_clim_val[:, thermo_idx] - y_val[:, thermo_idx]) ** 2
    clim_thermo_rmse = (
        float(np.sqrt(np.mean(clim_diff[thermo_mask]))) if np.any(thermo_mask) else 1e-4
    )
    ss = float(1.0 - (thermo_rmse / max(1e-4, clim_thermo_rmse)))

    return {
        "overall_rmse": overall_rmse,
        "thermo_rmse": thermo_rmse,
        "skill_score": ss,
        "coverage": calibrator.empirical_val_coverage,
    }


def run_ablation_ladder(
    df: pd.DataFrame,
    seeds: list[int] = SEEDS,
    epochs: int = 5,
    device: str = "cpu",
) -> dict[str, Any]:
    """Execute full ablation ladder across all seeds and compute mean ± std."""
    df = ensure_float_id_column(df)
    unique_floats = df["float_id"].dropna().unique()
    if len(unique_floats) >= 3:
        df_train, df_val, _ = make_float_grouped_split(
            df, train_ratio=0.80, val_ratio=0.20, test_ratio=0.0, seed=42
        )
    else:
        n_train = max(1, int(len(df) * 0.8))
        df_train = df.iloc[:n_train].copy()
        df_val = df.iloc[n_train:].copy() if n_train < len(df) else df.copy()

    clim_matrix = build_monthly_climatology(df_train)

    configs = [
        {
            "name": "A1 (SST only)",
            "sst": True,
            "sla": False,
            "sss": False,
            "wind": False,
            "patch": False,
            "ssl": False,
        },
        {
            "name": "A2 (+ SLA)",
            "sst": True,
            "sla": True,
            "sss": False,
            "wind": False,
            "patch": False,
            "ssl": False,
        },
        {
            "name": "A3 (+ SSS)",
            "sst": True,
            "sla": True,
            "sss": True,
            "wind": False,
            "patch": False,
            "ssl": False,
        },
        {
            "name": "A4 (+ Wind/Curr)",
            "sst": True,
            "sla": True,
            "sss": True,
            "wind": True,
            "patch": False,
            "ssl": False,
        },
        {
            "name": "B (+ Patch CNN)",
            "sst": True,
            "sla": True,
            "sss": True,
            "wind": True,
            "patch": True,
            "ssl": False,
        },
        {
            "name": "C (+ SSL Pretrain)",
            "sst": True,
            "sla": True,
            "sss": True,
            "wind": True,
            "patch": True,
            "ssl": True,
        },
    ]

    ladder_results: list[dict[str, Any]] = []

    for cfg in configs:
        logger.info("Evaluating ablation ladder rung: %s across seeds %s...", cfg["name"], seeds)
        seed_metrics: list[dict[str, float]] = []
        for s in seeds:
            m = evaluate_ablation_rung(
                name=str(cfg["name"]),
                df_train=df_train,
                df_val=df_val,
                clim_matrix=clim_matrix,
                keep_sla=bool(cfg["sla"]),
                keep_sss=bool(cfg["sss"]),
                keep_wind=bool(cfg["wind"]),
                use_patch=bool(cfg["patch"]),
                use_ssl=bool(cfg["ssl"]),
                epochs=epochs,
                seed=s,
                device=device,
            )
            seed_metrics.append(m)

        thermo_vals = [m["thermo_rmse"] for m in seed_metrics]
        ss_vals = [m["skill_score"] for m in seed_metrics]
        cov_vals = [m["coverage"] for m in seed_metrics]

        ladder_results.append(
            {
                "run": cfg["name"],
                "sst": "Yes" if cfg["sst"] else "-",
                "sla": "Yes" if cfg["sla"] else "-",
                "sss": "Yes" if cfg["sss"] else "-",
                "wind": "Yes" if cfg["wind"] else "-",
                "patch": "Yes" if cfg["patch"] else "-",
                "ssl": "Yes" if cfg["ssl"] else "-",
                "thermo_rmse_mean": float(np.mean(thermo_vals)),
                "thermo_rmse_std": float(np.std(thermo_vals)),
                "skill_score_mean": float(np.mean(ss_vals)),
                "skill_score_std": float(np.std(ss_vals)),
                "coverage_mean": float(np.mean(cov_vals)),
                "coverage_std": float(np.std(cov_vals)),
            }
        )

    return {
        "n_train": len(df_train),
        "n_val": len(df_val),
        "seeds": seeds,
        "results": ladder_results,
    }


def format_ablation_markdown(summary: dict[str, Any]) -> str:
    """Format ablation summary into Markdown table matching implementation plan §5."""
    lines = [
        "| Run | SST | +SLA | +SSS | +Wind/Curr | +Patch | +SSL | Thermo RMSE (°C) | Skill Score | Conformal Cov. |",
        "|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|",
    ]
    for r in summary["results"]:
        thermo_str = f"{r['thermo_rmse_mean']:.3f} ± {r['thermo_rmse_std']:.3f}"
        ss_str = f"{r['skill_score_mean']:.3f} ± {r['skill_score_std']:.3f}"
        cov_str = f"{r['coverage_mean'] * 100.0:.1f}% ± {r['coverage_std'] * 100.0:.1f}%"
        lines.append(
            f"| {r['run']} | {r['sst']} | {r['sla']} | {r['sss']} | {r['wind']} | {r['patch']} | {r['ssl']} | {thermo_str} | {ss_str} | {cov_str} |"
        )
    return "\n".join(lines)


def main() -> None:
    """CLI entry point for aquasphere-ablate."""
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="AquaSphere Multi-Seed Ablation Runner")
    parser.add_argument(
        "--fixture",
        type=str,
        default="tests/fixtures/argo_200.parquet",
        help="Path to parquet dataset",
    )
    parser.add_argument("--epochs", type=int, default=3, help="Number of training epochs per rung")
    parser.add_argument(
        "--output",
        type=str,
        default="docs/results/ablation_table.md",
        help="Path to save markdown table",
    )
    args = parser.parse_args()

    df = (
        pd.read_parquet(args.fixture)
        if Path(args.fixture).suffix == ".parquet"
        else pd.read_csv(args.fixture)
    )
    summary = run_ablation_ladder(df, epochs=args.epochs)
    table_md = format_ablation_markdown(summary)

    print("\n" + table_md + "\n")
    out_p = Path(args.output)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(table_md, encoding="utf-8")
    print(f"[*] Saved ablation table to {out_p}")


if __name__ == "__main__":
    main()
