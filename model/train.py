"""
OceanEmbed — Model Training Script
=====================================
Trains an MLP encoder-decoder to reconstruct subsurface ocean
temperature profiles from surface observations.

Architecture:
    Encoder : [lat, lon, sin(doy), cos(doy), sst]  →  16-dim embedding
    Decoder : 16-dim embedding  →  15 depth-temperature values

The 16-dim embedding IS the "Ocean Embedding" described in the SIH
problem statement. It is returned as a first-class output from the
serving layer, not just an internal detail.

Saves:
    model/model.pt          (PyTorch) or model/model.joblib (sklearn fallback)
    model/scaler.json       input normalisation statistics
    model/validation_metrics.json   per-depth and overall RMSE/bias/corr

Usage:
    python model/train.py
    python model/train.py --epochs 100 --hidden 64
"""

import argparse
import json
import math
import os
import sys
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR   = Path(__file__).parent
DATA_CSV     = SCRIPT_DIR.parent / "data" / "argo_sst_training.csv"
MODEL_PT     = SCRIPT_DIR / "model.pt"
MODEL_JL     = SCRIPT_DIR / "model.joblib"
SCALER_JSON  = SCRIPT_DIR / "scaler.json"
METRICS_JSON = SCRIPT_DIR / "validation_metrics.json"

STANDARD_DEPTHS = [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000]
DEPTH_COLS = [f"t_{d}" for d in STANDARD_DEPTHS]

# Depth groupings for the validation metrics table the UI shows
DEPTH_GROUPS = [
    ("0–30 m",    [0, 5, 10, 20, 30]),
    ("50–150 m",  [50, 75, 100, 125, 150]),
    ("200–300 m", [200, 300]),
    ("500–1000 m",[500, 700, 1000]),
]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_data(csv_path: Path):
    """Load CSV, return X (inputs) and Y (targets) as float32 arrays."""
    import csv
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                lat = float(row["lat"])
                lon = float(row["lon"])
                doy = float(row["day_of_year"])
                sst = float(row["sst"])
                temps = [float(row[c]) for c in DEPTH_COLS if row.get(c, "") != ""]
                if len(temps) < 12:          # need most depths valid
                    continue
                # Pad missing deep temps with last known value
                full_temps = []
                last = None
                for c in DEPTH_COLS:
                    v = row.get(c, "")
                    if v == "":
                        full_temps.append(last if last is not None else 4.0)
                    else:
                        last = float(v)
                        full_temps.append(last)
                rows.append((lat, lon, doy, sst, full_temps))
            except (ValueError, KeyError):
                continue

    if not rows:
        raise RuntimeError(f"No valid rows found in {csv_path}")

    X = np.array([[r[0], r[1], math.sin(2 * math.pi * r[2] / 365),
                   math.cos(2 * math.pi * r[2] / 365), r[3]]
                  for r in rows], dtype=np.float32)
    Y = np.array([r[4] for r in rows], dtype=np.float32)
    return X, Y


def normalise(X_train, X_val):
    """Standardise using training-set statistics."""
    mean = X_train.mean(axis=0)
    std  = X_train.std(axis=0) + 1e-8
    return (X_train - mean) / std, (X_val - mean) / std, mean, std


