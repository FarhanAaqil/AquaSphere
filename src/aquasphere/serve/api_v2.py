"""
/v2 routes (roadmap Phase 5). The v1 routes are unchanged; v2 adds the product features:

    GET /v2/meta                  capabilities of the served model (modes, intervals, DI, ONNX)
    GET /v2/grid                  map layers at one depth: temperature, anomaly, sigma, interval
                                  width, MLD, D20, D26, TCHP, DI, in-domain
    GET /v2/transect              depth x distance section between two points
    GET /v2/timeseries            depth x time (Hovmoller) at one point, local-store dates only
    GET /v2/export/profile        one profile as CSV or NetCDF with a provenance header
    GET /v2/export/grid           a grid of profiles as CSV or NetCDF
    GET /v2/drift                 input dissimilarity over time (needs the v2 model)

Missing observations are never filled: a cell or date without a surface observation is left
out and listed, and an empty result is a 503.
"""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from aquasphere.constants import LAT_MAX, LAT_MIN, LON_MAX, LON_MIN, STANDARD_DEPTHS
from aquasphere.serve import products
from aquasphere.serve.schemas import PredictRequest, PredictResponse

DATE = r"^\d{4}-\d{2}-\d{2}$"
Mode = Literal["delayed", "nowcast"]
MAX_SERIES = 200
MAX_GRID = 1200


class BatchV2Request(BaseModel):
    items: list[PredictRequest] = Field(..., min_length=1, max_length=5000)


class BatchV2Response(BaseModel):
    count: int
    missing: list[int] = Field(description="Request indices with no surface observation")
    predictions: list[PredictResponse]
    index: list[int] = Field(description="Request index of each prediction")


class GridCell(BaseModel):
    lat: float
    lon: float
    temperature: float
    climatology: float
    anomaly: float
    sigma: float
    interval_width: float
    mld: float | None
    d20: float | None
    d26: float | None
    tchp: float | None
    di: float | None = None
    in_domain: bool | None = None
    data_source: str


class GridV2Response(BaseModel):
    date: str
    depth: int
    mode: str
    step: float
    count: int
    missing: int = Field(description="Cells left out because no surface observation exists")
    model_version: str
    interval_method: str
    cells: list[GridCell]


class SectionResponse(BaseModel):
    kind: Literal["transect", "timeseries"]
    mode: str
    depths: list[int]
    axis: list[Any] = Field(description="Distance (km) for a transect, dates for a time series")
    lats: list[float]
    lons: list[float]
    dates: list[str]
    temperature: list[list[float]]
    sigma: list[list[float]]
    d20: list[float | None]
    tchp: list[float | None]
    data_source: list[str]
    skipped: list[str] = Field(default_factory=list, description="Points or dates with no data")
    model_version: str


class DriftPoint(BaseModel):
    date: str
    cells: int
    mean_di: float
    p90_di: float
    share_outside: float


class DriftResponse(BaseModel):
    threshold: float
    step: float
    model_version: str
    points: list[DriftPoint]


def _grid_coords(
    lat_min: float, lat_max: float, lon_min: float, lon_max: float, step: float
) -> list[tuple[float, float]]:
    lats = np.arange(lat_min, lat_max + 1e-6, step)
    lons = np.arange(lon_min, lon_max + 1e-6, step)
    coords = [(round(float(a), 4), round(float(b), 4)) for a in lats for b in lons]
    if len(coords) > MAX_GRID:
        raise HTTPException(
            422, f"{len(coords)} cells requested; use a larger step (max {MAX_GRID})"
        )
    return coords


