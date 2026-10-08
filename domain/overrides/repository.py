"""Override SQL Repository and Protocol (Prompt P04).

Enforces:
- Pattern P1: Protocol + SqlOverrideRepository (SQLAlchemy 2.0 async).
- Pattern P3: Injected dependency, zero mutable dict singletons as sources of truth.
- Pattern P4: Transactional RLS isolation via get_tenant_session().
- Pattern P6: Startup guard preventing InMemory repository outside development.
- Persistent operational and rate overrides with 8 mandatory attributes in PostgreSQL.
"""

from __future__ import annotations

import asyncio
import builtins
import concurrent.futures
import json
import logging
import os
import sys
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_tenant_session
from domain.models.enums import OverrideClass, OverrideStatus
from domain.models.exceptions import CrossTenantAccessForbiddenException
from domain.overrides.models import OverrideApproval, OverrideRecord
from domain.tenant.context import TenantContext, require_tenant_context

logger = logging.getLogger("cloudlens.domain.overrides.repository")


@runtime_checkable
class OverrideRepository(Protocol):
    """Authoritative protocol for tenant-scoped override persistence."""

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> OverrideRecord | None:
        ...

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[OverrideRecord]:
        ...

    def list_active(self, *, tenant_context: TenantContext) -> builtins.list[OverrideRecord]:
        ...

    def save(self, entity: OverrideRecord, *, tenant_context: TenantContext) -> OverrideRecord:
        ...

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        ...

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        ...


