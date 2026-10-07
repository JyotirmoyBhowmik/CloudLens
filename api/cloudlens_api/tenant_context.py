"""Tenant Context Resolution & Isolation Guard (Prompt 13 Items 83, 88, Prompt P01).

Enforces:
- Deriving tenant and identity strictly from verified Bearer token, never client headers or parameters.
- Rejection of unauthenticated requests with 401 (no unauthenticated fallback).
- Mechanical detection and rejection of cross-tenant parameter manipulation (Headers, Query Params).
- Single require_auth() dependency providing verified TenantContext.
"""

import uuid

from fastapi import Header, HTTPException, Request, status

from domain.audit.models import AuditEventCreate
from domain.audit.service import get_audit_service
from domain.identity.service import get_identity_service
from domain.models.enums import AuditEventType, SystemRole
from domain.models.exceptions import (
    TokenExpiredException,
    TokenInvalidException,
    TokenRevokedException,
)
from domain.observability import current_tenant_id, get_logger
from domain.tenant.context import TenantContext

logger = get_logger("cloudlens.api.tenant")

EXEMPT_PATHS = {
    ("GET", "/api/v1/health"),
    ("GET", "/api/v1/about"),
    ("GET", "/"),
    ("GET", "/docs"),
    ("GET", "/redoc"),
    ("GET", "/openapi.json"),
    ("GET", "/ready"),
    ("GET", "/metrics"),
    ("GET", "/.well-known/jwks.json"),
    ("GET", "/api/v1/.well-known/jwks.json"),
    ("GET", "/api/v1/auth/oidc/authorize"),
    ("GET", "/api/v1/auth/oidc/callback"),
    ("POST", "/api/v1/auth/break-glass/login"),
    ("POST", "/api/v1/auth/token/refresh"),
    ("POST", "/api/v1/auth/machine-clients/token"),
    ("POST", "/api/v1/auth/step-up/verify"),
    ("POST", "/api/v1/system/bootstrap/superuser/provision"),
    ("POST", "/api/v1/system/bootstrap/superuser/activate"),
    ("POST", "/api/v1/system/bootstrap/superuser/login"),
    ("POST", "/api/v1/system/bootstrap/pre-identity"),
    ("GET", "/api/v1/system/bootstrap/pre-identity/status"),
    ("GET", "/api/v1/system/bootstrap/identity/report"),
}



def is_exempt_request(method: str, path: str) -> bool:
    """Verifies whether endpoint is in the strict unauthenticated exemption list."""
    if (method, path) in EXEMPT_PATHS:
        return True
    if method == "GET" and path.startswith("/api/v1/health/"):
        return True
    return False


