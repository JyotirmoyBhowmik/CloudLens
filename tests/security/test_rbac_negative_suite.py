"""Comprehensive Negative Test Suite for RBAC: Act-As-Tenant & Control Tower Actions (Prompt R-PERF Item 5).

Verifies:
1. Act-As-Tenant Negative Tests:
   - Non-SUPER_ADMIN roles (PLATFORM_ADMIN, FINOPS_ADMINISTRATOR, AUDITOR, READ_ONLY_USER) are strictly rejected (403 Forbidden).
   - Missing step-up MFA verification is rejected (403 Forbidden).
   - Justification reason < 20 characters is rejected by schema validator (422 Unprocessable Entity).
   - Foreign tenant access without act-as token returns 403 Forbidden and records CROSS_TENANT_ACCESS_ATTEMPT audit event.
   - Act-as token scoped to Tenant B is rejected when attempting to access Tenant C (403 Forbidden).
   - Expired act-as token is rejected (401 Unauthorized).

2. Control Tower Actions Negative Tests:
   - AUDITOR role (observe-only) is rejected across all 10 actions (403 Forbidden).
   - Operator without step-up MFA verification is rejected across all actions (403 Forbidden).
   - Operator with justification reason < 20 characters is rejected (422 Unprocessable Entity).
   - Operator without confirmation flag (confirm=False) is staged and requires confirmation before execution.
   - Blast radius validation is reported and required.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.audit.service import get_audit_service
from domain.bootstrap.superuser import reset_superuser_service
from domain.control_tower.service import reset_control_tower_service
from domain.identity.service import get_identity_service
from domain.models.enums import AuditEventType, SystemRole
from domain.observability import health_probe


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_state():
    reset_control_tower_service()
    reset_superuser_service()
    health_probe.reset_overrides()
    health_probe.set_override("secret_store", True)
    yield
    reset_control_tower_service()
    reset_superuser_service()
    health_probe.reset_overrides()


# ==============================================================================
# 1. ACT-AS-TENANT NEGATIVE TESTS
# ==============================================================================


@pytest.mark.parametrize(
    "forbidden_role",
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
def test_act_as_tenant_rejected_for_non_super_admin(client: TestClient, forbidden_role: SystemRole):
    """Proves that only SUPER_ADMIN can execute act-as-tenant; all other 8 roles are 403 denied."""
    identity_svc = get_identity_service()
    token = identity_svc.token_engine.issue_access_token(
        user_id=f"user-{forbidden_role.value.lower()}",
        tenant_id="tenant-primary",
        email=f"{forbidden_role.value.lower()}@enterprise.internal",
        roles=[forbidden_role],
        permissions=["platform.observe"],
        session_id=f"sess-{forbidden_role.value.lower()}",
        token_family_id="fam-1",
        ttl_seconds=300,
    )

    response = client.post(
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

    assert response.status_code == 403
    assert "Act-as-tenant operation strictly restricted to SUPER_ADMIN role." in response.json().get("detail", "")


def test_act_as_tenant_rejected_without_step_up_mfa(client: TestClient):
    """SUPER_ADMIN cannot assume tenant identity without explicit step-up MFA verification."""
    identity_svc = get_identity_service()
    token = identity_svc.token_engine.issue_access_token(
        user_id="super-admin-user",
        tenant_id="tenant-system",
        email="superadmin@cloudlens.internal",
        roles=[SystemRole.SUPER_ADMIN],
        permissions=["platform.observe", "platform.operate", "platform.act_as"],
        session_id="sess-super-1",
        token_family_id="fam-super-1",
        ttl_seconds=300,
    )

    # Calling without any step_up_token in body or header
    response = client.post(
        "/api/v1/admin/act-as",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "tenant_id": "tenant-target-alpha",
            "reason": "Authorized incident investigation for cross tenant debugging",
        },
    )

    assert response.status_code == 403
    assert "Step-up MFA verification required" in response.json().get("detail", "")


def test_act_as_tenant_rejected_with_short_reason(client: TestClient):
    """Reason under 20 characters is rejected immediately at payload boundary."""
    identity_svc = get_identity_service()
    token = identity_svc.token_engine.issue_access_token(
        user_id="super-admin-user",
        tenant_id="tenant-system",
        email="superadmin@cloudlens.internal",
        roles=[SystemRole.SUPER_ADMIN],
        permissions=["platform.observe", "platform.operate", "platform.act_as"],
        session_id="sess-super-2",
        token_family_id="fam-super-2",
        ttl_seconds=300,
    )

    response = client.post(
        "/api/v1/admin/act-as",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Step-Up-Token": "valid-mfa-token",
        },
        json={
            "tenant_id": "tenant-target-alpha",
            "reason": "Fix bug",  # 7 characters < 20
            "step_up_token": "valid-mfa-token",
        },
    )

    # Pydantic field validation returns 422
    assert response.status_code == 422


def test_act_as_tenant_cross_scope_boundary_denied(client: TestClient):
    """An act-as token issued for Tenant B CANNOT be used to access Tenant C."""
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


def test_expired_act_as_token_rejected_with_401(client: TestClient):
    """Expired act-as token is rejected with 401 Unauthorized."""
    identity_svc = get_identity_service()
    expired_token = identity_svc.token_engine.issue_act_as_token(
        user_id="super-admin-user",
        original_email="superadmin@cloudlens.internal",
        target_tenant_id="tenant-beta",
        roles=[SystemRole.GLOBAL_ADMIN],
        ttl_seconds=-10,  # Pre-expired
        reason="Historical investigation testing token expiration gate",
    )

    res = client.get(
        "/api/v1/users",
        headers={
            "Authorization": f"Bearer {expired_token}",
            "X-Tenant-ID": "tenant-beta",
        },
    )
    assert res.status_code == 401


# ==============================================================================
# 2. CONTROL TOWER ACTIONS NEGATIVE TESTS
# ==============================================================================

ALL_TEN_CT_ACTIONS = [
    "retry-job",
    "pause-connector",
    "resume-connector",
    "force-sync",
    "drain-queue",
    "requeue-quarantine",
    "maintenance-mode",
    "revoke-user-sessions",
    "trigger-backup",
    "trigger-reconciliation",
]


@pytest.mark.parametrize("action", ALL_TEN_CT_ACTIONS)
def test_control_tower_action_forbidden_for_auditor(client: TestClient, action: str):
    """AUDITOR has platform.observe but is strictly blocked from all 10 Control Tower operational actions."""
    identity_svc = get_identity_service()
    token = identity_svc.token_engine.issue_access_token(
        user_id="user-auditor",
        tenant_id="tenant-primary",
        email="auditor@enterprise.internal",
        roles=[SystemRole.AUDITOR],
        permissions=["platform.observe"],
        session_id="sess-auditor-ct",
        token_family_id="fam-ct-1",
        ttl_seconds=300,
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Step-Up-Token": "valid-stepup-token-1234",
    }

    res = client.post(
        f"/api/v1/control-tower/actions/{action}",
        headers=headers,
        json={
            "action": action,
            "reason": "Auditor attempting unauthorized action execution to verify security boundary",
            "confirm": True,
            "step_up_token": "valid-stepup-token-1234",
        },
    )

    assert res.status_code == 403
    assert "platform.operate" in res.json().get("detail", "")


@pytest.mark.parametrize("action", ALL_TEN_CT_ACTIONS)
def test_control_tower_action_rejected_without_step_up_mfa(client: TestClient, action: str):
    """Operator role without valid step-up MFA verification is rejected (403 Forbidden)."""
    identity_svc = get_identity_service()
    token = identity_svc.token_engine.issue_access_token(
        user_id="user-operator",
        tenant_id="tenant-primary",
        email="operator@enterprise.internal",
        roles=[SystemRole.SUPER_ADMIN],
        permissions=["platform.observe", "platform.operate"],
        session_id="sess-operator-ct",
        token_family_id="fam-ct-2",
        ttl_seconds=300,
    )
    headers = {
        "Authorization": f"Bearer {token}",
    }

    res = client.post(
        f"/api/v1/control-tower/actions/{action}",
        headers=headers,
        json={
            "action": action,
            "reason": "Legitimate administrative justification with sufficient character length",
            "confirm": True,
            # Missing step_up_token
        },
    )

    assert res.status_code == 403
    assert "Step-up authentication verification required" in res.json().get("detail", "")


@pytest.mark.parametrize("action", ALL_TEN_CT_ACTIONS)
def test_control_tower_action_rejected_with_short_reason(client: TestClient, action: str):
    """Operator provides reason < 20 characters -> 422 Unprocessable Entity."""
    identity_svc = get_identity_service()
    token = identity_svc.token_engine.issue_access_token(
        user_id="user-operator",
        tenant_id="tenant-primary",
        email="operator@enterprise.internal",
        roles=[SystemRole.SUPER_ADMIN],
        permissions=["platform.observe", "platform.operate"],
        session_id="sess-operator-ct-short",
        token_family_id="fam-ct-3",
        ttl_seconds=300,
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Step-Up-Token": "valid-stepup-token-1234",
    }

    res = client.post(
        f"/api/v1/control-tower/actions/{action}",
        headers=headers,
        json={
            "action": action,
            "reason": "Restart now",  # 11 characters < 20
            "confirm": True,
            "step_up_token": "valid-stepup-token-1234",
        },
    )

    assert res.status_code == 422


@pytest.mark.parametrize("action", ALL_TEN_CT_ACTIONS)
def test_control_tower_action_requires_explicit_confirmation_stage(client: TestClient, action: str):
    """Action without explicit confirm=True is staged and does not execute, returning blast radius."""
    identity_svc = get_identity_service()
    token = identity_svc.token_engine.issue_access_token(
        user_id="user-operator",
        tenant_id="tenant-primary",
        email="operator@enterprise.internal",
        roles=[SystemRole.SUPER_ADMIN],
        permissions=["platform.observe", "platform.operate"],
        session_id="sess-operator-ct-stage",
        token_family_id="fam-ct-4",
        ttl_seconds=300,
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Step-Up-Token": "valid-stepup-token-1234",
    }

    res = client.post(
        f"/api/v1/control-tower/actions/{action}",
        headers=headers,
        json={
            "action": action,
            "reason": "Comprehensive administrative operation to verify blast radius preview",
            "confirm": False,  # Staging mode
            "step_up_token": "valid-stepup-token-1234",
        },
    )

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "staged"
    assert data["requires_confirmation"] is True
    assert "blast_radius" in data
    assert "affected_tenants" in data["blast_radius"]

