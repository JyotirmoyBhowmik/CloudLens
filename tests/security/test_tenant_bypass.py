"""Security Tests for Tenant Bypass Prevention (Prompt R-SEC Part 1).

Enforces:
1.1 No hardcoded email bypass.
1.2 Global-admin status derives strictly from SystemRole enum.
1.3 Explicit act-as-tenant flow required for cross-tenant access.
1.4 Without act-as token, foreign X-Tenant-Id returns 403 and records CROSS_TENANT_ACCESS_ATTEMPT.
1.5 Four mandatory test gates:
    a) token: email=admin@jyotirmoyb.com, roles=[] + foreign X-Tenant-Id -> 403 + audit
    b) token: GLOBAL_ADMIN role + foreign header, no act-as -> 403 + audit
    c) act-as token -> 200 for that tenant only; other tenant -> 403
    d) act-as token expires after configured minutes -> 401
"""

import pytest
from starlette.testclient import TestClient

from api.cloudlens_api.main import app
from domain.audit.service import get_audit_service
from domain.identity.service import get_identity_service
from domain.models.enums import AuditEventType, SystemRole


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def identity_service():
    return get_identity_service()


@pytest.fixture
def audit_service():
    return get_audit_service()


def test_tenant_bypass_gate_a_hardcoded_email_no_longer_bypasses(
    client: TestClient, identity_service, audit_service
):
    """Gate a: token with email=admin@jyotirmoyb.com, roles=[] and foreign X-Tenant-ID -> 403 + audit."""
    # Issue a token with email admin@jyotirmoyb.com, tenant "tenant-native", NO roles
    token = identity_service.token_engine.issue_access_token(
        user_id="usr-test-legacy-admin",
        tenant_id="tenant-native",
        email="admin@jyotirmoyb.com",
        roles=[],
        permissions=[],
        session_id="sess-legacy-1",
        token_family_id="fam-legacy-1",
        ttl_seconds=300,
    )

    initial_audit_count = len(
        [
            e
            for e in audit_service.repository._tenant_streams.get("tenant-native", [])
            if e.event_type == AuditEventType.CROSS_TENANT_ACCESS_ATTEMPT
        ]
    )

    response = client.get(
        "/api/v1/users",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-ID": "tenant-foreign",
        },
    )

    assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
    assert "Cross-tenant access forbidden" in response.text

    # Verify CROSS_TENANT_ACCESS_ATTEMPT audit event was recorded
    matching_audits = [
        e
        for e in audit_service.repository._tenant_streams.get("tenant-native", [])
        if e.event_type == AuditEventType.CROSS_TENANT_ACCESS_ATTEMPT
    ]
    assert len(matching_audits) > initial_audit_count


def test_tenant_bypass_gate_b_global_admin_without_act_as_rejected(
    client: TestClient, identity_service, audit_service
):
    """Gate b: token with GLOBAL_ADMIN role + foreign header, no act-as -> 403 + audit."""
    token = identity_service.token_engine.issue_access_token(
        user_id="usr-test-global-admin",
        tenant_id="tenant-system",
        email="globaladmin@enterprise.internal",
        roles=[SystemRole.GLOBAL_ADMIN],
        permissions=["admin:all"],
        session_id="sess-ga-1",
        token_family_id="fam-ga-1",
        ttl_seconds=300,
    )

    initial_audit_count = len(
        [
            e
            for e in audit_service.repository._tenant_streams.get("tenant-system", [])
            if e.event_type == AuditEventType.CROSS_TENANT_ACCESS_ATTEMPT
        ]
    )

    response = client.get(
        "/api/v1/users",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-ID": "tenant-customer-a",
        },
    )

    assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
    assert "Cross-tenant access forbidden" in response.text

    matching_audits = [
        e
        for e in audit_service.repository._tenant_streams.get("tenant-system", [])
        if e.event_type == AuditEventType.CROSS_TENANT_ACCESS_ATTEMPT
    ]
    assert len(matching_audits) > initial_audit_count


def test_tenant_bypass_gate_c_act_as_token_scoped_to_target_tenant_only(
    client: TestClient, identity_service
):
    """Gate c: act-as token -> 200 for that tenant only; other tenant -> 403."""
    # Issue valid act-as token for target tenant 'tenant-target'
    act_as_token = identity_service.token_engine.issue_act_as_token(
        user_id="usr-global-operator",
        original_email="operator@enterprise.internal",
        target_tenant_id="tenant-target",
        roles=[SystemRole.GLOBAL_ADMIN],
        ttl_seconds=600,
        reason="Investigating billing anomaly incident INC-9901",
    )

    # 1. Accessing target tenant -> 200 OK
    res_target = client.get(
        "/api/v1/users",
        headers={
            "Authorization": f"Bearer {act_as_token}",
            "X-Tenant-ID": "tenant-target",
        },
    )
    assert res_target.status_code == 200, f"Expected 200, got {res_target.status_code}: {res_target.text}"

    # 2. Accessing another tenant (tenant-other) with this act-as token -> 403
    res_other = client.get(
        "/api/v1/users",
        headers={
            "Authorization": f"Bearer {act_as_token}",
            "X-Tenant-ID": "tenant-other",
        },
    )
    assert res_other.status_code == 403, f"Expected 403, got {res_other.status_code}: {res_other.text}"


def test_tenant_bypass_gate_d_act_as_token_expiration(
    client: TestClient, identity_service
):
    """Gate d: act-as token expires after configured minutes -> 401."""
    # Issue expired act-as token
    expired_token = identity_service.token_engine.issue_act_as_token(
        user_id="usr-global-operator",
        original_email="operator@enterprise.internal",
        target_tenant_id="tenant-target",
        roles=[SystemRole.GLOBAL_ADMIN],
        ttl_seconds=-10,  # Expired 10 seconds ago
        reason="Past investigation expired session",
    )

    response = client.get(
        "/api/v1/users",
        headers={
            "Authorization": f"Bearer {expired_token}",
            "X-Tenant-ID": "tenant-target",
        },
    )
    assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
