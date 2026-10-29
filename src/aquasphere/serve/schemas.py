"""
Pydantic v2 schemas for the AquaSphere FastAPI serving layer (SIH 26066).

Enforces strict domain validation (lat 5-30°N, lon 45-105°E), date format YYYY-MM-DD,
and standardized response payloads carrying data provenance badges.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from aquasphere.constants import LAT_MAX, LAT_MIN, LON_MAX, LON_MIN, STANDARD_DEPTHS


class PredictRequest(BaseModel):
    """Single-point profile prediction request."""

    lat: float = Field(
        ...,
        ge=LAT_MIN,
        le=LAT_MAX,
        description=f"Latitude in degrees North ({LAT_MIN} to {LAT_MAX})",
    )
    lon: float = Field(
        ...,
        ge=LON_MIN,
        le=LON_MAX,
        description=f"Longitude in degrees East ({LON_MIN} to {LON_MAX})",
    )
    date: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Observation date in YYYY-MM-DD format",
    )
    features: dict[str, float] | None = Field(
        default=None,
        description="Optional manual satellite feature overrides (e.g. sst, sss, sla)",
    )


class PredictBatchRequest(BaseModel):
    """Vectorized batch prediction request."""

    items: list[PredictRequest] = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="List of target prediction points (up to 5,000 points)",
    )


class PredictResponse(BaseModel):
    """Calibrated subsurface temperature profile prediction with uncertainty."""

    lat: float
    lon: float
    date: str
    depths: list[int] = Field(default_factory=lambda: list(STANDARD_DEPTHS))
    temperatures: list[float] = Field(description="Predicted mean temperature profile (°C)")
    uncertainties: list[float] = Field(description="Predicted standard deviation sigma (°C)")
    interval_lower: list[float] = Field(
        description="Conformal 90% prediction interval lower bound (°C)"
    )
    interval_upper: list[float] = Field(
        description="Conformal 90% prediction interval upper bound (°C)"
    )
    embedding: list[float] = Field(description="L2-normalized ocean embedding vector")
    mld: float | None = Field(description="Mixed Layer Depth (m)")
    d20: float | None = Field(description="Depth of 20°C Isotherm (m)")
    climatology: list[float] | None = Field(
        default=None,
        description="Monthly climatology reference temperature profile (°C)",
    )
    ohc300: float | None = Field(
        default=None,
        description="Upper 300 m depth-averaged ocean heat content index (°C)",
    )
    data_source: str = Field(
        description="Provenance of surface observations: 'local_store' | 'disk_cache' | 'live' | 'unavailable'"
    )
    model_version: str = Field(description="Trained model version identifier")
    data_version: str = Field(description="Data release version")
    in_training_set: bool | None = Field(
        default=None,
        description=(
            "Whether a training profile lies in the same 0.25° cell on the same date. "
            "null when the training split cannot be determined."
        ),
    )


class PredictBatchResponse(BaseModel):
    """Vectorized batch prediction response."""

    count: int
    predictions: list[PredictResponse]


class GridRequest(BaseModel):
    """Spatial bounding box grid prediction request."""

    lat_min: float = Field(default=LAT_MIN, ge=LAT_MIN, le=LAT_MAX)
    lat_max: float = Field(default=LAT_MAX, ge=LAT_MIN, le=LAT_MAX)
    lon_min: float = Field(default=LON_MIN, ge=LON_MIN, le=LON_MAX)
    lon_max: float = Field(default=LON_MAX, ge=LON_MIN, le=LON_MAX)
    step: float = Field(default=2.0, ge=0.5, le=10.0, description="Grid step size in degrees")
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")


class GridPoint(BaseModel):
    """Single point prediction summary inside a spatial grid."""

    lat: float
    lon: float
    sst: float
    mld: float | None
    d20: float | None
    pca1: float = Field(description="Embedding projected on the grid's first principal component")
    pca2: float = Field(description="Embedding projected on the grid's second principal component")
    data_source: str = Field(
        default="unknown", description="Provenance of this cell's surface observations"
    )


class GridResponse(BaseModel):
    """Spatial grid prediction response."""

    date: str
    count: int
    points: list[GridPoint]
    projection: str = Field(
        default="pca",
        description="How pca1/pca2 were computed: PCA of this grid's embeddings",
    )
    explained_variance: list[float] = Field(
        default_factory=list,
        description="Fraction of embedding variance captured by pca1 and pca2",
    )


class ValidationProfileResponse(BaseModel):
    """Nearest held-out Argo profile comparison."""

    profile_id: str | int
    float_id: str | int
    cycle: int
    date: str
    lat: float
    lon: float
    distance_km: float
    depths: list[int]
    true_temperatures: list[float | None] = Field(
        description="Observed temperature (°C); null where the float has no observation"
    )
    pred_temperatures: list[float]
    uncertainties: list[float]
    rmse: float | None = Field(description="RMSE over observed depths only (°C)")
    n_observed: int = Field(default=0, description="Number of depths with an observation")
    in_training_set: bool | None = Field(
        default=None,
        description="Whether this float was in the served model's training split",
    )
    data_source: str = Field(
        default="local_store",
        description="Data provenance: 'local_store' | 'disk_cache' | 'live' | 'offline_synthetic'",
    )


class ExplainResponse(BaseModel):
    """Feature attribution explanation response."""

    lat: float
    lon: float
    date: str
    method: str = Field(default="gradient_x_input")
    target: str = Field(
        default="temperature_100m", description="Model output the attribution explains"
    )
    feature_attributions: dict[str, float]
    data_source: str | None = Field(
        default=None, description="Provenance of the surface observations explained"
    )


class MetaResponse(BaseModel):
    """Service metadata for bounding UI date-pickers and domains."""

    title: str = "AquaSphere Serving API"
    model_version: str
    data_version: str
    min_date: str
    max_date: str
    domain: dict[str, float]
    standard_depths: list[int]
    available_sources: list[str]
    available_dates: list[str] = Field(
        default_factory=list,
        description="Dates present in the local surface store (other dates may 503)",
    )
    model_provenance: dict[str, Any] = Field(
        default_factory=dict,
        description="Served checkpoint: weights trained/untrained, verification status, git SHA, data hash",
    )


class HealthResponse(BaseModel):
    """Liveness probe response."""

    status: str = "healthy"
    uptime_seconds: float


class ReadyResponse(BaseModel):
    """Readiness probe response verifying model integrity and data stores."""

    ready: bool
    model_loaded: bool
    scaler_loaded: bool
    store_open: bool
    details: dict[str, Any]
