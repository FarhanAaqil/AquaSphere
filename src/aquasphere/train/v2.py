"""
Protocol v2 profile models (roadmap Phase 4, blueprint §9): Tier A point model, Tier B patch
encoder, Tier C pre-trained patch encoder, all predicting the anomaly against the training-years
climatology with a masked heteroscedastic loss.

Inputs are the 18 Tier A scalars (lat, lon, season, 7 channels, 7 availability flags) and, for
Tiers B and C, the 4-lag 9x9 patch stack plus a land channel (aquasphere.data.patches).

Nowcast mode (blueprint §8): only SST and SLA arrive in real time. One model serves both modes:
during training a share of samples has every other sensor masked out, exactly as at inference in
nowcast mode, and single channels are dropped at random so the model never relies on a sensor
being present.

Only training-partition data is used to fit: climatology, standardisation, early stopping (on
10% of training floats held out by float) and patch statistics all come from 2015-2022.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import torch
from torch import nn

from aquasphere.constants import STANDARD_DEPTHS
from aquasphere.data.patches import CHANNELS as PATCH_CHANNELS
from aquasphere.data.patches import LAGS
from aquasphere.eval.baselines_v2 import CHANNELS, Climatology, season_features, targets
from aquasphere.models.decoder import TierAModel
from aquasphere.models.losses import MaskedHeteroscedasticLoss
from aquasphere.models.patch_cnn import PatchCNNEncoder, TierBModel
from aquasphere.models.ssl import PatchDecoder, TierCModel, generate_patch_mask

logger = logging.getLogger(__name__)

FEATURES = ["lat", "lon", "sin_doy", "cos_doy", *CHANNELS, *(f"{c}_avail" for c in CHANNELS)]
N_CH = len(CHANNELS)
MODES: dict[str, tuple[str, ...]] = {"delayed": tuple(CHANNELS), "nowcast": ("sst", "sla")}
# E3 sensor ablation (blueprint E3): SST, then +SLA, +SSS, +wind/currents
ABLATION: dict[str, tuple[str, ...]] = {
    "A1": ("sst",),
    "A2": ("sst", "sla"),
    "A3": ("sst", "sla", "sss"),
    "A4": tuple(CHANNELS),
}
# Patch channel k for each scalar channel name (SST enters the patch as an anomaly)
_PATCH_OF = {c: PATCH_CHANNELS.index("sst_anom" if c == "sst" else c) for c in CHANNELS}
PATCH_IN = len(LAGS) * len(PATCH_CHANNELS) + 1  # + land channel
THERMO = [STANDARD_DEPTHS.index(d) for d in (50, 75, 100, 125, 150)]


@dataclass
class Config:
    tier: str = "A"  # "A" point MLP | "B" patch CNN | "C" patch CNN with a pre-trained encoder
    channels: tuple[str, ...] = tuple(CHANNELS)  # sensors the model may ever see (E3)
    nowcast_share: float = 0.3  # share of training samples drawn in nowcast mode
    channel_dropout: float = 0.1  # per-sensor dropout on top, SST excluded
    epochs: int = 40
    warmup: int = 5  # epochs of masked MSE before the likelihood (blueprint §9.3)
    batch: int = 256
    lr: float = 1e-3
    weight_decay: float = 1e-4
    lambda_grad: float = 0.01
    lambda_phys: float = 0.001
    eps_inv: float = 0.05  # inversions do occur in NIO profiles: tolerate small ones
    patience: int = 8
    label_fraction: float = 1.0  # share of training floats with labels (E5 learning curves)
    freeze_epochs: int = 3  # Tier C: encoder frozen for these epochs, then unfrozen
    finetune_lr: float = 3e-4  # Tier C encoder learning rate after unfreezing
    extra: dict[str, Any] = field(default_factory=dict)


def scalar_features(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Raw scalars [N, 11] (NaN where a sensor is missing) and availability [N, 7]."""
    chans = df[CHANNELS].to_numpy(dtype=np.float64)
    base = np.column_stack(
        [df[["lat", "lon"]].to_numpy(dtype=np.float64), season_features(df), chans]
    )
    return base, np.isfinite(chans)


class PatchNorm:
    """Per-channel mean and std of the patch stack, fitted on training-year patches only."""

    def fit(self, patches: np.ndarray) -> PatchNorm:
        x = patches.astype(np.float32)
        self.mu = np.nan_to_num(np.nanmean(x, axis=(0, 3, 4)))  # [L, C]
        sd = np.nanstd(x, axis=(0, 3, 4))
        self.sd = np.where(np.isfinite(sd) & (sd > 1e-6), sd, 1.0)
        return self

    def apply(self, patches: np.ndarray) -> np.ndarray:
        """Standardised float16 stack [N, L, C, 9, 9] with NaN kept for missing pixels."""
        out = (patches.astype(np.float32) - self.mu[None, :, :, None, None]) / self.sd[
            None, :, :, None, None
        ]
        return np.asarray(out, dtype=np.float16)

    def to_dict(self) -> dict[str, Any]:
        return {"mu": self.mu.tolist(), "sd": self.sd.tolist()}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PatchNorm:
        p = cls()
        p.mu, p.sd = np.asarray(d["mu"]), np.asarray(d["sd"])
        return p


