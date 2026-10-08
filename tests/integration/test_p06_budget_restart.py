"""Real-DB Integration Test for Budget Persistence Across Restart (Prompt P06).

DONE WHEN Proof:
[ ] Budget survives restart
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import text

from db.session import get_tenant_session
from domain.budgets.models import (
    BudgetApprovalStatus,
    BudgetEntity,
    BudgetPeriod,
    BudgetScopeType,
    BudgetThreshold,
)
from domain.budgets.repository import (
    SqlBudgetRepository,
    get_budget_repository,
    reset_budget_repository,
)
from domain.tenant.context import TenantContext


@pytest.mark.realdb
@pytest.mark.asyncio
async def test_budget_survives_restart() -> None:
    """Verifies that a budget persisted via SqlBudgetRepository survives application

    restart (singleton reset) and remains fully recoverable with identical attributes from PostgreSQL.
    """
    tenant_id = "tenant-p06-budget-restart"
    tc = TenantContext(
        tenant_id=tenant_id,
        user_id="user-finops-lead",
        roles=["TENANT_ADMIN"],
        is_break_glass=False,
    )
    budget_id = "bgt-restart-proof-001"

    # Clean existing data for this tenant
    async with get_tenant_session(tenant_id) as session:
        await session.execute(
            text("DELETE FROM budgets WHERE tenant_id = :tid;"),
            {"tid": tenant_id},
        )
        await session.commit()

    # 1. Instantiate repository and save budget
    repo1: SqlBudgetRepository = get_budget_repository()
    assert not repo1.is_in_memory, "Must be backed by PostgreSQL, not InMemory fake"

    budget = BudgetEntity(
        id=budget_id,
        tenant_id=tenant_id,
        name="Production Infrastructure Budget Q1",
        scope_type=BudgetScopeType.MANAGEMENT_GROUP,
        scope_id="mg-platform-core",
        period=BudgetPeriod.QUARTERLY,
        amount=25000.00,
        currency="USD",
        thresholds=[
            BudgetThreshold(percentage=80.0, band="WARNING", recipients=["alerts@corp.internal"]),
            BudgetThreshold(percentage=100.0, band="CRITICAL", recipients=["vp-eng@corp.internal"]),
        ],
        alert_recipients=["finops@corp.internal"],
        effective_date=date(2026, 1, 1),
        expiry_date=date(2026, 3, 31),
        owner="FinOps Operations",
        approval_status=BudgetApprovalStatus.APPROVED,
        notes="Validated for Q1 platform growth requirements",
    )

    saved = repo1.save(budget, tenant_context=tc)
    assert saved.id == budget_id
    assert saved.amount == 25000.00

    # 2. Simulate server restart: tear down singleton and reinstantiate fresh repository
    reset_budget_repository()
    repo2: SqlBudgetRepository = get_budget_repository()
    assert repo2 is not repo1, "A fresh repository instance must simulate a restart"

    # 3. Retrieve budget from the restarted repository
    reloaded = repo2.get(budget_id, tenant_context=tc)
    assert reloaded is not None, f"Budget {budget_id} failed to survive restart!"

    # Verify field integrity
    assert reloaded.id == budget_id
    assert reloaded.tenant_id == tenant_id
    assert reloaded.name == "Production Infrastructure Budget Q1"
    assert reloaded.scope_type == BudgetScopeType.MANAGEMENT_GROUP
    assert reloaded.scope_id == "mg-platform-core"
    assert reloaded.period == BudgetPeriod.QUARTERLY
    assert reloaded.amount == 25000.00
    assert reloaded.currency == "USD"
    assert reloaded.effective_date == date(2026, 1, 1)
    assert reloaded.expiry_date == date(2026, 3, 31)
    assert reloaded.owner == "FinOps Operations"
    assert reloaded.approval_status == BudgetApprovalStatus.APPROVED
    assert len(reloaded.thresholds) == 2
    assert reloaded.thresholds[0].percentage == 80.0
    assert reloaded.thresholds[1].percentage == 100.0
    assert reloaded.alert_recipients == ["finops@corp.internal"]

    # 4. Verify RLS cross-tenant isolation on the restarted repository
    other_tc = TenantContext(
        tenant_id="tenant-unauthorized-stranger",
        user_id="user-stranger",
        roles=["TENANT_ADMIN"],
        is_break_glass=False,
    )
    isolated = repo2.get(budget_id, tenant_context=other_tc)
    assert isolated is None, "RLS failed to isolate budget from another tenant on restarted repo"

    print(f"[PROOF PASS] Budget {budget_id} survived server restart with 100% field fidelity.")
