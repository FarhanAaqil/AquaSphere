"""
Baseline ladder for evaluation protocol v2 (blueprint §12), on the real collocated table.

    B0  Climatology: T_clim(z; lat, lon, month) from training years only
    B1  B0 + per-depth ridge on SST and SLA anomalies
    B2  B0 + per-depth LightGBM on all Tier A inputs (NaN-native, so masks are implicit)
    B3  v1 network architecture (5 -> 64 -> 16 -> 64 -> 15) retrained on the training partition
        (the old v1 weights were trained on 2025 data, i.e. the test period, and are not used)
    B4  Deep ensemble of 5 Tier A heteroscedastic networks: the uncertainty baseline

Hyperparameters are fixed defaults, not tuned: protocol v2 forbids tuning before the hypotheses
are frozen. Every model sees training-partition data only; climatology and normalisation
statistics are fitted on it too.
"""

from __future__ import annotations

from typing import Any, Protocol

import numpy as np
import pandas as pd
import torch
from torch import nn

from aquasphere.constants import STANDARD_DEPTHS
from aquasphere.models.decoder import TierAModel
from aquasphere.models.losses import MaskedHeteroscedasticLoss

T_COLS = [f"t_{d}" for d in STANDARD_DEPTHS]
M_COLS = [f"m_{d}" for d in STANDARD_DEPTHS]
CHANNELS = ["sst", "sss", "sla", "ug", "vg", "u10", "v10"]
MIN_CELL = 5  # observations needed before a climatology cell is trusted


class Baseline(Protocol):
    name: str

    def fit(self, train: pd.DataFrame, seed: int = 0) -> Baseline: ...

    def predict(self, df: pd.DataFrame) -> np.ndarray: ...


