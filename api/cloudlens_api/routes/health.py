"""CloudLens Health, Readiness, Liveness & Prometheus Metrics Endpoints."""

from typing import Any

from fastapi import APIRouter, HTTPException, Response, status

from domain.observability import health_probe, metrics

router = APIRouter(tags=["Health & Metrics"])


@router.get("/api/v1/health/liveness", summary="Kubernetes liveness probe")
async def liveness_probe() -> dict[str, Any]:
    """Basic liveness probe checking process and event loop responsiveness."""
    return health_probe.evaluate_liveness()


@router.get("/api/v1/health/readiness", summary="Kubernetes readiness probe")
async def readiness_probe() -> dict[str, Any]:
    """Readiness probe verifying database, cache, and queue dependency connectivity.

    Returns 200 OK when all systems are reachable, or 503 SERVICE UNAVAILABLE if any
    dependency is degraded or disconnected.
    """
    is_ready, report = health_probe.evaluate_readiness()
    if not is_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=report,
        )
    return report


@router.get("/metrics", summary="Prometheus scrapable metrics")
async def prometheus_metrics() -> Response:
    """Exposes all 12 platform Prometheus metrics in standard exposition text format."""
    data = metrics.scrape()
    return Response(content=data, media_type="text/plain; version=0.0.4; charset=utf-8")
