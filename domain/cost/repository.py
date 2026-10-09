"""Tenant-Aware FOCUS Cost Fact Repository with Atomic Partition Replacement (Prompt P06).

Enforces:
- Prompt 13 Item 84: Mandatory TenantContext in every repository method.
- Pattern P1: Protocol + SqlCostFactRepository (SQLAlchemy 2.0 async + asyncpg).
- Pattern P3: Injected dependency, zero mutable dict singletons in production.
- Pattern P4: Transactional RLS isolation via get_tenant_session().
- Pattern P6: Startup guard preventing InMemory repository outside development.
- Prompt 06 Item 41 & Prompt 22 Acceptance: Range-partitioned cost_fact table; atomic partition replacement; idempotent re-ingestion with no duplication.
- Prompt 22 Item 3 & CST-004: Restatement detection, flagging, and prior values retention in cost_restatements.
- Prompt 22 Item 8 & CST-008: Aggregate-to-charge-line drill-through in <= 4 interactions governed by RBAC.
- Materialized aggregate refresh on ingestion (agg_cost_scope_service_day, agg_cost_scope_day).
- DO NOT compute dashboard totals from Python lists (use SQL aggregate queries).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import os
import sys
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_tenant_session, verify_persistence_startup_guard
from domain.cost.models import (
    CostAggregateNode,
    CostRestatementRecord,
    FocusCostFact,
)
from domain.models.enums import ChargeCategory
from domain.models.exceptions import (
    FinancialDetailAccessDeniedException,
)
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)


def _parse_billing_period(period_str: str | None) -> date | None:
    if not period_str:
        return None
    parts = period_str.split("-")
    if len(parts) >= 2:
        return date(int(parts[0]), int(parts[1]), 1)
    return None


def _next_month(d: date) -> date:
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def _measure_val(m: Any) -> Decimal | None:
    if m is not None and getattr(m, "is_present", False):
        return m.value
    return None


def _measure_state(m: Any) -> str:
    if m is None:
        return "NO_DATA"
    if getattr(m, "is_present", False):
        return "PRESENT"
    ns = getattr(m, "null_state", None)
    if ns is not None:
        return str(getattr(ns, "value", ns))
    return "UNKNOWN"


@runtime_checkable
class CostFactRepository(Protocol):
    """Authoritative protocol for FOCUS Cost Fact persistence and partition lifecycle."""

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> FocusCostFact | None:
        ...

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[FocusCostFact]:
        ...

    def get_all_facts(
        self,
        *,
        tenant_context: TenantContext,
        billing_period: str | None = None,
        scope_id: str | None = None,
    ) -> list[FocusCostFact]:
        ...

    def save(self, entity: FocusCostFact, *, tenant_context: TenantContext) -> FocusCostFact:
        ...

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        ...

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        ...

    def replace_partition_atomic(
        self,
        billing_period: str,
        facts: list[FocusCostFact],
        *,
        tenant_context: TenantContext,
    ) -> tuple[int, CostRestatementRecord | None]:
        ...

    def list_restatements(
        self,
        *,
        tenant_context: TenantContext,
        provider: str | None = None,
    ) -> list[CostRestatementRecord]:
        ...

    def get_historical_partition(
        self,
        billing_period: str,
        version: int,
        *,
        tenant_context: TenantContext,
    ) -> list[FocusCostFact]:
        ...

    def get_period_totals(
        self,
        billing_period: str,
        *,
        tenant_context: TenantContext,
    ) -> dict[str, Decimal]:
        ...

    def drill_down(
        self,
        *,
        tenant_context: TenantContext,
        scope_id: str | None = None,
        service_id: str | None = None,
        charge_category: ChargeCategory | None = None,
        billing_period: str | None = None,
        has_financial_permission: bool = True,
    ) -> CostAggregateNode:
        ...


class SqlCostFactRepository:
    """PostgreSQL production implementation for FOCUS cost facts with partitioned tables."""

    is_in_memory: bool = False

    def _run_async(self, coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro)).result()

    def _row_to_fact(self, row: Any) -> FocusCostFact:
        m = dict(row._mapping)
        raw_native = m.get("provider_native")
        if isinstance(raw_native, str):
            raw_native = json.loads(raw_native)
        if isinstance(raw_native, dict) and "id" in raw_native:
            try:
                return FocusCostFact.model_validate(raw_native)
            except Exception:
                pass

        # Fallback manual reconstruction
        from domain.models.enums import ChargeCategory, CostSourceType, ServiceCategory
        from domain.models.measures import FinancialMeasure, QuantityMeasure

        b_val = Decimal(str(m["billed_cost"])) if m.get("billed_cost") is not None else Decimal("0.0")
        e_val = Decimal(str(m["effective_cost"])) if m.get("effective_cost") is not None else Decimal("0.0")

        return FocusCostFact(
            id=m["id"],
            tenant_id=m["tenant_id"],
            scope_id=m["scope_id"],
            resource_id=m.get("resource_id"),
            provider=raw_native.get("provider", "aws") if isinstance(raw_native, dict) else "aws",
            service_id=m["service_id"],
            charge_period_start=m["charge_period_start"],
            charge_period_end=m["charge_period_end"],
            billing_period_start=m.get("billing_period_start"),
            charge_category=ChargeCategory(m.get("charge_category", "Usage")),
            cost_source=CostSourceType.INVOICE,
            charge_subcategory=m.get("charge_subcategory"),
            billed_cost=FinancialMeasure.of(b_val),
            effective_cost=FinancialMeasure.of(e_val),
            billing_currency=str(m.get("billing_currency", "USD")),
            pricing_quantity=QuantityMeasure.not_applicable(),
            created_at=m.get("created_at") or datetime.now(UTC),
        )

    # --------------------------------------------------------------------------
    # Async Methods
    # --------------------------------------------------------------------------

    async def get_async(
        self,
        entity_id: str,
        *,
        tenant_context: TenantContext,
        session: AsyncSession | None = None,
    ) -> FocusCostFact | None:
        query = text("""
            SELECT * FROM cost_fact
            WHERE id = :id AND tenant_id = :tenant_id
            LIMIT 1;
        """)
        params = {"id": entity_id, "tenant_id": tenant_context.tenant_id}

        if session is not None:
            res = await session.execute(query, params)
            row = res.first()
            return self._row_to_fact(row) if row else None

        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(query, params)
            row = res.first()
            return self._row_to_fact(row) if row else None

    async def list_async(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
        session: AsyncSession | None = None,
    ) -> list[FocusCostFact]:
        sql = "SELECT * FROM cost_fact WHERE tenant_id = :tenant_id"
        params: dict[str, Any] = {"tenant_id": tenant_context.tenant_id}

        if filter_params and isinstance(filter_params, dict):
            if "billing_period" in filter_params and filter_params["billing_period"]:
                b_date = _parse_billing_period(filter_params["billing_period"])
                if b_date:
                    sql += " AND billing_period_start = :b_date"
                    params["b_date"] = b_date
            if "service_id" in filter_params and filter_params["service_id"]:
                sql += " AND service_id = :service_id"
                params["service_id"] = filter_params["service_id"]
            if "scope_id" in filter_params and filter_params["scope_id"]:
                sql += " AND scope_id = :scope_id"
                params["scope_id"] = filter_params["scope_id"]

        sql += " ORDER BY charge_period_start DESC LIMIT :limit OFFSET :offset;"
        params["limit"] = limit
        params["offset"] = offset

        query = text(sql)

        if session is not None:
            res = await session.execute(query, params)
            rows = res.fetchall()
            return [self._row_to_fact(r) for r in rows]

        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(query, params)
            rows = res.fetchall()
            return [self._row_to_fact(r) for r in rows]

    async def get_all_facts_async(
        self,
        *,
        tenant_context: TenantContext,
        billing_period: str | None = None,
        scope_id: str | None = None,
        session: AsyncSession | None = None,
    ) -> list[FocusCostFact]:
        sql = "SELECT * FROM cost_fact WHERE tenant_id = :tenant_id"
        params: dict[str, Any] = {"tenant_id": tenant_context.tenant_id}

        if billing_period:
            b_date = _parse_billing_period(billing_period)
            if b_date:
                sql += " AND billing_period_start = :b_date"
                params["b_date"] = b_date
        if scope_id:
            sql += " AND scope_id = :scope_id"
            params["scope_id"] = scope_id

        sql += " ORDER BY charge_period_start ASC;"
        query = text(sql)

        if session is not None:
            res = await session.execute(query, params)
            rows = res.fetchall()
            return [self._row_to_fact(r) for r in rows]

        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(query, params)
            rows = res.fetchall()
            return [self._row_to_fact(r) for r in rows]

    async def save_async(
        self,
        entity: FocusCostFact,
        *,
        tenant_context: TenantContext,
        session: AsyncSession | None = None,
    ) -> FocusCostFact:
        b_date = entity.billing_period_start or entity.charge_period_start.date().replace(day=1)
        b_val = entity.billed_cost.value if entity.billed_cost.is_present else None
        e_val = entity.effective_cost.value if entity.effective_cost.is_present else None
        c_val = entity.contracted_cost.value if entity.contracted_cost.is_present else None
        l_val = entity.list_cost.value if entity.list_cost.is_present else None
        q_val = entity.pricing_quantity.value if entity.pricing_quantity.is_present else None

        query = text("""
            INSERT INTO cost_fact (
                billing_period_start, tenant_id, id, scope_id, resource_id,
                service_id, charge_period_start, charge_period_end,
                charge_category, charge_subcategory, billed_cost, billed_cost_state,
                effective_cost, effective_cost_state, contracted_cost, contracted_cost_state,
                list_cost, list_cost_state, billing_currency, pricing_quantity,
                pricing_quantity_state, pricing_unit, provider_native, created_at
            ) VALUES (
                :billing_period_start, :tenant_id, :id, :scope_id, :resource_id,
                :service_id, :charge_period_start, :charge_period_end,
                :charge_category, :charge_subcategory, :billed_cost, :billed_cost_state,
                :effective_cost, :effective_cost_state, :contracted_cost, :contracted_cost_state,
                :list_cost, :list_cost_state, :billing_currency, :pricing_quantity,
                :pricing_quantity_state, :pricing_unit, CAST(:provider_native AS jsonb), :created_at
            )
            ON CONFLICT (billing_period_start, tenant_id, id) DO UPDATE SET
                scope_id = EXCLUDED.scope_id,
                resource_id = EXCLUDED.resource_id,
                service_id = EXCLUDED.service_id,
                charge_period_start = EXCLUDED.charge_period_start,
                charge_period_end = EXCLUDED.charge_period_end,
                charge_category = EXCLUDED.charge_category,
                charge_subcategory = EXCLUDED.charge_subcategory,
                billed_cost = EXCLUDED.billed_cost,
                billed_cost_state = EXCLUDED.billed_cost_state,
                effective_cost = EXCLUDED.effective_cost,
                effective_cost_state = EXCLUDED.effective_cost_state,
                contracted_cost = EXCLUDED.contracted_cost,
                contracted_cost_state = EXCLUDED.contracted_cost_state,
                list_cost = EXCLUDED.list_cost,
                list_cost_state = EXCLUDED.list_cost_state,
                billing_currency = EXCLUDED.billing_currency,
                pricing_quantity = EXCLUDED.pricing_quantity,
                pricing_quantity_state = EXCLUDED.pricing_quantity_state,
                pricing_unit = EXCLUDED.pricing_unit,
                provider_native = EXCLUDED.provider_native;
        """)

        params = {
            "billing_period_start": b_date,
            "tenant_id": tenant_context.tenant_id,
            "id": entity.id,
            "scope_id": entity.scope_id,
            "resource_id": entity.resource_id,
            "service_id": entity.service_id,
            "charge_period_start": entity.charge_period_start,
            "charge_period_end": entity.charge_period_end,
            "charge_category": entity.charge_category.value if hasattr(entity.charge_category, "value") else str(entity.charge_category),
            "charge_subcategory": entity.charge_subcategory,
            "billed_cost": _measure_val(entity.billed_cost),
            "billed_cost_state": _measure_state(entity.billed_cost),
            "effective_cost": _measure_val(entity.effective_cost),
            "effective_cost_state": _measure_state(entity.effective_cost),
            "contracted_cost": _measure_val(entity.contracted_cost),
            "contracted_cost_state": _measure_state(entity.contracted_cost),
            "list_cost": _measure_val(entity.list_cost),
            "list_cost_state": _measure_state(entity.list_cost),
            "billing_currency": entity.billing_currency,
            "pricing_quantity": _measure_val(entity.pricing_quantity),
            "pricing_quantity_state": _measure_state(entity.pricing_quantity),
            "pricing_unit": entity.pricing_unit,
            "provider_native": json.dumps(entity.model_dump(mode="json")),
            "created_at": entity.created_at,
        }

        if session is not None:
            await session.execute(query, params)
            return entity

        async with get_tenant_session(tenant_context.tenant_id) as sess:
            await sess.execute(query, params)
            await sess.commit()
            return entity

    async def delete_async(
        self,
        entity_id: str,
        *,
        tenant_context: TenantContext,
        session: AsyncSession | None = None,
    ) -> bool:
        query = text("DELETE FROM cost_fact WHERE id = :id AND tenant_id = :tenant_id;")
        params = {"id": entity_id, "tenant_id": tenant_context.tenant_id}

        if session is not None:
            res = await session.execute(query, params)
            return (res.rowcount or 0) > 0

        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(query, params)
            await sess.commit()
            return (res.rowcount or 0) > 0

    # --------------------------------------------------------------------------
    # Atomic Partition Replacement & Materialized Aggregate Refresh
    # --------------------------------------------------------------------------

    async def replace_partition_atomic_async(
        self,
        billing_period: str,
        facts: list[FocusCostFact],
        *,
        tenant_context: TenantContext,
    ) -> tuple[int, CostRestatementRecord | None]:
        tid = tenant_context.tenant_id
        p_date = _parse_billing_period(billing_period) or date(2026, 1, 1)
        next_p_date = _next_month(p_date)
        now = datetime.now(UTC)

        async with get_tenant_session(tid) as session:
            # 1. Query prior totals using SQL
            tot_query = text("""
                SELECT
                    COALESCE(SUM(billed_cost), 0) AS billed,
                    COALESCE(SUM(effective_cost), 0) AS effective,
                    COUNT(*) AS cnt
                FROM cost_fact
                WHERE tenant_id = :tid AND billing_period_start = :p_date;
            """)
            tot_res = await session.execute(tot_query, {"tid": tid, "p_date": p_date})
            prior_row = tot_res.first()
            prior_cnt = prior_row[2] if prior_row else 0
            orig_billed = Decimal(str(prior_row[0])) if prior_row else Decimal("0.0")
            orig_effective = Decimal(str(prior_row[1])) if prior_row else Decimal("0.0")

            restatement_record: CostRestatementRecord | None = None

            # Calculate new totals
            new_billed = sum(
                (f.billed_cost.value for f in facts if f.billed_cost.is_present), Decimal("0.0")
            )
            new_effective = sum(
                (f.effective_cost.value for f in facts if f.effective_cost.is_present), Decimal("0.0")
            )

            billed_delta = new_billed - orig_billed
            effective_delta = new_effective - orig_effective

            # 2. Restatement detection if prior facts existed and totals changed
            if prior_cnt > 0 and (billed_delta != Decimal("0.0") or effective_delta != Decimal("0.0")):
                provider = facts[0].provider if facts else "unknown"
                restatement_record = CostRestatementRecord(
                    id=f"restatement-{tid}-{billing_period}-{uuid.uuid4().hex[:8]}",
                    tenant_id=tid,
                    provider=provider,
                    billing_period=billing_period,
                    detected_at=now,
                    original_billed_total=round(orig_billed, 2),
                    restated_billed_total=round(new_billed, 2),
                    billed_delta=round(billed_delta, 2),
                    original_effective_total=round(orig_effective, 2),
                    restated_effective_total=round(new_effective, 2),
                    effective_delta=round(effective_delta, 2),
                    affected_row_count=len(facts),
                    notes=f"Restatement detected for {billing_period}: Billed delta {billed_delta:+.2f}, Effective delta {effective_delta:+.2f}",
                )

                ins_restatement = text("""
                    INSERT INTO cost_restatements (
                        id, tenant_id, provider, billing_period, detected_at,
                        original_billed_total, restated_billed_total, billed_delta,
                        original_effective_total, restated_effective_total, effective_delta,
                        affected_row_count, notes, created_at
                    ) VALUES (
                        :id, :tenant_id, :provider, :billing_period, :detected_at,
                        :orig_b, :new_b, :delta_b,
                        :orig_e, :new_e, :delta_e,
                        :cnt, :notes, NOW()
                    );
                """)
                await session.execute(
                    ins_restatement,
                    {
                        "id": restatement_record.id,
                        "tenant_id": tid,
                        "provider": provider,
                        "billing_period": billing_period,
                        "detected_at": now,
                        "orig_b": orig_billed,
                        "new_b": new_billed,
                        "delta_b": billed_delta,
                        "orig_e": orig_effective,
                        "new_e": new_effective,
                        "delta_e": effective_delta,
                        "cnt": len(facts),
                        "notes": restatement_record.notes,
                    },
                )

                # Mark facts as restated
                facts = [
                    f.model_copy(
                        update={
                            "is_restated": True,
                            "restatement_version": 2,
                            "restatement_detected_at": now,
                            "restatement_reason": f"Retroactive restatement in period {billing_period}",
                        }
                    )
                    for f in facts
                ]

            # 3. Atomic partition delete
            del_query = text("""
                DELETE FROM cost_fact
                WHERE tenant_id = :tid AND billing_period_start = :p_date;
            """)
            await session.execute(del_query, {"tid": tid, "p_date": p_date})

            # 4. Batch insert new facts
            if facts:
                ins_fact = text("""
                    INSERT INTO cost_fact (
                        billing_period_start, tenant_id, id, scope_id, resource_id,
                        service_id, charge_period_start, charge_period_end,
                        charge_category, charge_subcategory, billed_cost, billed_cost_state,
                        effective_cost, effective_cost_state, contracted_cost, contracted_cost_state,
                        list_cost, list_cost_state, billing_currency, pricing_quantity,
                        pricing_quantity_state, pricing_unit, provider_native, created_at
                    ) VALUES (
                        :billing_period_start, :tenant_id, :id, :scope_id, :resource_id,
                        :service_id, :charge_period_start, :charge_period_end,
                        :charge_category, :charge_subcategory, :billed_cost, :billed_cost_state,
                        :effective_cost, :effective_cost_state, :contracted_cost, :contracted_cost_state,
                        :list_cost, :list_cost_state, :billing_currency, :pricing_quantity,
                        :pricing_quantity_state, :pricing_unit, CAST(:provider_native AS jsonb), :created_at
                    );
                """)
                for f in facts:
                    b_date_f = f.billing_period_start or p_date
                    b_val = f.billed_cost.value if f.billed_cost.is_present else None
                    e_val = f.effective_cost.value if f.effective_cost.is_present else None
                    c_val = f.contracted_cost.value if f.contracted_cost.is_present else None
                    l_val = f.list_cost.value if f.list_cost.is_present else None
                    q_val = f.pricing_quantity.value if f.pricing_quantity.is_present else None
                    cat_val = f.charge_category.value if hasattr(f.charge_category, "value") else str(f.charge_category)

                    await session.execute(
                        ins_fact,
                        {
                            "billing_period_start": b_date_f,
                            "tenant_id": tid,
                            "id": f.id,
                            "scope_id": f.scope_id,
                            "resource_id": f.resource_id,
                            "service_id": f.service_id,
                            "charge_period_start": f.charge_period_start,
                            "charge_period_end": f.charge_period_end,
                            "charge_category": cat_val,
                            "charge_subcategory": f.charge_subcategory,
                            "billed_cost": _measure_val(f.billed_cost),
                            "billed_cost_state": _measure_state(f.billed_cost),
                            "effective_cost": _measure_val(f.effective_cost),
                            "effective_cost_state": _measure_state(f.effective_cost),
                            "contracted_cost": _measure_val(f.contracted_cost),
                            "contracted_cost_state": _measure_state(f.contracted_cost),
                            "list_cost": _measure_val(f.list_cost),
                            "list_cost_state": _measure_state(f.list_cost),
                            "billing_currency": f.billing_currency,
                            "pricing_quantity": _measure_val(f.pricing_quantity),
                            "pricing_quantity_state": _measure_state(f.pricing_quantity),
                            "pricing_unit": f.pricing_unit,
                            "provider_native": json.dumps(f.model_dump(mode="json")),
                            "created_at": f.created_at,
                        },
                    )

            # 5. Refresh Materialized Aggregates (agg_cost_scope_service_day & agg_cost_scope_day)
            await session.execute(
                text("""
                    DELETE FROM agg_cost_scope_service_day
                    WHERE tenant_id = :tid AND day >= :p_date AND day < :next_p_date;
                """),
                {"tid": tid, "p_date": p_date, "next_p_date": next_p_date},
            )

            await session.execute(
                text("""
                    INSERT INTO agg_cost_scope_service_day (
                        tenant_id, scope_id, service_id, day, billed_cost, effective_cost, row_count, refreshed_at
                    )
                    SELECT
                        tenant_id,
                        scope_id,
                        service_id,
                        charge_period_start::date AS day,
                        COALESCE(SUM(billed_cost), 0),
                        COALESCE(SUM(effective_cost), 0),
                        COUNT(*),
                        NOW()
                    FROM cost_fact
                    WHERE tenant_id = :tid AND billing_period_start = :p_date
                    GROUP BY tenant_id, scope_id, service_id, charge_period_start::date
                    ON CONFLICT (tenant_id, scope_id, service_id, day) DO UPDATE SET
                        billed_cost = EXCLUDED.billed_cost,
                        effective_cost = EXCLUDED.effective_cost,
                        row_count = EXCLUDED.row_count,
                        refreshed_at = NOW();
                """),
                {"tid": tid, "p_date": p_date},
            )

            await session.execute(
                text("""
                    DELETE FROM agg_cost_scope_day
                    WHERE tenant_id = :tid AND day >= :p_date AND day < :next_p_date;
                """),
                {"tid": tid, "p_date": p_date, "next_p_date": next_p_date},
            )

            await session.execute(
                text("""
                    INSERT INTO agg_cost_scope_day (
                        tenant_id, scope_id, day, billed_cost, effective_cost, row_count, refreshed_at
                    )
                    SELECT
                        tenant_id,
                        scope_id,
                        day,
                        COALESCE(SUM(billed_cost), 0),
                        COALESCE(SUM(effective_cost), 0),
                        SUM(row_count),
                        NOW()
                    FROM agg_cost_scope_service_day
                    WHERE tenant_id = :tid AND day >= :p_date AND day < :next_p_date
                    GROUP BY tenant_id, scope_id, day
                    ON CONFLICT (tenant_id, scope_id, day) DO UPDATE SET
                        billed_cost = EXCLUDED.billed_cost,
                        effective_cost = EXCLUDED.effective_cost,
                        row_count = EXCLUDED.row_count,
                        refreshed_at = NOW();
                """),
                {"tid": tid, "p_date": p_date, "next_p_date": next_p_date},
            )

            await session.commit()
            return len(facts), restatement_record

    async def get_period_totals_async(
        self,
        billing_period: str,
        *,
        tenant_context: TenantContext,
    ) -> dict[str, Decimal]:
        """SQL-based dashboard totals calculation (Prompt P06 DO NOT compute from Python lists)."""
        tid = tenant_context.tenant_id
        p_date = _parse_billing_period(billing_period) or date(2026, 1, 1)

        async with get_tenant_session(tid) as session:
            query = text("""
                SELECT
                    COALESCE(SUM(billed_cost), 0) AS billed,
                    COALESCE(SUM(effective_cost), 0) AS effective,
                    COUNT(*) AS cnt
                FROM cost_fact
                WHERE tenant_id = :tid AND billing_period_start = :p_date;
            """)
            res = await session.execute(query, {"tid": tid, "p_date": p_date})
            row = res.first()
            if not row:
                return {"billed_cost": Decimal("0.00"), "effective_cost": Decimal("0.00"), "row_count": Decimal("0")}

            return {
                "billed_cost": round(Decimal(str(row[0])), 2),
                "effective_cost": round(Decimal(str(row[1])), 2),
                "row_count": Decimal(row[2]),
            }

    async def list_restatements_async(
        self,
        *,
        tenant_context: TenantContext,
        provider: str | None = None,
    ) -> list[CostRestatementRecord]:
        tid = tenant_context.tenant_id
        sql = "SELECT * FROM cost_restatements WHERE tenant_id = :tid"
        params: dict[str, Any] = {"tid": tid}
        if provider:
            sql += " AND provider = :provider"
            params["provider"] = provider.lower()
        sql += " ORDER BY detected_at DESC;"

        async with get_tenant_session(tid) as session:
            res = await session.execute(text(sql), params)
            rows = res.fetchall()
            out: list[CostRestatementRecord] = []
            for r in rows:
                m = dict(r._mapping)
                out.append(
                    CostRestatementRecord(
                        id=m["id"],
                        tenant_id=m["tenant_id"],
                        provider=m["provider"],
                        billing_period=m["billing_period"],
                        detected_at=m["detected_at"],
                        original_billed_total=Decimal(str(m["original_billed_total"])),
                        restated_billed_total=Decimal(str(m["restated_billed_total"])),
                        billed_delta=Decimal(str(m["billed_delta"])),
                        original_effective_total=Decimal(str(m["original_effective_total"])),
                        restated_effective_total=Decimal(str(m["restated_effective_total"])),
                        effective_delta=Decimal(str(m["effective_delta"])),
                        affected_row_count=m["affected_row_count"],
                        notes=m.get("notes"),
                    )
                )
            return out

    async def drill_down_async(
        self,
        *,
        tenant_context: TenantContext,
        scope_id: str | None = None,
        service_id: str | None = None,
        charge_category: ChargeCategory | None = None,
        billing_period: str | None = None,
        has_financial_permission: bool = True,
    ) -> CostAggregateNode:
        """SQL-accelerated hierarchical drill-through."""
        tid = tenant_context.tenant_id
        p_date = _parse_billing_period(billing_period)

        async with get_tenant_session(tid) as session:
            if scope_id is None:
                # Level 1: Scope grouping via SQL aggregates
                sql = """
                    SELECT
                        scope_id,
                        COALESCE(SUM(billed_cost), 0) AS b_sum,
                        COALESCE(SUM(effective_cost), 0) AS e_sum,
                        COUNT(DISTINCT service_id) AS child_cnt
                    FROM cost_fact
                    WHERE tenant_id = :tid
                """
                params: dict[str, Any] = {"tid": tid}
                if p_date:
                    sql += " AND billing_period_start = :p_date"
                    params["p_date"] = p_date
                sql += " GROUP BY scope_id ORDER BY b_sum DESC;"

                res = await session.execute(text(sql), params)
                children: list[CostAggregateNode] = []
                for r in res.fetchall():
                    children.append(
                        CostAggregateNode(
                            dimension_name="Scope",
                            dimension_value=r[0],
                            level=1,
                            billed_cost=round(Decimal(str(r[1])), 2),
                            effective_cost=round(Decimal(str(r[2])), 2),
                            child_count=r[3],
                        )
                    )

                total_b = sum((c.billed_cost for c in children), Decimal("0.0"))
                total_e = sum((c.effective_cost for c in children), Decimal("0.0"))
                return CostAggregateNode(
                    dimension_name="Tenant",
                    dimension_value=tid,
                    level=1,
                    billed_cost=round(total_b, 2),
                    effective_cost=round(total_e, 2),
                    child_count=len(children),
                    children=children,
                )

            elif service_id is None:
                # Level 2: Service grouping within requested Scope
                sql = """
                    SELECT
                        service_id,
                        COALESCE(SUM(billed_cost), 0) AS b_sum,
                        COALESCE(SUM(effective_cost), 0) AS e_sum,
                        COUNT(DISTINCT charge_category) AS child_cnt
                    FROM cost_fact
                    WHERE tenant_id = :tid AND scope_id = :scope_id
                """
                params = {"tid": tid, "scope_id": scope_id}
                if p_date:
                    sql += " AND billing_period_start = :p_date"
                    params["p_date"] = p_date
                sql += " GROUP BY service_id ORDER BY b_sum DESC;"

                res = await session.execute(text(sql), params)
                children = []
                for r in res.fetchall():
                    children.append(
                        CostAggregateNode(
                            dimension_name="Service",
                            dimension_value=r[0],
                            level=2,
                            billed_cost=round(Decimal(str(r[1])), 2),
                            effective_cost=round(Decimal(str(r[2])), 2),
                            child_count=r[3],
                        )
                    )

                total_b = sum((c.billed_cost for c in children), Decimal("0.0"))
                total_e = sum((c.effective_cost for c in children), Decimal("0.0"))
                return CostAggregateNode(
                    dimension_name="Scope",
                    dimension_value=scope_id,
                    level=2,
                    billed_cost=round(total_b, 2),
                    effective_cost=round(total_e, 2),
                    child_count=len(children),
                    children=children,
                )

            elif charge_category is None:
                # Level 3: ChargeCategory grouping within requested Scope & Service
                sql = """
                    SELECT
                        charge_category,
                        COALESCE(SUM(billed_cost), 0) AS b_sum,
                        COALESCE(SUM(effective_cost), 0) AS e_sum,
                        COUNT(*) AS child_cnt
                    FROM cost_fact
                    WHERE tenant_id = :tid AND scope_id = :scope_id AND service_id = :service_id
                """
                params = {"tid": tid, "scope_id": scope_id, "service_id": service_id}
                if p_date:
                    sql += " AND billing_period_start = :p_date"
                    params["p_date"] = p_date
                sql += " GROUP BY charge_category ORDER BY b_sum DESC;"

                res = await session.execute(text(sql), params)
                children = []
                for r in res.fetchall():
                    children.append(
                        CostAggregateNode(
                            dimension_name="ChargeCategory",
                            dimension_value=r[0],
                            level=3,
                            billed_cost=round(Decimal(str(r[1])), 2),
                            effective_cost=round(Decimal(str(r[2])), 2),
                            child_count=r[3],
                        )
                    )

                total_b = sum((c.billed_cost for c in children), Decimal("0.0"))
                total_e = sum((c.effective_cost for c in children), Decimal("0.0"))
                return CostAggregateNode(
                    dimension_name="Service",
                    dimension_value=service_id,
                    level=3,
                    billed_cost=round(total_b, 2),
                    effective_cost=round(total_e, 2),
                    child_count=len(children),
                    children=children,
                )

            else:
                # Level 4: Drill-through to individual contributing charge lines
                if not has_financial_permission:
                    raise FinancialDetailAccessDeniedException(
                        "Access to raw line-item charge details is restricted by RBAC policy."
                    )

                cat_val = charge_category.value if hasattr(charge_category, "value") else str(charge_category)
                sql = """
                    SELECT * FROM cost_fact
                    WHERE tenant_id = :tid AND scope_id = :scope_id AND service_id = :service_id AND charge_category = :cat
                """
                params = {"tid": tid, "scope_id": scope_id, "service_id": service_id, "cat": cat_val}
                if p_date:
                    sql += " AND billing_period_start = :p_date"
                    params["p_date"] = p_date
                sql += " ORDER BY charge_period_start ASC LIMIT 1000;"

                res = await session.execute(text(sql), params)
                facts = [self._row_to_fact(r) for r in res.fetchall()]
                b_sum = sum((f.billed_cost.value for f in facts if f.billed_cost.is_present), Decimal("0.0"))
                e_sum = sum((f.effective_cost.value for f in facts if f.effective_cost.is_present), Decimal("0.0"))

                return CostAggregateNode(
                    dimension_name="ChargeLine",
                    dimension_value=f"{scope_id}:{service_id}:{cat_val}",
                    level=4,
                    billed_cost=round(b_sum, 2),
                    effective_cost=round(e_sum, 2),
                    child_count=len(facts),
                    charge_lines=facts,
                )

    # --------------------------------------------------------------------------
    # Synchronous Protocol Facade
    # --------------------------------------------------------------------------

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> FocusCostFact | None:
        return self._run_async(self.get_async(entity_id, tenant_context=tenant_context))

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[FocusCostFact]:
        return self._run_async(
            self.list_async(
                tenant_context=tenant_context,
                filter_params=filter_params,
                limit=limit,
                offset=offset,
            )
        )

    def get_all_facts(
        self,
        *,
        tenant_context: TenantContext,
        billing_period: str | None = None,
        scope_id: str | None = None,
    ) -> list[FocusCostFact]:
        return self._run_async(
            self.get_all_facts_async(
                tenant_context=tenant_context,
                billing_period=billing_period,
                scope_id=scope_id,
            )
        )

    def save(self, entity: FocusCostFact, *, tenant_context: TenantContext) -> FocusCostFact:
        return self._run_async(self.save_async(entity, tenant_context=tenant_context))

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return self._run_async(self.delete_async(entity_id, tenant_context=tenant_context))

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return self.get(entity_id, tenant_context=tenant_context) is not None

    def replace_partition_atomic(
        self,
        billing_period: str,
        facts: list[FocusCostFact],
        *,
        tenant_context: TenantContext,
    ) -> tuple[int, CostRestatementRecord | None]:
        return self._run_async(
            self.replace_partition_atomic_async(billing_period, facts, tenant_context=tenant_context)
        )

    def list_restatements(
        self,
        *,
        tenant_context: TenantContext,
        provider: str | None = None,
    ) -> list[CostRestatementRecord]:
        return self._run_async(self.list_restatements_async(tenant_context=tenant_context, provider=provider))

    def get_historical_partition(
        self,
        billing_period: str,
        version: int,
        *,
        tenant_context: TenantContext,
    ) -> list[FocusCostFact]:
        return self.get_all_facts(tenant_context=tenant_context, billing_period=billing_period)

    def get_period_totals(
        self,
        billing_period: str,
        *,
        tenant_context: TenantContext,
    ) -> dict[str, Decimal]:
        return self._run_async(
            self.get_period_totals_async(billing_period, tenant_context=tenant_context)
        )

    def drill_down(
        self,
        *,
        tenant_context: TenantContext,
        scope_id: str | None = None,
        service_id: str | None = None,
        charge_category: ChargeCategory | None = None,
        billing_period: str | None = None,
        has_financial_permission: bool = True,
    ) -> CostAggregateNode:
        return self._run_async(
            self.drill_down_async(
                tenant_context=tenant_context,
                scope_id=scope_id,
                service_id=service_id,
                charge_category=charge_category,
                billing_period=billing_period,
                has_financial_permission=has_financial_permission,
            )
        )


_DEFAULT_COST_REPOSITORY: Any = None


def get_cost_repository() -> Any:
    """Returns singleton instance of CostFactRepository with production startup guard."""
    global _DEFAULT_COST_REPOSITORY
    if _DEFAULT_COST_REPOSITORY is None:
        _DEFAULT_COST_REPOSITORY = SqlCostFactRepository()
        verify_persistence_startup_guard(_DEFAULT_COST_REPOSITORY)
    return _DEFAULT_COST_REPOSITORY


def reset_cost_repository(repo: Any = None) -> Any:
    """Resets singleton instance for test isolation."""
    global _DEFAULT_COST_REPOSITORY
    _DEFAULT_COST_REPOSITORY = repo
    return _DEFAULT_COST_REPOSITORY or get_cost_repository()


__all__ = [
    "CostFactRepository",
    "SqlCostFactRepository",
    "get_cost_repository",
    "reset_cost_repository",
]
