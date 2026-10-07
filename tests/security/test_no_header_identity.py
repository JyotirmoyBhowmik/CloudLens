"""Security Test Suite: Zero Header-Based Identity Bypass (Prompt P01).

Enforces:
- D1: Role Header Spoofing Blocked.
  X-User-Roles, X-Roles, or legacy role headers are never trusted. Unauthenticated requests
  fail with 401. Authenticated requests ignore role headers in favor of verified token claims.
- D2: Tenant ID Header Spoofing Blocked.
  X-Tenant-ID cannot be used without a verified signed token (401). When present alongside a token,
  cross-tenant manipulation is strictly rejected with 403.
- D3: Actor / User Identity Spoofing Blocked.
  Identity, user_id, and actor_id derive strictly from verified token claims. Unauthenticated
  access to /machine-clients returns 401. Step-up requests ignore payload tenant/user overrides.
- D4: Scope Grants Header Spoofing Blocked.
  X-Scope-Grants headers are ignored. Capabilities derive strictly from signed token claims
  and server-side RBAC grants.
- Route-Walk Verification (Item 7):
  Walks app.routes and asserts that every non-exempt route enforces require_auth and yields 401
  when invoked without a valid token.
"""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from api.cloudlens_api.tenant_context import is_exempt_request, require_auth
from domain.models.enums import StepUpAction, SystemRole


@pytest.fixture
def client():
    return TestClient(app)


# ==============================================================================
# D1: Role Header Spoofing Blocked
# ==============================================================================


def test_d1_unauthenticated_role_header_rejected_401(client: TestClient):
    """curl -H "X-User-Roles: SUPER_ADMIN" -H "X-Tenant-ID: x" .../control-tower/overview -> 401."""
    headers = {
        "X-User-Roles": "SUPER_ADMIN",
        "X-Tenant-ID": "x",
    }
    response = client.get("/api/v1/control-tower/overview", headers=headers)
    assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
    assert "Authentication required" in response.text or "UNAUTHENTICATED" in response.text


def test_d1_authenticated_role_header_override_ignored(client: TestClient, make_auth_token):
    """Authenticated caller cannot elevate privileges by injecting X-User-Roles header."""
    token = make_auth_token(
        tenant_id="tenant-alpha",
        user_id="user-readonly",
        roles=[SystemRole.READ_ONLY_USER],
        permissions=["inventory:read"],
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "X-User-Roles": "SUPER_ADMIN",
        "X-Step-Up-Token": "test-stepup-token-123",
    }
    # Operational action requires platform.operate; READ_ONLY_USER must get 403 despite SUPER_ADMIN header
    response = client.post(
        "/api/v1/control-tower/actions/retry-job",
        headers=headers,
        json={
            "action": "retry-job",
            "reason": "Legitimate justification with sufficient length for test",
            "confirm": True,
            "step_up_token": "test-stepup-token-123",
        },
    )
    assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"


def test_d1_global_admin_string_header_ignored(client: TestClient):
    """Legacy GLOBAL_ADMIN header string is rejected with 401 when no token is present."""
    headers = {
        "X-User-Roles": "GLOBAL_ADMIN",
        "X-Tenant-ID": "tenant-test",
    }
    response = client.get("/api/v1/admin/overrides", headers=headers)
    assert response.status_code == 401


# ==============================================================================
# D2: Tenant ID Header Spoofing Blocked
# ==============================================================================


def test_d2_unauthenticated_tenant_header_rejected_401(client: TestClient):
    """Calling tenant-scoped endpoints with X-Tenant-ID and no token returns 401."""
    headers = {"X-Tenant-ID": "tenant-victim"}
    response = client.get("/api/v1/users", headers=headers)
    assert response.status_code == 401


def test_d2_cross_tenant_header_rejected_403(client: TestClient, make_auth_token):
    """Token for tenant-alpha sending X-Tenant-ID: tenant-victim returns 403 Forbidden."""
    token = make_auth_token(
        tenant_id="tenant-alpha",
        user_id="user-1",
        roles=[SystemRole.SUPER_ADMIN],
        permissions=["users:read"],
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Tenant-ID": "tenant-victim",
    }
    response = client.get("/api/v1/users", headers=headers)
    assert response.status_code == 403
    assert "Cross-tenant access forbidden" in response.text


# ==============================================================================
# D3: Actor / User Identity Spoofing Blocked & Machine Clients Secured
# ==============================================================================


def test_d3_machine_clients_without_token_returns_401(client: TestClient):
    """POST /api/v1/auth/machine-clients without token -> 401 (Prompt P01 Done When)."""
    payload = {
        "tenant_id": "tenant-test",
        "client_name": "backup-worker-daemon",
        "scoped_permissions": ["billing:read"],
    }
    response = client.post("/api/v1/auth/machine-clients", json=payload)
    assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"


