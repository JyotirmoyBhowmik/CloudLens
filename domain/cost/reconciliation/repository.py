"""Tenant-Aware Reconciliation Repository and Protocol (Prompt P06).

Enforces:
- Prompt 13 Item 84: Mandatory TenantContext in every repository method.
- Pattern P1: Protocol + SqlReconciliationRepository (SQLAlchemy 2.0 async + asyncpg).
- Pattern P3: Injected dependency, zero mutable dict singletons in production.
- Pattern P4: Transactional RLS isolation via get_tenant_session().
- Pattern P6: Startup guard preventing InMemory repository outside development.
- Prompt 24 Item 4: Persisting and tracking investigation items on tolerance failures.
- Prompt 24 Item 7: Retaining historical reconciliation audits per billing period.
- Prompt 24 Item 6: Persisting and querying estimate-vs-actual comparison items.
- Strict prohibition against adjusting ingested cost data to force a match (ReconciliationAdjustmentForbiddenException).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_tenant_session
from domain.cost.reconciliation.models import (
    EstimateVsActualItem,
    InvestigationStatus,
    ReconciliationInvestigationItem,
    ReconciliationReport,
)
from domain.models.exceptions import (
    ReconciliationAdjustmentForbiddenException,
    ReconciliationInvestigationNotFoundException,
)
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)


@runtime_checkable
class ReconciliationRepository(Protocol):
    """Authoritative protocol for Reconciliation reports, investigations, and estimates."""

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> ReconciliationReport | None:
        ...

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ReconciliationReport]:
        ...

    def save(
        self, entity: ReconciliationReport, *, tenant_context: TenantContext
    ) -> ReconciliationReport:
        ...

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        ...

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        ...

    def save_investigation_item(
        self,
        item: ReconciliationInvestigationItem,
        *,
        tenant_context: TenantContext,
    ) -> ReconciliationInvestigationItem:
        ...

    def get_investigation_item(
        self,
        item_id: str,
        *,
        tenant_context: TenantContext,
    ) -> ReconciliationInvestigationItem | None:
        ...

    def list_investigation_items(
        self,
        *,
        tenant_context: TenantContext,
        status: InvestigationStatus | None = None,
        provider: str | None = None,
    ) -> list[ReconciliationInvestigationItem]:
        ...

    def update_investigation_item(
        self,
        item_id: str,
        status: InvestigationStatus,
        notes: str | None = None,
        *,
        tenant_context: TenantContext,
    ) -> ReconciliationInvestigationItem:
        ...

    def get_history(
        self,
        *,
        tenant_context: TenantContext,
        provider: str | None = None,
        scope_id: str | None = None,
    ) -> list[ReconciliationReport]:
        ...

    def save_estimate_vs_actual(
        self,
        item: EstimateVsActualItem,
        *,
        tenant_context: TenantContext,
    ) -> EstimateVsActualItem:
        ...

    def list_estimate_vs_actual(
        self,
        *,
        tenant_context: TenantContext,
        billing_period: str | None = None,
    ) -> list[EstimateVsActualItem]:
        ...

    def prevent_cost_adjustment(
        self,
        cost_fact_id: str,
        *,
        tenant_context: TenantContext,
    ) -> None:
        ...


class SqlReconciliationRepository:
    """PostgreSQL implementation of ReconciliationRepository using SQLAlchemy async."""

    is_in_memory: bool = False

    def _run_async(self, coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro)).result()

    def _row_to_report(self, row: Any) -> ReconciliationReport:
        m = dict(row._mapping)
        raw = m.get("report_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "id" in raw:
            return ReconciliationReport.model_validate(raw)

        from domain.cost.reconciliation.models import ReconciliationStatus, VarianceClassification
        return ReconciliationReport(
            id=m["id"],
            tenant_id=m["tenant_id"],
            provider=m["provider"],
            scope_id=m["scope_id"],
            billing_period=m["billing_period"],
            reconciled_at=m.get("created_at") or datetime.now(UTC),
            platform_cost=0.0,
            provider_cost=0.0,
            variance_amount=float(m["variance_amount"]),
            percentage_variance=float(m["percentage_variance"]),
            status=ReconciliationStatus(m["status"]),
            classification=VarianceClassification(m["classification"]),
            tolerances_applied={},
            notes="",
        )

    def _row_to_investigation(self, row: Any) -> ReconciliationInvestigationItem:
        m = dict(row._mapping)
        raw = m.get("item_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "id" in raw:
            return ReconciliationInvestigationItem.model_validate(raw)

        from domain.cost.reconciliation.models import InvestigationPriority, VarianceClassification
        return ReconciliationInvestigationItem(
            id=m["id"],
            report_id=m["report_id"],
            tenant_id=m["tenant_id"],
            provider=m["provider"],
            scope_id=m["scope_id"],
            billing_period=m["billing_period"],
            platform_total=0.0,
            provider_total=0.0,
            variance_amount=float(m["variance_amount"]),
            percentage_variance=float(m["percentage_variance"]),
            classification=VarianceClassification.UNCLASSIFIED,
            priority=InvestigationPriority(m["priority"]),
            status=InvestigationStatus(m["status"]),
            created_at=m.get("created_at") or datetime.now(UTC),
            notes="",
        )

    def _row_to_estimate(self, row: Any) -> EstimateVsActualItem:
        m = dict(row._mapping)
        raw = m.get("item_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "id" in raw:
            return EstimateVsActualItem.model_validate(raw)

        from domain.cost.reconciliation.models import EstimationBias
        return EstimateVsActualItem(
            id=m["id"],
            tenant_id=m["tenant_id"],
            scope_id=m["scope_id"],
            billing_period=m["billing_period"],
            estimated_amount=float(m["estimated_amount"]),
            actual_amount=float(m["actual_amount"]),
            variance_amount=float(m["variance_amount"]),
            percentage_error=float(m["percentage_error"]),
            bias_direction=EstimationBias(m["bias_direction"]),
            evaluated_at=m.get("created_at") or datetime.now(UTC),
        )

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> ReconciliationReport | None:
        async def _get():
            tid = tenant_context.tenant_id
            async with get_tenant_session(tid) as session:
                res = await session.execute(
                    text("SELECT * FROM reconciliation_reports WHERE id = :id AND tenant_id = :tid;"),
                    {"id": entity_id, "tid": tid},
                )
                row = res.first()
                return self._row_to_report(row) if row else None

        return self._run_async(_get())

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ReconciliationReport]:
        async def _list():
            tid = tenant_context.tenant_id
            sql = "SELECT * FROM reconciliation_reports WHERE tenant_id = :tid"
            params: dict[str, Any] = {"tid": tid}
            if filter_params and isinstance(filter_params, dict):
                if "billing_period" in filter_params and filter_params["billing_period"]:
                    sql += " AND billing_period = :bp"
                    params["bp"] = filter_params["billing_period"]
                if "provider" in filter_params and filter_params["provider"]:
                    sql += " AND provider = :prov"
                    params["prov"] = filter_params["provider"]
                if "scope_id" in filter_params and filter_params["scope_id"]:
                    sql += " AND scope_id = :sid"
                    params["sid"] = filter_params["scope_id"]
                if "status" in filter_params and filter_params["status"]:
                    st = filter_params["status"]
                    sql += " AND status = :st"
                    params["st"] = st.value if hasattr(st, "value") else str(st)

            sql += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset;"
            params["limit"] = limit
            params["offset"] = offset

            async with get_tenant_session(tid) as session:
                res = await session.execute(text(sql), params)
                return [self._row_to_report(r) for r in res.fetchall()]

        return self._run_async(_list())

    def save(
        self, entity: ReconciliationReport, *, tenant_context: TenantContext
    ) -> ReconciliationReport:
        async def _save():
            tid = tenant_context.tenant_id
            async with get_tenant_session(tid) as session:
                query = text("""
                    INSERT INTO reconciliation_reports (
                        id, tenant_id, provider, scope_id, billing_period,
                        status, variance_amount, percentage_variance, classification,
                        report_payload, created_at
                    ) VALUES (
                        :id, :tid, :provider, :scope_id, :bp,
                        :status, :var_amt, :pct_var, :class,
                        CAST(:payload AS jsonb), :created_at
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        status = EXCLUDED.status,
                        variance_amount = EXCLUDED.variance_amount,
                        percentage_variance = EXCLUDED.percentage_variance,
                        classification = EXCLUDED.classification,
                        report_payload = EXCLUDED.report_payload;
                """)
                await session.execute(
                    query,
                    {
                        "id": entity.id,
                        "tid": tid,
                        "provider": entity.provider,
                        "scope_id": entity.scope_id,
                        "bp": entity.billing_period,
                        "status": entity.status.value,
                        "var_amt": entity.variance_amount,
                        "pct_var": entity.percentage_variance,
                        "class": entity.classification.value,
                        "payload": json.dumps(entity.model_dump(mode="json")),
                        "created_at": entity.reconciled_at,
                    },
                )
                await session.commit()
                return entity

        return self._run_async(_save())

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        async def _del():
            tid = tenant_context.tenant_id
            async with get_tenant_session(tid) as session:
                res = await session.execute(
                    text("DELETE FROM reconciliation_reports WHERE id = :id AND tenant_id = :tid;"),
                    {"id": entity_id, "tid": tid},
                )
                await session.commit()
                return (res.rowcount or 0) > 0

        return self._run_async(_del())

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return self.get(entity_id, tenant_context=tenant_context) is not None

    def save_investigation_item(
        self,
        item: ReconciliationInvestigationItem,
        *,
        tenant_context: TenantContext,
    ) -> ReconciliationInvestigationItem:
        async def _save():
            tid = tenant_context.tenant_id
            async with get_tenant_session(tid) as session:
                query = text("""
                    INSERT INTO reconciliation_investigations (
                        id, report_id, tenant_id, provider, scope_id, billing_period,
                        status, priority, variance_amount, percentage_variance,
                        item_payload, created_at, updated_at
                    ) VALUES (
                        :id, :rep_id, :tid, :provider, :scope_id, :bp,
                        :status, :priority, :var_amt, :pct_var,
                        CAST(:payload AS jsonb), :created_at, NOW()
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        status = EXCLUDED.status,
                        priority = EXCLUDED.priority,
                        variance_amount = EXCLUDED.variance_amount,
                        percentage_variance = EXCLUDED.percentage_variance,
                        item_payload = EXCLUDED.item_payload,
                        updated_at = NOW();
                """)
                await session.execute(
                    query,
                    {
                        "id": item.id,
                        "rep_id": item.report_id,
                        "tid": tid,
                        "provider": item.provider,
                        "scope_id": item.scope_id,
                        "bp": item.billing_period,
                        "status": item.status.value,
                        "priority": item.priority.value,
                        "var_amt": item.variance_amount,
                        "pct_var": item.percentage_variance,
                        "payload": json.dumps(item.model_dump(mode="json")),
                        "created_at": item.created_at,
                    },
                )
                await session.commit()
                return item

        return self._run_async(_save())

    def get_investigation_item(
        self,
        item_id: str,
        *,
        tenant_context: TenantContext,
    ) -> ReconciliationInvestigationItem | None:
        async def _get():
            tid = tenant_context.tenant_id
            async with get_tenant_session(tid) as session:
                res = await session.execute(
                    text("SELECT * FROM reconciliation_investigations WHERE id = :id AND tenant_id = :tid;"),
                    {"id": item_id, "tid": tid},
                )
                row = res.first()
                return self._row_to_investigation(row) if row else None

        return self._run_async(_get())

    def list_investigation_items(
        self,
        *,
        tenant_context: TenantContext,
        status: InvestigationStatus | None = None,
        provider: str | None = None,
    ) -> list[ReconciliationInvestigationItem]:
        async def _list():
            tid = tenant_context.tenant_id
            sql = "SELECT * FROM reconciliation_investigations WHERE tenant_id = :tid"
            params: dict[str, Any] = {"tid": tid}
            if status is not None:
                sql += " AND status = :st"
                params["st"] = status.value
            if provider is not None:
                sql += " AND provider = :prov"
                params["prov"] = provider.lower()
            sql += " ORDER BY created_at DESC;"

            async with get_tenant_session(tid) as session:
                res = await session.execute(text(sql), params)
                return [self._row_to_investigation(r) for r in res.fetchall()]

        return self._run_async(_list())

    def update_investigation_item(
        self,
        item_id: str,
        status: InvestigationStatus,
        notes: str | None = None,
        *,
        tenant_context: TenantContext,
    ) -> ReconciliationInvestigationItem:
        existing = self.get_investigation_item(item_id, tenant_context=tenant_context)
        if not existing:
            raise ReconciliationInvestigationNotFoundException(item_id)

        update_dict: dict[str, Any] = {"status": status}
        if status in (InvestigationStatus.RESOLVED, InvestigationStatus.CLOSED):
            update_dict["resolved_at"] = datetime.now(UTC)
        if notes:
            combined_notes = f"{existing.notes}\n{notes}".strip() if existing.notes else notes
            update_dict["notes"] = combined_notes

        updated = existing.model_copy(update=update_dict)
        return self.save_investigation_item(updated, tenant_context=tenant_context)

    def get_history(
        self,
        *,
        tenant_context: TenantContext,
        provider: str | None = None,
        scope_id: str | None = None,
    ) -> list[ReconciliationReport]:
        async def _history():
            tid = tenant_context.tenant_id
            sql = "SELECT * FROM reconciliation_reports WHERE tenant_id = :tid"
            params: dict[str, Any] = {"tid": tid}
            if provider:
                sql += " AND provider = :prov"
                params["prov"] = provider.lower()
            if scope_id:
                sql += " AND scope_id = :sid"
                params["sid"] = scope_id
            sql += " ORDER BY billing_period ASC, created_at ASC;"

            async with get_tenant_session(tid) as session:
                res = await session.execute(text(sql), params)
                return [self._row_to_report(r) for r in res.fetchall()]

        return self._run_async(_history())

    def save_estimate_vs_actual(
        self,
        item: EstimateVsActualItem,
        *,
        tenant_context: TenantContext,
    ) -> EstimateVsActualItem:
        async def _save():
            tid = tenant_context.tenant_id
            async with get_tenant_session(tid) as session:
                query = text("""
                    INSERT INTO estimate_vs_actual_items (
                        id, tenant_id, scope_id, billing_period,
                        estimated_amount, actual_amount, variance_amount,
                        percentage_error, bias_direction, item_payload, created_at
                    ) VALUES (
                        :id, :tid, :scope_id, :bp,
                        :est, :act, :var_amt,
                        :pct_err, :bias, CAST(:payload AS jsonb), :created_at
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        estimated_amount = EXCLUDED.estimated_amount,
                        actual_amount = EXCLUDED.actual_amount,
                        variance_amount = EXCLUDED.variance_amount,
                        percentage_error = EXCLUDED.percentage_error,
                        bias_direction = EXCLUDED.bias_direction,
                        item_payload = EXCLUDED.item_payload;
                """)
                await session.execute(
                    query,
                    {
                        "id": item.id,
                        "tid": tid,
                        "scope_id": item.scope_id,
                        "bp": item.billing_period,
                        "est": item.estimated_amount,
                        "act": item.actual_amount,
                        "var_amt": item.variance_amount,
                        "pct_err": item.percentage_error,
                        "bias": item.bias_direction.value,
                        "payload": json.dumps(item.model_dump(mode="json")),
                        "created_at": item.evaluated_at,
                    },
                )
                await session.commit()
                return item

        return self._run_async(_save())

    def list_estimate_vs_actual(
        self,
        *,
        tenant_context: TenantContext,
        billing_period: str | None = None,
    ) -> list[EstimateVsActualItem]:
        async def _list():
            tid = tenant_context.tenant_id
            sql = "SELECT * FROM estimate_vs_actual_items WHERE tenant_id = :tid"
            params: dict[str, Any] = {"tid": tid}
            if billing_period:
                sql += " AND billing_period = :bp"
                params["bp"] = billing_period
            sql += " ORDER BY created_at DESC;"

            async with get_tenant_session(tid) as session:
                res = await session.execute(text(sql), params)
                return [self._row_to_estimate(r) for r in res.fetchall()]

        return self._run_async(_list())

    def prevent_cost_adjustment(
        self,
        cost_fact_id: str,
        *,
        tenant_context: TenantContext,
    ) -> None:
        raise ReconciliationAdjustmentForbiddenException(cost_fact_id)


_GLOBAL_RECONCILIATION_REPO: Any = None


def get_reconciliation_repository() -> Any:
    """Dependency injection provider for ReconciliationRepository with startup guard."""
    global _GLOBAL_RECONCILIATION_REPO
    mode = os.getenv("PERSISTENCE_MODE", "sql").strip().lower()
    env = os.getenv("CLOUDLENS_ENV", "development").strip().lower()

    if mode == "inmemory":
        if env in ("staging", "production"):
            logger.critical("FATAL STARTUP GUARD: Staging/production refuses InMemory reconciliation repository.")
            sys.exit(1)
        from tests.fakes.reconciliation import InMemoryReconciliationRepository
        return InMemoryReconciliationRepository()

    if _GLOBAL_RECONCILIATION_REPO is None:
        _GLOBAL_RECONCILIATION_REPO = SqlReconciliationRepository()
    return _GLOBAL_RECONCILIATION_REPO


def reset_reconciliation_repository() -> Any:
    """Resets the ReconciliationRepository singleton for testing."""
    global _GLOBAL_RECONCILIATION_REPO
    _GLOBAL_RECONCILIATION_REPO = None
    return get_reconciliation_repository()


__all__ = [
    "ReconciliationRepository",
    "SqlReconciliationRepository",
    "get_reconciliation_repository",
    "reset_reconciliation_repository",
]
