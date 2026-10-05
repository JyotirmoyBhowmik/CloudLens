"""Automated RBAC Matrix Test Suite (Prompt 11 Item 76).

Verifies Acceptance Criterion 1:
"Each built-in role can reach exactly the capabilities in the permission matrix and nothing more,
proven by the matrix test suite."

Covers:
1. Complete 9-role permission capability matrix (Item 70, 76).
2. Negative testing: proving no role can exercise permissions outside its assigned catalogue.
3. Financial sensitivity separation across roles (Item 73).
4. Deny-over-allow evaluation across representative scope combinations (Item 72).
5. Live FastAPI endpoint authorization tests with TestClient (Item 76).
"""

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.models.enums import FinancialSensitivity, GranteeType, GrantEffect, SystemRole
from domain.rbac.catalogue import get_permission_catalogue
from domain.rbac.models import ResourceTarget, ScopeGrant
from domain.rbac.service import get_rbac_service

client = TestClient(app)


# Canonical Built-In Roles under test (Prompt 11 Item 70 / BBP Section 33)
ALL_NINE_ROLES = [
    SystemRole.SUPER_ADMIN,
    SystemRole.PLATFORM_ADMIN,
    SystemRole.CLOUD_ADMINISTRATOR,
    SystemRole.FINOPS_ADMINISTRATOR,
    SystemRole.FINANCE_USER,
    SystemRole.IT_OPERATIONS_USER,
    SystemRole.APPLICATION_OWNER,
    SystemRole.READ_ONLY_USER,
    SystemRole.AUDITOR,
]

# Canonical representative permissions across platform domains
CORE_CAPABILITIES = [
    "config:read",
    "config:write",
    "features:read",
    "features:toggle",
    "tenants:settings:read",
    "tenants:settings:write",
    "billing:read",
    "billing:export",
    "cost:totals:read",
    "financial:detail:read",
    "cost:rates:read",
    "pricing:read",
    "inventory:read",
    "inventory:write",
    "audit:read",
    "reports:read",
    "budgets:read",
    "budgets:write",
    "budgets:approve",
    "policies:read",
    "policies:write",
]


@pytest.fixture(autouse=True)
def clean_grants():
    """Clears grants between test runs."""
    service = get_rbac_service()
    service.clear_scope_grants()
    yield
    service.clear_scope_grants()


# ==============================================================================
# Matrix Test 1: Full Role-to-Permission Capability Verification (Item 76)
# ==============================================================================


@pytest.mark.parametrize("role", ALL_NINE_ROLES)
def test_each_role_reaches_exact_capabilities_and_nothing_more(role: SystemRole):
    """Acceptance Criterion 1: Built-in role reaches exactly its permissions and nothing more."""
    catalogue = get_permission_catalogue()
    rbac_svc = get_rbac_service()

    role_def = catalogue.get_role(role.value)
    assert role_def is not None, f"Role {role.value} must exist in catalogue"

    allowed_set = set(role_def.allowed_permissions)
    all_perms = {p.code for p in catalogue.list_permissions()}

    # Check every permission in the platform catalogue
    for perm_code in all_perms:
        decision = rbac_svc.authorize(
            user_id=f"test-user-{role.value}",
            tenant_id="tenant-matrix",
            role_codes=[role.value],
            permission_code=perm_code,
            target=None,
        )

        if perm_code in allowed_set:
            assert decision.allowed is True, (
                f"Role {role.value} should be granted permission '{perm_code}', but was denied: {decision.reason}"
            )
        else:
            assert decision.allowed is False, (
                f"Role {role.value} MUST NOT possess unassigned permission '{perm_code}'"
            )
            assert f"Principal lacks required permission '{perm_code}'" in decision.reason


# ==============================================================================
# Matrix Test 2: Specific Role Capability Bounds
# ==============================================================================


def test_super_admin_has_complete_platform_authority():
    """Verify Super Admin (SUPER_ADMIN) has complete platform capabilities."""
    catalogue = get_permission_catalogue()
    role_def = catalogue.get_role(SystemRole.SUPER_ADMIN.value)
    all_perm_codes = {p.code for p in catalogue.list_permissions()}
    assert set(role_def.allowed_permissions) == all_perm_codes
    assert "platform.observe" in role_def.allowed_permissions
    assert "platform.operate" in role_def.allowed_permissions
    assert "platform.act_as" in role_def.allowed_permissions


