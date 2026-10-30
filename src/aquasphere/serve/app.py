"""
AquaSphere FastAPI serving application (SIH 26066).

Features:
- Pydantic v2 domain validation (lat 5-30°N, lon 45-105°E).
- 4-stage data-source resolution (local Zarr, disk cache, live ERDDAP, 503 fail-fast).
- Conformal calibrated prediction intervals.
- Vectorized batch prediction (/predict_batch, up to 5,000 points).
- Spatial grid overview with PCA embedding coordinates (/grid).
- Held-out validation profile comparison (/validation/profile).
- Model explainability (/explain).
- Static assets serving.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any, Literal

import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from aquasphere.constants import LAT_MAX, LAT_MIN, LON_MAX, LON_MIN, STANDARD_DEPTHS
from aquasphere.serve import ops
from aquasphere.serve.api_v2 import build_router
from aquasphere.serve.engine import InferenceEngine
from aquasphere.serve.resolver import SurfaceResolver
from aquasphere.serve.schemas import (
    ExplainResponse,
    GridPoint,
    GridResponse,
    HealthResponse,
    MetaResponse,
    PredictBatchRequest,
    PredictBatchResponse,
    PredictRequest,
    PredictResponse,
    ReadyResponse,
    ValidationProfileResponse,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("aquasphere.serve")

START_TIME = time.time()

app = FastAPI(
    title="AquaSphere Serving API",
    description="Subsurface ocean temperature profile reconstruction from multi-sensor satellite observations",
    version="2.0.0",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# App-level services
engine = InferenceEngine()
resolver = SurfaceResolver()


# Gzip, ETags, JSON access logs, Prometheus metrics and rate limiting (aquasphere.serve.ops)
metrics = ops.install(app)
app.include_router(build_router(engine, resolver))


@app.get("/metrics", response_class=PlainTextResponse, include_in_schema=False)
def prometheus_metrics() -> str:
    """Prometheus text exposition."""
    return metrics.render(
        {
            "aquasphere_model_ready": float(engine.is_ready),
            "aquasphere_onnx_runtime": float(engine.onnx),
            "aquasphere_store_dates": float(
                len(resolver.zarr_store.dates) if resolver.zarr_store else 0
            ),
        }
    )


@app.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Liveness probe."""
    return HealthResponse(
        status="healthy",
        uptime_seconds=time.time() - START_TIME,
    )


@app.get("/ready", response_model=ReadyResponse)
def readiness_check() -> ReadyResponse:
    """Readiness probe verifying model integrity and data store status."""
    store_open = resolver.zarr_store is not None
    is_ready = engine.is_ready
    return ReadyResponse(
        ready=is_ready,
        model_loaded=engine.model is not None,
        scaler_loaded=engine.scaler_mean is not None,
        store_open=store_open,
        details={
            "model_version": engine.model_version,
            "data_version": engine.data_version,
            "zarr_store_path": str(resolver.store_path),
            "store_synthetic": resolver.store_synthetic,
            "store_dates": len(resolver.zarr_store.dates) if resolver.zarr_store else 0,
            "checkpoint_path": str(engine.checkpoint_path),
            "weights": engine.weights,
            "training_membership": engine.membership.source,
            "provenance_status": engine.provenance_status,
            "provenance_detail": engine.provenance_detail,
            "git_sha": engine.provenance.get("git_sha"),
            "data_sha256": engine.provenance.get("data_sha256"),
            "trained_at": engine.provenance.get("trained_at"),
        },
    )


@app.get("/meta", response_model=MetaResponse)
def get_metadata() -> MetaResponse:
    """Return domain bounds, available date ranges, and standard depths."""
    return MetaResponse(
        title="AquaSphere Subsurface Ocean Reconstruction API",
        model_version=engine.model_version,
        data_version=engine.data_version,
        min_date="2020-01-01",
        max_date="2025-12-31",
        domain={
            "lat_min": LAT_MIN,
            "lat_max": LAT_MAX,
            "lon_min": LON_MIN,
            "lon_max": LON_MAX,
        },
        standard_depths=list(STANDARD_DEPTHS),
        available_sources=["offline_synthetic", "disk_cache", "live"],
        available_dates=(
            sorted(resolver.zarr_store.get_available_dates()) if resolver.zarr_store else []
        ),
        model_provenance={
            "weights": engine.weights,
            "status": engine.provenance_status,
            "git_sha": engine.provenance.get("git_sha"),
            "data_sha256": engine.provenance.get("data_sha256"),
            "trained_at": engine.provenance.get("trained_at"),
        },
    )


