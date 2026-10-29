"""
Inference engine and model management for AquaSphere serving (SIH 26066).

Features:
- Checkpoint integrity verification and state loading.
- Single & vectorized batch prediction with conformal confidence intervals.
- Oceanographic diagnostics: Mixed Layer Depth (MLD) and 20°C Isotherm Depth (D20).
- Nearest held-out Argo profile resolver.
- Feature attribution via integrated gradients / permutation importance.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch

from aquasphere.constants import DEPTH_COLS, STANDARD_DEPTHS
from aquasphere.data.provenance import MISMATCH, NOT_RECORDED, verify_provenance
from aquasphere.eval.metrics import compute_d20, compute_mld, compute_ohc300
from aquasphere.models.decoder import TierAModel
from aquasphere.serve.membership import ARGO_TABLES, TrainingMembership
from aquasphere.train.calibrate import ConformalCalibrator
from aquasphere.train.train import compute_doy_features

# Protocol v2 model (roadmap Phase 4). Served when present; otherwise the v1 checkpoint below.
V2_CHECKPOINT = Path(os.environ.get("AQUASPHERE_CHECKPOINT_V2", "checkpoints/tier_a_v2/model.pt"))
V2_TABLE = Path("data/processed/argo_nio_collocated.parquet")
CHANNELS = ("sst", "sss", "sla", "ug", "vg", "u10", "v10")
NOWCAST = ("sst", "sla")
MODES = ("delayed", "nowcast")

logger = logging.getLogger(__name__)


@lru_cache(maxsize=4096)
def _season(date: str) -> tuple[float, float, int]:
    """(sin_doy, cos_doy, month index) for a date, parsed once (same formula as training)."""
    sin_doy, cos_doy = compute_doy_features(pd.Series([date]))
    return float(sin_doy[0]), float(cos_doy[0]), int(pd.to_datetime(date).month) - 1


class InferenceEngine:
    """Manages loaded PyTorch neural network, scaler, and conformal calibrator."""

    def __init__(
        self,
        checkpoint_path: Path | str = "checkpoints/tier_a/model_a.pt",
        validation_parquet_path: Path | str = "tests/fixtures/argo_200.parquet",
        device: str = "cpu",
        v2_checkpoint_path: Path | str | None = V2_CHECKPOINT,
    ) -> None:
        self.checkpoint_path = Path(checkpoint_path)
        self.validation_parquet_path = Path(validation_parquet_path)
        self.device = torch.device(device)

        self.model: TierAModel | None = None
        self.scaler_mean: np.ndarray = np.zeros(18, dtype=np.float32)
        self.scaler_std: np.ndarray = np.ones(18, dtype=np.float32)
        self.climatology: np.ndarray = np.full((12, 15), 20.0, dtype=np.float32)
        self.calibrator: ConformalCalibrator = ConformalCalibrator(
            scale_factor=1.65,
            nominal_coverage=0.90,
            n_calibration_samples=100,
            empirical_val_coverage=0.90,
        )
        self.model_version = "tier_a_v1.0"
        self.data_version = "2026.1"
        self.is_ready = False
        self.weights = "untrained"
        self._checkpoint: dict[str, Any] | None = None
        self.provenance: dict[str, Any] = {}
        self.provenance_status = NOT_RECORDED
        self.provenance_detail = "No checkpoint loaded."

        # Protocol v2 serving state (None while the v1 checkpoint is served)
        self.v2: Any = None
        self.conformal: dict[str, Any] = {}
        self.dissimilarity: Any = None

        self.val_df: pd.DataFrame | None = None
        self._load_validation_profiles()
        self._load_checkpoint()
        tables = ARGO_TABLES
        if v2_checkpoint_path is not None and Path(v2_checkpoint_path).exists():
            self._load_v2(Path(v2_checkpoint_path))
            if self.v2 is not None:
                tables = (V2_TABLE, *ARGO_TABLES)
        self.membership = TrainingMembership.resolve(self._checkpoint, tables=tables)

    @property
    def interval_method(self) -> str:
        if self.v2 is not None:
            return "mondrian_conformal_region_season"
        return "conformal_per_depth"

    def _load_v2(self, path: Path) -> None:
        """Tier A v2: anomaly model, Mondrian conformal per mode, dissimilarity index."""
        from aquasphere.eval.applicability import DissimilarityIndex
        from aquasphere.eval.protocol import partition
        from aquasphere.train.conformal_v2 import MondrianConformal
        from aquasphere.train.v2 import ProfileModel

        try:
            ckpt = torch.load(path, map_location="cpu", weights_only=True)
            if ckpt.get("format") != "aquasphere-v2":
                raise ValueError(f"unexpected checkpoint format {ckpt.get('format')!r}")
            self.v2 = ProfileModel.from_state(ckpt)
            self.conformal = {
                k: MondrianConformal.from_dict(v) for k, v in ckpt["conformal"].items()
            }
            self.dissimilarity = DissimilarityIndex.from_dict(ckpt["dissimilarity"])
        except Exception as e:
            logger.error("Failed loading v2 checkpoint %s: %s; serving v1", path, e)
            self.v2 = None
            return
        self.checkpoint_path = path
        self._checkpoint = ckpt
        self.model_version = str(ckpt.get("model_version", "tier_a_v2"))
        self.weights = "trained"
        self.provenance = dict(ckpt.get("provenance") or {})
        self.provenance_status, self.provenance_detail = verify_provenance(self.provenance)
        self.is_ready = self.provenance_status != MISMATCH
        # Held-out lookups come from the protocol v2 validation year: never training floats
        if V2_TABLE.exists():
            try:
                self.val_df = partition(pd.read_parquet(V2_TABLE), "val")
            except Exception as e:
                logger.warning("Could not read %s for validation lookups: %s", V2_TABLE, e)
        logger.info("Serving protocol v2 model %s from %s", self.model_version, path)

    def _load_validation_profiles(self) -> None:
        """Load validation profiles for held-out validation queries."""
        if self.validation_parquet_path.exists():
            try:
                self.val_df = pd.read_parquet(self.validation_parquet_path)
                logger.info("Loaded %d validation profiles for held-out lookup.", len(self.val_df))
            except Exception as e:
                logger.warning(
                    "Could not read validation profiles from %s: %s",
                    self.validation_parquet_path,
                    e,
                )

    def _load_checkpoint(self) -> None:
        """Load trained model weights, scaler, and calibrator."""
        self.model = TierAModel(input_dim=18, hidden_dim=128, embed_dim=16, n_depths=15).to(
            self.device
        )

        if self.checkpoint_path.exists():
            try:
                ckpt = torch.load(self.checkpoint_path, map_location=self.device)
                self.model.load_state_dict(ckpt["model_state"])
                self._checkpoint = ckpt
                self.scaler_mean = np.array(ckpt["scaler"]["mean"], dtype=np.float32)
                self.scaler_std = np.array(ckpt["scaler"]["std"], dtype=np.float32)
                self.scaler_std[self.scaler_std < 1e-4] = 1.0
                self.climatology = np.array(ckpt["climatology"], dtype=np.float32)
                self.calibrator = ConformalCalibrator.from_dict(ckpt["conformal_calibration"])
                self.weights = "trained"
                self.provenance = dict(ckpt.get("provenance") or {})
                self.provenance_status, self.provenance_detail = verify_provenance(self.provenance)
                # A checkpoint whose training data has since changed is not trustworthy.
                self.is_ready = self.provenance_status != MISMATCH
                if not self.is_ready:
                    logger.error("Refusing to report ready: %s", self.provenance_detail)
                logger.info(
                    "Loaded AquaSphere Tier A model from %s (provenance: %s)",
                    self.checkpoint_path,
                    self.provenance_status,
                )
                self.model.eval()
                return
            except Exception as e:
                logger.error("Failed loading checkpoint from %s: %s", self.checkpoint_path, e)

        # Fresh clone / CI: no checkpoint, so the network has random weights. Predictions still
        # work for contract tests, but /ready says so and every response carries the tag.
        logger.warning("No trained checkpoint: serving UNTRAINED weights (not ready).")
        self.model_version = f"{self.model_version}+untrained"
        self.model.eval()
        self.is_ready = False

    def build_feature_vector(
        self,
        lat: float,
        lon: float,
        date: str,
        features: dict[str, float],
    ) -> np.ndarray:
        """Construct normalized 18-d input vector."""
        sin_doy, cos_doy, _ = _season(date)

        sst = features.get("sst", 28.0)
        sss = features.get("sss", 35.0)
        sla = features.get("sla", 0.0)
        ug = features.get("ug", 0.0)
        vg = features.get("vg", 0.0)
        u10 = features.get("u10", 0.0)
        v10 = features.get("v10", 0.0)

        sss_m = 1.0 if "sss" in features else 0.0
        sla_m = 1.0 if "sla" in features else 0.0
        ug_m = 1.0 if "ug" in features else 0.0
        vg_m = 1.0 if "vg" in features else 0.0
        u10_m = 1.0 if "u10" in features else 0.0
        v10_m = 1.0 if "v10" in features else 0.0
        sst_m = 1.0 if "sst" in features else 0.0

        x = np.array(
            [
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
            ],
            dtype=np.float32,
        )
        return x

    def _infer(
        self,
        points: list[dict[str, Any]],
        features_list: list[dict[str, float]],
        mode: str,
    ) -> dict[str, Any]:
        """Arrays for a batch: mean, sigma, embedding, interval, climatology, DI."""
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        if self.v2 is not None:
            from aquasphere.train.conformal_v2 import strata

            df = pd.DataFrame(
                {
                    "lat": [p["lat"] for p in points],
                    "lon": [p["lon"] for p in points],
                    "date": [p["date"] for p in points],
                    **{c: [f.get(c, np.nan) for f in features_list] for c in CHANNELS},
                }
            )
            mean, sigma, emb = self.v2.predict(df, mode=mode)
            reg, sea = strata(df)
            lower, upper = self.conformal[mode].interval(mean, sigma, reg, sea)
            di, inside = self.dissimilarity.in_domain(emb)
            return {
                "mean": mean,
                "sigma": sigma,
                "emb": emb,
                "lower": lower,
                "upper": upper,
                "clim": self.v2.clim.predict(df),
                "di": di,
                "in_domain": inside,
            }

        if self.model is None:
            raise RuntimeError("Model is not initialized.")
        # v1 has availability flags too: nowcast simply withholds the delayed sensors
        keep = CHANNELS if mode == "delayed" else NOWCAST
        x_raw = np.array(
            [
                self.build_feature_vector(
                    p["lat"], p["lon"], p["date"], {k: v for k, v in f.items() if k in keep}
                )
                for p, f in zip(points, features_list, strict=True)
            ],
            dtype=np.float32,
        )
        x_norm = (x_raw - self.scaler_mean) / self.scaler_std
        tx = torch.tensor(x_norm, dtype=torch.float32, device=self.device)
        with torch.no_grad():
            anom, log_s2, emb = self.model(tx)
        clim = np.array([self.climatology[_season(p["date"])[2]] for p in points])
        mean = anom.cpu().numpy() + clim
        sigma = torch.exp(0.5 * log_s2).cpu().numpy()
        lower, upper = self.calibrator.predict_interval(mean, sigma)
        return {
            "mean": mean,
            "sigma": sigma,
            "emb": emb.cpu().numpy(),
            "lower": lower,
            "upper": upper,
            "clim": clim,
            "di": None,
            "in_domain": None,
        }

    def predict_point(
        self,
        lat: float,
        lon: float,
        date: str,
        features: dict[str, float],
        source: str = "offline_synthetic",
        mode: str = "delayed",
    ) -> dict[str, Any]:
        """Perform single point inference."""
        return self.predict_batch(
            [{"lat": lat, "lon": lon, "date": date}], [features], [source], mode=mode
        )[0]

    def predict_batch(
        self,
        points: list[dict[str, Any]],
        features_list: list[dict[str, float]],
        sources_list: list[str],
        mode: str = "delayed",
    ) -> list[dict[str, Any]]:
        """Vectorized batch prediction."""
        if not points:
            return []
        r = self._infer(points, features_list, mode)
        results: list[dict[str, Any]] = []
        for i, p in enumerate(points):
            prof = r["mean"][i]
            mld, d20, ohc = compute_mld(prof), compute_d20(prof), compute_ohc300(prof)
            results.append(
                {
                    "lat": p["lat"],
                    "lon": p["lon"],
                    "date": p["date"],
                    "depths": list(STANDARD_DEPTHS),
                    "temperatures": [float(t) for t in prof],
                    "uncertainties": [float(s) for s in r["sigma"][i]],
                    "interval_lower": [float(v) for v in r["lower"][i]],
                    "interval_upper": [float(v) for v in r["upper"][i]],
                    "embedding": [float(e) for e in r["emb"][i]],
                    "mld": float(mld) if not np.isnan(mld) else None,
                    "d20": float(d20) if not np.isnan(d20) else None,
                    "ohc300": float(ohc) if not np.isnan(ohc) else None,
                    "climatology": [float(c) for c in r["clim"][i]],
                    "data_source": sources_list[i],
                    "model_version": self.model_version,
                    "data_version": self.data_version,
                    "in_training_set": self.membership.point_in_training(
                        p["lat"], p["lon"], p["date"]
                    ),
                    "mode": mode,
                    "interval_method": self.interval_method,
                    "di": None if r["di"] is None else float(r["di"][i]),
                    "in_domain": None if r["in_domain"] is None else bool(r["in_domain"][i]),
                }
            )
        return results

    def find_nearest_held_out_profile(
        self,
        lat: float,
        lon: float,
        date: str | None = None,
        include_training: bool = False,
    ) -> dict[str, Any] | None:
        """Find the nearest validation-store Argo profile by great-circle distance.

        By default only floats outside the served model's training split are candidates
        (blueprint §10.2). Depths without an observation are returned as None and excluded
        from the RMSE.
        """
        if self.val_df is None or len(self.val_df) == 0:
            return None

        candidates = self.val_df
        if not include_training and self.membership.known:
            float_ids = candidates.get("float_id")
            if float_ids is None:
                float_ids = candidates["profile_id"].astype(str).str.split("_").str[0]
            held_out = ~float_ids.astype(str).isin(self.membership.train_float_ids or set())
            candidates = candidates[held_out.to_numpy()]
            if len(candidates) == 0:
                return None

        # Haversine distance in km
        lat1 = np.radians(lat)
        lon1 = np.radians(lon)
        lat2 = np.radians(candidates["lat"].to_numpy())
        lon2 = np.radians(candidates["lon"].to_numpy())

        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
        c = 2.0 * np.arcsin(np.clip(np.sqrt(a), 0.0, 1.0))
        dist_km = 6371.0 * c

        nearest_idx = int(np.argmin(dist_km))
        row = candidates.iloc[nearest_idx]

        true_temps: list[float | None] = [
            float(row[c]) if c in row and np.isfinite(row[c]) else None for c in DEPTH_COLS
        ]
        prof_date = str(row["date"])[:10] if "date" in row else (date or "2023-06-15")
        float_id = str(row.get("float_id", str(row.get("profile_id", "")).split("_")[0]))

        # The profile's own collocated surface observations (whatever the table carries)
        feats = {c: float(row[c]) for c in CHANNELS if c in row and np.isfinite(row[c])}
        feats.setdefault("sst", float(row.get("sst", 28.0)))
        pred = self.predict_point(
            lat=float(row["lat"]),
            lon=float(row["lon"]),
            date=prof_date,
            features=feats,
            source="local_store",
        )

        observed = [i for i, t in enumerate(true_temps) if t is not None]
        if observed:
            diff = np.array([pred["temperatures"][i] - (true_temps[i] or 0.0) for i in observed])
            rmse: float | None = float(np.sqrt(np.mean(diff**2)))
        else:
            rmse = None

        return {
            "profile_id": str(row.get("profile_id", f"prof_{nearest_idx}")),
            "float_id": float_id,
            "cycle": int(row.get("cycle", 1)),
            "date": prof_date,
            "lat": float(row["lat"]),
            "lon": float(row["lon"]),
            "distance_km": float(dist_km[nearest_idx]),
            "depths": list(STANDARD_DEPTHS),
            "true_temperatures": true_temps,
            "pred_temperatures": pred["temperatures"],
            "uncertainties": pred["uncertainties"],
            "rmse": rmse,
            "n_observed": len(observed),
            "in_training_set": self.membership.float_in_training(float_id),
            # Real Argo observations from the local validation table; the prediction is driven by
            # the profile's own collocated SST from the same table.
            "data_source": "local_store",
        }

    def explain_point(
        self,
        lat: float,
        lon: float,
        date: str,
        features: dict[str, float],
    ) -> dict[str, float]:
        """Compute input feature attribution using integrated gradients."""
        if self.v2 is not None:
            return self._explain_v2(lat, lon, date, features)
        if self.model is None:
            return {}

        x_raw = self.build_feature_vector(lat, lon, date, features)
        x_norm = (x_raw - self.scaler_mean) / self.scaler_std
        tx = torch.tensor(x_norm, dtype=torch.float32, device=self.device).unsqueeze(0)
        tx.requires_grad = True

        pred_mean, _, _ = self.model(tx)
        # Target thermocline depth 100m (index 7)
        target = pred_mean[0, 7]
        target.backward()

        grads = tx.grad.cpu().numpy()[0] if tx.grad is not None else np.zeros(18)
        feature_names = [
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
            "sss_avail",
            "sla_avail",
            "ug_avail",
            "vg_avail",
            "u10_avail",
            "v10_avail",
            "sst_avail",
        ]
        # Attribution score = |grad * x|
        attributions = {
            name: float(np.abs(grads[i] * x_norm[i])) for i, name in enumerate(feature_names)
        }
        total = sum(attributions.values()) + 1e-6
        normalized = {k: v / total for k, v in attributions.items()}
        return normalized

    def _explain_v2(
        self, lat: float, lon: float, date: str, features: dict[str, float]
    ) -> dict[str, float]:
        """Gradient x input on the v2 scalars, for the 100 m anomaly (delayed mode)."""
        from aquasphere.train.v2 import FEATURES, scalar_features

        cols: dict[str, list[Any]] = {"lat": [lat], "lon": [lon], "date": [date]}
        cols.update({c: [features.get(c, np.nan)] for c in CHANNELS})
        base, avail = scalar_features(pd.DataFrame(cols))
        s = self.v2._scalars(base, self.v2._keep(avail, CHANNELS))
        s.requires_grad_(True)
        mean, _, _ = self.v2.model(s, None)
        mean[0, STANDARD_DEPTHS.index(100)].backward()
        grad = s.grad.numpy()[0] if s.grad is not None else np.zeros(len(FEATURES))
        attr = np.abs(grad * s.detach().numpy()[0])
        total = float(attr.sum()) + 1e-6
        return {name: float(a / total) for name, a in zip(FEATURES, attr, strict=True)}