def test_platform_admin_boundary():
    """Verify Platform Admin (PLATFORM_ADMIN) has tenant write authority but not global config write."""
    rbac_svc = get_rbac_service()

    role = SystemRole.PLATFORM_ADMIN.value
    # Allowed: tenant settings, billing, inventory, rbac, audit, platform observe/operate
    assert rbac_svc.authorize("u1", "t1", [role], "tenants:settings:write").allowed is True
    assert rbac_svc.authorize("u1", "t1", [role], "billing:read").allowed is True
    assert rbac_svc.authorize("u1", "t1", [role], "audit:read").allowed is True
    assert rbac_svc.authorize("u1", "t1", [role], "platform.observe").allowed is True
    assert rbac_svc.authorize("u1", "t1", [role], "platform.operate").allowed is True

    # Forbidden: system level config write, act-as-tenant
    assert rbac_svc.authorize("u1", "t1", [role], "config:write").allowed is False
    assert rbac_svc.authorize("u1", "t1", [role], "platform.act_as").allowed is False


def test_finops_analyst_vs_it_operations_user_financial_bounds():
    """BBP Table 33-2: Finance User can see rate details; IT Operations User cannot."""
    rbac_svc = get_rbac_service()

    # Finance User (FINANCE_USER) has financial:detail:read
    fin_dec = rbac_svc.authorize(
        user_id="fin-user",
        tenant_id="t1",
        role_codes=[SystemRole.FINANCE_USER.value],
        permission_code="financial:detail:read",
    )
    assert fin_dec.allowed is True
    assert fin_dec.can_view_rates is True

    # IT Operations User (IT_OPERATIONS_USER) has cost:totals:read, but NOT financial:detail:read
    ops_dec_totals = rbac_svc.authorize(
        user_id="ops-user",
        tenant_id="t1",
        role_codes=[SystemRole.IT_OPERATIONS_USER.value],
        permission_code="cost:totals:read",
    )
    assert ops_dec_totals.allowed is True

    ops_dec_detail = rbac_svc.authorize(
        user_id="ops-user",
        tenant_id="t1",
        role_codes=[SystemRole.IT_OPERATIONS_USER.value],
        permission_code="financial:detail:read",
    )
    assert ops_dec_detail.allowed is False


def test_read_only_user_cannot_mutate():
    """Verify Read Only User (READ_ONLY_USER) has zero write/mutation permissions."""
    catalogue = get_permission_catalogue()
    role_def = catalogue.get_role(SystemRole.READ_ONLY_USER.value)
    for perm in role_def.allowed_permissions:
        assert not perm.endswith(":write")
        assert not perm.endswith(":toggle")
        assert not perm.endswith(":create")
        assert not perm.endswith(":delete")
        assert not perm.endswith(":approve")


def test_security_auditor_bounds():
    """Verify Auditor cannot alter configurations or mutate financial data."""
    catalogue = get_permission_catalogue()
    role_def = catalogue.get_role(SystemRole.AUDITOR.value)
    allowed = set(role_def.allowed_permissions)

    assert "audit:read" in allowed
    assert "governance:read" in allowed
    assert "roles:read" in allowed
    assert "platform.observe" in allowed
    assert "config:write" not in allowed
    assert "billing:write" not in allowed
    assert "budgets:approve" not in allowed
    assert "platform.operate" not in allowed
    assert "platform.act_as" not in allowed


def test_auditor_can_observe_but_every_operate_action_returns_403():
    """Requirement: AUDITOR can observe but every operate action returns 403."""
    rbac_svc = get_rbac_service()
    auditor_role = SystemRole.AUDITOR.value

    # 1. Authorize checks: observe is True, operate and act_as are False
    obs_decision = rbac_svc.authorize(
        user_id="aud-1", tenant_id="t1", role_codes=[auditor_role], permission_code="platform.observe"
    )
    assert obs_decision.allowed is True, "AUDITOR must have platform.observe capability"

    op_decision = rbac_svc.authorize(
        user_id="aud-1", tenant_id="t1", role_codes=[auditor_role], permission_code="platform.operate"
    )
    assert op_decision.allowed is False, "AUDITOR must NOT have platform.operate capability"

    act_decision = rbac_svc.authorize(
        user_id="aud-1", tenant_id="t1", role_codes=[auditor_role], permission_code="platform.act_as"
    )
    assert act_decision.allowed is False, "AUDITOR must NOT have platform.act_as capability"

    # 2. HTTP Endpoint Level checks:
    # Observe endpoint (audit logs read) -> 200 Allowed
    auditor_headers = {
        "X-Tenant-ID": "t1",
        "X-Roles": auditor_role,
        "X-User-Roles": auditor_role,
        "X-User-ID": "aud-1",
    }
    obs_res = client.get("/api/v1/rbac/permissions", headers=auditor_headers)
    assert obs_res.status_code == 200

    # Operate endpoints -> 403 Forbidden
    op_res_override = client.post(
        "/api/v1/admin/overrides",
        json={
            "override_class": "BUDGET_THRESHOLD",
            "who": "aud-1",
            "what": "quota",
            "why": "Unauthorized operate attempt for 403 verification test",
            "previous_value": "100",
            "new_value": "200",
            "expiry": "2028-01-01T00:00:00Z",
        },
        headers=auditor_headers,
    )
    assert op_res_override.status_code == 403, f"Expected 403 on override operate, got {op_res_override.status_code}"

    op_res_act_as = client.post(
        "/api/v1/admin/act-as",
        json={"tenant_id": "tenant-other", "reason": "Unauthorized act-as attempt for 403 verification"},
        headers=auditor_headers,
    )
    assert op_res_act_as.status_code == 403, f"Expected 403 on act-as operate, got {op_res_act_as.status_code}"

    op_res_step_up = client.post(
        "/api/v1/admin/step-up",
        json={"password": "any-password"},
        headers=auditor_headers,
    )
    assert op_res_step_up.status_code == 403, f"Expected 403 on step-up operate, got {op_res_step_up.status_code}"


