"""Unit Tests for Scope Hierarchy Historical Attribution & SCD-2 Lineage.

Acceptance Criteria:
- Moving a subscription between management groups preserves the historical attribution of prior cost.
- Scope history tracks materialized paths so past billing intervals resolve to the hierarchy in force at the time.
"""

from datetime import UTC, datetime
from decimal import Decimal

from domain.models.enums import ChargeCategory, ProviderType, ScopeRole
from domain.models.facts import CostFact
from domain.models.measures import FinancialMeasure
from domain.models.scope import Scope, ScopeTree


def test_moving_subscription_between_management_groups_preserves_historical_cost():
    """Acceptance: Moving a subscription between management groups preserves the historical attribution of prior cost."""
    tree = ScopeTree()

    # Timeline Definition (2026 UTC)
    t0_init = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    t1_prior_cost = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
    t2_reparent = datetime(2026, 3, 1, 0, 0, 0, tzinfo=UTC)
    t3_post_cost = datetime(2026, 3, 15, 12, 0, 0, tzinfo=UTC)

    # 1. Setup Initial Hierarchy: Root MG -> MG Alpha -> Subscription
    tenant = tree.add_scope(
        Scope(
            id="scope-tenant",
            tenant_id="tenant-corp-01",
            name="Contoso Tenant",
            canonical_role=ScopeRole.TENANT,
            provider=ProviderType.AZURE,
            native_type="AzureTenant",
            native_id="tenant-contoso-id",
        ),
        effective_time=t0_init,
    )

    mg_alpha = tree.add_scope(
        Scope(
            id="scope-mg-alpha",
            tenant_id="tenant-corp-01",
            parent_id=tenant.id,
            name="Business Unit Alpha Management Group",
            canonical_role=ScopeRole.GROUP,
            provider=ProviderType.AZURE,
            native_type="ManagementGroup",
            native_id="/providers/Microsoft.Management/managementGroups/mg-alpha",
        ),
        effective_time=t0_init,
    )

    mg_beta = tree.add_scope(
        Scope(
            id="scope-mg-beta",
            tenant_id="tenant-corp-01",
            parent_id=tenant.id,
            name="Business Unit Beta Management Group",
            canonical_role=ScopeRole.GROUP,
            provider=ProviderType.AZURE,
            native_type="ManagementGroup",
            native_id="/providers/Microsoft.Management/managementGroups/mg-beta",
        ),
        effective_time=t0_init,
    )

    subscription = tree.add_scope(
        Scope(
            id="scope-sub-prod-01",
            tenant_id="tenant-corp-01",
            parent_id=mg_alpha.id,  # Initially under MG Alpha
            name="Production Workloads Subscription",
            canonical_role=ScopeRole.BILLING_BOUNDARY,
            provider=ProviderType.AZURE,
            native_type="Subscription",
            native_id="/subscriptions/11111111-2222-3333-4444-555555555555",
        ),
        effective_time=t0_init,
    )

    # Verify initial path under Alpha
    assert subscription.materialized_path == f"/{tenant.id}/{mg_alpha.id}/{subscription.id}"
    assert subscription.parent_id == mg_alpha.id

    # 2. Record Prior Cost Fact at T1 (under MG Alpha)
    fact_jan = CostFact(
        tenant_id="tenant-corp-01",
        scope_id=subscription.id,
        charge_period_start=t1_prior_cost,
        charge_period_end=t1_prior_cost,
        charge_category=ChargeCategory.USAGE,
        billed_cost=FinancialMeasure.of(Decimal("12000.00")),
        effective_cost=FinancialMeasure.of(Decimal("12000.00")),
    )

    # 3. Perform Organization Restructure at T2 (Move Subscription from Alpha to Beta)
    tree.reparent_scope(
        scope_id=subscription.id,
        new_parent_id=mg_beta.id,
        effective_time=t2_reparent,
        reason="REPARENTED_TO_BU_BETA",
    )

    # Verify active Scope has updated to Beta
    assert subscription.parent_id == mg_beta.id
    assert subscription.materialized_path == f"/{tenant.id}/{mg_beta.id}/{subscription.id}"

    # 4. Record Post-Move Cost Fact at T3 (under MG Beta)
    fact_mar = CostFact(
        tenant_id="tenant-corp-01",
        scope_id=subscription.id,
        charge_period_start=t3_post_cost,
        charge_period_end=t3_post_cost,
        charge_category=ChargeCategory.USAGE,
        billed_cost=FinancialMeasure.of(Decimal("25000.00")),
        effective_cost=FinancialMeasure.of(Decimal("25000.00")),
    )

    # 5. Resolve Scope Lineage at T1 (January - Prior to Reparenting)
    resolved_t1 = tree.resolve_scope_at(subscription.id, fact_jan.charge_period_start)
    assert resolved_t1.parent_scope_id == mg_alpha.id
    assert resolved_t1.materialized_path == f"/{tenant.id}/{mg_alpha.id}/{subscription.id}"
    assert resolved_t1.effective_from <= fact_jan.charge_period_start < resolved_t1.effective_to

    # 6. Resolve Scope Lineage at T3 (March - After Reparenting)
    resolved_t3 = tree.resolve_scope_at(subscription.id, fact_mar.charge_period_start)
    assert resolved_t3.parent_scope_id == mg_beta.id
    assert resolved_t3.materialized_path == f"/{tenant.id}/{mg_beta.id}/{subscription.id}"
    assert resolved_t3.effective_from <= fact_mar.charge_period_start
    assert resolved_t3.effective_to is None  # Currently active window

    # 7. Assert FinOps Aggregation Invariance:
    # Historical queries for January aggregate the $12,000 to MG Alpha, while March aggregates the $25,000 to MG Beta.
    def attribute_cost_to_group(fact: CostFact, group_id: str) -> bool:
        history_record = tree.resolve_scope_at(fact.scope_id, fact.charge_period_start)
        return group_id in history_record.materialized_path

    assert attribute_cost_to_group(fact_jan, mg_alpha.id) is True
    assert attribute_cost_to_group(fact_jan, mg_beta.id) is False

    assert attribute_cost_to_group(fact_mar, mg_beta.id) is True
    assert attribute_cost_to_group(fact_mar, mg_alpha.id) is False
