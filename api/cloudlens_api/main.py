"""CloudLens API - Application Layer."""

import time
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.cloudlens_api.routes import (
    attribution_router,
    auth_router,
    bootstrap_router,
    config_router,
    demo_mode_router,
    demo_router,
    health_router,
    masterdata_router,
)
from domain.models.exceptions import DomainModelException
from domain.observability import (
    current_correlation_id,
    current_operation,
    current_tenant_id,
    get_logger,
    metrics,
    setup_tracing,
    trace_api_request,
)

# Initialize OpenTelemetry in-memory / OTLP tracing
setup_tracing(service_name="cloudlens-api", in_memory=True)
logger = get_logger("cloudlens.api")

app = FastAPI(
    title="CloudLens API",
    description="Multi-cloud governance, inventory, pricing, cost, usage, and budgeting API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def correlation_id_and_timing_middleware(request: Request, call_next):
    """Propagate Correlation-ID, execute OpenTelemetry span, and record Prometheus metrics."""
    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    tenant_id = request.headers.get("X-Tenant-ID", "global")
    request.state.correlation_id = correlation_id
    request.state.tenant_id = tenant_id

    current_correlation_id.set(correlation_id)
    current_tenant_id.set(tenant_id)
    current_operation.set(f"{request.method} {request.url.path}")

    start_time = time.perf_counter()

    with trace_api_request(
        endpoint=request.url.path,
        method=request.method,
        correlation_id=correlation_id,
        tenant_id=tenant_id,
    ):
        try:
            response: Response = await call_next(request)
            status_code = response.status_code
        except Exception:
            duration_s = time.perf_counter() - start_time
            duration_ms = duration_s * 1000.0
            metrics.api_request_duration_seconds.labels(
                method=request.method,
                endpoint=request.url.path,
                status_code="500",
            ).observe(duration_s)
            logger.error(
                "Request failed with unhandled internal server error",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": 500,
                    "duration_ms": duration_ms,
                },
            )
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "timestamp": datetime.now(UTC).isoformat(),
                    "status_code": 500,
                    "error_code": "INTERNAL_SERVER_ERROR",
                    "correlation_id": correlation_id,
                    "message": "An internal server error occurred.",
                },
                headers={
                    "X-Correlation-ID": correlation_id,
                    "X-Response-Time-MS": f"{duration_ms:.2f}",
                },
            )

        duration_s = time.perf_counter() - start_time
        duration_ms = duration_s * 1000.0
        metrics.api_request_duration_seconds.labels(
            method=request.method,
            endpoint=request.url.path,
            status_code=str(status_code),
        ).observe(duration_s)

        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Response-Time-MS"] = f"{duration_ms:.2f}"
        return response


@app.exception_handler(HTTPException)
async def standardized_http_exception_handler(request: Request, exc: HTTPException):
    """Sanitized and standardized error response (Enterprise Rule 2.4)."""
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "timestamp": datetime.now(UTC).isoformat(),
            "status_code": exc.status_code,
            "error_code": "HTTP_ERROR",
            "correlation_id": correlation_id,
            "message": str(exc.detail),
        },
        headers={"X-Correlation-ID": correlation_id},
    )


@app.exception_handler(DomainModelException)
async def standardized_domain_exception_handler(request: Request, exc: DomainModelException):
    """Global domain model exception handler mapping business errors to sanitized JSON (Rule 2.3 & 2.4)."""
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "timestamp": datetime.now(UTC).isoformat(),
            "status_code": 422,
            "error_code": exc.error_code,
            "correlation_id": correlation_id,
            "message": exc.message,
        },
        headers={"X-Correlation-ID": correlation_id},
    )


app.include_router(config_router)
app.include_router(auth_router)
app.include_router(health_router)
app.include_router(masterdata_router)
app.include_router(bootstrap_router)
app.include_router(attribution_router)
app.include_router(demo_router)
app.include_router(demo_mode_router)


class HealthResponse(BaseModel):
    status: str = Field(default="healthy", description="Service health status")
    service: str = Field(default="cloudlens-api", description="Service identifier")
    version: str = Field(default="0.1.0", description="API version")
    timestamp: str = Field(description="ISO 8601 UTC timestamp")
    correlation_id: str = Field(description="Request trace correlation ID")


@app.get("/api/v1/health", response_model=HealthResponse, tags=["Health"])
async def health_check(request: Request) -> dict[str, Any]:
    """Health check endpoint for liveness and readiness monitoring."""
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    return {
        "status": "healthy",
        "service": "cloudlens-api",
        "version": "0.1.0",
        "timestamp": datetime.now(UTC).isoformat(),
        "correlation_id": correlation_id,
    }


@app.get("/", tags=["Root"])
async def root() -> dict[str, str]:
    """Root redirect / index information."""
    return {
        "message": "Welcome to CloudLens API. Visit /docs for OpenAPI documentation.",
        "status": "operational",
    }
