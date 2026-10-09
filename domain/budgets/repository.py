"""Tenant-Scoped Repository for Budget Entities and Amendment Audit Trail (Prompt P06).

Enforces:
- Pattern P1: Protocol + SqlBudgetRepository (SQLAlchemy 2.0 async + asyncpg).
- Pattern P3: Injected dependency, zero mutable dict singletons in production.
- Pattern P4: Transactional RLS isolation via get_tenant_session().
- Pattern P6: Startup guard preventing InMemory repository outside development.
- Budgets at all seventeen scope types with immutable amendment history surviving restarts.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import os
import sys
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_tenant_session, run_async, verify_persistence_startup_guard
from domain.budgets.models import (
    BudgetAmendment,
    BudgetApprovalDecision,
    BudgetApprovalStatus,
    BudgetEntity,
    BudgetEscalation,
    BudgetPeriod,
    BudgetRolloverPolicy,
    BudgetScopeType,
    BudgetSourceType,
    BudgetThreshold,
    CloudProvider,
)
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)


@runtime_checkable
class BudgetRepository(Protocol):
    """Authoritative protocol for budget persistence."""

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> BudgetEntity | None:
        ...

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[BudgetEntity]:
        ...

    def list_all(
        self,
        *,
        tenant_context: TenantContext,
    ) -> list[BudgetEntity]:
        ...

    def save(self, entity: BudgetEntity, *, tenant_context: TenantContext) -> BudgetEntity:
        ...

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        ...

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        ...

    def count(self, *, tenant_context: TenantContext, filter_params: Any = None) -> int:
        ...

    def get_children(
        self,
        parent_budget_id: str,
        *,
        tenant_context: TenantContext,
    ) -> list[BudgetEntity]:
        ...

    def find_by_scope(
        self,
        scope_type: BudgetScopeType,
        scope_id: str,
        *,
        tenant_context: TenantContext,
    ) -> list[BudgetEntity]:
        ...


class SqlBudgetRepository:
    """PostgreSQL production implementation for BudgetEntity with RLS."""

    is_in_memory: bool = False

    def _run_async(self, coro: Any) -> Any:
        return run_async(coro)

    def _row_to_budget(self, row: Any) -> BudgetEntity:
        m = dict(row._mapping)
        thresh_raw = m.get("thresholds") or []
        if isinstance(thresh_raw, str):
            thresh_raw = json.loads(thresh_raw)
        thresholds = [BudgetThreshold.model_validate(t) for t in thresh_raw]

        recips_raw = m.get("alert_recipients") or []
        if isinstance(recips_raw, str):
            recips_raw = json.loads(recips_raw)
        recipients = list(recips_raw)

        esc_raw = m.get("escalation")
        if isinstance(esc_raw, str):
            esc_raw = json.loads(esc_raw)
        escalation = BudgetEscalation.model_validate(esc_raw) if esc_raw else None

        appr_raw = m.get("approval_decision")
        if isinstance(appr_raw, str):
            appr_raw = json.loads(appr_raw)
        approval_decision = (
            BudgetApprovalDecision.model_validate(appr_raw) if appr_raw else None
        )

        amend_raw = m.get("amendments") or []
        if isinstance(amend_raw, str):
            amend_raw = json.loads(amend_raw)
        amendments = [BudgetAmendment.model_validate(a) for a in amend_raw]

        st_val = m.get("scope_type") or "account"
        try:
            scope_type = BudgetScopeType(st_val)
        except ValueError:
            try:
                scope_type = BudgetScopeType(st_val.lower())
            except ValueError:
                scope_type = BudgetScopeType.ACCOUNT

        per_val = m.get("period") or "MONTHLY"
        try:
            period = BudgetPeriod(per_val)
        except ValueError:
            period = BudgetPeriod.MONTHLY

        stat_val = m.get("approval_status") or "DRAFT"
        try:
            approval_status = BudgetApprovalStatus(stat_val)
        except ValueError:
            approval_status = BudgetApprovalStatus.DRAFT

        roll_val = m.get("rollover_policy") or "NONE"
        try:
            rollover_policy = BudgetRolloverPolicy(roll_val)
        except ValueError:
            rollover_policy = BudgetRolloverPolicy.NONE

        src_val = m.get("budget_source") or "CLOUDLENS_LOGICAL"
        try:
            budget_source = BudgetSourceType(src_val)
        except ValueError:
            budget_source = BudgetSourceType.CLOUDLENS_LOGICAL

        prov_val = m.get("native_provider")
        native_prov = None
        if prov_val:
            try:
                native_prov = CloudProvider(prov_val)
            except ValueError:
                native_prov = None

        amt = float(m["amount"]) if m.get("amount") is not None else 0.0
        forecast_thresh = (
            float(m["forecast_threshold"])
            if m.get("forecast_threshold") is not None
            else None
        )

        return BudgetEntity(
            id=m["id"],
            tenant_id=m["tenant_id"],
            name=m["name"],
            scope_type=scope_type,
            scope_id=m["scope_id"],
            parent_budget_id=m.get("parent_budget_id"),
            period=period,
            amount=amt,
            currency=m.get("currency") or "USD",
            thresholds=thresholds,
            alert_recipients=recipients,
            escalation=escalation,
            forecast_threshold=forecast_thresh,
            effective_date=m["effective_date"],
            expiry_date=m.get("expiry_date"),
            owner=m.get("owner") or "system",
            approval_status=approval_status,
            approval_decision=approval_decision,
            rollover_policy=rollover_policy,
            notes=m.get("notes"),
            budget_source=budget_source,
            is_native=bool(m.get("is_native", False)),
            is_read_only=bool(m.get("is_read_only", False)),
            native_provider=native_prov,
            native_budget_id=m.get("native_budget_id"),
            native_budget_name=m.get("native_budget_name"),
            amendments=amendments,
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
    ) -> BudgetEntity | None:
        query = text("""
            SELECT * FROM budgets
            WHERE id = :id AND tenant_id = :tenant_id
            LIMIT 1;
        """)
        params = {"id": entity_id, "tenant_id": tenant_context.tenant_id}

        if session is not None:
            res = await session.execute(query, params)
            row = res.first()
            return self._row_to_budget(row) if row else None

        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(query, params)
            row = res.first()
            return self._row_to_budget(row) if row else None

    async def save_async(
        self,
        entity: BudgetEntity,
        *,
        tenant_context: TenantContext,
        session: AsyncSession | None = None,
    ) -> BudgetEntity:
        if entity.tenant_id != tenant_context.tenant_id:
            raise ValueError(
                f"Cross-tenant isolation violation: Entity tenant {entity.tenant_id} "
                f"does not match context tenant {tenant_context.tenant_id}."
            )

        query = text("""
            INSERT INTO budgets (
                id, tenant_id, scope_id, name, amount, period,
                start_date, end_date,
                scope_type, parent_budget_id, currency, owner, approval_status,
                effective_date, expiry_date, forecast_threshold, rollover_policy,
                notes, budget_source, is_native, is_read_only, native_provider,
                native_budget_id, native_budget_name, thresholds, alert_recipients,
                escalation, approval_decision, amendments, created_at, updated_at
            ) VALUES (
                :id, :tenant_id, :scope_id, :name, :amount, :period,
                :start_date, :end_date,
                :scope_type, :parent_budget_id, :currency, :owner, :approval_status,
                :effective_date, :expiry_date, :forecast_threshold, :rollover_policy,
                :notes, :budget_source, :is_native, :is_read_only, :native_provider,
                :native_budget_id, :native_budget_name, CAST(:thresholds AS jsonb), CAST(:alert_recipients AS jsonb),
                CAST(:escalation AS jsonb), CAST(:approval_decision AS jsonb), CAST(:amendments AS jsonb), :created_at, NOW()
            )
            ON CONFLICT (id) DO UPDATE SET
                scope_id = EXCLUDED.scope_id,
                name = EXCLUDED.name,
                amount = EXCLUDED.amount,
                period = EXCLUDED.period,
                start_date = EXCLUDED.start_date,
                end_date = EXCLUDED.end_date,
                scope_type = EXCLUDED.scope_type,
                parent_budget_id = EXCLUDED.parent_budget_id,
                currency = EXCLUDED.currency,
                owner = EXCLUDED.owner,
                approval_status = EXCLUDED.approval_status,
                effective_date = EXCLUDED.effective_date,
                expiry_date = EXCLUDED.expiry_date,
                forecast_threshold = EXCLUDED.forecast_threshold,
                rollover_policy = EXCLUDED.rollover_policy,
                notes = EXCLUDED.notes,
                budget_source = EXCLUDED.budget_source,
                is_native = EXCLUDED.is_native,
                is_read_only = EXCLUDED.is_read_only,
                native_provider = EXCLUDED.native_provider,
                native_budget_id = EXCLUDED.native_budget_id,
                native_budget_name = EXCLUDED.native_budget_name,
                thresholds = EXCLUDED.thresholds,
                alert_recipients = EXCLUDED.alert_recipients,
                escalation = EXCLUDED.escalation,
                approval_decision = EXCLUDED.approval_decision,
                amendments = EXCLUDED.amendments,
                updated_at = NOW();
        """)

        thresh_json = json.dumps([t.model_dump(mode="json") for t in entity.thresholds])
        recips_json = json.dumps(entity.alert_recipients)
        esc_json = json.dumps(entity.escalation.model_dump(mode="json")) if entity.escalation else None
        appr_json = (
            json.dumps(entity.approval_decision.model_dump(mode="json"))
            if entity.approval_decision
            else None
        )
        amend_json = json.dumps([a.model_dump(mode="json") for a in entity.amendments])

        params = {
            "id": entity.id,
            "tenant_id": entity.tenant_id,
            "scope_id": entity.scope_id,
            "name": entity.name,
            "amount": entity.amount,
            "period": entity.period.value,
            "start_date": entity.effective_date,
            "end_date": entity.expiry_date or entity.effective_date,
            "scope_type": entity.scope_type.value,
            "parent_budget_id": entity.parent_budget_id,
            "currency": entity.currency,
            "owner": entity.owner,
            "approval_status": entity.approval_status.value,
            "effective_date": entity.effective_date,
            "expiry_date": entity.expiry_date,
            "forecast_threshold": entity.forecast_threshold,
            "rollover_policy": entity.rollover_policy.value,
            "notes": entity.notes,
            "budget_source": entity.budget_source.value,
            "is_native": entity.is_native,
            "is_read_only": entity.is_read_only,
            "native_provider": entity.native_provider.value if entity.native_provider else None,
            "native_budget_id": entity.native_budget_id,
            "native_budget_name": entity.native_budget_name,
            "thresholds": thresh_json,
            "alert_recipients": recips_json,
            "escalation": esc_json,
            "approval_decision": appr_json,
            "amendments": amend_json,
            "created_at": entity.created_at,
        }

        if session is not None:
            await session.execute(query, params)
            return entity

        async with get_tenant_session(tenant_context.tenant_id) as sess:
            await sess.execute(query, params)
            await sess.commit()
            return entity

    async def list_async(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
        session: AsyncSession | None = None,
    ) -> list[BudgetEntity]:
        sql = "SELECT * FROM budgets WHERE tenant_id = :tenant_id"
        params: dict[str, Any] = {"tenant_id": tenant_context.tenant_id}

        if filter_params and isinstance(filter_params, dict):
            if "scope_type" in filter_params and filter_params["scope_type"]:
                st = filter_params["scope_type"]
                st_val = st.value if hasattr(st, "value") else str(st)
                sql += " AND scope_type = :scope_type"
                params["scope_type"] = st_val
            if "scope_id" in filter_params and filter_params["scope_id"]:
                sql += " AND scope_id = :scope_id"
                params["scope_id"] = filter_params["scope_id"]
            if "approval_status" in filter_params and filter_params["approval_status"]:
                stat = filter_params["approval_status"]
                stat_val = stat.value if hasattr(stat, "value") else str(stat)
                sql += " AND approval_status = :approval_status"
                params["approval_status"] = stat_val
            if "is_native" in filter_params and filter_params["is_native"] is not None:
                sql += " AND is_native = :is_native"
                params["is_native"] = filter_params["is_native"]

        sql += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset;"
        params["limit"] = limit
        params["offset"] = offset

        query = text(sql)

        if session is not None:
            res = await session.execute(query, params)
            rows = res.fetchall()
            return [self._row_to_budget(r) for r in rows]

        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(query, params)
            rows = res.fetchall()
            return [self._row_to_budget(r) for r in rows]

    async def delete_async(
        self,
        entity_id: str,
        *,
        tenant_context: TenantContext,
        session: AsyncSession | None = None,
    ) -> bool:
        query = text("DELETE FROM budgets WHERE id = :id AND tenant_id = :tenant_id;")
        params = {"id": entity_id, "tenant_id": tenant_context.tenant_id}

        if session is not None:
            res = await session.execute(query, params)
            return (res.rowcount or 0) > 0

        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(query, params)
            await sess.commit()
            return (res.rowcount or 0) > 0

    # --------------------------------------------------------------------------
    # Synchronous Protocol Facade
    # --------------------------------------------------------------------------

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> BudgetEntity | None:
        return self._run_async(self.get_async(entity_id, tenant_context=tenant_context))

    def save(self, entity: BudgetEntity, *, tenant_context: TenantContext) -> BudgetEntity:
        return self._run_async(self.save_async(entity, tenant_context=tenant_context))

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[BudgetEntity]:
        return self._run_async(
            self.list_async(
                tenant_context=tenant_context,
                filter_params=filter_params,
                limit=limit,
                offset=offset,
            )
        )

    def list_all(
        self,
        *,
        tenant_context: TenantContext,
    ) -> list[BudgetEntity]:
        return self._run_async(
            self.list_async(
                tenant_context=tenant_context,
                limit=100000,
                offset=0,
            )
        )

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return self._run_async(self.delete_async(entity_id, tenant_context=tenant_context))

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return self.get(entity_id, tenant_context=tenant_context) is not None

    def count(self, *, tenant_context: TenantContext, filter_params: Any = None) -> int:
        async def _count():
            sql = "SELECT COUNT(*) FROM budgets WHERE tenant_id = :tenant_id"
            params: dict[str, Any] = {"tenant_id": tenant_context.tenant_id}
            if filter_params and isinstance(filter_params, dict):
                if "scope_type" in filter_params and filter_params["scope_type"]:
                    st = filter_params["scope_type"]
                    params["scope_type"] = st.value if hasattr(st, "value") else str(st)
                    sql += " AND scope_type = :scope_type"
                if "scope_id" in filter_params and filter_params["scope_id"]:
                    params["scope_id"] = filter_params["scope_id"]
                    sql += " AND scope_id = :scope_id"
            async with get_tenant_session(tenant_context.tenant_id) as sess:
                res = await sess.execute(text(sql), params)
                return res.scalar() or 0

        return self._run_async(_count())

    def get_children(
        self,
        parent_budget_id: str,
        *,
        tenant_context: TenantContext,
    ) -> list[BudgetEntity]:
        async def _get_children():
            sql = "SELECT * FROM budgets WHERE tenant_id = :tenant_id AND parent_budget_id = :parent_id;"
            async with get_tenant_session(tenant_context.tenant_id) as sess:
                res = await sess.execute(
                    text(sql),
                    {"tenant_id": tenant_context.tenant_id, "parent_id": parent_budget_id},
                )
                return [self._row_to_budget(r) for r in res.fetchall()]

        return self._run_async(_get_children())

    def find_by_scope(
        self,
        scope_type: BudgetScopeType,
        scope_id: str,
        *,
        tenant_context: TenantContext,
    ) -> list[BudgetEntity]:
        async def _find():
            st_val = scope_type.value if hasattr(scope_type, "value") else str(scope_type)
            sql = "SELECT * FROM budgets WHERE tenant_id = :tenant_id AND scope_type = :st AND scope_id = :sid;"
            async with get_tenant_session(tenant_context.tenant_id) as sess:
                res = await sess.execute(
                    text(sql),
                    {
                        "tenant_id": tenant_context.tenant_id,
                        "st": st_val,
                        "sid": scope_id,
                    },
                )
                return [self._row_to_budget(r) for r in res.fetchall()]

        return self._run_async(_find())


# Singleton repository instance
_budget_repository: Any = None


def get_budget_repository() -> Any:
    """Returns the singleton BudgetRepository instance with startup guard."""
    global _budget_repository
    if _budget_repository is None:
        _budget_repository = SqlBudgetRepository()
        verify_persistence_startup_guard(_budget_repository)
    return _budget_repository


def reset_budget_repository(repo: Any = None) -> Any:
    """Resets the singleton BudgetRepository instance for testing."""
    global _budget_repository
    _budget_repository = repo
    return _budget_repository or get_budget_repository()


__all__ = [
    "BudgetRepository",
    "SqlBudgetRepository",
    "get_budget_repository",
    "reset_budget_repository",
]