# ---------------------------------------------------------------------------
# PyTorch model
# ---------------------------------------------------------------------------
def try_torch_train(X_tr, Y_tr, X_val, Y_val, epochs: int, hidden: int):
    """Returns (model, embedding_fn) or raises ImportError."""
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset

    class OceanEmbedNet(nn.Module):
        def __init__(self, embed_dim=16, hidden=hidden):
            super().__init__()
            # Encoder: 5 inputs → embed_dim latent
            self.encoder = nn.Sequential(
                nn.Linear(5, hidden),
                nn.ReLU(),
                nn.Linear(hidden, embed_dim),
            )
            # Decoder: embed_dim → 15 depth temperatures
            self.decoder = nn.Sequential(
                nn.Linear(embed_dim, hidden),
                nn.ReLU(),
                nn.Linear(hidden, 15),
            )

        def forward(self, x):
            emb = self.encoder(x)
            out = self.decoder(emb)
            return out, emb

    X_tr_t  = torch.from_numpy(X_tr)
    Y_tr_t  = torch.from_numpy(Y_tr)
    X_val_t = torch.from_numpy(X_val)
    Y_val_t = torch.from_numpy(Y_val)

    ds  = TensorDataset(X_tr_t, Y_tr_t)
    dl  = DataLoader(ds, batch_size=64, shuffle=True)

    model     = OceanEmbedNet(embed_dim=16, hidden=hidden)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    criterion = nn.MSELoss()

    best_val_loss = float("inf")
    patience_cnt  = 0
    PATIENCE      = 20

    print(f"Training PyTorch MLP  ({sum(p.numel() for p in model.parameters())} params) "
          f"on {X_tr.shape[0]} samples …")

    for epoch in range(1, epochs + 1):
        model.train()
        for xb, yb in dl:
            optimizer.zero_grad()
            pred, _ = model(xb)
            loss = criterion(pred, yb)
            loss.backward()
            optimizer.step()

        if epoch % 10 == 0 or epoch == 1:
            model.eval()
            with torch.no_grad():
                val_pred, _ = model(X_val_t)
                val_loss = criterion(val_pred, Y_val_t).item()
            print(f"  epoch {epoch:4d}/{epochs}   val_mse={val_loss:.4f}")

            if val_loss < best_val_loss - 1e-5:
                best_val_loss = val_loss
                patience_cnt  = 0
                torch.save(model.state_dict(), MODEL_PT + ".best.tmp")
            else:
                patience_cnt += 1
                if patience_cnt >= PATIENCE:
                    print(f"  Early stopping at epoch {epoch}")
                    break

    # Restore best weights
    if os.path.exists(MODEL_PT.as_posix() + ".best.tmp"):
        model.load_state_dict(torch.load(MODEL_PT.as_posix() + ".best.tmp"))
        os.remove(MODEL_PT.as_posix() + ".best.tmp")

    torch.save({
        "model_state": model.state_dict(),
        "embed_dim": 16,
        "hidden": hidden,
    }, MODEL_PT)
    print(f"Saved model → {MODEL_PT}")

    # Validation predictions for metrics
    model.eval()
    with torch.no_grad():
        val_pred_np, _ = model(X_val_t)
        val_pred_np = val_pred_np.numpy()

    return val_pred_np


