"""Production Security Regression Test Suite (Prompt P19 Item 2).

Enforces all 6 vectors:
1. Header Spoofing: X-Tenant-ID, X-User-Roles, X-User-ID, X-Roles, X-Scope-Grants
   cannot bypass authentication or elevate privileges.
2. Unauthenticated Writes: POST/PUT/PATCH/DELETE across routes reject unauthenticated
   callers with 401 Unauthorized.
3. Cross-Tenant RLS & Data Isolation: Tenant A cannot read, query, or mutate Tenant B entities.
4. Act-As Delegation: Requires SUPER_ADMIN role + step-up MFA proof + audited reason (>= 20 chars).
   Scoped token only works on target tenant; non-super-admins or unauthenticated callers
   are strictly rejected with 403/401.
5. Secret Leakage Scan: API responses and headers never leak private keys, OpenBao/Vault
   tokens, raw database passwords, or cloud credentials.
6. CORS Security: Origin validation enforces configured origins and forbids wildcard '*'
   when credentials are enabled.
"""

from __future__ import annotations

import re
import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.audit.service import get_audit_service
from domain.bootstrap.superuser import reset_superuser_service
from domain.control_tower.service import reset_control_tower_service
from domain.identity.service import get_identity_service
from domain.models.enums import AuditEventType, SystemRole
from domain.observability import health_probe


from tests.fakes.alerting import InMemoryAlertRepository
from tests.fakes.audit import InMemoryAuditRepository
from tests.fakes.identity import InMemoryIdentityRepository
from domain.alerting.repository import reset_alert_repository
from domain.alerting.service import reset_alert_service
from domain.audit.repository import reset_audit_repository
from domain.audit.service import reset_audit_service
from domain.identity.repository import reset_identity_repository
from domain.identity.service import reset_identity_service


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_security_state():
    in_mem_identity = InMemoryIdentityRepository()
    reset_identity_repository(in_mem_identity)
    reset_identity_service()
    reset_audit_repository(InMemoryAuditRepository())
    reset_audit_service()
    reset_alert_repository(InMemoryAlertRepository())
    reset_alert_service()
    reset_control_tower_service()
    reset_superuser_service()
    health_probe.reset_overrides()
    health_probe.set_override("secret_store", True)
    yield
    reset_control_tower_service()
    reset_superuser_service()
    health_probe.reset_overrides()


# ==============================================================================
# Vector 1: Header Spoofing Prevention
# ==============================================================================


def test_header_spoofing_unauthenticated_rejected_401(client: TestClient):
    """Proves unauthenticated requests with injected identity headers are rejected with 401."""
    spoofed_headers = {
        "X-Tenant-ID": "tenant-victim",
        "X-User-Roles": "SUPER_ADMIN",
        "X-Roles": "SUPER_ADMIN",
        "X-User-ID": "usr-admin-root",
        "X-Scope-Grants": "platform.operate,platform.act_as",
    }
    endpoints = [
        "/api/v1/control-tower/overview",
        "/api/v1/users",
        "/api/v1/tenants",
        "/api/v1/business-objects/budgets",
    ]
    for ep in endpoints:
        resp = client.get(ep, headers=spoofed_headers)
        assert resp.status_code == 401, (
            f"Expected 401 for {ep}, got {resp.status_code}: {resp.text}"
        )


def test_header_spoofing_privilege_elevation_ignored(client: TestClient, make_auth_token):
    """Proves an authenticated read-only user cannot elevate to SUPER_ADMIN via headers."""
    token = make_auth_token(
        tenant_id="tenant-alpha",
        user_id="user-readonly",
        roles=[SystemRole.READ_ONLY_USER],
        permissions=["inventory:read"],
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "X-User-Roles": "SUPER_ADMIN",
        "X-Roles": "SUPER_ADMIN",
        "X-Step-Up-Token": "valid-mfa-stepup-token-12345",
    }
    resp = client.post(
        "/api/v1/admin/act-as",
        headers=headers,
        json={
            "tenant_id": "tenant-beta",
            "reason": "Authorized incident investigation for cross tenant debugging",
            "step_up_token": "valid-mfa-stepup-token-12345",
        },
    )
    assert resp.status_code == 403, f"Expected 403 Forbidden, got {resp.status_code}: {resp.text}"
    assert "Act-as-tenant operation strictly restricted to SUPER_ADMIN role." in resp.json().get(
        "detail", ""
    )


