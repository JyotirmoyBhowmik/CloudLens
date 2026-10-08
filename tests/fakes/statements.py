"""In-memory test fake for StatementRepository (Prompt P07 / Prompt 52)."""

from __future__ import annotations

import threading

from domain.statements.models import (
    ReallocationRecord,
    ShowbackStatement,
    StatementAdjustment,
    StatementDispute,
    StatementLifecycleStatus,
)
from domain.tenant.context import TenantContext, require_tenant_context


class InMemoryStatementRepository:
    """In-memory thread-safe repository fake with strict tenant isolation."""

    is_in_memory: bool = True

    def __init__(self) -> None:
        self._statements: dict[tuple[str, str], ShowbackStatement] = {}
        self._adjustments: dict[tuple[str, str], StatementAdjustment] = {}
        self._disputes: dict[tuple[str, str], StatementDispute] = {}
        self._reallocations: dict[tuple[str, str], ReallocationRecord] = {}
        self._lock = threading.RLock()

    def save_statement(
        self, statement: ShowbackStatement, *, tenant_context: TenantContext
    ) -> ShowbackStatement:
        tc = require_tenant_context(tenant_context)
        with self._lock:
            self._statements[(tc.tenant_id, statement.statement_id)] = statement.model_copy()
            return statement

    def get_statement(
        self, statement_id: str, *, tenant_context: TenantContext
    ) -> ShowbackStatement | None:
        tc = require_tenant_context(tenant_context)
        with self._lock:
            stmt = self._statements.get((tc.tenant_id, statement_id))
            return stmt.model_copy() if stmt else None

    def list_statements(
        self,
        *,
        tenant_context: TenantContext,
        period: str | None = None,
        scope_code: str | None = None,
        status: StatementLifecycleStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ShowbackStatement]:
        tc = require_tenant_context(tenant_context)
        with self._lock:
            items = [
                s.model_copy()
                for (tid, _), s in self._statements.items()
                if tid == tc.tenant_id
                and (period is None or s.period == period)
                and (scope_code is None or s.scope_code == scope_code)
                and (status is None or s.status == status)
            ]
        items.sort(key=lambda x: x.generated_at, reverse=True)
        return items[offset : offset + limit]

    def save_adjustment(
        self, adjustment: StatementAdjustment, *, tenant_context: TenantContext
    ) -> StatementAdjustment:
        tc = require_tenant_context(tenant_context)
        with self._lock:
            self._adjustments[(tc.tenant_id, adjustment.adjustment_id)] = adjustment.model_copy()
            return adjustment

    def get_adjustment(
        self, adjustment_id: str, *, tenant_context: TenantContext
    ) -> StatementAdjustment | None:
        tc = require_tenant_context(tenant_context)
        with self._lock:
            adj = self._adjustments.get((tc.tenant_id, adjustment_id))
            return adj.model_copy() if adj else None

    def list_adjustments_for_statement(
        self, statement_id: str, *, tenant_context: TenantContext
    ) -> list[StatementAdjustment]:
        tc = require_tenant_context(tenant_context)
        with self._lock:
            items = [
                a.model_copy()
                for (tid, _), a in self._adjustments.items()
                if tid == tc.tenant_id
                and (
                    a.original_statement_id == statement_id
                    or a.adjusted_statement_id == statement_id
                )
            ]
        items.sort(key=lambda x: x.adjustment_timestamp, reverse=True)
        return items

    def save_dispute(
        self, dispute: StatementDispute, *, tenant_context: TenantContext
    ) -> StatementDispute:
        tc = require_tenant_context(tenant_context)
        with self._lock:
            self._disputes[(tc.tenant_id, dispute.dispute_id)] = dispute.model_copy()
            return dispute

    def get_dispute(
        self, dispute_id: str, *, tenant_context: TenantContext
    ) -> StatementDispute | None:
        tc = require_tenant_context(tenant_context)
        with self._lock:
            disp = self._disputes.get((tc.tenant_id, dispute_id))
            return disp.model_copy() if disp else None

    def list_disputes_for_statement(
        self, statement_id: str, *, tenant_context: TenantContext
    ) -> list[StatementDispute]:
        tc = require_tenant_context(tenant_context)
        with self._lock:
            items = [
                d.model_copy()
                for (tid, _), d in self._disputes.items()
                if tid == tc.tenant_id and d.statement_id == statement_id
            ]
        items.sort(key=lambda x: x.created_at, reverse=True)
        return items

    def save_reallocation(
        self, reallocation: ReallocationRecord, *, tenant_context: TenantContext
    ) -> ReallocationRecord:
        tc = require_tenant_context(tenant_context)
        with self._lock:
            self._reallocations[(tc.tenant_id, reallocation.reallocation_id)] = (
                reallocation.model_copy()
            )
            return reallocation

    def list_reallocations_for_statement(
        self, statement_id: str, *, tenant_context: TenantContext
    ) -> list[ReallocationRecord]:
        tc = require_tenant_context(tenant_context)
        with self._lock:
            items = [
                r.model_copy()
                for (tid, _), r in self._reallocations.items()
                if tid == tc.tenant_id and r.statement_id == statement_id
            ]
        return items