# ==============================================================================
# Matrix Test 3: Representative Scope Combinations & Deny Overlap
# ==============================================================================


def test_representative_multidimensional_scope_combination():
    """Verify combination of provider + BU + project + deny exception."""
    rbac_svc = get_rbac_service()

    # Scope grant 1: Allow AWS for BU 'Engineering'
    rbac_svc.create_scope_grant(
        ScopeGrant(
            id="grant-eng-aws",
            tenant_id="t-matrix",
            grantee_type=GranteeType.USER,
            grantee_id="eng-analyst",
            effect=GrantEffect.ALLOW,
            providers=["aws"],
            business_unit_ids=["engineering"],
        )
    )

    # Scope grant 2: Deny Project 'proj-topsecret' on AWS
    rbac_svc.create_scope_grant(
        ScopeGrant(
            id="grant-deny-topsecret",
            tenant_id="t-matrix",
            grantee_type=GranteeType.USER,
            grantee_id="eng-analyst",
            effect=GrantEffect.DENY,
            project_ids=["proj-topsecret"],
        )
    )

    # 1. Matches allow, not deny -> ALLOWED
    dec1 = rbac_svc.authorize(
        user_id="eng-analyst",
        tenant_id="t-matrix",
        role_codes=[SystemRole.FINANCE_USER.value],
        permission_code="billing:read",
        target=ResourceTarget(
            provider="aws",
            business_unit_id="engineering",
            project_id="proj-web",
            resource_id="res-1",
        ),
    )
    assert dec1.allowed is True

    # 2. Matches allow, BUT matches deny on project -> DENIED (Item 72)
    dec2 = rbac_svc.authorize(
        user_id="eng-analyst",
        tenant_id="t-matrix",
        role_codes=[SystemRole.FINANCE_USER.value],
        permission_code="billing:read",
        target=ResourceTarget(
            provider="aws",
            business_unit_id="engineering",
            project_id="proj-topsecret",
            resource_id="res-2",
        ),
    )
    assert dec2.allowed is False
    assert dec2.effect == GrantEffect.DENY
    assert dec2.matched_grant_id == "grant-deny-topsecret"

    # 3. Wrong provider (GCP) -> DENIED
    dec3 = rbac_svc.authorize(
        user_id="eng-analyst",
        tenant_id="t-matrix",
        role_codes=[SystemRole.FINANCE_USER.value],
        permission_code="billing:read",
        target=ResourceTarget(
            provider="gcp",
            business_unit_id="engineering",
            project_id="proj-web",
            resource_id="res-3",
        ),
    )
    assert dec3.allowed is False


# ==============================================================================
# Matrix Test 4: Live HTTP Endpoint RBAC Matrix (Item 76)
# ==============================================================================


def test_http_endpoint_permissions_and_roles_discovery():
    """Verify discovery of permission catalogue and roles via REST API."""
    # List permissions
    res_perms = client.get("/api/v1/rbac/permissions")
    assert res_perms.status_code == 200
    perms_data = res_perms.json()
    assert len(perms_data) >= 40

    # Get single permission
    res_single = client.get("/api/v1/rbac/permissions/billing:read")
    assert res_single.status_code == 200
    assert res_single.json()["code"] == "billing:read"

    # List roles
    res_roles = client.get("/api/v1/rbac/roles")
    assert res_roles.status_code == 200
    roles_data = res_roles.json()
    assert len(roles_data) >= 9


def test_http_endpoint_custom_role_lifecycle():
    """Verify custom role creation and retrieval over HTTP API."""
    payload = {
        "code": "API_CUSTOM_VIEWER",
        "display_name": "API Custom Viewer",
        "description": "Custom viewer for API tests",
        "allowed_permissions": ["billing:read", "inventory:read"],
    }
    headers = {
        "X-Tenant-ID": "tenant-api-test",
        "X-Roles": SystemRole.PLATFORM_ADMIN.value,
    }

    # Create custom role
    res = client.post("/api/v1/rbac/roles", json=payload, headers=headers)
    assert res.status_code == 201
    data = res.json()
    assert data["code"] == "API_CUSTOM_VIEWER"
    assert "billing:read" in data["allowed_permissions"]

    # Rejection of invalid permission
    bad_payload = {
        "code": "BAD_ROLE",
        "display_name": "Bad Role",
        "description": "Bogus",
        "allowed_permissions": ["not:real:perm"],
    }
    bad_res = client.post("/api/v1/rbac/roles", json=bad_payload, headers=headers)
    assert bad_res.status_code == 422