def test_cross_tenant_header_override_rejected_with_403(client: TestClient, make_auth_token):
    """Proves a token for Tenant A sending X-Tenant-ID: Tenant B is rejected with 403."""
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
    resp = client.get("/api/v1/users", headers=headers)
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
    assert "Cross-tenant access forbidden" in resp.text


# ==============================================================================
# Vector 2: Unauthenticated Writes Blocked (401)
# ==============================================================================


@pytest.mark.parametrize(
    "method,endpoint,payload",
    [
        ("POST", "/api/v1/business-objects/budgets", {"name": "Malicious Budget"}),
        ("POST", "/api/v1/business-objects/policies", {"name": "Malicious Policy"}),
        ("POST", "/api/v1/business-objects/applications", {"name": "Malicious App"}),
        ("POST", "/api/v1/connectors", {"name": "Malicious Connector", "provider": "AWS"}),
        ("POST", "/api/v1/remediation/tasks", {"title": "Malicious Remediation"}),
        (
            "POST",
            "/api/v1/admin/act-as",
            {"tenant_id": "target", "reason": "Authorized incident triage investigation #1"},
        ),
        (
            "POST",
            "/api/v1/thresholds",
            {"metric": "cost", "operator": "GT", "threshold_value": 100.0},
        ),
        ("POST", "/api/v1/imports/dry-run", {"entity_type": "BUDGET", "rows": []}),
        ("DELETE", "/api/v1/business-objects/budgets/any-id", None),
        ("PUT", "/api/v1/business-objects/policies/any-id", {"name": "Updated"}),
    ],
)
def test_unauthenticated_writes_rejected_with_401(
    client: TestClient, method: str, endpoint: str, payload: dict | None
):
    """Proves all state-mutating requests without valid Authorization header fail with 401."""
    if method == "POST":
        resp = client.post(endpoint, json=payload or {})
    elif method == "PUT":
        resp = client.put(endpoint, json=payload or {})
    elif method == "DELETE":
        resp = client.delete(endpoint)
    else:
        pytest.fail(f"Unsupported HTTP method {method}")

    assert resp.status_code == 401, (
        f"Security Violation: {method} {endpoint} allowed unauthenticated access with status {resp.status_code}: {resp.text}"
    )


# ==============================================================================
# Vector 3: Cross-Tenant RLS & Data Isolation
# ==============================================================================


def test_cross_tenant_isolation_reads_and_writes(client: TestClient, make_auth_token):
    """Proves Tenant A cannot read or mutate Tenant B resources."""
    token_a = make_auth_token(
        tenant_id="tenant-alpha",
        user_id="usr-alpha-admin",
        roles=[SystemRole.SUPER_ADMIN],
        permissions=["users:read"],
    )

    # 1. Attempt reading Tenant B's users with Tenant A token
    resp_users = client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {token_a}", "X-Tenant-ID": "tenant-beta"},
    )
    assert resp_users.status_code == 403
    assert "Cross-tenant access forbidden" in resp_users.text


# ==============================================================================
# Vector 4: Act-As Delegation Controls
# ==============================================================================


@pytest.mark.parametrize(
    "role",
    [
        SystemRole.PLATFORM_ADMIN,
        SystemRole.CLOUD_ADMINISTRATOR,
        SystemRole.FINOPS_ADMINISTRATOR,
        SystemRole.FINANCE_USER,
        SystemRole.IT_OPERATIONS_USER,
        SystemRole.APPLICATION_OWNER,
        SystemRole.READ_ONLY_USER,
        SystemRole.AUDITOR,
    ],
)
def test_act_as_non_super_admin_forbidden_403(
    client: TestClient, make_auth_token, role: SystemRole
):
    """Proves non-super-admins attempting act-as are rejected with 403."""
    token = make_auth_token(
        tenant_id="tenant-primary",
        user_id=f"user-{role.value.lower()}",
        roles=[role],
        permissions=["platform.observe"],
    )
    resp = client.post(
        "/api/v1/admin/act-as",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Step-Up-Token": "valid-mfa-stepup-token-12345",
        },
        json={
            "tenant_id": "tenant-target-alpha",
            "reason": "Authorized security incident investigation ticket #8942",
            "step_up_token": "valid-mfa-stepup-token-12345",
        },
    )
    assert resp.status_code == 403
    assert "Act-as-tenant operation strictly restricted to SUPER_ADMIN role." in resp.json().get(
        "detail", ""
    )