def patch_tensor(std: np.ndarray, land: np.ndarray, keep: np.ndarray) -> torch.Tensor:
    """[B, L*C + 1, 9, 9] network input: standardised values (0 where missing or masked) + land.

    keep: [B, 7] boolean, scalar-channel order; a dropped sensor is zeroed at every lag.
    """
    x = np.nan_to_num(std.astype(np.float32))
    for j, c in enumerate(CHANNELS):
        x[:, :, _PATCH_OF[c]] *= keep[:, j, None, None, None]
    b = x.shape[0]
    flat = x.reshape(b, -1, x.shape[-2], x.shape[-1])
    return torch.from_numpy(np.concatenate([flat, land[:, None].astype(np.float32)], axis=1))


class _Net(nn.Module):
    """One forward signature for all tiers: (scalars, patches | None) -> (mean, log_s2, emb)."""

    def __init__(self, tier: str, encoder: PatchCNNEncoder | None = None) -> None:
        super().__init__()
        self.tier = tier
        if tier == "A":
            self.net: nn.Module = TierAModel(input_dim=len(FEATURES))
        elif tier == "B":
            self.net = TierBModel(in_channels=PATCH_IN, scalar_dim=len(FEATURES))
        else:
            self.net = TierCModel(
                pretrained_encoder=encoder, in_channels=PATCH_IN, scalar_dim=len(FEATURES)
            )

    def forward(
        self, s: torch.Tensor, p: torch.Tensor | None
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        out: tuple[torch.Tensor, torch.Tensor, torch.Tensor]
        out = self.net(s) if self.tier == "A" else self.net(p, s)
        return out


class ProfileModel:
    """Fit on the training partition, predict absolute temperature, sigma and the embedding."""

    def __init__(self, cfg: Config | None = None) -> None:
        self.cfg = cfg or Config()

    # ── inputs ──────────────────────────────────────────────────────────────
    def _keep(self, avail: np.ndarray, sensors: tuple[str, ...]) -> np.ndarray:
        allowed = np.array([c in sensors and c in self.cfg.channels for c in CHANNELS])
        return np.asarray(avail & allowed[None, :], dtype=bool)

    def _scalars(self, base: np.ndarray, keep: np.ndarray) -> torch.Tensor:
        z = np.nan_to_num((base - self.mu) / self.sd)
        z[:, 4:] *= keep  # a masked sensor reads as the training mean, with its flag at 0
        return torch.tensor(np.column_stack([z, keep]), dtype=torch.float32)

    # ── training ────────────────────────────────────────────────────────────
    def fit(
        self,
        train: pd.DataFrame,
        seed: int = 0,
        patches: np.ndarray | None = None,
        land: np.ndarray | None = None,
        patch_norm: PatchNorm | None = None,
        encoder: PatchCNNEncoder | None = None,
    ) -> ProfileModel:
        """patches/land: aligned with `train` rows; required for Tiers B and C."""
        cfg = self.cfg
        torch.manual_seed(seed)
        rng = np.random.default_rng(seed)
        y, mask = targets(train)
        self.clim = Climatology().fit(train, y)
        base, avail = scalar_features(train)
        self.mu = np.nan_to_num(np.nanmean(base, axis=0))
        sd = np.nanstd(base, axis=0)
        self.sd = np.where(sd > 1e-9, sd, 1.0)
        clim = self.clim.predict(train)
        anom = np.nan_to_num(y - clim)
        self.patch_norm = patch_norm
        std = patch_norm.apply(patches) if patches is not None and patch_norm else None

        # Hold out 10% of training floats for early stopping; optionally keep only a share of
        # the remaining floats' labels (E5)
        floats = train["float_id"].astype(str).to_numpy()
        uniq = np.array(sorted(set(floats)))
        rng.shuffle(uniq)
        n_stop = max(1, round(0.1 * len(uniq)))
        stop_f = set(uniq[:n_stop])
        fit_f = uniq[n_stop:]
        if cfg.label_fraction < 1.0:
            fit_f = fit_f[: max(1, round(cfg.label_fraction * len(fit_f)))]
        fit_set = set(fit_f)
        fit_idx = np.flatnonzero([f in fit_set for f in floats])
        stop_idx = np.flatnonzero([f in stop_f for f in floats])
        self.train_floats = sorted(set(floats))
        self.n_label_floats = len(fit_set)

        self.model = _Net(cfg.tier, encoder)
        loss_fn = MaskedHeteroscedasticLoss(
            lambda_grad=cfg.lambda_grad, lambda_phys=cfg.lambda_phys, eps_inv=cfg.eps_inv
        )
        params: list[dict[str, Any]]
        enc_params: list[nn.Parameter] = []
        if cfg.tier == "C" and encoder is not None:
            enc_params = list(self.model.net.patch_encoder.parameters())
            enc_ids = {id(p) for p in enc_params}
            rest = [p for p in self.model.parameters() if id(p) not in enc_ids]
            params = [{"params": rest, "lr": cfg.lr}, {"params": enc_params, "lr": 0.0}]
        else:
            params = [{"params": list(self.model.parameters()), "lr": cfg.lr}]
        opt = torch.optim.AdamW(params, weight_decay=cfg.weight_decay)

        t_anom = torch.tensor(anom, dtype=torch.float32)
        t_mask = torch.tensor(mask, dtype=torch.float32)
        t_clim = torch.tensor(clim, dtype=torch.float32)
        others = np.array([c not in MODES["nowcast"] for c in CHANNELS])
        not_sst = np.array([c != "sst" for c in CHANNELS])
        best = (np.inf, copy.deepcopy(self.model.state_dict()))
        stale = 0
        self.history: list[dict[str, float]] = []
        for epoch in range(cfg.epochs):
            if enc_params and epoch == cfg.freeze_epochs:
                opt.param_groups[1]["lr"] = cfg.finetune_lr
            self.model.train()
            order = rng.permutation(fit_idx)
            for start in range(0, len(order), cfg.batch):
                idx = order[start : start + cfg.batch]
                keep = self._keep(avail[idx], tuple(CHANNELS))
                # Nowcast samples: only SST and SLA; plus independent single-sensor dropout
                now = rng.random(len(idx)) < cfg.nowcast_share
                keep[now] &= ~others[None, :]
                keep &= ~((rng.random(keep.shape) < cfg.channel_dropout) & not_sst[None, :])
                s = self._scalars(base[idx], keep)
                p = (
                    patch_tensor(std[idx], land[idx], keep)
                    if std is not None and land is not None
                    else None
                )
                mean, log_s2, _ = self.model(s, p)
                loss = loss_fn(
                    mean,
                    log_s2,
                    t_anom[idx],
                    mask=t_mask[idx],
                    use_nll=epoch >= cfg.warmup,
                    offset=t_clim[idx],
                )
                opt.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), 2.0)
                opt.step()
            # Early stopping on held-out training floats, delayed mode, thermocline RMSE
            pred, _, _ = self._forward(
                train.iloc[stop_idx],
                "delayed",
                std[stop_idx] if std is not None else None,
                land[stop_idx] if land is not None else None,
            )
            err = np.where(mask[stop_idx][:, THERMO], pred[:, THERMO] - y[stop_idx][:, THERMO], 0)
            n = max(int(mask[stop_idx][:, THERMO].sum()), 1)
            score = float(np.sqrt((err**2).sum() / n))
            self.history.append({"epoch": epoch + 1, "stop_thermo_rmse": score})
            # Selection starts once the likelihood is on (or at the last epoch of a short run)
            eligible = epoch >= min(cfg.warmup, cfg.epochs - 1)
            if eligible and score < best[0] - 1e-4:
                best, stale = (score, copy.deepcopy(self.model.state_dict())), 0
            elif eligible:
                stale += 1
                if stale >= cfg.patience:
                    break
        self.model.load_state_dict(best[1])
        self.model.eval()
        self.stop_score = best[0]
        logger.info("tier %s seed %d: stop-set thermocline RMSE %.3f", cfg.tier, seed, best[0])
        return self

    # ── inference ───────────────────────────────────────────────────────────
    def _forward(
        self,
        df: pd.DataFrame,
        mode: str,
        std: np.ndarray | None,
        land: np.ndarray | None,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        base, avail = scalar_features(df)
        keep = self._keep(avail, MODES[mode])
        self.model.eval()
        means, sigmas, embs = [], [], []
        with torch.no_grad():
            for start in range(0, len(df), 4096):
                sl = slice(start, start + 4096)
                s = self._scalars(base[sl], keep[sl])
                p = (
                    patch_tensor(std[sl], land[sl], keep[sl])
                    if std is not None and land is not None
                    else None
                )
                mean, log_s2, emb = self.model(s, p)
                means.append(mean.numpy())
                sigmas.append(np.exp(0.5 * log_s2.clamp(-6.0, 4.0).numpy()))
                embs.append(emb.numpy())
        clim = self.clim.predict(df)
        return clim + np.concatenate(means), np.concatenate(sigmas), np.concatenate(embs)

    def predict(
        self,
        df: pd.DataFrame,
        mode: str = "delayed",
        patches: np.ndarray | None = None,
        land: np.ndarray | None = None,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Absolute temperature [N, 15], sigma [N, 15] (°C) and embedding [N, d]."""
        if mode not in MODES:
            raise ValueError(f"mode must be one of {sorted(MODES)}")
        std = self.patch_norm.apply(patches) if patches is not None and self.patch_norm else None
        return self._forward(df, mode, std, land)

    # ── persistence (plain types and tensors only: torch.load(weights_only=True)) ──
    def state(self) -> dict[str, Any]:
        cfg = asdict(self.cfg)
        cfg["channels"] = list(cfg["channels"])
        return {
            "config": cfg,
            "model_state": self.model.state_dict(),
            "mu": self.mu.tolist(),
            "sd": self.sd.tolist(),
            "climatology": self.clim.to_dict(),
            "patch_norm": self.patch_norm.to_dict() if self.patch_norm else None,
            "features": FEATURES,
            "train_float_ids": self.train_floats,
        }

    @classmethod
    def from_state(cls, st: dict[str, Any]) -> ProfileModel:
        cfg = dict(st["config"])
        cfg["channels"] = tuple(cfg["channels"])
        m = cls(Config(**cfg))
        m.mu, m.sd = np.asarray(st["mu"]), np.asarray(st["sd"])
        m.clim = Climatology.from_dict(st["climatology"])
        m.patch_norm = PatchNorm.from_dict(st["patch_norm"]) if st.get("patch_norm") else None
        m.train_floats = list(st.get("train_float_ids", []))
        m.model = _Net(m.cfg.tier)
        m.model.load_state_dict(st["model_state"])
        m.model.eval()
        return m


# ── Tier C pre-training (blueprint §9.2) ──────────────────────────────────────


class _Pretrainer(nn.Module):
    def __init__(self, temporal: bool) -> None:
        super().__init__()
        self.encoder = PatchCNNEncoder(in_channels=PATCH_IN)
        self.recon = PatchDecoder(embed_dim=32, out_channels=PATCH_IN)
        # Temporal pretext: predict the lag-0 fields from lags of 7 days or more
        self.forecast = (
            PatchDecoder(embed_dim=32, out_channels=len(PATCH_CHANNELS)) if temporal else None
        )


def pretrain(
    patches: np.ndarray,
    land: np.ndarray,
    patch_norm: PatchNorm,
    variant: str = "masked",
    epochs: int = 15,
    batch: int = 512,
    seed: int = 0,
    mask_ratio: float = 0.5,
) -> tuple[PatchCNNEncoder, list[float]]:
    """Masked reconstruction ("masked") or masked + temporal forecasting ("masked+temporal").

    Unlabelled patches must come from training years only. The loss is computed only on pixels
    that were observed and are not land.
    """
    if variant not in ("masked", "masked+temporal"):
        raise ValueError(variant)
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    std = patch_norm.apply(patches)
    model = _Pretrainer(temporal=variant == "masked+temporal")
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    all_keep = np.ones((batch, N_CH), dtype=bool)
    lag0 = len(PATCH_CHANNELS)
    losses: list[float] = []
    for _ in range(epochs):
        total, nb = 0.0, 0
        order = rng.permutation(len(std))
        for start in range(0, len(std), batch):
            idx = order[start : start + batch]
            x = patch_tensor(std[idx], land[idx], all_keep[: len(idx)])
            valid = torch.from_numpy(
                np.concatenate(
                    [
                        np.isfinite(std[idx].astype(np.float32)).reshape(len(idx), -1, 9, 9)
                        & ~land[idx][:, None],
                        np.zeros((len(idx), 1, 9, 9), dtype=bool),  # never reconstruct land
                    ],
                    axis=1,
                ).astype(np.float32)
            )
            hide = generate_patch_mask(len(idx), PATCH_IN, 9, 9, mask_ratio=mask_ratio)
            rec = model.recon(model.encoder(x * (1.0 - hide)))
            w = hide * valid
            loss = (((rec - x) ** 2) * w).sum() / w.sum().clamp(min=1.0)
            if model.forecast is not None:
                past = x.clone()
                past[:, :lag0] = 0.0
                fc = model.forecast(model.encoder(past))
                w0 = valid[:, :lag0]
                loss = loss + (((fc - x[:, :lag0]) ** 2) * w0).sum() / w0.sum().clamp(min=1.0)
            opt.zero_grad()
            loss.backward()
            opt.step()
            total += float(loss.item())
            nb += 1
        losses.append(total / max(nb, 1))
        logger.info("pretrain %s epoch %d loss %.4f", variant, len(losses), losses[-1])
    model.encoder.eval()
    return model.encoder, losses