class SqlOverrideRepository:
    """PostgreSQL production implementation for tenant-scoped override records."""

    is_in_memory: bool = False

    def _run_async(self, coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro)).result()

    def _validate_tenant_context(self, tenant_context: TenantContext) -> TenantContext:
        return require_tenant_context(tenant_context)

    def _row_to_record(self, row: Any) -> OverrideRecord:
        raw_prev = row[7]
        prev_val = raw_prev if not isinstance(raw_prev, str) else json.loads(raw_prev)
        raw_new = row[8]
        new_val = raw_new if not isinstance(raw_new, str) else json.loads(raw_new)

        raw_approval = row[11]
        approval = None
        if raw_approval:
            app_dict = raw_approval if isinstance(raw_approval, dict) else json.loads(raw_approval)
            approval = OverrideApproval.model_validate(app_dict)

        return OverrideRecord(
            id=row[0],
            tenant_id=row[1],
            override_class=OverrideClass(row[2]) if isinstance(row[2], str) else row[2],
            who=row[3],
            what=row[4],
            why=row[5],
            when=row[6],
            previous_value=prev_val,
            new_value=new_val,
            expiry=row[9],
            is_permanent=row[10],
            approval=approval,
            status=OverrideStatus(row[12]) if isinstance(row[12], str) else row[12],
            reverted_at=row[13],
            reverted_by=row[14],
            reversion_reason=row[15],
            correlation_id=row[16],
            created_at=row[17],
            updated_at=row[18],
        )

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> OverrideRecord | None:
        self._validate_tenant_context(tenant_context)
        return self._run_async(self._get_async(entity_id, tenant_context))

    async def _get_async(self, entity_id: str, tenant_context: TenantContext) -> OverrideRecord | None:
        query = text("""
            SELECT id, tenant_id, override_class, who, what, why, "when",
                   previous_value, new_value, expiry, is_permanent, approval_metadata,
                   status, reverted_at, reverted_by, reversion_reason, correlation_id,
                   created_at, updated_at
            FROM overrides
            WHERE tenant_id = :tid AND id = :oid
            LIMIT 1;
        """)
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            result = await sess.execute(query, {"tid": tenant_context.tenant_id, "oid": entity_id})
            row = result.fetchone()
            if not row:
                return None
            return self._row_to_record(row)

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[OverrideRecord]:
        self._validate_tenant_context(tenant_context)
        return self._run_async(self._list_async(tenant_context, limit, offset))

    async def _list_async(
        self, tenant_context: TenantContext, limit: int, offset: int
    ) -> builtins.list[OverrideRecord]:
        query = text("""
            SELECT id, tenant_id, override_class, who, what, why, "when",
                   previous_value, new_value, expiry, is_permanent, approval_metadata,
                   status, reverted_at, reverted_by, reversion_reason, correlation_id,
                   created_at, updated_at
            FROM overrides
            WHERE tenant_id = :tid
            ORDER BY "when" DESC
            LIMIT :limit OFFSET :offset;
        """)
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            result = await sess.execute(query, {"tid": tenant_context.tenant_id, "limit": limit, "offset": offset})
            rows = result.fetchall()
            return [self._row_to_record(r) for r in rows]

    def list_active(self, *, tenant_context: TenantContext) -> builtins.list[OverrideRecord]:
        self._validate_tenant_context(tenant_context)
        return self._run_async(self._list_active_async(tenant_context))

    async def _list_active_async(self, tenant_context: TenantContext) -> builtins.list[OverrideRecord]:
        query = text("""
            SELECT id, tenant_id, override_class, who, what, why, "when",
                   previous_value, new_value, expiry, is_permanent, approval_metadata,
                   status, reverted_at, reverted_by, reversion_reason, correlation_id,
                   created_at, updated_at
            FROM overrides
            WHERE tenant_id = :tid AND status = 'ACTIVE'
            ORDER BY "when" DESC;
        """)
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            result = await sess.execute(query, {"tid": tenant_context.tenant_id})
            rows = result.fetchall()
            return [self._row_to_record(r) for r in rows]

    def save(self, entity: OverrideRecord, *, tenant_context: TenantContext) -> OverrideRecord:
        self._validate_tenant_context(tenant_context)
        if entity.tenant_id != tenant_context.tenant_id:
            raise CrossTenantAccessForbiddenException(
                f"Cannot save override: entity tenant '{entity.tenant_id}' does not match "
                f"context tenant '{tenant_context.tenant_id}'."
            )
        return self._run_async(self._save_async(entity, tenant_context))

    async def _save_async(self, entity: OverrideRecord, tenant_context: TenantContext) -> OverrideRecord:
        approval_json = json.dumps(entity.approval.model_dump(mode="json")) if entity.approval else None
        prev_json = json.dumps(entity.previous_value) if entity.previous_value is not None else None
        new_json = json.dumps(entity.new_value) if entity.new_value is not None else "null"

        query = text("""
            INSERT INTO overrides (
                id, tenant_id, override_class, who, what, why, "when",
                previous_value, new_value, expiry, is_permanent, approval_metadata,
                status, reverted_at, reverted_by, reversion_reason, correlation_id,
                created_at, updated_at
            )
            VALUES (
                :id, :tenant_id, :override_class, :who, :what, :why, :when,
                CAST(:previous_value AS jsonb), CAST(:new_value AS jsonb), :expiry, :is_permanent,
                CAST(:approval_metadata AS jsonb), :status, :reverted_at, :reverted_by,
                :reversion_reason, :correlation_id, NOW(), NOW()
            )
            ON CONFLICT (id)
            DO UPDATE SET
                override_class = EXCLUDED.override_class,
                who = EXCLUDED.who,
                what = EXCLUDED.what,
                why = EXCLUDED.why,
                "when" = EXCLUDED."when",
                previous_value = EXCLUDED.previous_value,
                new_value = EXCLUDED.new_value,
                expiry = EXCLUDED.expiry,
                is_permanent = EXCLUDED.is_permanent,
                approval_metadata = EXCLUDED.approval_metadata,
                status = EXCLUDED.status,
                reverted_at = EXCLUDED.reverted_at,
                reverted_by = EXCLUDED.reverted_by,
                reversion_reason = EXCLUDED.reversion_reason,
                correlation_id = EXCLUDED.correlation_id,
                updated_at = NOW();
        """)
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            await sess.execute(
                query,
                {
                    "id": entity.id,
                    "tenant_id": entity.tenant_id,
                    "override_class": entity.override_class.value if hasattr(entity.override_class, "value") else str(entity.override_class),
                    "who": entity.who,
                    "what": entity.what,
                    "why": entity.why,
                    "when": entity.when,
                    "previous_value": prev_json,
                    "new_value": new_json,
                    "expiry": entity.expiry,
                    "is_permanent": entity.is_permanent,
                    "approval_metadata": approval_json,
                    "status": entity.status.value if hasattr(entity.status, "value") else str(entity.status),
                    "reverted_at": entity.reverted_at,
                    "reverted_by": entity.reverted_by,
                    "reversion_reason": entity.reversion_reason,
                    "correlation_id": entity.correlation_id,
                },
            )
            await sess.commit()
        return entity

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        self._validate_tenant_context(tenant_context)
        return self._run_async(self._delete_async(entity_id, tenant_context))

    async def _delete_async(self, entity_id: str, tenant_context: TenantContext) -> bool:
        query = text("DELETE FROM overrides WHERE tenant_id = :tid AND id = :oid;")
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(query, {"tid": tenant_context.tenant_id, "oid": entity_id})
            await sess.commit()
            return res.rowcount > 0

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return self.get(entity_id, tenant_context=tenant_context) is not None


_override_repo_instance: OverrideRepository | None = None


def get_override_repository() -> OverrideRepository:
    """Dependency provider with production startup guard."""
    global _override_repo_instance
    mode = os.getenv("PERSISTENCE_MODE", "sql").strip().lower()
    env = os.getenv("CLOUDLENS_ENV", "development").strip().lower()

    if mode == "inmemory":
        if env in ("staging", "production"):
            logger.critical("FATAL STARTUP GUARD: Staging/production refuses InMemory repository.")
            sys.exit(1)
        from tests.fakes.overrides import InMemoryOverrideRepository
        return InMemoryOverrideRepository()

    if _override_repo_instance is None:
        _override_repo_instance = SqlOverrideRepository()
    return _override_repo_instance
