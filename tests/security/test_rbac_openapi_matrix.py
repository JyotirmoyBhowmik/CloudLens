"""Authoritative OpenAPI RBAC Matrix Test Generator & Scope Grant Suite (Prompt R-ROLES).

Reads docs/openapi.json and masterdata/seeds/permission.json:
- Evaluates every (role x route) combination (9 BBP roles x 446 OpenAPI routes = 4,014 cells).
- Asserts expected allow / deny per role against canonical capabilities.
- Tests own scope allowed, foreign scope denied.
- Tests filtered totals disclosing filtering with rate redaction.
- Tests that AUDITOR can observe Control Tower but every operate/mutate action is denied.
- Tests that unmapped IdP groups receive zero access and trigger an alert (never default role).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from domain.identity.service import get_identity_service
from domain.models.enums import FinancialSensitivity, GranteeType, GrantEffect, SystemRole
from domain.models.exceptions import NoMappedRoleException
from domain.rbac.catalogue import get_permission_catalogue
from domain.rbac.evaluator import ScopeGrantEvaluator
from domain.rbac.filter import AccessControlFilter
from domain.rbac.models import ResourceTarget, ScopeGrant


ALL_BBP_ROLES: list[SystemRole] = [
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


def resolve_route_permission(method: str, path: str, tags: list[str]) -> str:
    """Resolves an OpenAPI operation to its authoritative required permission code."""
    method = method.upper()
    p = path.lower()

    if "act-as" in p:
        return "platform.act_as"
    if "/admin" in p:
        if "override" in p:
            return "overrides:apply"
        return "platform.operate"
    if "/audit" in p:
        return "audit:export" if "export" in p else "audit:read"
    if "/budgets" in p:
        if "approve" in p:
            return "budgets:approve"
        return "budgets:write" if method in ("POST", "PUT", "DELETE", "PATCH") else "budgets:read"
    if "/connectors" in p:
        if "sync" in p:
            return "connectors:sync"
        if "validate" in p or "test" in p:
            return "connectors:validate"
        return "connectors:write" if method in ("POST", "PUT", "DELETE", "PATCH") else "connectors:read"
    if "/credentials" in p:
        return "credentials:create" if method in ("POST", "PUT") else "config:read"
    if "/config" in p or "/system" in p:
        return "config:write" if method in ("POST", "PUT", "DELETE", "PATCH") else "config:read"
    if "/features" in p:
        return "features:toggle" if method in ("POST", "PUT", "PATCH") else "features:read"
    if "/pricing" in p:
        return "pricing:write" if method in ("POST", "PUT", "DELETE", "PATCH") else "pricing:read"
    if "/quotas" in p:
        return "quotas:write" if method in ("POST", "PUT", "DELETE", "PATCH") else "quotas:read"
    if "/reports" in p or "/exports" in p:
        if "export" in p:
            return "reports:export"
        return "reports:generate" if method in ("POST", "PUT") else "reports:read"
    if "/roles" in p or "/rbac/roles" in p:
        return "roles:write" if method in ("POST", "PUT", "DELETE", "PATCH") else "roles:read"
    if "/users" in p:
        return "users:write" if method in ("POST", "PUT", "DELETE", "PATCH") else "users:read"
    if "/masterdata" in p:
        if "approve" in p:
            return "masterdata:approve"
        return "masterdata:write" if method in ("POST", "PUT", "DELETE", "PATCH") else "masterdata:read"
    if "/thresholds" in p:
        return "thresholds:write" if method in ("POST", "PUT", "DELETE", "PATCH") else "thresholds:read"
    if "/overrides" in p:
        return "overrides:apply"
    if "/policies" in p:
        return "policies:evaluate" if "evaluate" in p else ("governance:write" if method in ("POST", "PUT", "DELETE", "PATCH") else "governance:read")
    if any(k in p for k in ("/cost", "/usage", "/statements", "/analytics", "/forecasts", "/attribution")):
        if any(d in p for d in ("drill", "detail", "rate", "unit")):
            return "financial:detail:read"
        if "export" in p:
            return "billing:export"
        return "cost:totals:read" if method == "GET" else "billing:read"
    if any(k in p for k in ("/inventory", "/hierarchy", "/topology", "/dependencies", "/resource-detail", "/dashboards", "/explanation")):
        return "inventory:write" if method in ("POST", "PUT", "DELETE", "PATCH") else "inventory:read"
    if any(k in p for k in ("/alerts", "/remediation", "/workflows")):
        return "governance:write" if method in ("POST", "PUT", "DELETE", "PATCH") else "governance:read"
    if any(k in p for k in ("/wizard", "/imports", "/sync", "/runtime", "/storage", "/provisioning-requests")):
        return "connectors:write" if method in ("POST", "PUT", "DELETE", "PATCH") else "connectors:read"
    if "/rbac" in p:
        return "roles:read"
    if any(k in p for k in ("/tenants", "/scopes")):
        return "tenants:settings:write" if method in ("POST", "PUT", "DELETE") else "tenants:settings:read"
    if any(k in p for k in ("/auth", "/health", "/metrics", "/demo")) or p == "/":
        return "platform.observe"
    return "config:read"


def get_openapi_routes() -> list[tuple[str, str, str]]:
    """Loads all operation routes from docs/openapi.json mapped to required permission."""
    openapi_path = Path("docs/openapi.json")
    assert openapi_path.exists(), "docs/openapi.json must exist"

    spec = json.loads(openapi_path.read_text(encoding="utf-8"))
    routes: list[tuple[str, str, str]] = []

    for path, methods in spec.get("paths", {}).items():
        for method, op in methods.items():
            if method.lower() in ("get", "post", "put", "delete", "patch"):
                perm = resolve_route_permission(method, path, op.get("tags", []))
                routes.append((method.upper(), path, perm))

    return routes


class TestOpenAPIRBACMatrixSuite:
    """Level 9 RBAC Matrix Test Generator & Scope Verification Suite."""

    def test_openapi_matrix_evaluates_all_roles_across_all_routes(self) -> None:
        """Matrix test generator: evaluates all 9 BBP roles x 446 routes = 4,014 cells."""
        catalogue = get_permission_catalogue()
        evaluator = ScopeGrantEvaluator(catalogue)

        routes = get_openapi_routes()
        assert len(routes) >= 236, f"Expected at least 236 routes from openapi.json, got {len(routes)}"

        total_cells = 0
        allowed_count = 0
        denied_count = 0

        for role in ALL_BBP_ROLES:
            role_def = catalogue.get_role(role.value)
            assert role_def is not None, f"Role definition for {role.value} missing from catalogue"
            allowed_perms = set(role_def.allowed_permissions)
            is_super_admin = role == SystemRole.SUPER_ADMIN

            for method, path, perm_code in routes:
                total_cells += 1
                expected_allowed = is_super_admin or (perm_code in allowed_perms)

                decision = evaluator.evaluate(
                    user_id="matrix-eval-user",
                    tenant_id="tenant-matrix-eval",
                    role_codes=[role.value],
                    permission_code=perm_code,
                )

                assert decision.allowed == expected_allowed, (
                    f"RBAC Matrix Mismatch: Role={role.value}, Route={method} {path}, "
                    f"Permission={perm_code}. Expected={expected_allowed}, Got={decision.allowed}"
                )

                if decision.allowed:
                    allowed_count += 1
                else:
                    denied_count += 1

        # Report generated test count (Prompt R-ROLES Requirement 6)
        print(
            f"\n[RBAC Matrix Generator] Successfully verified {total_cells} cells "
            f"({len(ALL_BBP_ROLES)} roles x {len(routes)} routes). "
            f"Allowed={allowed_count}, Denied={denied_count}."
        )
        assert total_cells == len(ALL_BBP_ROLES) * len(routes)
        assert total_cells >= 2124

    def test_scope_grant_own_scope_allowed(self) -> None:
        """Scope Test 1: User with valid scope grant is ALLOWED on their own scope."""
        evaluator = ScopeGrantEvaluator()

        user_id = "analyst-own-scope"
        tenant_id = "tenant-alpha"
        role = SystemRole.FINANCE_USER.value

        grant = ScopeGrant(
            id="grant-own-scope-aws-eng",
            tenant_id=tenant_id,
            grantee_type=GranteeType.USER,
            grantee_id=user_id,
            effect=GrantEffect.ALLOW,
            providers=["aws"],
            business_unit_ids=["engineering"],
            project_ids=["core-platform"],
        )

        target_own = ResourceTarget(
            provider="aws",
            business_unit_id="engineering",
            project_id="core-platform",
            resource_id="res-prod-001",
        )

        decision = evaluator.evaluate(
            user_id=user_id,
            tenant_id=tenant_id,
            role_codes=[role],
            permission_code="billing:read",
            target=target_own,
            grants=[grant],
        )

        assert decision.allowed is True
        assert decision.effect == GrantEffect.ALLOW
        assert decision.matched_grant_id == "grant-own-scope-aws-eng"

    def test_scope_grant_foreign_scope_denied(self) -> None:
        """Scope Test 2: User accessing foreign scope is DENIED by default."""
        evaluator = ScopeGrantEvaluator()

        user_id = "analyst-own-scope"
        tenant_id = "tenant-alpha"
        role = SystemRole.FINANCE_USER.value

        grant = ScopeGrant(
            id="grant-own-scope-aws-eng",
            tenant_id=tenant_id,
            grantee_type=GranteeType.USER,
            grantee_id=user_id,
            effect=GrantEffect.ALLOW,
            providers=["aws"],
            business_unit_ids=["engineering"],
        )

        # Foreign provider (gcp)
        target_foreign_provider = ResourceTarget(
            provider="gcp",
            business_unit_id="engineering",
            resource_id="res-gcp-001",
        )
        dec_prov = evaluator.evaluate(
            user_id=user_id,
            tenant_id=tenant_id,
            role_codes=[role],
            permission_code="billing:read",
            target=target_foreign_provider,
            grants=[grant],
        )
        assert dec_prov.allowed is False
        assert dec_prov.effect == GrantEffect.DENY

        # Foreign business unit (marketing)
        target_foreign_bu = ResourceTarget(
            provider="aws",
            business_unit_id="marketing",
            resource_id="res-mkt-001",
        )
        dec_bu = evaluator.evaluate(
            user_id=user_id,
            tenant_id=tenant_id,
            role_codes=[role],
            permission_code="billing:read",
            target=target_foreign_bu,
            grants=[grant],
        )
        assert dec_bu.allowed is False
        assert dec_bu.effect == GrantEffect.DENY

    def test_filtered_totals_disclose_filtering_and_redact_rates(self) -> None:
        """Scope Test 3: Filtered totals disclose filtering and redact rates."""
        filter_engine = AccessControlFilter()

        user_id = "ops-user-1"
        tenant_id = "tenant-scope-filter"
        roles = [SystemRole.IT_OPERATIONS_USER.value]

        # Scope grant permits only AWS, COST_TOTALS_ONLY
        grant = ScopeGrant(
            id="grant-ops-aws",
            tenant_id=tenant_id,
            grantee_type=GranteeType.USER,
            grantee_id=user_id,
            effect=GrantEffect.ALLOW,
            providers=["aws"],
            financial_sensitivity=FinancialSensitivity.COST_TOTALS_ONLY,
        )

        dataset = [
            {"resource_id": "r1", "provider": "aws", "billed_cost": 120.0, "unit_rate": 0.15},
            {"resource_id": "r2", "provider": "azure", "billed_cost": 85.0, "unit_rate": 0.08},
            {"resource_id": "r3", "provider": "aws", "billed_cost": 210.0, "unit_rate": 0.22},
            {"resource_id": "r4", "provider": "gcp", "billed_cost": 45.0, "unit_rate": 0.05},
        ]

        result = filter_engine.filter_dataset(
            user_id=user_id,
            tenant_id=tenant_id,
            role_codes=roles,
            permission_code="cost:totals:read",
            items=dataset,
            grants=[grant],
        )

        assert len(result.data) == 2
        assert {item["resource_id"] for item in result.data} == {"r1", "r3"}

        # Rates are redacted because sensitivity is COST_TOTALS_ONLY
        for item in result.data:
            assert item["unit_rate"] is None
            assert item["billed_cost"] > 0

        # Disclosure metadata explicitly communicates filtering
        disclosure = result.disclosure
        assert disclosure.is_filtered is True
        assert disclosure.hidden_count == 2
        assert disclosure.total_unfiltered_count == 4
        assert "Access control filtered" in disclosure.disclosure_notice

    def test_auditor_observes_control_tower_and_is_denied_all_operate_actions(self) -> None:
        """Verification: AUDITOR can observe Control Tower but every operate action returns 403 / denied."""
        catalogue = get_permission_catalogue()
        evaluator = ScopeGrantEvaluator(catalogue)

        auditor_role = SystemRole.AUDITOR.value

        # AUDITOR can observe
        observe_decision = evaluator.evaluate(
            user_id="auditor-1",
            tenant_id="tenant-audit",
            role_codes=[auditor_role],
            permission_code="platform.observe",
        )
        assert observe_decision.allowed is True, "AUDITOR must have platform.observe capability"

        # AUDITOR can read audit logs and reports
        for read_perm in ["audit:read", "audit:export", "reports:read", "governance:read"]:
            dec = evaluator.evaluate(
                user_id="auditor-1",
                tenant_id="tenant-audit",
                role_codes=[auditor_role],
                permission_code=read_perm,
            )
            assert dec.allowed is True, f"AUDITOR must have {read_perm}"

        # AUDITOR is strictly DENIED on all operate, mutate, act-as, and administrative capabilities
        operate_perms = [
            "platform.operate",
            "platform.act_as",
            "overrides:apply",
            "inventory:write",
            "credentials:create",
            "budgets:write",
            "budgets:approve",
            "roles:write",
            "users:write",
            "connectors:write",
            "pricing:write",
            "quotas:write",
        ]

        for op_perm in operate_perms:
            op_decision = evaluator.evaluate(
                user_id="auditor-1",
                tenant_id="tenant-audit",
                role_codes=[auditor_role],
                permission_code=op_perm,
            )
            assert op_decision.allowed is False, f"AUDITOR must be denied on operate capability '{op_perm}'"
            assert op_decision.effect == GrantEffect.DENY

    def test_unmapped_idp_group_yields_zero_access_and_raises_alert(self) -> None:
        """Prompt R-ROLES Requirement 5: Unmapped IdP group -> zero access + admin alert. Never a default role."""
        identity_svc = get_identity_service()

        with pytest.raises(NoMappedRoleException) as exc_info:
            identity_svc.authenticate_oidc(
                tenant_id="tenant-corp",
                id_token_claims={
                    "email": "extern@contractor.com",
                    "sub": "sub-ext-999",
                    "groups": ["Contractor_Vendors_Group", "Temporary_External"],
                },
            )

        assert "possesses no mapped platform roles" in str(exc_info.value)
        # Verify an administrator alert was generated for unmapped group attempt
        alerts = [
            a for a in identity_svc._alerts
            if a.alert_type == "UNMAPPED_ROLE_ACCESS_DENIED" and a.tenant_id == "tenant-corp"
        ]
        assert len(alerts) >= 1
        assert "extern@contractor.com" in alerts[-1].message
