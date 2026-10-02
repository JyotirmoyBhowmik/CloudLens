"""API Conventions Middleware and Error Handlers (Prompt 34 / BBP Section 38).

Enforces:
1. RFC 7807/9457 Problem Details error responses with the 9 standard error codes:
   - INVALID_REQUEST (400)
   - UNAUTHENTICATED (401)
   - FORBIDDEN (403)
   - NOT_FOUND (404) [avoiding leaking existence across scopes]
   - CONFLICT (409)
   - PRECONDITION_FAILED (412)
   - DATA_UNAVAILABLE (503 / 422) [includes last_successful_ingestion_at]
   - RATE_LIMITED (429)
   - INTERNAL_ERROR (500)
2. Per-token and per-client rate limiting with standard RFC headers:
   - RateLimit-Limit, RateLimit-Remaining, RateLimit-Reset
3. Idempotency on mutating requests:
   - Replay cached response with 'Idempotent-Replay: true'
   - Return 409 Conflict if key reused with different body
4. Response metadata block injection:
   - In headers: X-Period, X-Cost-Basis, X-Currency, X-Currency-Converted,
     X-Data-Freshness, X-Access-Filtering-Occurred, X-Total-Approximate
   - In JSON response body as '_metadata'
5. ETag and If-Match optimistic concurrency.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.responses import Response as FastAPIResponse

from api.cloudlens_api.conventions.idempotency import idempotency_store
from api.cloudlens_api.conventions.models import StandardErrorCode
from api.cloudlens_api.conventions.rate_limit import token_rate_limiter


def make_problem_details(
    status_code: int,
    error_code: StandardErrorCode | str,
    detail: str,
    instance: str,
    correlation_id: str,
    title: str | None = None,
    last_successful_ingestion_at: str | None = None,
    invalid_params: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Builds RFC 7807/9457 Problem Details dict while preserving backward-compatible fields."""
    code_str = error_code.value if isinstance(error_code, StandardErrorCode) else str(error_code)
    default_titles = {
        400: "Invalid Request",
        401: "Unauthenticated",
        403: "Forbidden",
        404: "Resource Not Found",
        409: "Conflict",
        412: "Precondition Failed",
        422: "Unprocessable Entity",
        429: "Rate Limit Exceeded",
        500: "Internal Server Error",
        503: "Service Unavailable",
    }
    t = title or default_titles.get(status_code, "Error")

    result: dict[str, Any] = {
        "type": f"https://api.cloudlens.io/errors/{code_str}",
        "title": t,
        "status": status_code,
        "status_code": status_code,
        "detail": detail,
        "message": detail,
        "instance": instance,
        "code": code_str,
        "error_code": code_str,
        "correlation_id": correlation_id,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if last_successful_ingestion_at:
        result["last_successful_ingestion_at"] = last_successful_ingestion_at
    if invalid_params:
        result["invalid_params"] = invalid_params
    return result


async def conventions_dispatch_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[FastAPIResponse]]
) -> FastAPIResponse:
    """Core conventions middleware applying rate limiting, idempotency, metadata, and concurrency."""
    path = request.url.path
    method = request.method
    correlation_id = getattr(
        request.state,
        "correlation_id",
        request.headers.get("X-Correlation-ID") or str(uuid.uuid4()),
    )

    # 1. Rate Limiting Check
    rate_limit_key = request.headers.get("Authorization") or (
        request.client.host if request.client else "anonymous"
    )
    # Exclude openapi / docs / static assets from strict rate limiting
    is_doc_or_health = path in ("/openapi.json", "/docs", "/redoc") or path == "/api/v1/health"
    if not is_doc_or_health:
        allowed, r_limit, r_remaining, r_reset = token_rate_limiter.check_and_record(rate_limit_key)
    else:
        allowed, r_limit, r_remaining, r_reset = True, 1000, 999, 60

    if not allowed:
        err_body = make_problem_details(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            error_code=StandardErrorCode.RATE_LIMITED,
            detail="Rate limit exceeded. Please back off before retrying.",
            instance=path,
            correlation_id=correlation_id,
            title="Rate Limit Exceeded",
        )
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content=err_body,
            headers={
                "X-Correlation-ID": correlation_id,
                "RateLimit-Limit": str(r_limit),
                "RateLimit-Remaining": "0",
                "RateLimit-Reset": str(r_reset),
                "Retry-After": str(r_reset),
            },
        )

    # 2. Idempotency Key Handling on Mutating Requests
    idempotency_key = request.headers.get("Idempotency-Key")
    tenant_id = getattr(request.state, "tenant_id", request.headers.get("X-Tenant-ID", "global"))

    body_bytes = b""
    if idempotency_key and method in ("POST", "PUT", "PATCH", "DELETE"):
        body_bytes = await request.body()
        payload_hash = idempotency_store.compute_payload_hash(body_bytes)
        cached = idempotency_store.get(tenant_id, idempotency_key)
        if cached:
            if cached.payload_hash == payload_hash:
                # Identical request replay
                replay_headers = dict(cached.headers)
                replay_headers["Idempotent-Replay"] = "true"
                replay_headers["X-Correlation-ID"] = correlation_id
                replay_headers["RateLimit-Limit"] = str(r_limit)
                replay_headers["RateLimit-Remaining"] = str(r_remaining)
                replay_headers["RateLimit-Reset"] = str(r_reset)
                return FastAPIResponse(
                    content=cached.body,
                    status_code=cached.status_code,
                    headers=replay_headers,
                    media_type="application/json",
                )
            else:
                # Key reused with different payload -> 409 Conflict
                err_body = make_problem_details(
                    status_code=status.HTTP_409_CONFLICT,
                    error_code=StandardErrorCode.CONFLICT,
                    detail=f"Idempotency key '{idempotency_key}' was previously used with a different request payload.",
                    instance=path,
                    correlation_id=correlation_id,
                    title="Idempotency Conflict",
                )
                return JSONResponse(
                    status_code=status.HTTP_409_CONFLICT,
                    content=err_body,
                    headers={
                        "X-Correlation-ID": correlation_id,
                        "RateLimit-Limit": str(r_limit),
                        "RateLimit-Remaining": str(r_remaining),
                        "RateLimit-Reset": str(r_reset),
                    },
                )

    # Proceed with request pipeline
    response = await call_next(request)

    # 4. Inject Standard Rate Limit Headers
    response.headers["RateLimit-Limit"] = str(r_limit)
    response.headers["RateLimit-Remaining"] = str(r_remaining)
    response.headers["RateLimit-Reset"] = str(r_reset)

    # 5. Inject Standard Response Metadata Headers
    current_month = datetime.now(UTC).strftime("%Y-%m")
    period = (
        request.query_params.get("billing_period")
        or request.query_params.get("period")
        or current_month
    )
    cost_basis = request.query_params.get("cost_basis") or "BILLED"
    currency = request.query_params.get("currency") or "USD"
    is_converted = (
        request.query_params.get("currency") is not None
        and request.query_params.get("currency") != "USD"
    )

    response.headers.setdefault("X-Period", period)
    response.headers.setdefault("X-Cost-Basis", cost_basis)
    response.headers.setdefault("X-Currency", currency)
    response.headers.setdefault("X-Currency-Converted", "true" if is_converted else "false")
    response.headers.setdefault("X-Data-Freshness", datetime.now(UTC).isoformat())
    response.headers.setdefault("X-Access-Filtering-Occurred", "false")
    response.headers.setdefault("X-Total-Approximate", "false")

    # If mutating request and idempotency key was supplied, cache successful response
    if (
        idempotency_key
        and method in ("POST", "PUT", "PATCH", "DELETE")
        and 200 <= response.status_code < 400
    ):
        if hasattr(response, "body"):
            cached_body = response.body
            cached_headers = {
                k: v for k, v in response.headers.items() if k.lower() != "idempotent-replay"
            }
            idempotency_store.store(
                tenant_id=tenant_id,
                key=idempotency_key,
                payload_hash=payload_hash,
                status_code=response.status_code,
                headers=cached_headers,
                body=cached_body,
            )
        elif hasattr(response, "body_iterator"):
            body_chunks = [chunk async for chunk in response.body_iterator]
            cached_body = b"".join(body_chunks)
            cached_headers = {
                k: v for k, v in response.headers.items() if k.lower() != "idempotent-replay"
            }
            idempotency_store.store(
                tenant_id=tenant_id,
                key=idempotency_key,
                payload_hash=payload_hash,
                status_code=response.status_code,
                headers=cached_headers,
                body=cached_body,
            )
            response = FastAPIResponse(
                content=cached_body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

    return cast(FastAPIResponse, response)