@app.post("/predict", response_model=PredictResponse)
async def predict_single(req: PredictRequest) -> PredictResponse:
    """Reconstruct subsurface temperature profile for a single point."""
    obs_features, source = await resolver.resolve(
        lat=req.lat,
        lon=req.lon,
        date=req.date,
        overrides=req.features,
    )

    pred = engine.predict_point(
        lat=req.lat,
        lon=req.lon,
        date=req.date,
        features=obs_features,
        source=source,
        mode=req.mode,
    )
    return PredictResponse(**pred)


@app.get("/predict", response_model=PredictResponse)
async def predict_single_get(
    lat: float = Query(..., ge=LAT_MIN, le=LAT_MAX),
    lon: float = Query(..., ge=LON_MIN, le=LON_MAX),
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    mode: Literal["delayed", "nowcast"] = Query(default="delayed"),
) -> PredictResponse:
    """Reconstruct subsurface temperature profile for a single point via GET query."""
    obs_features, source = await resolver.resolve(lat=lat, lon=lon, date=date)
    pred = engine.predict_point(
        lat=lat,
        lon=lon,
        date=date,
        features=obs_features,
        source=source,
        mode=mode,
    )
    return PredictResponse(**pred)


@app.post("/predict_batch", response_model=PredictBatchResponse)
async def predict_batch(req: PredictBatchRequest) -> PredictBatchResponse:
    """Vectorized batch prediction for up to 5,000 points."""
    points = [{"lat": item.lat, "lon": item.lon, "date": item.date} for item in req.items]
    resolved = await resolver.resolve_many(
        [(item.lat, item.lon, item.date, item.features) for item in req.items]
    )
    missing = [i for i, r in enumerate(resolved) if r is None]
    if missing:
        first = req.items[missing[0]]
        raise HTTPException(
            status_code=503,
            detail=(
                f"Surface satellite observation unavailable for {len(missing)} of "
                f"{len(req.items)} points (first: {first.lat:.2f}°N, {first.lon:.2f}°E on "
                f"{first.date}). Silent simulation is strictly prohibited by AquaSphere "
                "integrity policies."
            ),
        )
    features_list = [r[0] for r in resolved if r is not None]
    sources_list = [r[1] for r in resolved if r is not None]

    # One forward pass per mode; results go back in request order
    preds: list[dict[str, Any]] = [{} for _ in points]
    for mode in sorted({item.mode for item in req.items}):
        idx = [i for i, item in enumerate(req.items) if item.mode == mode]
        out = engine.predict_batch(
            [points[i] for i in idx],
            [features_list[i] for i in idx],
            [sources_list[i] for i in idx],
            mode=mode,
        )
        for i, p in zip(idx, out, strict=True):
            preds[i] = p
    return PredictBatchResponse(
        count=len(preds),
        predictions=[PredictResponse(**p) for p in preds],
    )


@app.get("/grid", response_model=GridResponse)
async def get_grid_predictions(
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    step: float = Query(default=2.5, ge=1.0, le=5.0),
    lat_min: float = Query(default=LAT_MIN, ge=LAT_MIN, le=LAT_MAX),
    lat_max: float = Query(default=LAT_MAX, ge=LAT_MIN, le=LAT_MAX),
    lon_min: float = Query(default=LON_MIN, ge=LON_MIN, le=LON_MAX),
    lon_max: float = Query(default=LON_MAX, ge=LON_MIN, le=LON_MAX),
    mode: Literal["delayed", "nowcast"] = Query(default="delayed"),
) -> GridResponse:
    """Generate spatial field and PCA coordinates across a regular grid."""
    lats = np.arange(lat_min, lat_max + 1e-4, step)
    lons = np.arange(lon_min, lon_max + 1e-4, step)

    coords = [(float(lt), float(ln)) for lt in lats for ln in lons]
    resolved = await resolver.resolve_many([(lt, ln, date, None) for lt, ln in coords])
    # Cells with no observation are left out rather than invented
    kept = [(c, r) for c, r in zip(coords, resolved, strict=True) if r is not None]
    preds = engine.predict_batch(
        [{"lat": lt, "lon": ln, "date": date} for (lt, ln), _ in kept],
        [r[0] for _, r in kept],
        [r[1] for _, r in kept],
        mode=mode,
    )
    cells: list[tuple[float, float, dict[str, float], str, dict[str, Any]]] = [
        (lt, ln, obs, src, pred) for ((lt, ln), (obs, src)), pred in zip(kept, preds, strict=True)
    ]

    # Real PCA of this grid's embeddings (centred, first two right-singular vectors)
    proj = np.zeros((len(cells), 2))
    explained: list[float] = []
    if len(cells) >= 3:
        emb = np.array([c[4]["embedding"] for c in cells], dtype=np.float64)
        centred = emb - emb.mean(axis=0)
        _, s, vt = np.linalg.svd(centred, full_matrices=False)
        proj = centred @ vt[:2].T
        total = float((s**2).sum())
        explained = [float(v) for v in (s[:2] ** 2) / total] if total > 0 else []

    points = [
        GridPoint(
            lat=lt,
            lon=ln,
            sst=float(obs.get("sst", pred["temperatures"][0])),
            mld=pred["mld"],
            d20=pred["d20"],
            pca1=float(proj[i, 0]),
            pca2=float(proj[i, 1]),
            data_source=src,
            di=pred.get("di"),
            in_domain=pred.get("in_domain"),
        )
        for i, (lt, ln, obs, src, pred) in enumerate(cells)
    ]
    return GridResponse(
        date=date,
        count=len(points),
        points=points,
        projection="pca",
        explained_variance=explained,
    )