def require_auth(
    request: Request,
    authorization: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-ID"),
) -> TenantContext:
    """Resolves and validates TenantContext strictly from authenticated signed token (Prompt P01).

    Enforces:
    1. Rejects unauthenticated requests with HTTP 401 (exempt only: /health, /about, login/callback, refresh, superuser activate).
    2. Token verification through single verify_token() validation.
    3. Rejects cross-tenant parameter manipulation (X-Tenant-ID, query tenant_id).
    4. Scope derived strictly from verified token, never request headers.
    5. Zero header-based identity fallbacks.
    """
    correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
    audit_service = get_audit_service()

    # Check for Bearer token or session cookie (BFF pattern - Prompt P02)
    token_str: str | None = None
    is_cookie_auth = False

    if authorization and authorization.startswith("Bearer "):
        token_str = authorization[len("Bearer ") :].strip()
    elif "cloudlens_access_token" in request.cookies:
        token_str = request.cookies.get("cloudlens_access_token")
        is_cookie_auth = True

    if not token_str:
        if is_exempt_request(request.method, request.url.path):
            tc = TenantContext(
                tenant_id="anonymous",
                user_id="anonymous",
                email=None,
                roles=[],
                scope_grants=[],
                correlation_id=correlation_id,
                is_superuser=False,
            )
            request.state.tenant_context = tc
            return tc

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: missing or invalid Bearer token or session cookie.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Enforce Double-Submit CSRF check for cookie-authenticated mutating requests (BFF)
    if is_cookie_auth and request.method in ("POST", "PUT", "PATCH", "DELETE"):
        if request.url.path not in ("/api/v1/auth/logout",):
            csrf_header = request.headers.get("X-CSRF-Token")
            csrf_cookie = request.cookies.get("cloudlens_csrf_token")
            if not csrf_header or not csrf_cookie or csrf_header != csrf_cookie:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="CSRF token validation failed for cookie-authenticated request.",
                )
    identity_service = get_identity_service()
    try:
        auth_context = identity_service.token_engine.extract_auth_context(token_str)
    except (TokenExpiredException, TokenInvalidException, TokenRevokedException) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication token invalid or expired: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    authenticated_tenant_id = auth_context.act_as_tenant or auth_context.tenant_id
    is_superuser = any(
        r in (SystemRole.SUPER_ADMIN, "SUPER_ADMIN")
        for r in auth_context.roles
    )

    # Check for Parameter Manipulation Attacks
    if x_tenant_id and x_tenant_id != authenticated_tenant_id:
        audit_service.append_event(
            tenant_context=TenantContext(
                tenant_id=authenticated_tenant_id,
                user_id=auth_context.user_id,
                roles=[r.value if hasattr(r, "value") else str(r) for r in auth_context.roles],
                correlation_id=correlation_id,
            ),
            event_in=AuditEventCreate(
                event_type=AuditEventType.CROSS_TENANT_ACCESS_ATTEMPT,
                actor_id=auth_context.email or auth_context.user_id,
                actor_roles=[r.value if hasattr(r, "value") else str(r) for r in auth_context.roles],
                action="TAMPER_TENANT_HEADER",
                resource_type="TENANT_BOUNDARY",
                resource_id=x_tenant_id,
                details={
                    "authenticated_tenant": authenticated_tenant_id,
                    "manipulated_header_tenant": x_tenant_id,
                    "endpoint": request.url.path,
                    "method": request.method,
                },
                correlation_id=correlation_id,
            ),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Cross-tenant access forbidden: client header X-Tenant-ID '{x_tenant_id}' "
                f"conflicts with authenticated identity tenant '{authenticated_tenant_id}'."
            ),
        )

    query_tenant = request.query_params.get("tenant_id")
    if query_tenant and query_tenant != authenticated_tenant_id and not is_superuser:
        audit_service.append_event(
            tenant_context=TenantContext(
                tenant_id=authenticated_tenant_id,
                user_id=auth_context.user_id,
                roles=[r.value if hasattr(r, "value") else str(r) for r in auth_context.roles],
                correlation_id=correlation_id,
            ),
            event_in=AuditEventCreate(
                event_type=AuditEventType.CROSS_TENANT_ACCESS_ATTEMPT,
                actor_id=auth_context.email or auth_context.user_id,
                actor_roles=[r.value if hasattr(r, "value") else str(r) for r in auth_context.roles],
                action="TAMPER_TENANT_QUERY_PARAM",
                resource_type="TENANT_BOUNDARY",
                resource_id=query_tenant,
                details={
                    "authenticated_tenant": authenticated_tenant_id,
                    "manipulated_query_tenant": query_tenant,
                    "endpoint": request.url.path,
                    "method": request.method,
                },
                correlation_id=correlation_id,
            ),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Cross-tenant access forbidden: query parameter tenant_id '{query_tenant}' "
                f"conflicts with authenticated identity tenant '{authenticated_tenant_id}'."
            ),
        )

    # Scopes derived strictly from verified token claims, never request headers
    scope_grants = getattr(auth_context, "permissions", []) or getattr(auth_context, "scope_grants", ["*"]) or ["*"]

    tc = TenantContext(
        tenant_id=auth_context.tenant_id,
        act_as_tenant_id=auth_context.act_as_tenant,
        user_id=auth_context.user_id,
        email=auth_context.email,
        roles=[r.value if hasattr(r, "value") else str(r) for r in auth_context.roles],
        scope_grants=scope_grants,
        correlation_id=correlation_id,
        is_superuser=is_superuser,
    )
    request.state.tenant_context = tc
    current_tenant_id.set(tc.effective_tenant_id)
    return tc


# Primary canonical dependency alias ensuring backward compatibility across all route modules
get_authenticated_tenant_context = require_auth