def build_router(engine: Any, resolver: Any) -> APIRouter:
    r = APIRouter(prefix="/v2", tags=["v2"])

    def store_dates() -> list[str]:
        if resolver.zarr_store is None:
            raise HTTPException(503, "No local surface store: time series need stored dates")
        return sorted(resolver.zarr_store.get_available_dates())

    def meta_fields() -> dict[str, Any]:
        return {
            "model_version": engine.model_version,
            "interval_method": engine.interval_method,
            "git_sha": engine.provenance.get("git_sha"),
            "data_sha256": engine.provenance.get("data_sha256"),
        }

    async def predict_points(
        pts: list[tuple[float, float, str]], mode: str, store_only: bool = True
    ) -> tuple[list[dict[str, Any]], list[int]]:
        """Predictions for the points that have observations, and indices of those without.

        Grids, sections and series trust the local store for the dates it holds (land and gaps
        stay empty); dates outside it still go through the cache and live chain.
        """
        resolved = await resolver.resolve_many(
            [(a, b, d, None) for a, b, d in pts], store_only=store_only
        )
        return run(pts, resolved, mode)

    def run(
        pts: list[tuple[float, float, str]],
        resolved: list[tuple[dict[str, float], str] | None],
        mode: str,
    ) -> tuple[list[dict[str, Any]], list[int]]:
        kept = [(i, x) for i, x in enumerate(resolved) if x is not None]
        missing = [i for i, x in enumerate(resolved) if x is None]
        preds = engine.predict_batch(
            [{"lat": pts[i][0], "lon": pts[i][1], "date": pts[i][2]} for i, _ in kept],
            [x[0] for _, x in kept],
            [x[1] for _, x in kept],
            mode=mode,
        )
        return preds, missing

    @r.post("/predict_batch", response_model=BatchV2Response)
    async def predict_batch(req: BatchV2Request) -> BatchV2Response:
        """Like /predict_batch, but points without an observation are listed instead of failing
        the whole batch (a grid over a real store always has a few coastal gaps)."""
        out: dict[int, dict[str, Any]] = {}
        missing: list[int] = []
        for mode in sorted({it.mode for it in req.items}):
            idx = [i for i, it in enumerate(req.items) if it.mode == mode]
            resolved = await resolver.resolve_many(
                [
                    (req.items[i].lat, req.items[i].lon, req.items[i].date, req.items[i].features)
                    for i in idx
                ],
                store_only=True,
            )
            pts = [(req.items[i].lat, req.items[i].lon, req.items[i].date) for i in idx]
            preds, miss = run(pts, resolved, mode)
            kept = [i for j, i in enumerate(idx) if j not in set(miss)]
            out.update(zip(kept, preds, strict=True))
            missing += [idx[j] for j in miss]
        order = sorted(out)
        if not order:
            raise HTTPException(503, "No surface observation for any requested point")
        return BatchV2Response(
            count=len(order),
            missing=sorted(missing),
            predictions=[PredictResponse(**out[i]) for i in order],
            index=order,
        )

    @r.get("/meta")
    def meta() -> dict[str, Any]:
        return {
            **meta_fields(),
            "protocol": "v2" if engine.v2 is not None else "v1",
            "modes": ["delayed", "nowcast"],
            "dissimilarity": engine.dissimilarity is not None,
            "dissimilarity_threshold": (
                engine.dissimilarity.threshold if engine.dissimilarity is not None else None
            ),
            "onnx": bool(engine.onnx),
            "layers": [
                "temperature",
                "anomaly",
                "sigma",
                "interval_width",
                "mld",
                "d20",
                "d26",
                "tchp",
                "di",
            ],
            "depths": list(STANDARD_DEPTHS),
            "available_dates": store_dates() if resolver.zarr_store is not None else [],
        }

    @r.get("/grid", response_model=GridV2Response)
    async def grid(
        date: str = Query(..., pattern=DATE),
        depth: int = Query(default=100),
        step: float = Query(default=1.0, ge=0.5, le=5.0),
        mode: Mode = Query(default="delayed"),
        lat_min: float = Query(default=LAT_MIN, ge=LAT_MIN, le=LAT_MAX),
        lat_max: float = Query(default=LAT_MAX, ge=LAT_MIN, le=LAT_MAX),
        lon_min: float = Query(default=LON_MIN, ge=LON_MIN, le=LON_MAX),
        lon_max: float = Query(default=LON_MAX, ge=LON_MIN, le=LON_MAX),
    ) -> GridV2Response:
        if depth not in STANDARD_DEPTHS:
            raise HTTPException(422, f"depth must be one of {list(STANDARD_DEPTHS)}")
        k = STANDARD_DEPTHS.index(depth)
        coords = _grid_coords(lat_min, lat_max, lon_min, lon_max, step)
        preds, missing = await predict_points([(a, b, date) for a, b in coords], mode)
        if not preds:
            raise HTTPException(503, f"No surface observations for {date} in this area")
        cells = [
            GridCell(
                lat=p["lat"],
                lon=p["lon"],
                temperature=p["temperatures"][k],
                climatology=p["climatology"][k],
                anomaly=p["temperatures"][k] - p["climatology"][k],
                sigma=p["uncertainties"][k],
                interval_width=p["interval_upper"][k] - p["interval_lower"][k],
                mld=p["mld"],
                d20=p["d20"],
                d26=p["d26"],
                tchp=p["tchp"],
                di=p["di"],
                in_domain=p["in_domain"],
                data_source=p["data_source"],
            )
            for p in preds
        ]
        return GridV2Response(
            date=date,
            depth=depth,
            mode=mode,
            step=step,
            count=len(cells),
            missing=len(missing),
            model_version=engine.model_version,
            interval_method=engine.interval_method,
            cells=cells,
        )

    def section(
        kind: Literal["transect", "timeseries"],
        mode: str,
        axis: list[Any],
        preds: list[dict[str, Any]],
        skipped: list[str],
    ) -> SectionResponse:
        return SectionResponse(
            kind=kind,
            mode=mode,
            depths=list(STANDARD_DEPTHS),
            axis=axis,
            lats=[p["lat"] for p in preds],
            lons=[p["lon"] for p in preds],
            dates=[p["date"] for p in preds],
            temperature=[p["temperatures"] for p in preds],
            sigma=[p["uncertainties"] for p in preds],
            d20=[p["d20"] for p in preds],
            tchp=[p["tchp"] for p in preds],
            data_source=[p["data_source"] for p in preds],
            skipped=skipped,
            model_version=engine.model_version,
        )

    @r.get("/transect", response_model=SectionResponse)
    async def transect(
        lat1: float = Query(..., ge=LAT_MIN, le=LAT_MAX),
        lon1: float = Query(..., ge=LON_MIN, le=LON_MAX),
        lat2: float = Query(..., ge=LAT_MIN, le=LAT_MAX),
        lon2: float = Query(..., ge=LON_MIN, le=LON_MAX),
        date: str = Query(..., pattern=DATE),
        n: int = Query(default=40, ge=5, le=120),
        mode: Mode = Query(default="delayed"),
    ) -> SectionResponse:
        lats, lons, dist = products.great_circle(lat1, lon1, lat2, lon2, n)
        pts = [(float(a), float(b), date) for a, b in zip(lats, lons, strict=True)]
        preds, missing = await predict_points(pts, mode)
        if not preds:
            raise HTTPException(503, "No surface observations along this line (land or no data)")
        kept = [i for i in range(n) if i not in set(missing)]
        skipped = [f"{lats[i]:.2f}N {lons[i]:.2f}E" for i in missing]
        return section("transect", mode, [round(float(dist[i]), 1) for i in kept], preds, skipped)

    @r.get("/timeseries", response_model=SectionResponse)
    async def timeseries(
        lat: float = Query(..., ge=LAT_MIN, le=LAT_MAX),
        lon: float = Query(..., ge=LON_MIN, le=LON_MAX),
        start: str = Query(..., pattern=DATE),
        end: str = Query(..., pattern=DATE),
        step_days: int = Query(default=7, ge=1, le=90),
        mode: Mode = Query(default="delayed"),
    ) -> SectionResponse:
        if end < start:
            raise HTTPException(422, "end is before start")
        dates = [d for d in store_dates() if start <= d <= end][::step_days]
        if len(dates) > MAX_SERIES:
            raise HTTPException(422, f"{len(dates)} dates; raise step_days (max {MAX_SERIES})")
        if not dates:
            raise HTTPException(503, f"The local store has no dates between {start} and {end}")
        pts = [(lat, lon, d) for d in dates]
        # One cell through time: read the store's time column directly, chunk by chunk
        preds, missing = run(pts, resolver.store_series(lat, lon, dates), mode)
        if not preds:
            raise HTTPException(503, "No surface observations at this point on any stored date")
        return section(
            "timeseries", mode, [p["date"] for p in preds], preds, [dates[i] for i in missing]
        )

    def file_response(rows: list[dict[str, Any]], fmt: str, name: str, mode: str) -> Response:
        meta = {**meta_fields(), "input_mode": mode, "points": len(rows)}
        if fmt == "csv":
            return Response(
                products.to_csv(rows, meta),
                media_type="text/csv",
                headers={"Content-Disposition": f'attachment; filename="{name}.csv"'},
            )
        return Response(
            products.to_netcdf(rows, meta),
            media_type="application/x-netcdf",
            headers={"Content-Disposition": f'attachment; filename="{name}.nc"'},
        )

    @r.get("/export/profile")
    async def export_profile(
        lat: float = Query(..., ge=LAT_MIN, le=LAT_MAX),
        lon: float = Query(..., ge=LON_MIN, le=LON_MAX),
        date: str = Query(..., pattern=DATE),
        mode: Mode = Query(default="delayed"),
        format: Literal["csv", "netcdf"] = Query(default="csv"),
    ) -> Response:
        preds, _ = await predict_points([(lat, lon, date)], mode, store_only=False)
        if not preds:
            raise HTTPException(503, "No surface observation for this point and date")
        return file_response(preds, format, f"aquasphere_profile_{lat:.2f}_{lon:.2f}_{date}", mode)

    @r.get("/export/grid")
    async def export_grid(
        date: str = Query(..., pattern=DATE),
        step: float = Query(default=2.0, ge=0.5, le=5.0),
        mode: Mode = Query(default="delayed"),
        format: Literal["csv", "netcdf"] = Query(default="csv"),
        lat_min: float = Query(default=LAT_MIN, ge=LAT_MIN, le=LAT_MAX),
        lat_max: float = Query(default=LAT_MAX, ge=LAT_MIN, le=LAT_MAX),
        lon_min: float = Query(default=LON_MIN, ge=LON_MIN, le=LON_MAX),
        lon_max: float = Query(default=LON_MAX, ge=LON_MIN, le=LON_MAX),
    ) -> Response:
        coords = _grid_coords(lat_min, lat_max, lon_min, lon_max, step)
        preds, _ = await predict_points([(a, b, date) for a, b in coords], mode)
        if not preds:
            raise HTTPException(503, f"No surface observations for {date} in this area")
        return file_response(preds, format, f"aquasphere_grid_{date}_{step}deg", mode)

    drift_cache: dict[tuple[str, str, int, float], DriftResponse] = {}

    @r.get("/drift", response_model=DriftResponse)
    async def drift(
        start: str = Query(..., pattern=DATE),
        end: str = Query(..., pattern=DATE),
        step_days: int = Query(default=30, ge=1, le=365),
        step: float = Query(default=3.0, ge=1.0, le=5.0),
    ) -> DriftResponse:
        if engine.dissimilarity is None:
            raise HTTPException(503, "Drift needs the dissimilarity index of the v2 model")
        key = (start, end, step_days, step)
        if key in drift_cache:
            return drift_cache[key]
        dates = [d for d in store_dates() if start <= d <= end][::step_days]
        if not dates or len(dates) > MAX_SERIES:
            raise HTTPException(422, f"{len(dates)} dates in range; need 1 to {MAX_SERIES}")
        coords = _grid_coords(LAT_MIN, LAT_MAX, LON_MIN, LON_MAX, step)
        points: list[DriftPoint] = []
        for d in dates:
            preds, _ = await predict_points([(a, b, d) for a, b in coords], "delayed")
            if not preds:
                continue
            di = np.array([p["di"] for p in preds], dtype=np.float64)
            points.append(
                DriftPoint(
                    date=d,
                    cells=len(preds),
                    mean_di=float(di.mean()),
                    p90_di=float(np.percentile(di, 90)),
                    share_outside=float(np.mean(di > engine.dissimilarity.threshold)),
                )
            )
        if not points:
            raise HTTPException(503, "No observations on any date in range")
        out = DriftResponse(
            threshold=float(engine.dissimilarity.threshold),
            step=step,
            model_version=engine.model_version,
            points=points,
        )
        drift_cache[key] = out
        return out

    return r
