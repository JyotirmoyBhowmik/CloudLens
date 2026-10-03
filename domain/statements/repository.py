"""Thread-Safe, Tenant-Isolated Statement Repository (Prompt 52).

Enforces:
- Strict TenantContext requirement on all repository operations.
- Deterministic isolation of showback statements, adjustments, and disputes.
- In-app statement history per recipient scope.
"""

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


class StatementRepository:
    """In-memory thread-safe repository with strict tenant isolation."""

    def __init__(self) -> None:
        self._statements: dict[tuple[str, str], ShowbackStatement] = {}
        self._adjustments: dict[tuple[str, str], StatementAdjustment] = {}
        self._disputes: dict[tuple[str, str], StatementDispute] = {}
        self._reallocations: dict[tuple[str, str], ReallocationRecord] = {}
        self._lock = threading.RLock()

    def save_statement(
        self, statement: ShowbackStatement, *, tenant_context: TenantContext
    ) -> ShowbackStatement:
        """Persists or updates a showback statement."""
        tc = require_tenant_context(tenant_context)
        with self._lock:
            self._statements[(tc.tenant_id, statement.statement_id)] = statement.model_copy()
            return statement

    def get_statement(
        self, statement_id: str, *, tenant_context: TenantContext
    ) -> ShowbackStatement | None:
        """Retrieves a statement by ID with strict tenant isolation."""
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
        """Lists showback statements filtered by period, scope, or status."""
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
        """Persists a post-finalisation restatement adjustment record."""
        tc = require_tenant_context(tenant_context)
        with self._lock:
            self._adjustments[(tc.tenant_id, adjustment.adjustment_id)] = adjustment.model_copy()
            return adjustment

    def get_adjustment(
        self, adjustment_id: str, *, tenant_context: TenantContext
    ) -> StatementAdjustment | None:
        """Retrieves an adjustment record by ID."""
        tc = require_tenant_context(tenant_context)
        with self._lock:
            adj = self._adjustments.get((tc.tenant_id, adjustment_id))
            return adj.model_copy() if adj else None

    def list_adjustments_for_statement(
        self, statement_id: str, *, tenant_context: TenantContext
    ) -> list[StatementAdjustment]:
        """Lists all adjustments linked to a statement."""
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
        """Persists or updates a line dispute record."""
        tc = require_tenant_context(tenant_context)
        with self._lock:
            self._disputes[(tc.tenant_id, dispute.dispute_id)] = dispute.model_copy()
            return dispute

    def get_dispute(
        self, dispute_id: str, *, tenant_context: TenantContext
    ) -> StatementDispute | None:
        """Retrieves a dispute by ID."""
        tc = require_tenant_context(tenant_context)
        with self._lock:
            disp = self._disputes.get((tc.tenant_id, dispute_id))
            return disp.model_copy() if disp else None

    def list_disputes_for_statement(
        self, statement_id: str, *, tenant_context: TenantContext
    ) -> list[StatementDispute]:
        """Lists all disputes for a statement."""
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
        """Persists a documented reallocation record."""
        tc = require_tenant_context(tenant_context)
        with self._lock:
            self._reallocations[(tc.tenant_id, reallocation.reallocation_id)] = (
                reallocation.model_copy()
            )
            return reallocation

    def list_reallocations_for_statement(
        self, statement_id: str, *, tenant_context: TenantContext
    ) -> list[ReallocationRecord]:
        """Lists all reallocations associated with a statement."""
        tc = require_tenant_context(tenant_context)
        with self._lock:
            items = [
                r.model_copy()
                for (tid, _), r in self._reallocations.items()
                if tid == tc.tenant_id and r.statement_id == statement_id
            ]
        return items


_global_statement_repository: StatementRepository | None = None
_repo_lock = threading.RLock()


def get_statement_repository() -> StatementRepository:
    """Returns singleton instance of StatementRepository."""
    global _global_statement_repository
    if _global_statement_repository is None:
        with _repo_lock:
            if _global_statement_repository is None:
                _global_statement_repository = StatementRepository()
    return _global_statement_repository


def reset_statement_repository() -> None:
    """Resets singleton repository for testing isolation."""
    global _global_statement_repository
    with _repo_lock:
        _global_statement_repository = None