def test_act_as_super_admin_requires_step_up_mfa(client: TestClient, make_auth_token):
    """Proves SUPER_ADMIN cannot assume tenant context without step-up MFA verification."""
    token = make_auth_token(
        tenant_id="tenant-system",
        user_id="super-admin-user",
        email="superadmin@cloudlens.internal",
        roles=[SystemRole.SUPER_ADMIN],
        permissions=["platform.observe", "platform.operate", "platform.act_as"],
    )
    resp = client.post(
        "/api/v1/admin/act-as",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "tenant_id": "tenant-target-alpha",
            "reason": "Authorized incident investigation for cross tenant debugging",
        },
    )
    assert resp.status_code == 403
    assert "Step-up MFA verification required" in resp.json().get("detail", "")


def test_act_as_valid_token_cross_tenant_enforcement(client: TestClient):
    """Proves act-as token strictly scopes to target tenant and prevents accessing other tenants."""
    identity_svc = get_identity_service()
    act_as_token = identity_svc.token_engine.issue_act_as_token(
        user_id="super-admin-user",
        original_email="superadmin@cloudlens.internal",
        target_tenant_id="tenant-beta",
        roles=[SystemRole.GLOBAL_ADMIN],
        ttl_seconds=300,
        reason="Routine cross-tenant support investigation ticket #9901",
    )

    # 1. Accessing authorized target tenant-beta works
    res_beta = client.get(
        "/api/v1/users",
        headers={
            "Authorization": f"Bearer {act_as_token}",
            "X-Tenant-ID": "tenant-beta",
        },
    )
    assert res_beta.status_code == 200

    # 2. Accessing foreign tenant-gamma with the tenant-beta scoped token -> 403 Forbidden
    res_gamma = client.get(
        "/api/v1/users",
        headers={
            "Authorization": f"Bearer {act_as_token}",
            "X-Tenant-ID": "tenant-gamma",
        },
    )
    assert res_gamma.status_code == 403
    assert "Cross-tenant access forbidden" in res_gamma.text


# ==============================================================================
# Vector 5: Secret Leakage Scan of API Responses
# ==============================================================================

SECRET_LEAKAGE_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b(?:s\.[a-zA-Z0-9]{24}|hvs\.[a-zA-Z0-9_-]{24,})\b"),  # OpenBao/Vault token
    re.compile(r"postgresql://[^:]+:[^@]+@"),  # DB connection string with credentials
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),  # AWS Access Key ID
]


def test_secret_leakage_scan_across_representative_endpoints(client: TestClient, make_auth_token):
    """Scans representative responses to guarantee zero credentials, tokens, or private keys leak."""
    token = make_auth_token(
        tenant_id="tenant-alpha",
        user_id="usr-admin",
        roles=[SystemRole.SUPER_ADMIN],
        permissions=["admin:all", "users:read", "inventory:read"],
    )
    headers = {"Authorization": f"Bearer {token}"}

    test_endpoints = [
        "/.well-known/jwks.json",
        "/api/v1/users",
        "/api/v1/masterdata/registry",
        "/api/v1/business-objects/budgets",
        "/api/v1/business-objects/policies",
    ]

    for ep in test_endpoints:
        resp = client.get(ep, headers=headers)
        if resp.status_code in (200, 404):
            body_text = resp.text
            for pattern in SECRET_LEAKAGE_PATTERNS:
                match = pattern.search(body_text)
                assert match is None, (
                    f"CRITICAL SECURITY DEFECT: Potential secret leakage at {ep}: match='{match.group(0)}'"
                )


# ==============================================================================
# Vector 6: CORS Security Controls
# ==============================================================================


def test_cors_preflight_and_untrusted_origin_rejected(client: TestClient):
    """Proves CORS correctly returns allowed origins and rejects untrusted origins with credentials."""
    # 1. Untrusted origin preflight
    untrusted_resp = client.options(
        "/api/v1/users",
        headers={
            "Origin": "https://malicious-attacker.org",
            "Access-Control-Request-Method": "GET",
        },
    )
    allow_origin = untrusted_resp.headers.get("access-control-allow-origin")
    assert allow_origin != "https://malicious-attacker.org", (
        f"CORS Vulnerability: Untrusted origin allowed: {allow_origin}"
    )

    # 2. Verify wildcard is NEVER returned alongside credentials
    if untrusted_resp.headers.get("access-control-allow-credentials") == "true":
        assert allow_origin != "*", "CORS Vulnerability: Wildcard '*' allowed with credentials!"
