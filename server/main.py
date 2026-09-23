"""
OceanEmbed — FastAPI Serving Layer
=====================================
Serves trained model predictions and validation metrics over HTTP.

Endpoints:
    GET /predict?lat=..&lon=..&date=..
        Returns 15-depth temperature profile, 16-dim ocean embedding,
        the SST used, and a source tag ("real" | "model_simulated_sst" | "simulated").

    GET /validation
        Returns the saved validation metrics (RMSE / bias / corr per depth).

    GET /health
        Liveness probe.

CORS is fully open (origins=["*"]) so the HTML can be opened from
file:// or any localhost port without proxy gymnastics.

Run:
    uvicorn server.main:app --reload --port 8000
"""

import json
import math
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------------------
# Paths  (server/main.py lives one level below the repo root)
# ---------------------------------------------------------------------------
ROOT         = Path(__file__).parent.parent
MODEL_PT     = ROOT / "model" / "model.pt"
MODEL_JL     = ROOT / "model" / "model.joblib"
SCALER_JSON  = ROOT / "model" / "scaler.json"
METRICS_JSON = ROOT / "model" / "validation_metrics.json"

STANDARD_DEPTHS = [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000]

ERDDAP_BASE = (
    "https://www.ncei.noaa.gov/erddap/griddap/"
    "ncdc_oisst_v2_avhrr_by_time_zlev_lat_lon.csv"
)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(
    title="OceanEmbed API",
    description="Subsurface temperature reconstruction from surface satellite observations",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Model state (loaded once at startup)
# ---------------------------------------------------------------------------
_model        = None   # PyTorch nn.Module or sklearn estimator
_backend      = None   # "pytorch" | "sklearn" | None
_scaler_mean  = None
_scaler_std   = None


@app.on_event("startup")
def load_model():
    global _model, _backend, _scaler_mean, _scaler_std

    # Load scaler
    if SCALER_JSON.exists():
        sc = json.loads(SCALER_JSON.read_text())
        _scaler_mean = np.array(sc["mean"], dtype=np.float32)
        _scaler_std  = np.array(sc["std"],  dtype=np.float32)
        _backend     = sc.get("backend", "pytorch")
    else:
        print("[startup] scaler.json not found — model-derived predictions unavailable.")
        return

    # Try loading PyTorch model
    if _backend == "pytorch" and MODEL_PT.exists():
        try:
            import torch
            import torch.nn as nn

            ckpt   = torch.load(MODEL_PT, map_location="cpu")
            hidden = ckpt.get("hidden", 64)

            class OceanEmbedNet(nn.Module):
                def __init__(self, embed_dim=16, hidden=hidden):
                    super().__init__()
                    self.encoder = nn.Sequential(
                        nn.Linear(5, hidden), nn.ReLU(), nn.Linear(hidden, embed_dim)
                    )
                    self.decoder = nn.Sequential(
                        nn.Linear(embed_dim, hidden), nn.ReLU(), nn.Linear(hidden, 15)
                    )
                def forward(self, x):
                    emb = self.encoder(x)
                    return self.decoder(emb), emb

            net = OceanEmbedNet(embed_dim=16, hidden=hidden)
            net.load_state_dict(ckpt["model_state"])
            net.eval()
            _model = net
            print(f"[startup] Loaded PyTorch model from {MODEL_PT}")
        except Exception as exc:
            print(f"[startup] PyTorch model load failed: {exc}")

    # Try sklearn fallback
    elif _backend == "sklearn" and MODEL_JL.exists():
        try:
            import joblib
            _model = joblib.load(MODEL_JL)
            print(f"[startup] Loaded sklearn model from {MODEL_JL}")
        except Exception as exc:
            print(f"[startup] sklearn model load failed: {exc}")

    if _model is None:
        print("[startup] Running in degraded mode — responses will be fully simulated.")


# ---------------------------------------------------------------------------
# OISST fetching (with simple time-based cache)
# ---------------------------------------------------------------------------
_sst_cache: dict[str, tuple[float, float]] = {}   # key → (sst, timestamp)
SST_CACHE_TTL = 86400   # 24 hours


def snap(value: float, step: float = 0.25) -> float:
    return round(round(value / step) * step, 2)


def fetch_oisst(lat: float, lon: float, date_str: str, timeout: float = 5.0) -> Optional[float]:
    cache_key = f"{snap(lat)}_{snap(lon)}_{date_str}"
    if cache_key in _sst_cache:
        val, ts = _sst_cache[cache_key]
        if time.time() - ts < SST_CACHE_TTL:
            return val

    slat   = snap(lat)
    slon   = snap(lon)
    slon360 = slon if slon >= 0 else slon + 360

    url = (
        f"{ERDDAP_BASE}"
        f"?sst[({date_str}T12:00:00Z)][0][({slat:.2f})]"
        f"[({slon360:.2f})]"
    )
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        lines = [l.strip() for l in r.text.splitlines() if l.strip()]
        for line in lines[2:]:
            parts = line.split(",")
            val = float(parts[-1])
            if -5 < val < 45:
                _sst_cache[cache_key] = (val, time.time())
                return round(val, 3)
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Simulated SST (deterministic fallback — mirrors the JS formula)
# ---------------------------------------------------------------------------
def _hash(x: float) -> float:
    s = math.sin(x * 127.1) * 43758.5453
    return s - math.floor(s)


def _seed(lat: float, lon: float, di: int, salt: float) -> float:
    return _hash(lat * 12.9898 + lon * 78.233 + di * 37.719 + salt * 5.41)


def simulated_sst(lat: float, lon: float, date_str: str) -> float:
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        dt = datetime.now(timezone.utc)
    m  = dt.month
    sp = math.sin((m / 12) * 2 * math.pi - math.pi / 2)
    bob = lon >= 78
    base     = 27.2 + (18 - lat) * 0.11
    seasonal = sp * 1.6 + (0.4 if bob else -0.2)
    di       = (dt - datetime(2025, 1, 1)).days
    noise    = (_seed(lat, lon, di, 1) - 0.5) * 1.1
    return round(base + seasonal + noise, 2)


def simulated_profile(lat: float, lon: float, date_str: str) -> list[float]:
    """Port of the JS getProfile() function for the graceful fallback."""
    sst = simulated_sst(lat, lon, date_str)
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        dt = datetime.utcnow()
    m  = dt.month
    sp = math.sin((m / 12) * 2 * math.pi - math.pi / 2)
    bob = lon >= 78
    di  = (dt - datetime(2025, 1, 1)).days

    td_base = 95 if bob else 70
    td = td_base + sp * (15 if bob else -25) + (_seed(lat, lon, di, 8) - 0.5) * 20
    td = max(25.0, td)
    deep_t = 3.6 + (_seed(lat, lon, di, 9) - 0.5) * 0.6

    profile = []
    for z in STANDARD_DEPTHS:
        s = 1 / (1 + math.exp(-(z - td) / 55 * 2.1))
        t = sst - (sst - deep_t) * s
        if z > 700:
            t = max(deep_t - 0.3, t - (z - 700) * 0.0015)
        profile.append(round(t, 2))
    return profile


def simulated_embedding(lat: float, lon: float, date_str: str) -> list[float]:
    """16-dim deterministic embedding for full-fallback mode."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        dt = datetime.utcnow()
    di = (dt - datetime(2025, 1, 1)).days
    return [round((_seed(lat, lon, di, i) - 0.5) * 4, 4) for i in range(16)]


# ---------------------------------------------------------------------------
# Model inference
# ---------------------------------------------------------------------------
def model_predict(lat: float, lon: float, date_str: str, sst: float):
    """
    Run trained model. Returns (profile_list, embedding_list).
    Raises ValueError if model not loaded.
    """
    if _model is None or _scaler_mean is None:
        raise ValueError("Model not loaded")

    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        dt = datetime.utcnow()
    doy = dt.timetuple().tm_yday

    x = np.array([[lat, lon,
                   math.sin(2 * math.pi * doy / 365),
                   math.cos(2 * math.pi * doy / 365),
                   sst]], dtype=np.float32)
    x = (x - _scaler_mean) / _scaler_std

    if _backend == "pytorch":
        import torch
        with torch.no_grad():
            xt = torch.from_numpy(x)
            pred, emb = _model(xt)
            profile   = pred.numpy()[0].tolist()
            embedding = emb.numpy()[0].tolist()
    else:
        # sklearn: model predicts profile only; derive embedding from encoder manually
        profile = _model.predict(x)[0].tolist()
        # sklearn fallback: embedding is a deterministic projection for display
        embedding = simulated_embedding(lat, lon, date_str)

    profile   = [round(float(v), 3) for v in profile]
    embedding = [round(float(v), 4) for v in embedding]
    return profile, embedding


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {
        "status": "ok",
        "model_loaded": _model is not None,
        "backend": _backend,
    }


@app.get("/predict")
def predict(
    lat:  float = Query(..., ge=5.0,   le=30.0,  description="Latitude (°N)"),
    lon:  float = Query(..., ge=45.0,  le=105.0, description="Longitude (°E)"),
    date: str   = Query(..., description="Date (YYYY-MM-DD)"),
):
    # 1. Try to get real OISST SST
    sst    = fetch_oisst(lat, lon, date)
    source = "real"

    # 2. If real SST unavailable, use simulated SST but still run model
    if sst is None:
        sst    = simulated_sst(lat, lon, date)
        source = "model_simulated_sst"

    # 3. Run model (or fall back to full simulation)
    try:
        profile, embedding = model_predict(lat, lon, date, sst)
    except ValueError:
        # Model not available at all — pure simulation
        profile   = simulated_profile(lat, lon, date)
        embedding = simulated_embedding(lat, lon, date)
        sst       = simulated_sst(lat, lon, date)
        source    = "simulated"

    return {
        "lat":       lat,
        "lon":       lon,
        "date":      date,
        "sst":       sst,
        "source":    source,
        "depths":    STANDARD_DEPTHS,
        "profile":   profile,
        "embedding": embedding,
    }


@app.get("/validation")
def validation():
    if not METRICS_JSON.exists():
        # Return graceful placeholder if model hasn't been trained yet
        return {
            "status": "not_trained",
            "message": "Run python model/train.py to generate real validation metrics.",
            "grouped": [
                {"depth": "0–30 m",    "rmse": None, "bias": None, "corr": None},
                {"depth": "50–150 m",  "rmse": None, "bias": None, "corr": None},
                {"depth": "200–300 m", "rmse": None, "bias": None, "corr": None},
                {"depth": "500–1000 m","rmse": None, "bias": None, "corr": None},
            ],
        }
    return json.loads(METRICS_JSON.read_text())