@app.get("/validation/profile", response_model=ValidationProfileResponse)
def get_validation_profile(
    lat: float = Query(..., ge=LAT_MIN, le=LAT_MAX),
    lon: float = Query(..., ge=LON_MIN, le=LON_MAX),
    date: str | None = Query(default=None),
    include_training: bool = Query(
        default=False,
        description="Also consider profiles from floats the served model was trained on",
    ),
) -> ValidationProfileResponse:
    """Retrieve the nearest held-out validation profile and evaluate model accuracy."""
    res = engine.find_nearest_held_out_profile(lat, lon, date, include_training=include_training)
    if res is None:
        raise HTTPException(
            status_code=404,
            detail="No held-out validation profiles found in validation store.",
        )
    return ValidationProfileResponse(**res)


@app.get("/validation")
def get_validation_metrics() -> Any:
    """Return offline evaluation metrics JSON (404 until the evaluation has produced it)."""
    metrics_path = Path("docs/results/metrics.json")
    if metrics_path.exists():
        return json.loads(metrics_path.read_text(encoding="utf-8"))
    raise HTTPException(
        status_code=404,
        detail="No evaluation results yet: run `make eval` to produce docs/results/metrics.json.",
    )


@app.get("/explain", response_model=ExplainResponse)
async def explain_prediction(
    lat: float = Query(..., ge=LAT_MIN, le=LAT_MAX),
    lon: float = Query(..., ge=LON_MIN, le=LON_MAX),
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
) -> ExplainResponse:
    """Compute input feature attributions for model prediction."""
    obs, src = await resolver.resolve(lat, lon, date)
    attributions = engine.explain_point(lat, lon, date, obs)
    return ExplainResponse(
        lat=lat,
        lon=lon,
        date=date,
        method="gradient_x_input",
        target="temperature_100m",
        feature_attributions=attributions,
        data_source=src,
    )


# Serve static frontend from web/
WEB_DIR = Path("web")

if WEB_DIR.exists():
    for _static in ("js", "styles", "vendor", "fonts", "assets", "data"):
        if (WEB_DIR / _static).exists():
            app.mount(f"/{_static}", StaticFiles(directory=str(WEB_DIR / _static)), name=_static)

    @app.get("/", include_in_schema=False)
    def serve_index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/sw.js", include_in_schema=False)
    def serve_service_worker() -> FileResponse:
        """Served from the root so it controls the whole app; always revalidated."""
        return FileResponse(
            WEB_DIR / "sw.js",
            media_type="text/javascript",
            headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"},
        )

    @app.get("/manifest.webmanifest", include_in_schema=False)
    def serve_manifest() -> FileResponse:
        return FileResponse(
            WEB_DIR / "manifest.webmanifest", media_type="application/manifest+json"
        )

    @app.get("/index.html", include_in_schema=False)
    def serve_index_html() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")


def main() -> None:
    """CLI entry point for aquasphere-serve."""
    import uvicorn

    parser = argparse.ArgumentParser(description="AquaSphere FastAPI Server")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host address to bind")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    uvicorn.run("aquasphere.serve.app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
