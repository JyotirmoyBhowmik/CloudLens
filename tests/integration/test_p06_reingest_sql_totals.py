"""Real-DB Integration Test for Atomic Partition Replacement and Re-Ingestion (Prompt P06).

DONE WHEN Proof:
[ ] Re-ingest gives identical totals (SQL)
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text

from db.session import get_tenant_session
from domain.cost.models import FocusCostFact
from domain.cost.repository import SqlCostFactRepository, get_cost_repository
from domain.models.enums import ChargeCategory, CostSourceType, ServiceCategory
from domain.models.measures import FinancialMeasure, QuantityMeasure
from domain.tenant.context import TenantContext


@pytest.mark.realdb
@pytest.mark.asyncio
async def test_reingest_gives_identical_totals_sql() -> None:
    """Verifies that re-ingesting a billing period partition with identical data

    produces strictly identical totals in PostgreSQL with zero duplication (CST-004 & Prompt P06).
    """
    tenant_id = "tenant-p06-reingest-test"
    tc = TenantContext(
        tenant_id=tenant_id,
        user_id="user-p06-test",
        roles=["TENANT_ADMIN"],
        is_break_glass=False,
    )
    repo: SqlCostFactRepository = get_cost_repository()
    billing_period = "2026-03"
    period_start = date(2026, 3, 1)

    # Clean existing data for this tenant
    async with get_tenant_session(tenant_id) as session:
        await session.execute(
            text("DELETE FROM cost_fact WHERE tenant_id = :tid;"),
            {"tid": tenant_id},
        )
        await session.execute(
            text("DELETE FROM cost_restatements WHERE tenant_id = :tid;"),
            {"tid": tenant_id},
        )
        await session.execute(
            text("DELETE FROM agg_cost_scope_service_day WHERE tenant_id = :tid;"),
            {"tid": tenant_id},
        )
        await session.execute(
            text("DELETE FROM agg_cost_scope_day WHERE tenant_id = :tid;"),
            {"tid": tenant_id},
        )
        await session.commit()

    # 1. Create batch of FOCUS cost facts
    now = datetime.now(UTC)
    charge_start = datetime(2026, 3, 15, 10, 0, 0, tzinfo=UTC)
    charge_end = datetime(2026, 3, 15, 11, 0, 0, tzinfo=UTC)
    facts = [
        FocusCostFact(
            id=f"fact-p06-{i}",
            tenant_id=tenant_id,
            scope_id="scope-core-services",
            resource_id=f"res-vm-{i}",
            provider="aws",
            service_id="AmazonEC2",
            charge_period_start=charge_start,
            charge_period_end=charge_end,
            billing_period_start=period_start,
            charge_category=ChargeCategory.USAGE,
            cost_source=CostSourceType.INVOICE,
            billed_cost=FinancialMeasure.of(Decimal("150.25")),
            effective_cost=FinancialMeasure.of(Decimal("120.00")),
            billing_currency="USD",
            pricing_quantity=QuantityMeasure.not_applicable(),
            created_at=now,
        )
        for i in range(1, 6)  # 5 rows: total billed = 5 * 150.25 = 751.25, effective = 600.00
    ]

    expected_billed_total = Decimal("751.25")
    expected_effective_total = Decimal("600.00")
    expected_row_count = 5

    # 2. First ingestion via atomic partition replacement
    count1, restatement1 = repo.replace_partition_atomic(billing_period, facts, tenant_context=tc)
    assert count1 == expected_row_count
    assert restatement1 is None  # Initial ingestion is not a restatement

    # 3. Direct SQL verification of totals from PostgreSQL
    async with get_tenant_session(tenant_id) as session:
        res = await session.execute(
            text("""
                SELECT
                    COALESCE(SUM(billed_cost), 0),
                    COALESCE(SUM(effective_cost), 0),
                    COUNT(*)
                FROM cost_fact
                WHERE tenant_id = :tid AND billing_period_start = :p_date;
            """),
            {"tid": tenant_id, "p_date": period_start},
        )
        row = res.first()
        sql_billed_1 = Decimal(str(row[0]))
        sql_effective_1 = Decimal(str(row[1]))
        sql_count_1 = row[2]

    assert sql_count_1 == expected_row_count
    assert sql_billed_1 == expected_billed_total
    assert sql_effective_1 == expected_effective_total

    # Dashboard period totals via SQL aggregate query
    totals_1 = repo.get_period_totals(billing_period, tenant_context=tc)
    assert totals_1["billed_cost"] == expected_billed_total
    assert totals_1["effective_cost"] == expected_effective_total
    assert totals_1["row_count"] == Decimal(expected_row_count)

    # 4. Re-ingestion of identical dataset (idempotency & zero duplication proof)
    count2, restatement2 = repo.replace_partition_atomic(billing_period, facts, tenant_context=tc)
    assert count2 == expected_row_count
    assert restatement2 is None  # Identical re-ingest -> NO restatement raised

    # 5. Direct SQL verification after re-ingestion
    async with get_tenant_session(tenant_id) as session:
        res = await session.execute(
            text("""
                SELECT
                    COALESCE(SUM(billed_cost), 0),
                    COALESCE(SUM(effective_cost), 0),
                    COUNT(*)
                FROM cost_fact
                WHERE tenant_id = :tid AND billing_period_start = :p_date;
            """),
            {"tid": tenant_id, "p_date": period_start},
        )
        row = res.first()
        sql_billed_2 = Decimal(str(row[0]))
        sql_effective_2 = Decimal(str(row[1]))
        sql_count_2 = row[2]

    # Verify identical counts and totals with ZERO duplication
    assert sql_count_2 == sql_count_1 == expected_row_count
    assert sql_billed_2 == sql_billed_1 == expected_billed_total
    assert sql_effective_2 == sql_effective_1 == expected_effective_total

    # Verify materialized aggregates refreshed in database
    async with get_tenant_session(tenant_id) as session:
        agg_res = await session.execute(
            text("SELECT SUM(billed_cost), SUM(effective_cost), SUM(row_count) FROM agg_cost_scope_service_day WHERE tenant_id = :tid;"),
            {"tid": tenant_id},
        )
        agg_row = agg_res.first()
        assert Decimal(str(agg_row[0])) == expected_billed_total
        assert Decimal(str(agg_row[1])) == expected_effective_total
        assert agg_row[2] == expected_row_count

    print(
        f"[PROOF PASS] Re-ingest produced IDENTICAL SQL totals: billed={sql_billed_2}, effective={sql_effective_2}, count={sql_count_2}"
    )
