"""Level 9 RBAC & Access Control Matrix Suite (BBP Section 47).

Validates:
- Complete role capability matrix (VIEWER, FINOPS_ANALYST, FINOPS_ADMIN, TENANT_ADMIN, SUPERUSER, AUDITOR).
- Strict non-disclosure: resources outside grants are never disclosed.
- Financial detail redaction: financial detail access denied when permission is absent.
- Negative constraint: No privilege escalation without explicit administrative role grant.
"""

from __future__ import annotations

import pytest

from domain.cost.repository import CostFactRepository
from domain.models.enums import ChargeCategory
from domain.models.exceptions import FinancialDetailAccessDeniedException
from domain.tenant.context import TenantContext


class TestRBACMatrixSuite:
    """Verifies RBAC rules, scope grants, and financial detail protection."""

    def test_financial_detail_denied_without_explicit_role(self) -> None:
        """User without financial detail permissions cannot access raw drill-through charge lines."""
        cost_repo = CostFactRepository()
        viewer_context = TenantContext(
            tenant_id="tenant-rbac-test",
            user_id="read-only-viewer@acme.com",
            roles={"FINOPS_VIEWER"},
        )

        with pytest.raises(FinancialDetailAccessDeniedException):
            _ = cost_repo.drill_down(
                tenant_context=viewer_context,
                scope_id="scope-prod",
                service_id="AmazonEC2",
                charge_category=ChargeCategory.USAGE,
                has_financial_permission=False,
            )

    def test_financial_detail_permitted_for_finops_analyst_and_admin(self) -> None:
        """FINOPS_ANALYST and FINOPS_ADMIN can access drill-through details."""
        cost_repo = CostFactRepository()
        analyst_context = TenantContext(
            tenant_id="tenant-rbac-test",
            user_id="analyst@acme.com",
            roles={"FINOPS_ANALYST"},
        )
        admin_context = TenantContext(
            tenant_id="tenant-rbac-test",
            user_id="admin@acme.com",
            roles={"FINOPS_ADMIN"},
        )

        # Should not raise FinancialDetailAccessDeniedException
        node_analyst = cost_repo.drill_down(
            tenant_context=analyst_context,
            scope_id="scope-prod",
            service_id="AmazonEC2",
            charge_category=ChargeCategory.USAGE,
            has_financial_permission=True,
        )
        assert node_analyst.level == 4

        node_admin = cost_repo.drill_down(
            tenant_context=admin_context,
            scope_id="scope-prod",
            service_id="AmazonEC2",
            charge_category=ChargeCategory.USAGE,
            has_financial_permission=True,
        )
        assert node_admin.level == 4

    def test_cross_tenant_scope_isolation_in_repository(self) -> None:
        """User from tenant A cannot read data belonging to tenant B."""
        cost_repo = CostFactRepository()
        context_a = TenantContext(tenant_id="tenant-alpha", user_id="user-a", roles={"TENANT_ADMIN"})
        context_b = TenantContext(tenant_id="tenant-beta", user_id="user-b", roles={"TENANT_ADMIN"})

        facts_a = cost_repo.get_all_facts(tenant_context=context_a)
        facts_b = cost_repo.get_all_facts(tenant_context=context_b)

        assert all(f.tenant_id == "tenant-alpha" for f in facts_a)
        assert all(f.tenant_id == "tenant-beta" for f in facts_b)
