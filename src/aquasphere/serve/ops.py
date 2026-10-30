"""
Operational layer for the API (roadmap Phase 5, blueprint B11): one JSON log line per request,
Prometheus metrics in the text exposition format, ETags on GET responses, and a per-client
token-bucket rate limit. No extra dependencies: the metrics format is a few lines of text.

    AQUASPHERE_RATE_LIMIT   requests per minute per client (default 600; 0 disables)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import uuid
from collections import defaultdict
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

access_log = logging.getLogger("aquasphere.access")

BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
EXEMPT = {"/health", "/ready", "/metrics"}


class Metrics:
    """Request counter and latency histogram keyed by route template, method and status."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.count: dict[tuple[str, str, int], int] = defaultdict(int)
        self.hist: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0] * (len(BUCKETS) + 1))
        self.total: dict[tuple[str, str], float] = defaultdict(float)
        self.limited = 0
        self.started = time.time()

    def observe(self, route: str, method: str, status: int, seconds: float) -> None:
        with self.lock:
            self.count[(route, method, status)] += 1
            h = self.hist[(route, method)]
            for i, b in enumerate(BUCKETS):
                if seconds <= b:
                    h[i] += 1
            h[-1] += 1  # +Inf
            self.total[(route, method)] += seconds

    def render(self, extra: dict[str, float] | None = None) -> str:
        lines = [
            "# HELP aquasphere_requests_total HTTP requests by route, method and status.",
            "# TYPE aquasphere_requests_total counter",
        ]
        with self.lock:
            for (r, m, s), n in sorted(self.count.items()):
                lines.append(
                    f'aquasphere_requests_total{{route="{r}",method="{m}",status="{s}"}} {n}'
                )
            lines += [
                "# HELP aquasphere_request_seconds Request latency.",
                "# TYPE aquasphere_request_seconds histogram",
            ]
            for (r, m), h in sorted(self.hist.items()):
                for b, n in zip((*BUCKETS, "+Inf"), h, strict=True):
                    lines.append(
                        f'aquasphere_request_seconds_bucket{{route="{r}",method="{m}",le="{b}"}} {n}'
                    )
                lines.append(
                    f'aquasphere_request_seconds_sum{{route="{r}",method="{m}"}} {self.total[(r, m)]:.6f}'
                )
                lines.append(
                    f'aquasphere_request_seconds_count{{route="{r}",method="{m}"}} {h[-1]}'
                )
            lines += [
                "# HELP aquasphere_rate_limited_total Requests refused with 429.",
                "# TYPE aquasphere_rate_limited_total counter",
                f"aquasphere_rate_limited_total {self.limited}",
                "# HELP aquasphere_uptime_seconds Seconds since the API started.",
                "# TYPE aquasphere_uptime_seconds gauge",
                f"aquasphere_uptime_seconds {time.time() - self.started:.1f}",
            ]
        for k, v in (extra or {}).items():
            lines += [f"# TYPE {k} gauge", f"{k} {v}"]
        return "\n".join(lines) + "\n"


class TokenBucket:
    def __init__(self, per_minute: int) -> None:
        self.rate = per_minute / 60.0
        self.capacity = float(per_minute)
        self.state: dict[str, tuple[float, float]] = {}
        self.lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, float]:
        """(allowed, seconds until the next token)."""
        now = time.monotonic()
        with self.lock:
            tokens, last = self.state.get(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - last) * self.rate)
            if tokens >= 1.0:
                self.state[key] = (tokens - 1.0, now)
                return True, 0.0
            self.state[key] = (tokens, now)
            return False, (1.0 - tokens) / self.rate


def _route(request: Request) -> str:
    r = request.scope.get("route")
    return getattr(r, "path", None) or "unmatched"


class OpsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, metrics: Metrics, per_minute: int | None = None) -> None:
        super().__init__(app)
        self.metrics = metrics
        limit = (
            per_minute
            if per_minute is not None
            else int(os.environ.get("AQUASPHERE_RATE_LIMIT", "600"))
        )
        self.bucket = TokenBucket(limit) if limit > 0 else None

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:8]
        t0 = time.perf_counter()
        client = request.client.host if request.client else "unknown"
        if self.bucket and request.url.path not in EXEMPT:
            ok, wait = self.bucket.allow(client)
            if not ok:
                self.metrics.limited += 1
                return JSONResponse(
                    {"detail": "Rate limit exceeded; slow down."},
                    status_code=429,
                    headers={"Retry-After": str(max(1, round(wait))), "X-Request-ID": request_id},
                )
        response = await call_next(request)
        if request.method == "GET" and response.status_code == 200:
            response = await _with_etag(request, response)
        elapsed = time.perf_counter() - t0
        route = _route(request)
        self.metrics.observe(route, request.method, response.status_code, elapsed)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = f"{elapsed * 1000:.1f}"
        access_log.info(
            json.dumps(
                {
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "route": route,
                    "status": response.status_code,
                    "ms": round(elapsed * 1000, 1),
                    "client": client,
                }
            )
        )
        return response


async def _with_etag(request: Request, response: Response) -> Response:
    """Strong ETag over the body; 304 when the client already has it."""
    ctype = response.headers.get("content-type", "")
    if "etag" in response.headers or not (
        ctype.startswith("application/json") or ctype.startswith("text/")
    ):
        return response  # static files already carry their own validator
    body = b""
    async for chunk in response.body_iterator:  # type: ignore[attr-defined]
        body += chunk if isinstance(chunk, bytes) else chunk.encode()
    etag = '"' + hashlib.sha256(body).hexdigest()[:32] + '"'
    headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
    headers["ETag"] = etag
    headers.setdefault("Cache-Control", "no-cache")  # revalidate every time; cheap with 304s
    if etag in [t.strip() for t in request.headers.get("if-none-match", "").split(",")]:
        return Response(
            status_code=304, headers={"ETag": etag, "Cache-Control": headers["Cache-Control"]}
        )
    return Response(
        content=body, status_code=response.status_code, headers=headers, media_type=None
    )


def install(app: Any, metrics: Metrics | None = None) -> Metrics:
    """Wire gzip, ops middleware and GET /metrics into a FastAPI app."""
    from starlette.middleware.gzip import GZipMiddleware

    metrics = metrics or Metrics()
    app.add_middleware(OpsMiddleware, metrics=metrics)
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    return metrics