# ---------------------------------------------------------------------------
# sklearn fallback
# ---------------------------------------------------------------------------
def sklearn_train(X_tr, Y_tr, X_val, Y_val, hidden: int):
    """Fallback MLP via sklearn. Returns val predictions."""
    from sklearn.neural_network import MLPRegressor
    from sklearn.multioutput import MultiOutputRegressor
    import joblib

    print(f"PyTorch not available — using sklearn MLPRegressor on {X_tr.shape[0]} samples …")

    mlp = MLPRegressor(
        hidden_layer_sizes=(hidden, 16, hidden),
        activation="relu",
        max_iter=500,
        early_stopping=True,
        validation_fraction=0.1,
        n_iter_no_change=20,
        random_state=42,
        verbose=False,
    )
    # MultiOutputRegressor wraps the MLP for multi-target regression
    model = MultiOutputRegressor(mlp, n_jobs=-1)
    model.fit(X_tr, Y_tr)

    joblib.dump(model, MODEL_JL)
    print(f"Saved model → {MODEL_JL}")

    return model.predict(X_val)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def compute_metrics(Y_true: np.ndarray, Y_pred: np.ndarray) -> dict:
    """Compute RMSE, bias, Pearson r per depth and per depth group."""
    per_depth = []
    for i, d in enumerate(STANDARD_DEPTHS):
        t = Y_true[:, i]
        p = Y_pred[:, i]
        rmse  = float(np.sqrt(np.mean((p - t) ** 2)))
        bias  = float(np.mean(p - t))
        # Pearson r — protect against zero variance
        if t.std() > 1e-8 and p.std() > 1e-8:
            corr = float(np.corrcoef(t, p)[0, 1])
        else:
            corr = 0.0
        per_depth.append({
            "depth_m": d,
            "rmse":    round(rmse, 4),
            "bias":    round(bias, 4),
            "corr":    round(corr, 4),
        })

    # Group-level averages (for the UI table)
    grouped = []
    for label, depths in DEPTH_GROUPS:
        idxs = [STANDARD_DEPTHS.index(d) for d in depths if d in STANDARD_DEPTHS]
        t = Y_true[:, idxs].ravel()
        p = Y_pred[:, idxs].ravel()
        rmse = float(np.sqrt(np.mean((p - t) ** 2)))
        bias = float(np.mean(p - t))
        corr = float(np.corrcoef(t, p)[0, 1]) if t.std() > 1e-8 else 0.0
        grouped.append({
            "depth":  label,
            "rmse":   round(rmse, 3),
            "bias":   round(bias, 3),
            "corr":   round(corr, 3),
        })

    # Overall
    overall_rmse = float(np.sqrt(np.mean((Y_pred - Y_true) ** 2)))
    overall_bias = float(np.mean(Y_pred - Y_true))
    overall_corr = float(np.corrcoef(Y_true.ravel(), Y_pred.ravel())[0, 1])

    return {
        "n_val_samples":  int(Y_true.shape[0]),
        "overall": {
            "rmse": round(overall_rmse, 4),
            "bias": round(overall_bias, 4),
            "corr": round(overall_corr, 4),
        },
        "per_depth": per_depth,
        "grouped":   grouped,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Train OceanEmbed MLP")
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--hidden", type=int, default=64,
                        help="Hidden layer size (encoder and decoder)")
    args = parser.parse_args()

    if not DATA_CSV.exists():
        sys.exit(f"Training CSV not found: {DATA_CSV}\nRun  python data/collect.py  first.")

    print(f"Loading data from {DATA_CSV} …")
    X, Y = load_data(DATA_CSV)
    print(f"  {X.shape[0]} samples  |  {X.shape[1]} inputs  |  {Y.shape[1]} targets")

    if X.shape[0] < 20:
        sys.exit("Not enough samples to train (need at least 20). Collect more data first.")

    # Train / val split (70 / 30)
    rng    = np.random.default_rng(42)
    idx    = rng.permutation(X.shape[0])
    split  = int(0.7 * len(idx))
    tr_idx = idx[:split]
    va_idx = idx[split:]

    X_tr, Y_tr   = X[tr_idx], Y[tr_idx]
    X_val, Y_val = X[va_idx], Y[va_idx]

    # Normalise inputs
    X_tr_n, X_val_n, mu, sigma = normalise(X_tr, X_val)

    # Save scaler
    scaler = {
        "mean":  mu.tolist(),
        "std":   sigma.tolist(),
        "features": ["lat", "lon", "sin_doy", "cos_doy", "sst"],
        "backend": "unknown",   # filled in below
    }

    # Attempt PyTorch, fall back to sklearn
    try:
        val_pred = try_torch_train(X_tr_n, Y_tr, X_val_n, Y_val,
                                   epochs=args.epochs, hidden=args.hidden)
        scaler["backend"] = "pytorch"
    except ImportError:
        val_pred = sklearn_train(X_tr_n, Y_tr, X_val_n, Y_val, hidden=args.hidden)
        scaler["backend"] = "sklearn"

    SCALER_JSON.write_text(json.dumps(scaler, indent=2))
    print(f"Saved scaler → {SCALER_JSON}")

    # Metrics
    metrics = compute_metrics(Y_val, val_pred)
    METRICS_JSON.write_text(json.dumps(metrics, indent=2))
    print(f"Saved metrics → {METRICS_JSON}")

    # Summary print
    ov = metrics["overall"]
    print(f"\n=== Validation Results  (n={metrics['n_val_samples']}) ===")
    print(f"  Overall  RMSE={ov['rmse']:.3f}°C  bias={ov['bias']:+.3f}°C  r={ov['corr']:.3f}")
    print("\n  Per depth group:")
    for g in metrics["grouped"]:
        print(f"  {g['depth']:<14s}  RMSE={g['rmse']:.3f}  bias={g['bias']:+.3f}  r={g['corr']:.3f}")


if __name__ == "__main__":
    main()
