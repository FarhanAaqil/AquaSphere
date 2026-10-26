"""
Training pipeline for AquaSphere Tier A neural network (SIH 26066).

Features:
- Config-driven training via YAML.
- Anomaly reconstruction over monthly climatology.
- Masked heteroscedastic loss with MSE warmup and physics penalties.
- Float-grouped leak-free validation split.
- Conformal uncertainty interval calibration.
- Headless / fixture training for CI smoke testing.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
import yaml
from torch.utils.data import DataLoader, TensorDataset

from aquasphere.constants import DEPTH_COLS, MASK_COLS, STANDARD_DEPTHS
from aquasphere.data.splits import make_float_grouped_split
from aquasphere.models.decoder import TierAModel
from aquasphere.models.losses import MaskedHeteroscedasticLoss
from aquasphere.train.calibrate import fit_conformal_calibrator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("aquasphere.train")

DEFAULT_SCALARS = [
    "lat",
    "lon",
    "sin_doy",
    "cos_doy",
    "sst",
    "sss",
    "sla",
    "ug",
    "vg",
    "u10",
    "v10",
]
DEFAULT_MASKS = [
    "sss_avail",
    "sla_avail",
    "ug_avail",
    "vg_avail",
    "u10_avail",
    "v10_avail",
    "sst_avail",
]


def compute_doy_features(date_series: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """Compute sine and cosine day-of-year cyclic temporal features."""
    dts = pd.to_datetime(date_series)
    doy = dts.dt.dayofyear.to_numpy(dtype=np.float32)
    sin_doy = np.sin(2.0 * np.pi * doy / 365.25).astype(np.float32)
    cos_doy = np.cos(2.0 * np.pi * doy / 365.25).astype(np.float32)
    return sin_doy, cos_doy


def build_monthly_climatology(
    df: pd.DataFrame,
    depth_cols: list[str] = DEPTH_COLS,
    mask_cols: list[str] = MASK_COLS,
) -> np.ndarray:
    """Compute 12-month mean temperature profile matrix [12, 15] (°C)."""
    dts = pd.to_datetime(df["date"])
    months = dts.dt.month.to_numpy()

    t_matrix = df[depth_cols].to_numpy(dtype=np.float32)
    m_matrix = df[mask_cols].to_numpy(dtype=np.float32)

    clim = np.zeros((12, len(depth_cols)), dtype=np.float32)
    for m in range(1, 13):
        m_idx = months == m
        if not np.any(m_idx):
            continue
        sub_t = t_matrix[m_idx]
        sub_m = m_matrix[m_idx]

        for d_i in range(len(depth_cols)):
            valid = sub_m[:, d_i] > 0
            if np.any(valid):
                clim[m - 1, d_i] = float(np.mean(sub_t[valid, d_i]))
            else:
                # Fallback to column average if month has no valid observations
                col_valid = m_matrix[:, d_i] > 0
                clim[m - 1, d_i] = (
                    float(np.mean(t_matrix[col_valid, d_i])) if np.any(col_valid) else 20.0
                )

    return clim


def prepare_features_and_targets(
    df: pd.DataFrame,
    clim_matrix: np.ndarray | None = None,
    predict_anomaly: bool = True,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Extract 18-d input features, target temperatures, target masks, and climatology baseline.

    Features: [lat, lon, sin_doy, cos_doy, sst, sss, sla, ug, vg, u10, v10] + 7 availability masks.

    Returns:
        X [N, 18], Y [N, 15], M [N, 15], Y_clim [N, 15]
    """
    n_samples = len(df)
    sin_doy, cos_doy = compute_doy_features(df["date"])

    lat = df["lat"].to_numpy(dtype=np.float32)
    lon = df["lon"].to_numpy(dtype=np.float32)
    sst = (
        df["sst"].to_numpy(dtype=np.float32)
        if "sst" in df.columns
        else np.full(n_samples, 28.0, dtype=np.float32)
    )

    # Secondary satellite features (graceful fallback if absent from CSV)
    def _get_feature(col: str, fallback_val: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
        if col in df.columns and not df[col].isna().all():
            vals = df[col].fillna(fallback_val).to_numpy(dtype=np.float32)
            avail = (~df[col].isna()).to_numpy(dtype=np.float32)
            return vals, avail
        return np.full(n_samples, fallback_val, dtype=np.float32), np.zeros(
            n_samples, dtype=np.float32
        )

    sss, sss_m = _get_feature("sss", fallback_val=35.0)
    sla, sla_m = _get_feature("sla", fallback_val=0.0)
    ug, ug_m = _get_feature("ug", fallback_val=0.0)
    vg, vg_m = _get_feature("vg", fallback_val=0.0)
    u10, u10_m = _get_feature("u10", fallback_val=0.0)
    v10, v10_m = _get_feature("v10", fallback_val=0.0)
    sst_m = (~np.isnan(sst)).astype(np.float32)
    sst = np.nan_to_num(sst, nan=28.0)

    # 18-d input vector
    feature_cols = [
        lat,
        lon,
        sin_doy,
        cos_doy,
        sst,
        sss,
        sla,
        ug,
        vg,
        u10,
        v10,
        sss_m,
        sla_m,
        ug_m,
        vg_m,
        u10_m,
        v10_m,
        sst_m,
    ]
    x = np.column_stack(feature_cols).astype(np.float32)

    # Targets & Masks
    y = df[DEPTH_COLS].to_numpy(dtype=np.float32)
    m = (
        df[MASK_COLS].to_numpy(dtype=np.float32)
        if all(c in df.columns for c in MASK_COLS)
        else (~np.isnan(y)).astype(np.float32)
    )
    y = np.nan_to_num(y, nan=0.0)

    # Climatology lookup
    dts = pd.to_datetime(df["date"])
    months = dts.dt.month.to_numpy() - 1
    if clim_matrix is not None:
        y_clim = clim_matrix[months]
    else:
        y_clim = np.zeros_like(y)

    return x, y, m, y_clim


def train_tier_a(
    config_path: Path | str = "configs/model_a.yaml",
    epochs_override: int | None = None,
    fixture_path: Path | str | None = None,
    no_save: bool = False,
    seed_override: int | None = None,
    batch_size_override: int | None = None,
    device: str = "cpu",
) -> dict[str, Any]:
    """Train AquaSphere Tier A neural network and compute validation metrics.

    Args:
        config_path: Path to model_a.yaml config file
        epochs_override: If provided, overrides config epoch count (useful for smoke runs)
        fixture_path: Path to parquet dataset (fixture or processed argo)
        no_save: If True, skips writing checkpoint files to disk
        seed_override: If provided, overrides random seed
        batch_size_override: If provided, overrides batch size
        device: "cpu" or "cuda"

    Returns:
        Dictionary containing validation RMSE, thermocline RMSE, and training history.
    """
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    seed = seed_override if seed_override is not None else cfg.get("training", {}).get("seed", 42)
    torch.manual_seed(seed)
    np.random.seed(seed)

    # 1. Load Data
    if fixture_path is not None:
        p = Path(fixture_path)
        logger.info("Loading dataset from fixture: %s", p)
        df = pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_csv(p)
    else:
        parquet_p = Path("data/processed/argo_profiles.parquet")
        csv_p = Path("data/argo_sst_training.csv")
        if parquet_p.exists():
            logger.info("Loading dataset from %s", parquet_p)
            df = pd.read_parquet(parquet_p)
        elif csv_p.exists():
            logger.info("Loading dataset from legacy %s", csv_p)
            df = pd.read_csv(csv_p)
        else:
            raise FileNotFoundError(
                "No Argo dataset found at data/processed/ or data/argo_sst_training.csv"
            )

    # 2. Float-grouped train/val split
    from aquasphere.data.splits import ensure_float_id_column

    df = ensure_float_id_column(df)
    unique_floats = df["float_id"].dropna().unique()
    if len(unique_floats) >= 3:
        df_train, df_val, _ = make_float_grouped_split(
            df, train_ratio=0.80, val_ratio=0.20, test_ratio=0.0, seed=seed
        )
    else:
        n_train = max(1, int(len(df) * 0.8))
        df_train = df.iloc[:n_train].copy()
        df_val = df.iloc[n_train:].copy() if n_train < len(df) else df.copy()

    n_floats_train = df_train["float_id"].nunique()
    n_floats_val = df_val["float_id"].nunique()
    logger.info(
        "Split profiles: %d train (%d floats), %d val (%d floats)",
        len(df_train),
        n_floats_train,
        len(df_val),
        n_floats_val,
    )

    # 3. Monthly Climatology
    clim_matrix = build_monthly_climatology(df_train)
    predict_anomaly = cfg.get("model", {}).get("predict_anomaly", True)

    # 4. Feature Preparation & Normalization
    x_train, y_train, m_train, y_clim_train = prepare_features_and_targets(
        df_train, clim_matrix, predict_anomaly
    )
    x_val, y_val, m_val, y_clim_val = prepare_features_and_targets(
        df_val, clim_matrix, predict_anomaly
    )

    x_mean = np.mean(x_train, axis=0, keepdims=True)
    x_std = np.std(x_train, axis=0, keepdims=True)
    x_std[x_std < 1e-4] = 1.0  # avoid zero division on constant masks

    x_train_norm = (x_train - x_mean) / x_std
    x_val_norm = (x_val - x_mean) / x_std

    target_train = (y_train - y_clim_train) if predict_anomaly else y_train
    target_val = (y_val - y_clim_val) if predict_anomaly else y_val

    # PyTorch DataLoaders
    batch_size = (
        batch_size_override
        if batch_size_override is not None
        else cfg.get("training", {}).get("batch_size", 256)
    )
    train_ds = TensorDataset(
        torch.tensor(x_train_norm, dtype=torch.float32),
        torch.tensor(target_train, dtype=torch.float32),
        torch.tensor(m_train, dtype=torch.float32),
        torch.tensor(y_clim_train, dtype=torch.float32),
    )
    val_ds = TensorDataset(
        torch.tensor(x_val_norm, dtype=torch.float32),
        torch.tensor(target_val, dtype=torch.float32),
        torch.tensor(m_val, dtype=torch.float32),
        torch.tensor(y_clim_val, dtype=torch.float32),
    )

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)

    # 5. Model & Loss setup
    hidden_dim = cfg.get("model", {}).get("hidden", 128)
    embed_dim = cfg.get("model", {}).get("embed_dim", 16)
    model = TierAModel(input_dim=18, hidden_dim=hidden_dim, embed_dim=embed_dim, n_depths=15).to(
        device
    )

    loss_cfg = cfg.get("loss", {})
    warmup_epochs = loss_cfg.get("warmup_epochs", 10)
    clamp_vals = loss_cfg.get("log_sigma2_clamp", [-6.0, 4.0])
    loss_fn = MaskedHeteroscedasticLoss(
        thermocline_weight=loss_cfg.get("thermocline_weight", 2.0),
        lambda_grad=loss_cfg.get("lambda_grad", 0.01),
        lambda_phys=loss_cfg.get("lambda_phys", 0.001),
        log_sigma2_min=clamp_vals[0],
        log_sigma2_max=clamp_vals[1],
    )

    lr = float(cfg.get("training", {}).get("lr", 1e-3))
    weight_decay = float(cfg.get("training", {}).get("weight_decay", 1e-4))
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)

    epochs = (
        epochs_override
        if epochs_override is not None
        else cfg.get("training", {}).get("epochs", 100)
    )
    patience = cfg.get("training", {}).get("patience", 25)

    best_val_rmse = float("inf")
    best_thermo_rmse = float("inf")
    best_state_dict: dict[str, Any] | None = None
    epochs_no_improve = 0

    history: list[dict[str, float]] = []

    logger.info(
        "Starting Tier A training for %d epochs (anomaly_mode=%s)...", epochs, predict_anomaly
    )

    for epoch in range(1, epochs + 1):
        model.train()
        train_loss = 0.0
        n_batches = 0
        use_nll = epoch > warmup_epochs

        for bx, by, bm, _ in train_loader:
            bx, by, bm = bx.to(device), by.to(device), bm.to(device)
            optimizer.zero_grad()
            pred_mean, pred_log_sigma2, _ = model(bx)
            loss = loss_fn(pred_mean, pred_log_sigma2, by, mask=bm, use_nll=use_nll)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=2.0)
            optimizer.step()

            train_loss += float(loss.item())
            n_batches += 1

        avg_train_loss = train_loss / max(1, n_batches)

        # Validation step
        model.eval()
        val_preds_list: list[np.ndarray] = []
        val_sigma_list: list[np.ndarray] = []

        with torch.no_grad():
            for bx, _by, _bm, bclim in val_loader:
                bx = bx.to(device)
                pred_mean, pred_log_sigma2, _ = model(bx)
                sigma = torch.exp(0.5 * pred_log_sigma2)

                # Reconstruct absolute temperature
                pred_abs = (pred_mean + bclim.to(device)) if predict_anomaly else pred_mean
                val_preds_list.append(pred_abs.cpu().numpy())
                val_sigma_list.append(sigma.cpu().numpy())

        val_preds = np.concatenate(val_preds_list, axis=0)
        val_sigmas = np.concatenate(val_sigma_list, axis=0)

        # Compute validation RMSE over observed entries
        diff = (val_preds - y_val) ** 2
        valid_mask = m_val > 0
        val_rmse = float(np.sqrt(np.mean(diff[valid_mask]))) if np.any(valid_mask) else 0.0

        # Thermocline RMSE (depths 50 to 150 m: indices 5 to 9)
        thermo_idx = [STANDARD_DEPTHS.index(d) for d in [50, 75, 100, 125, 150]]
        thermo_mask = valid_mask[:, thermo_idx]
        thermo_diff = diff[:, thermo_idx]
        thermo_rmse = (
            float(np.sqrt(np.mean(thermo_diff[thermo_mask]))) if np.any(thermo_mask) else 0.0
        )

        history.append(
            {
                "epoch": epoch,
                "train_loss": avg_train_loss,
                "val_rmse": val_rmse,
                "thermo_rmse": thermo_rmse,
            }
        )

        if epoch % 5 == 0 or epoch == epochs or epochs <= 5:
            logger.info(
                "Epoch %3d/%3d | Train Loss: %.4f | Val RMSE: %.3f °C | Thermo RMSE: %.3f °C",
                epoch,
                epochs,
                avg_train_loss,
                val_rmse,
                thermo_rmse,
            )

        if val_rmse < best_val_rmse:
            best_val_rmse = val_rmse
            best_thermo_rmse = thermo_rmse
            best_state_dict = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            epochs_no_improve = 0
        else:
            epochs_no_improve += 1
            if epochs_no_improve >= patience and epochs > 30:
                logger.info("Early stopping triggered at epoch %d (patience: %d)", epoch, patience)
                break

    # 6. Fit Conformal Calibrator on Validation Set
    calibrator = fit_conformal_calibrator(
        y_true=y_val,
        y_pred=val_preds,
        sigma=val_sigmas,
        mask=m_val,
        alpha=0.10,
    )

    # 7. Save Checkpoint (if requested)
    checkpoint_dir = Path(cfg.get("output", {}).get("checkpoint_dir", "checkpoints/tier_a"))
    if not no_save and best_state_dict is not None:
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        ckpt_path = checkpoint_dir / "model_a.pt"
        payload = {
            "model_state": best_state_dict,
            "scaler": {
                "mean": x_mean.squeeze(0).tolist(),
                "std": x_std.squeeze(0).tolist(),
            },
            "climatology": clim_matrix.tolist(),
            "conformal_calibration": calibrator.to_dict(),
            "config": cfg,
            "val_rmse": best_val_rmse,
            "val_thermo_rmse": best_thermo_rmse,
        }
        torch.save(payload, ckpt_path)
        logger.info(
            "Saved best Tier A checkpoint to %s (Val RMSE: %.3f °C)", ckpt_path, best_val_rmse
        )

    return {
        "best_val_rmse": best_val_rmse,
        "best_thermo_rmse": best_thermo_rmse,
        "calibrator": calibrator.to_dict(),
        "n_train": len(df_train),
        "n_val": len(df_val),
        "history": history,
    }


