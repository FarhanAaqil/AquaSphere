"""
Baseline ladder models for ocean subsurface temperature reconstruction (SIH 26066).

Defines the 4 comparative baselines specified in Phase 2:
1. ClimatologyBaseline: Monthly climatological vertical profiles.
2. RidgeAnomalyBaseline: Climatology + Ridge regression on SST anomaly per depth.
3. GradientBoostedBaseline: Fast histogram gradient boosting per depth.
4. V1OceanEmbedNetBaseline: Re-evaluation of the pre-rebuild v1 OceanEmbedNet.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

from aquasphere.constants import DEPTH_COLS, STANDARD_DEPTHS

logger = logging.getLogger(__name__)


def prepare_features(df: pd.DataFrame) -> np.ndarray:
    """Extract standard input features: [lat, lon, sin_doy, cos_doy, sst].

    Handles both numeric 'day_of_year' column and 'date' string column.
    """
    lat = df["lat"].to_numpy(dtype=np.float32)
    lon = df["lon"].to_numpy(dtype=np.float32)
    sst = df["sst"].to_numpy(dtype=np.float32)

    if "day_of_year" in df.columns:
        doy = df["day_of_year"].to_numpy(dtype=np.float32)
    elif "date" in df.columns:
        doy = pd.to_datetime(df["date"]).dt.dayofyear.to_numpy(dtype=np.float32)
    else:
        # Default fallback to mid-year
        doy = np.full_like(lat, 180.0)

    sin_doy = np.sin(2.0 * np.pi * doy / 365.25).astype(np.float32)
    cos_doy = np.cos(2.0 * np.pi * doy / 365.25).astype(np.float32)

    return np.column_stack([lat, lon, sin_doy, cos_doy, sst])


def extract_targets(df: pd.DataFrame, target_cols: list[str] | None = None) -> np.ndarray:
    """Extract 15 depth target temperatures [N, 15] from dataframe."""
    cols = target_cols or DEPTH_COLS
    return np.asarray(df[cols].to_numpy(dtype=np.float64), dtype=np.float64)


class BaseReconstructionModel(ABC):
    """Abstract interface for subsurface temperature reconstruction models."""

    @abstractmethod
    def fit(self, df: pd.DataFrame, targets: np.ndarray | None = None) -> BaseReconstructionModel:
        """Fit model on training dataframe and target temperature matrix."""
        ...

    @abstractmethod
    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """Predict vertical temperature profiles [N, 15] for input samples."""
        ...


class ClimatologyBaseline(BaseReconstructionModel):
    """Monthly climatology baseline.

    Computes monthly average vertical temperature profiles for the North Indian Ocean.
    Falls back to global training mean if a month is unobserved.
    """

    def __init__(self) -> None:
        self.monthly_profiles: dict[int, np.ndarray] = {}
        self.overall_mean: np.ndarray = np.zeros(len(STANDARD_DEPTHS))

    def fit(self, df: pd.DataFrame, targets: np.ndarray | None = None) -> ClimatologyBaseline:
        y = targets if targets is not None else extract_targets(df)
        df_work = df.copy()
        if "month" not in df_work.columns:
            if "date" in df_work.columns:
                df_work["month"] = pd.to_datetime(df_work["date"]).dt.month
            elif "day_of_year" in df_work.columns:
                df_work["month"] = (df_work["day_of_year"] // 30.5).clip(1, 12).astype(int)
            else:
                df_work["month"] = 6

        # Overall mean per depth (ignoring NaNs)
        self.overall_mean = np.nanmean(y, axis=0)

        # Monthly mean per depth
        for m in range(1, 13):
            mask_m = (df_work["month"] == m).to_numpy()
            if np.any(mask_m):
                month_y = y[mask_m]
                month_mean = np.nanmean(month_y, axis=0)
                # If any depth in that month is NaN, fill with overall mean
                month_mean = np.where(np.isnan(month_mean), self.overall_mean, month_mean)
                self.monthly_profiles[m] = month_mean
            else:
                self.monthly_profiles[m] = self.overall_mean.copy()

        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        df_work = df.copy()
        if "month" not in df_work.columns:
            if "date" in df_work.columns:
                months = pd.to_datetime(df_work["date"]).dt.month.to_numpy()
            elif "day_of_year" in df_work.columns:
                months = (df_work["day_of_year"] // 30.5).clip(1, 12).astype(int).to_numpy()
            else:
                months = np.full(len(df_work), 6, dtype=int)
        else:
            months = df_work["month"].to_numpy(dtype=int)

        preds = np.zeros((len(df_work), len(STANDARD_DEPTHS)), dtype=np.float64)
        for i, m in enumerate(months):
            preds[i] = self.monthly_profiles.get(m, self.overall_mean)

        return preds


class RidgeAnomalyBaseline(BaseReconstructionModel):
    """Climatology + Ridge regression on SST anomaly.

    First removes climatology:
        SST_anom = SST - SST_clim
    Then fits Ridge regression per depth to predict subsurface temperature anomalies:
        T_anom(d) = w_d * SST_anom + b_d
    """

    def __init__(self, alpha: float = 1.0) -> None:
        self.alpha = alpha
        self.climatology = ClimatologyBaseline()
        self.regressors: list[Ridge] = []

    def fit(self, df: pd.DataFrame, targets: np.ndarray | None = None) -> RidgeAnomalyBaseline:
        y = targets if targets is not None else extract_targets(df)
        self.climatology.fit(df, y)
        y_clim = self.climatology.predict(df)

        sst = df["sst"].to_numpy(dtype=np.float64)
        sst_clim = y_clim[:, 0]  # depth 0 is surface SST
        sst_anom = (sst - sst_clim).reshape(-1, 1)

        y_anom = y - y_clim

        self.regressors = []
        for i in range(y.shape[1]):
            valid = ~np.isnan(sst_anom.ravel()) & ~np.isnan(y_anom[:, i])
            rg = Ridge(alpha=self.alpha)
            if np.sum(valid) > 5:
                rg.fit(sst_anom[valid], y_anom[valid, i])
            else:
                rg.coef_ = np.array([0.0])
                rg.intercept_ = 0.0
            self.regressors.append(rg)

        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        y_clim = self.climatology.predict(df)
        sst = df["sst"].to_numpy(dtype=np.float64)
        sst_clim = y_clim[:, 0]
        sst_anom = (sst - sst_clim).reshape(-1, 1)

        y_pred = y_clim.copy()
        for i, rg in enumerate(self.regressors):
            y_pred[:, i] += rg.predict(sst_anom)

        return y_pred


class GradientBoostedBaseline(BaseReconstructionModel):
    """Gradient-boosted decision trees baseline (HistGradientBoosting / LightGBM).

    Trains a gradient boosted regressor per depth using the 5 surface features:
        [lat, lon, sin_doy, cos_doy, sst].
    """

    def __init__(self, max_iter: int = 100, max_depth: int = 6, random_state: int = 42) -> None:
        self.max_iter = max_iter
        self.max_depth = max_depth
        self.random_state = random_state
        self.models: list[Any] = []

    def fit(self, df: pd.DataFrame, targets: np.ndarray | None = None) -> GradientBoostedBaseline:
        from sklearn.ensemble import HistGradientBoostingRegressor

        x = prepare_features(df)
        y = targets if targets is not None else extract_targets(df)

        self.models = []
        self.fallback_means = []
        for i in range(y.shape[1]):
            valid = ~np.isnan(y[:, i])
            mean_val = float(np.nanmean(y[valid, i])) if np.any(valid) else 20.0
            self.fallback_means.append(mean_val)

            gbr = HistGradientBoostingRegressor(
                max_iter=self.max_iter,
                max_depth=self.max_depth,
                random_state=self.random_state,
            )
            if np.sum(valid) >= 5:
                gbr.fit(x[valid], y[valid, i])
                self.models.append(gbr)
            else:
                self.models.append(None)

        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        x = prepare_features(df)
        preds = np.zeros((len(df), len(self.models)), dtype=np.float64)
        for i, m in enumerate(self.models):
            if m is not None:
                preds[:, i] = m.predict(x)
            else:
                fallback = self.fallback_means[i] if hasattr(self, "fallback_means") else 20.0
                preds[:, i] = fallback
        return preds


class V1OceanEmbedNetBaseline(BaseReconstructionModel):
    """Evaluates the v1 OceanEmbedNet model (5 -> 64 -> 16 -> 64 -> 15).

    Loads weights from model/model.pt and normalisation statistics from model/scaler.json.
    Evaluates honestly on any given hold-out split.
    """

    def __init__(
        self,
        model_path: str | Path = "model/model.pt",
        scaler_path: str | Path = "model/scaler.json",
    ) -> None:
        self.model_path = Path(model_path)
        self.scaler_path = Path(scaler_path)
        self.loaded = False
        self.mean: np.ndarray = np.zeros(5)
        self.std: np.ndarray = np.ones(5)
        self.torch_model: Any = None
        self._load()

    def _load(self) -> None:
        if not self.scaler_path.exists():
            logger.warning("Scaler file %s not found; v1 baseline uninitialised.", self.scaler_path)
            return

        with open(self.scaler_path, encoding="utf-8") as f:
            scaler_data = json.load(f)
            self.mean = np.array(scaler_data["mean"], dtype=np.float32)
            self.std = np.array(scaler_data["std"], dtype=np.float32)

        if not self.model_path.exists():
            logger.warning("Model file %s not found; v1 baseline uninitialised.", self.model_path)
            return

        import torch
        import torch.nn as nn

        class OceanEmbedNet(nn.Module):
            def __init__(self, embed_dim: int = 16, hidden: int = 64) -> None:
                super().__init__()
                self.encoder = nn.Sequential(
                    nn.Linear(5, hidden),
                    nn.ReLU(),
                    nn.Linear(hidden, embed_dim),
                )
                self.decoder = nn.Sequential(
                    nn.Linear(embed_dim, hidden),
                    nn.ReLU(),
                    nn.Linear(hidden, 15),
                )

            def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
                emb = self.encoder(x)
                out = self.decoder(emb)
                return out, emb

        ckpt = torch.load(self.model_path, map_location="cpu", weights_only=True)
        embed_dim = ckpt.get("embed_dim", 16) if isinstance(ckpt, dict) else 16
        hidden = ckpt.get("hidden", 64) if isinstance(ckpt, dict) else 64
        state_dict = (
            ckpt["model_state"] if isinstance(ckpt, dict) and "model_state" in ckpt else ckpt
        )

        model = OceanEmbedNet(embed_dim=embed_dim, hidden=hidden)
        model.load_state_dict(state_dict)
        model.eval()
        self.torch_model = model
        self.loaded = True

    def fit(self, df: pd.DataFrame, targets: np.ndarray | None = None) -> V1OceanEmbedNetBaseline:
        """V1 model is already trained and frozen; fit is a no-op."""
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        if not self.loaded or self.torch_model is None:
            raise RuntimeError("v1 OceanEmbedNet is not loaded.")

        import torch

        x = prepare_features(df)
        x_norm = (x - self.mean) / self.std

        with torch.no_grad():
            x_t = torch.from_numpy(x_norm)
            out_t, _ = self.torch_model(x_t)
            return np.asarray(out_t.numpy(), dtype=np.float64)
