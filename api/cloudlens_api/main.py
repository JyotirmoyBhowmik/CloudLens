"""CloudLens API - Application Layer."""

import time
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

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
    """Propagate Correlation-ID and measure request latency (Enterprise Rule 4.2)."""
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    request.state.correlation_id = correlation_id
    start_time = time.perf_counter()

    try:
        response: Response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - start_time) * 1000.0
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

    duration_ms = (time.perf_counter() - start_time) * 1000.0
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