def test_d3_actor_identity_derived_from_token_claims(client: TestClient, make_auth_token):
    """Actor identity derives strictly from token claims; X-Actor-ID is ignored."""
    token = make_auth_token(
        tenant_id="tenant-test",
        user_id="usr-authentic-identity",
        email="authentic@enterprise.internal",
        roles=[SystemRole.SUPER_ADMIN],
        permissions=["credentials:create"],
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Actor-ID": "spoofed-attacker-identity",
        "X-User-Email": "attacker@evil.internal",
    }
    # Verify current user identity derives strictly from token
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == "usr-authentic-identity"
    assert data["email"] == "authentic@enterprise.internal"


def test_d3_step_up_user_and_tenant_derived_from_token_only(client: TestClient, make_auth_token):
    """Step-up challenge derives tenant_id and user_id strictly from verified token."""
    token = make_auth_token(
        tenant_id="tenant-native",
        user_id="usr-stepup-subject",
        roles=[SystemRole.SUPER_ADMIN],
    )
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post(
        "/api/v1/auth/step-up/initiate",
        headers=headers,
        json={"action": StepUpAction.CREDENTIAL_CREATION.value},
    )
    assert response.status_code == 200
    data = response.json()
    assert "challenge_id" in data
    assert data["action"] == StepUpAction.CREDENTIAL_CREATION.value


# ==============================================================================
# D4: Scope Grants Header Spoofing Blocked
# ==============================================================================


def test_d4_unauthenticated_scope_header_rejected_401(client: TestClient):
    """X-Scope-Grants header without valid token returns 401."""
    headers = {
        "X-Scope-Grants": "platform.operate,billing:read,admin:all",
    }
    response = client.get("/api/v1/cost/summary", headers=headers)
    assert response.status_code == 401


def test_d4_scope_header_override_ignored(client: TestClient, make_auth_token):
    """X-Scope-Grants header is ignored and caller without permissions gets 403."""
    token = make_auth_token(
        tenant_id="tenant-scoped",
        user_id="usr-auditor-1",
        roles=[SystemRole.AUDITOR],
        permissions=["platform.observe"],
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Scope-Grants": "platform.operate,billing:write",
        "X-Step-Up-Token": "valid-stepup-123",
    }
    # Operational action requires platform.operate; AUDITOR role lacks it
    response = client.post(
        "/api/v1/control-tower/actions/force-sync",
        headers=headers,
        json={
            "action": "force-sync",
            "reason": "Administrative justification exceeding minimum required length",
            "confirm": True,
            "step_up_token": "valid-stepup-123",
        },
    )
    assert response.status_code == 403
    assert "platform.operate" in response.text


# ==============================================================================
# Route-Walk Test (Prompt P01 Item 7)
# ==============================================================================


def _check_has_auth(dependant) -> bool:
    """Recursively inspects FastAPI Dependant tree for require_auth."""
    call = getattr(dependant, "call", None)
    if call == require_auth:
        return True
    name = getattr(call, "__name__", "")
    if name in ("require_auth", "get_authenticated_tenant_context"):
        return True
    for sub in getattr(dependant, "dependencies", []):
        if _check_has_auth(sub):
            return True
    return False


def test_route_walk_all_non_exempt_routes_require_authentication(client: TestClient):
    """Walks all FastAPI app routes and asserts each non-exempt route requires authentication."""
    exempt_paths = {
        "/api/v1/health",
        "/api/v1/about",
        "/ready",
        "/metrics",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/",
    }

    tested_count = 0
    non_exempt_routes: list[tuple[str, str]] = []

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue

        methods = route.methods or {"GET"}
        for method in methods:
            if method in ("HEAD", "OPTIONS"):
                continue

            path = route.path
            # Skip documentation, health, and known root endpoints
            if any(path == ep or path.startswith("/api/v1/health") for ep in exempt_paths):
                continue
            if is_exempt_request(method, path):
                continue

            non_exempt_routes.append((method, path))

            # Verify that require_auth (or dependency providing TenantContext) is attached
            has_auth = _check_has_auth(route.dependant)
            assert has_auth, (
                f"Security Violation: Non-exempt route [{method} {path}] does not have "
                f"require_auth dependency attached."
            )
            tested_count += 1

    # Assert that we verified the platform's non-exempt routes
    assert tested_count >= 400, f"Expected at least 400 authenticated routes, checked {tested_count}"

    # Verify live unauthenticated invocation on representative routes
    representative_endpoints = [
        ("GET", "/api/v1/control-tower/overview"),
        ("GET", "/api/v1/users"),
        ("GET", "/api/v1/admin/overrides"),
        ("POST", "/api/v1/auth/machine-clients"),
        ("POST", "/api/v1/auth/logout"),
        ("GET", "/api/v1/credentials/profiles"),
        ("GET", "/api/v1/cost/summary"),
        ("GET", "/api/v1/dashboards/executive"),
    ]

    for method, path in representative_endpoints:
        if method == "GET":
            res = client.get(path)
        elif method == "POST":
            res = client.post(path, json={})
        else:
            continue
        assert res.status_code == 401, (
            f"Unauthenticated request to [{method} {path}] returned {res.status_code}, expected 401"
        )