def main() -> None:
    """CLI entry point for aquasphere-train."""
    parser = argparse.ArgumentParser(description="AquaSphere Model Training Engine")
    parser.add_argument(
        "--config", type=str, default="configs/model_a.yaml", help="Path to YAML training config"
    )
    parser.add_argument(
        "--epochs", type=int, default=None, help="Override number of training epochs"
    )
    parser.add_argument("--fixture", type=str, default=None, help="Path to fixture dataset")
    parser.add_argument(
        "--no-save", action="store_true", help="Skip checkpoint file writing (for testing)"
    )
    parser.add_argument("--seed", type=int, default=None, help="Random seed override")
    parser.add_argument("--batch-size", type=int, default=None, help="Batch size override")
    parser.add_argument("--device", type=str, default="cpu", help="Device to use ('cpu' or 'cuda')")

    args = parser.parse_args()
    results = train_tier_a(
        config_path=args.config,
        epochs_override=args.epochs,
        fixture_path=args.fixture,
        no_save=args.no_save,
        seed_override=args.seed,
        batch_size_override=args.batch_size,
        device=args.device,
    )
    print(
        f"[*] Training finished: Val RMSE = {results['best_val_rmse']:.3f} °C, Thermo RMSE = {results['best_thermo_rmse']:.3f} °C"
    )


if __name__ == "__main__":
    main()