def test_http_endpoint_scope_grant_lifecycle_and_evaluation():
    """Verify grant creation, server-side evaluation, and deletion over HTTP API."""
    headers = {
        "X-Tenant-ID": "tenant-http-eval",
        "X-Roles": SystemRole.FINANCE_USER.value,
        "X-User-ID": "user-eval-1",
    }

    # Create grant
    grant_payload = {
        "grantee_type": GranteeType.USER.value,
        "grantee_id": "user-eval-1",
        "effect": GrantEffect.ALLOW.value,
        "providers": ["aws"],
        "business_unit_ids": ["bu-cloud"],
    }
    create_res = client.post("/api/v1/rbac/grants", json=grant_payload, headers=headers)
    assert create_res.status_code == 201
    grant_data = create_res.json()
    grant_id = grant_data["id"]

    # Evaluate matching target -> 200 Allowed
    eval_res_match = client.post(
        "/api/v1/rbac/evaluate",
        json={
            "permission_code": "billing:read",
            "target": {"provider": "aws", "business_unit_id": "bu-cloud"},
        },
        headers=headers,
    )
    assert eval_res_match.status_code == 200
    assert eval_res_match.json()["allowed"] is True

    # Evaluate mismatching target -> 200 Denied
    eval_res_mismatch = client.post(
        "/api/v1/rbac/evaluate",
        json={
            "permission_code": "billing:read",
            "target": {"provider": "azure", "business_unit_id": "bu-cloud"},
        },
        headers=headers,
    )
    assert eval_res_mismatch.status_code == 200
    assert eval_res_mismatch.json()["allowed"] is False

    # Delete grant
    del_res = client.delete(f"/api/v1/rbac/grants/{grant_id}")
    assert del_res.status_code == 204


def test_http_endpoint_access_review_export():
    """Verify access review export in JSON and CSV over HTTP API."""
    headers = {
        "X-Tenant-ID": "tenant-review-test",
        "X-Roles": SystemRole.SUPER_ADMIN.value,
    }

    # JSON export
    res_json = client.get("/api/v1/rbac/access-review?format=json", headers=headers)
    assert res_json.status_code == 200
    data = res_json.json()
    assert "tenant_id" in data
    assert "records" in data

    # CSV export
    res_csv = client.get("/api/v1/rbac/access-review?format=csv", headers=headers)
    assert res_csv.status_code == 200
    assert "text/csv" in res_csv.headers["content-type"]
    assert "user_id,email" in res_csv.text


def test_http_endpoint_filter_demo_with_disclosure():
    """Verify filter-demo endpoint applies disclosure rule and rate redaction."""
    rbac_svc = get_rbac_service()
    rbac_svc.create_scope_grant(
        ScopeGrant(
            id="grant-demo-scope",
            tenant_id="tenant-demo",
            grantee_type=GranteeType.ROLE,
            grantee_id=SystemRole.IT_OPERATIONS_USER.value,
            effect=GrantEffect.ALLOW,
            providers=["aws"],
            financial_sensitivity=FinancialSensitivity.COST_TOTALS_ONLY,
        )
    )

    headers = {
        "X-Tenant-ID": "tenant-demo",
        "X-Roles": SystemRole.IT_OPERATIONS_USER.value,
        "X-User-ID": "user-demo",
    }

    items = [
        {"resource_id": "r1", "provider": "aws", "billed_cost": 50, "unit_rate": 0.5},
        {"resource_id": "r2", "provider": "gcp", "billed_cost": 80, "unit_rate": 0.8},
    ]

    res = client.post(
        "/api/v1/rbac/filter-demo",
        json={"permission_code": "cost:totals:read", "items": items},
        headers=headers,
    )
    assert res.status_code == 200
    payload = res.json()

    # R2 excluded (GCP), R1 kept with rate redacted
    assert len(payload["data"]) == 1
    assert payload["data"][0]["resource_id"] == "r1"
    assert payload["data"][0]["unit_rate"] is None
    assert payload["data"][0]["billed_cost"] == 50

    # Disclosure metadata must report filtering (Item 74)
    disc = payload["disclosure"]
    assert disc["is_filtered"] is True
    assert disc["hidden_count"] == 1
    assert disc["total_unfiltered_count"] == 2
    assert disc["disclosure_notice"] is not None