def targets(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    mask = df[M_COLS].to_numpy(dtype=bool)
    y = df[T_COLS].to_numpy(dtype=np.float64)
    return np.where(mask, y, np.nan), mask


def season_features(df: pd.DataFrame) -> np.ndarray:
    doy = pd.to_datetime(df["date"]).dt.dayofyear.to_numpy(dtype=np.float64)
    return np.column_stack([np.sin(2 * np.pi * doy / 365.25), np.cos(2 * np.pi * doy / 365.25)])


def tier_a_features(df: pd.DataFrame) -> np.ndarray:
    """[lat, lon, sin_doy, cos_doy, 7 channels (NaN when missing), 7 availability flags]."""
    chans = df[CHANNELS].to_numpy(dtype=np.float64)
    avail = np.isfinite(chans).astype(np.float64)
    return np.column_stack(
        [df[["lat", "lon"]].to_numpy(dtype=np.float64), season_features(df), chans, avail]
    )


class Climatology:
    """Monthly gridded climatology with fallback 2° -> 5° -> basin-month -> overall."""

    LEVELS = (2.0, 5.0, None)

    def fit(self, df: pd.DataFrame, values: np.ndarray) -> Climatology:
        self.width = values.shape[1]
        month = pd.to_datetime(df["date"]).dt.month.to_numpy()
        self.overall = np.nanmean(values, axis=0)
        self.tables: list[dict[tuple[Any, ...], np.ndarray]] = []
        for res in self.LEVELS:
            keys = self._keys(df["lat"].to_numpy(), df["lon"].to_numpy(), month, res)
            frame = pd.DataFrame(values).assign(_k=keys)
            means = frame.groupby("_k").mean()
            counts = frame.groupby("_k").count()
            table = {
                k: np.where(c >= MIN_CELL, mm, np.nan)
                for k, mm, c in zip(means.index, means.to_numpy(), counts.to_numpy(), strict=True)
            }
            self.tables.append(table)
        return self

    @staticmethod
    def _keys(
        lat: np.ndarray, lon: np.ndarray, month: np.ndarray, res: float | None
    ) -> list[tuple[Any, ...]]:
        if res is None:
            return [(int(m),) for m in month]
        return [
            (int(m), int(np.floor(a / res)), int(np.floor(b / res)))
            for a, b, m in zip(lat, lon, month, strict=True)
        ]

    def to_dict(self) -> dict[str, Any]:
        """Plain lists only, so a checkpoint loads with torch.load(weights_only=True)."""
        return {
            "width": int(self.width),
            "overall": [float(v) for v in self.overall],
            "tables": [
                [
                    [list(k), [None if np.isnan(v) else float(v) for v in row]]
                    for k, row in t.items()
                ]
                for t in self.tables
            ],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Climatology:
        c = cls()
        c.width = int(d["width"])
        c.overall = np.asarray(d["overall"], dtype=np.float64)
        c.tables = [
            {tuple(k): np.array([np.nan if v is None else v for v in row]) for k, row in t}
            for t in d["tables"]
        ]
        return c

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        month = pd.to_datetime(df["date"]).dt.month.to_numpy()
        out = np.full((len(df), self.width), np.nan)
        for res, table in zip(self.LEVELS, self.tables, strict=True):
            keys = self._keys(df["lat"].to_numpy(), df["lon"].to_numpy(), month, res)
            for i, k in enumerate(keys):
                row = table.get(k)
                if row is not None:
                    fill = np.isnan(out[i])
                    out[i, fill] = row[fill]
        return np.where(np.isnan(out), self.overall, out)


class B0Climatology:
    name = "B0 Climatology"

    def fit(self, train: pd.DataFrame, seed: int = 0) -> B0Climatology:
        y, _ = targets(train)
        self.clim = Climatology().fit(train, y)
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return self.clim.predict(df)


class _AnomalyModel:
    """Shared plumbing: climatology from training years, learn the anomaly on top."""

    def _prepare(self, train: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        y, mask = targets(train)
        self.clim = Climatology().fit(train, y)
        self.sst_clim = Climatology().fit(train, train[["sst"]].to_numpy(dtype=np.float64))
        return y - self.clim.predict(train), mask


class B1Ridge(_AnomalyModel):
    name = "B1 Climatology + ridge (SST, SLA anomalies)"

    def _x(self, df: pd.DataFrame) -> np.ndarray:
        sst_anom = df["sst"].to_numpy(dtype=np.float64) - self.sst_clim.predict(df)[:, 0]
        sla = df["sla"].to_numpy(dtype=np.float64)
        x = np.column_stack(
            [np.nan_to_num(sst_anom), np.nan_to_num(sla), np.isfinite(sla), season_features(df)]
        )
        return (x - self.mu) / self.sd

    def fit(self, train: pd.DataFrame, seed: int = 0) -> B1Ridge:
        from sklearn.linear_model import Ridge

        anom, mask = self._prepare(train)
        self.mu, self.sd = np.zeros(5), np.ones(5)
        raw = self._x(train)
        self.mu, self.sd = raw.mean(axis=0), np.where(raw.std(axis=0) > 0, raw.std(axis=0), 1.0)
        x = self._x(train)
        self.models = [
            Ridge(alpha=1.0).fit(x[mask[:, k]], anom[mask[:, k], k])
            for k in range(len(STANDARD_DEPTHS))
        ]
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        x = self._x(df)
        anomaly = np.column_stack([np.asarray(m.predict(x), dtype=np.float64) for m in self.models])
        return np.asarray(self.clim.predict(df) + anomaly, dtype=np.float64)


class B2LightGBM(_AnomalyModel):
    name = "B2 Climatology + LightGBM (all Tier A inputs)"

    def fit(self, train: pd.DataFrame, seed: int = 0) -> B2LightGBM:
        import lightgbm as lgb

        anom, mask = self._prepare(train)
        x = tier_a_features(train)
        params: dict[str, Any] = {
            "n_estimators": 400,
            "learning_rate": 0.05,
            "num_leaves": 31,
            "min_child_samples": 20,
            "subsample": 0.8,
            "subsample_freq": 1,
            "colsample_bytree": 0.8,
            "random_state": seed,
            "verbose": -1,
        }
        self.models = [
            lgb.LGBMRegressor(**params).fit(x[mask[:, k]], anom[mask[:, k], k])
            for k in range(len(STANDARD_DEPTHS))
        ]
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        x = tier_a_features(df)
        anomaly = np.column_stack([np.asarray(m.predict(x), dtype=np.float64) for m in self.models])
        return np.asarray(self.clim.predict(df) + anomaly, dtype=np.float64)


def _standardise(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mu = np.nanmean(x, axis=0)
    sd = np.nanstd(x, axis=0)
    return np.nan_to_num(mu), np.where(sd > 1e-9, sd, 1.0)


class B3V1Net:
    """The v1 architecture, retrained on the training partition with masked MSE."""

    name = "B3 v1 network (retrained, blocked protocol)"
    EPOCHS = 40

    def _x(self, df: pd.DataFrame) -> np.ndarray:
        raw = np.column_stack(
            [
                df[["lat", "lon"]].to_numpy(dtype=np.float64),
                season_features(df),
                df["sst"].to_numpy(dtype=np.float64),
            ]
        )
        x: np.ndarray = np.nan_to_num((raw - self.mu) / self.sd)
        return x

    def fit(self, train: pd.DataFrame, seed: int = 0) -> B3V1Net:
        torch.manual_seed(seed)
        y, mask = targets(train)
        raw = np.column_stack(
            [
                train[["lat", "lon"]].to_numpy(dtype=np.float64),
                season_features(train),
                train["sst"].to_numpy(dtype=np.float64),
            ]
        )
        self.mu, self.sd = _standardise(raw)
        self.y_mu, self.y_sd = _standardise(y)
        self.net = nn.Sequential(
            nn.Linear(5, 64),
            nn.ReLU(),
            nn.Linear(64, 16),
            nn.Linear(16, 64),
            nn.ReLU(),
            nn.Linear(64, 15),
        )
        x = torch.tensor(self._x(train), dtype=torch.float32)
        t = torch.tensor(np.nan_to_num((y - self.y_mu) / self.y_sd), dtype=torch.float32)
        m = torch.tensor(mask, dtype=torch.float32)
        opt = torch.optim.Adam(self.net.parameters(), lr=1e-3)
        g = torch.Generator().manual_seed(seed)
        for _ in range(self.EPOCHS):
            for idx in torch.randperm(len(x), generator=g).split(256):
                opt.zero_grad()
                loss = (((self.net(x[idx]) - t[idx]) ** 2) * m[idx]).sum() / m[idx].sum().clamp(
                    min=1
                )
                loss.backward()
                opt.step()
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        with torch.no_grad():
            out = self.net(torch.tensor(self._x(df), dtype=torch.float32)).numpy()
        pred: np.ndarray = out * self.y_sd + self.y_mu
        return pred


class B4DeepEnsemble(_AnomalyModel):
    """Five Tier A heteroscedastic networks; mixture mean and variance (Lakshminarayanan 2017)."""

    name = "B4 Deep ensemble (5 x Tier A)"
    MEMBERS = 5
    EPOCHS = 30
    WARMUP = 5  # epochs of masked MSE before switching to the likelihood (blueprint §9.3)

    def _x(self, df: pd.DataFrame) -> np.ndarray:
        x: np.ndarray = np.nan_to_num((tier_a_features(df) - self.mu) / self.sd)
        return x

    def fit(self, train: pd.DataFrame, seed: int = 0) -> B4DeepEnsemble:
        anom, mask = self._prepare(train)
        self.mu, self.sd = _standardise(tier_a_features(train))
        self.a_sd = np.where(np.nanstd(anom, axis=0) > 1e-9, np.nanstd(anom, axis=0), 1.0)
        x = torch.tensor(self._x(train), dtype=torch.float32)
        t = torch.tensor(np.nan_to_num(anom / self.a_sd), dtype=torch.float32)
        m = torch.tensor(mask, dtype=torch.float32)
        # Anomaly targets: the anti-inversion and gradient terms assume absolute temperatures
        loss_fn = MaskedHeteroscedasticLoss(lambda_grad=0.0, lambda_phys=0.0)
        self.members: list[TierAModel] = []
        for k in range(self.MEMBERS):
            torch.manual_seed(seed * 100 + k)
            net = TierAModel(input_dim=x.shape[1])
            opt = torch.optim.Adam(net.parameters(), lr=1e-3, weight_decay=1e-4)
            g = torch.Generator().manual_seed(seed * 100 + k)
            net.train()
            for epoch in range(self.EPOCHS):
                for idx in torch.randperm(len(x), generator=g).split(256):
                    opt.zero_grad()
                    mean, log_s2, _ = net(x[idx])
                    loss = loss_fn(mean, log_s2, t[idx], m[idx], use_nll=epoch >= self.WARMUP)
                    loss.backward()
                    opt.step()
            net.eval()
            self.members.append(net)
        return self

    def predict_dist(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        x = torch.tensor(self._x(df), dtype=torch.float32)
        means, variances = [], []
        with torch.no_grad():
            for net in self.members:
                mu, log_s2, _ = net(x)
                means.append(mu.numpy() * self.a_sd)
                variances.append(np.exp(log_s2.numpy()) * self.a_sd**2)
        mu_e = np.mean(means, axis=0)
        var_e = (
            np.mean([v + mu**2 for v, mu in zip(variances, means, strict=True)], axis=0) - mu_e**2
        )
        return self.clim.predict(df) + mu_e, np.sqrt(np.maximum(var_e, 1e-12))

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return self.predict_dist(df)[0]


LADDER: dict[str, type[Baseline]] = {
    "B0": B0Climatology,
    "B1": B1Ridge,
    "B2": B2LightGBM,
    "B3": B3V1Net,
    "B4": B4DeepEnsemble,
}
