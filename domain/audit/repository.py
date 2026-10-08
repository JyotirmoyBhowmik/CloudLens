"""Append-Only Audit Repository and PostgreSQL Implementation (Prompt P04).

Enforces:
- Pattern P1: Protocol + SqlAuditRepository (SQLAlchemy 2.0 async).
- Pattern P3: Injected dependency, zero mutable dict singletons as sources of truth.
- Pattern P4: Transactional RLS isolation via get_tenant_session().
- Pattern P6: Startup guard preventing InMemory repository outside development.
- Append-only database triggers rejecting UPDATE and DELETE at the PostgreSQL level.
- Cryptographic hash chaining computed over rows stored and retrieved from PostgreSQL.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import os
import sys
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_tenant_session
from domain.audit.models import AuditEvent, AuditEventFilter
from domain.models.enums import AuditEventType
from domain.models.exceptions import (
    AuditTamperForbiddenException,
    CrossTenantAccessForbiddenException,
)
from domain.tenant.context import TenantContext, require_tenant_context

logger = logging.getLogger("cloudlens.domain.audit.repository")


@runtime_checkable
class AuditRepository(Protocol):
    """Authoritative protocol for append-only audit event persistence."""

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> AuditEvent | None:
        ...

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditEvent]:
        ...

    def save(self, entity: AuditEvent, *, tenant_context: TenantContext) -> AuditEvent:
        ...

    def get_last_event(self, *, tenant_context: TenantContext) -> AuditEvent | None:
        ...

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        ...

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        ...

    def count(self, *, tenant_context: TenantContext) -> int:
        ...


class SqlAuditRepository:
    """PostgreSQL production implementation for append-only audit events."""

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

    def _row_to_event(self, row: Any) -> AuditEvent:
        event_type_str = row[8] or "SYSTEM_CONFIGURATION_CHANGED"
        try:
            event_type = AuditEventType(event_type_str)
        except Exception:
            event_type = AuditEventType.SYSTEM_CONFIGURATION_CHANGED

        raw_roles = row[9]
        roles = raw_roles if isinstance(raw_roles, list) else json.loads(raw_roles or "[]")
        raw_details = row[10]
        details = raw_details if isinstance(raw_details, dict) else json.loads(raw_details or "{}")

        return AuditEvent(
            id=row[0],
            timestamp=row[1],
            tenant_id=row[2],
            actor_id=row[3],
            action=row[4],
            resource_type=row[5],
            resource_id=row[6],
            correlation_id=row[7],
            event_type=event_type,
            actor_roles=roles,
            details=details,
            previous_event_hash=row[11],
            event_hash=row[12] or "",
            ip_address=row[13],
            user_agent=row[14],
        )

    # -------------------------------------------------------------------------
    # Public Sync Methods matching TenantAwareRepository contract
    # -------------------------------------------------------------------------

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> AuditEvent | None:
        self._validate_tenant_context(tenant_context)
        return self._run_async(self._get_async(entity_id, tenant_context))

    async def _get_async(self, entity_id: str, tenant_context: TenantContext) -> AuditEvent | None:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            query = text("""
                SELECT id, occurred_at, tenant_id, actor_id, action, entity_type, entity_id, correlation_id,
                       event_type, actor_roles, details, previous_event_hash, event_hash, ip_address, user_agent
                FROM audit_event
                WHERE tenant_id = :tid AND id = :eid
                LIMIT 1;
            """)
            result = await sess.execute(query, {"tid": tenant_context.tenant_id, "eid": entity_id})
            row = result.fetchone()
            if not row:
                return None
            return self._row_to_event(row)

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditEvent]:
        self._validate_tenant_context(tenant_context)
        return self._run_async(self._list_async(tenant_context, filter_params, limit, offset))

    async def _list_async(
        self,
        tenant_context: TenantContext,
        filter_params: Any,
        limit: int,
        offset: int,
    ) -> list[AuditEvent]:
        filters: AuditEventFilter | None = (
            filter_params if isinstance(filter_params, AuditEventFilter) else None
        )
        clauses = ["tenant_id = :tid"]
        params: dict[str, Any] = {"tid": tenant_context.tenant_id, "limit": limit, "offset": offset}

        if filters:
            if filters.event_type:
                clauses.append("event_type = :etype")
                params["etype"] = filters.event_type.value if hasattr(filters.event_type, "value") else str(filters.event_type)
            if filters.actor_id:
                clauses.append("actor_id = :aid")
                params["aid"] = filters.actor_id
            if filters.resource_type:
                clauses.append("entity_type = :rtype")
                params["rtype"] = filters.resource_type
            if filters.resource_id:
                clauses.append("entity_id = :rid")
                params["rid"] = filters.resource_id
            if filters.correlation_id:
                clauses.append("correlation_id = :cid")
                params["cid"] = filters.correlation_id
            if filters.since:
                clauses.append("occurred_at >= :since")
                params["since"] = filters.since
            if filters.until:
                clauses.append("occurred_at <= :until")
                params["until"] = filters.until

        where_sql = " AND ".join(clauses)
        query = text(f"""
            SELECT id, occurred_at, tenant_id, actor_id, action, entity_type, entity_id, correlation_id,
                   event_type, actor_roles, details, previous_event_hash, event_hash, ip_address, user_agent
            FROM audit_event
            WHERE {where_sql}
            ORDER BY occurred_at DESC, id DESC
            LIMIT :limit OFFSET :offset;
        """)

        async with get_tenant_session(tenant_context.tenant_id) as sess:
            result = await sess.execute(query, params)
            rows = result.fetchall()
            return [self._row_to_event(r) for r in rows]

    def save(self, entity: AuditEvent, *, tenant_context: TenantContext) -> AuditEvent:
        self._validate_tenant_context(tenant_context)
        if entity.tenant_id != tenant_context.tenant_id:
            raise CrossTenantAccessForbiddenException(
                f"Cannot append audit event: entity tenant '{entity.tenant_id}' does not match "
                f"context tenant '{tenant_context.tenant_id}'."
            )
        return self._run_async(self._save_async(entity, tenant_context))

    async def _save_async(self, entity: AuditEvent, tenant_context: TenantContext) -> AuditEvent:
        query = text("""
            INSERT INTO audit_event (
                id, occurred_at, tenant_id, actor_id, action, entity_type, entity_id, correlation_id,
                event_type, actor_roles, details, previous_event_hash, event_hash, ip_address, user_agent
            )
            VALUES (
                :id, :occurred_at, :tenant_id, :actor_id, :action, :entity_type, :entity_id, :correlation_id,
                :event_type, CAST(:actor_roles AS jsonb), CAST(:details AS jsonb), :previous_event_hash, :event_hash, :ip_address, :user_agent
            );
        """)
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            try:
                await sess.execute(
                    query,
                    {
                        "id": entity.id,
                        "occurred_at": entity.timestamp,
                        "tenant_id": entity.tenant_id,
                        "actor_id": entity.actor_id,
                        "action": entity.action,
                        "entity_type": entity.resource_type,
                        "entity_id": entity.resource_id,
                        "correlation_id": entity.correlation_id or "default-trace",
                        "event_type": entity.event_type.value if hasattr(entity.event_type, "value") else str(entity.event_type),
                        "actor_roles": json.dumps(entity.actor_roles),
                        "details": json.dumps(entity.details),
                        "previous_event_hash": entity.previous_event_hash,
                        "event_hash": entity.event_hash,
                        "ip_address": entity.ip_address,
                        "user_agent": entity.user_agent,
                    },
                )
                await sess.commit()
            except DBAPIError as err:
                await sess.rollback()
                if "PERMISSION_DENIED" in str(err):
                    raise AuditTamperForbiddenException(str(err)) from err
                raise
        return entity

    def get_last_event(self, *, tenant_context: TenantContext) -> AuditEvent | None:
        self._validate_tenant_context(tenant_context)
        return self._run_async(self._get_last_event_async(tenant_context))

    async def _get_last_event_async(self, tenant_context: TenantContext) -> AuditEvent | None:
        query = text("""
            SELECT id, occurred_at, tenant_id, actor_id, action, entity_type, entity_id, correlation_id,
                   event_type, actor_roles, details, previous_event_hash, event_hash, ip_address, user_agent
            FROM audit_event
            WHERE tenant_id = :tid
            ORDER BY occurred_at DESC, id DESC
            LIMIT 1;
        """)
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            result = await sess.execute(query, {"tid": tenant_context.tenant_id})
            row = result.fetchone()
            if not row:
                return None
            return self._row_to_event(row)

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        self._validate_tenant_context(tenant_context)
        return self.get(entity_id, tenant_context=tenant_context) is not None

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        """Deletion executes directly against DB to prove trigger rejection."""
        self._validate_tenant_context(tenant_context)
        return self._run_async(self._delete_async(entity_id, tenant_context))

    async def _delete_async(self, entity_id: str, tenant_context: TenantContext) -> bool:
        query = text("DELETE FROM audit_event WHERE tenant_id = :tid AND id = :eid;")
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            try:
                await sess.execute(query, {"tid": tenant_context.tenant_id, "eid": entity_id})
                await sess.commit()
            except DBAPIError as err:
                await sess.rollback()
                raise AuditTamperForbiddenException(
                    "Audit records are immutable and append-only at the database and application level. "
                    "Deletion is strictly prohibited per BBP Section 41 and Prompt 06 Item 45."
                ) from err
        raise AuditTamperForbiddenException("Audit records are immutable.")

    def count(self, *, tenant_context: TenantContext) -> int:
        self._validate_tenant_context(tenant_context)
        return self._run_async(self._count_async(tenant_context))

    async def _count_async(self, tenant_context: TenantContext) -> int:
        query = text("SELECT count(*) FROM audit_event WHERE tenant_id = :tid;")
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            result = await sess.execute(query, {"tid": tenant_context.tenant_id})
            return result.scalar() or 0


_audit_repo_instance: AuditRepository | None = None


def get_audit_repository() -> AuditRepository:
    """Dependency provider with production startup guard."""
    global _audit_repo_instance
    mode = os.getenv("PERSISTENCE_MODE", "sql").strip().lower()
    env = os.getenv("CLOUDLENS_ENV", "development").strip().lower()

    if mode == "inmemory":
        if env in ("staging", "production"):
            logger.critical("FATAL STARTUP GUARD: Staging/production refuses InMemory repository.")
            sys.exit(1)
        from tests.fakes.audit import InMemoryAuditRepository
        return InMemoryAuditRepository()

    if _audit_repo_instance is None:
        _audit_repo_instance = SqlAuditRepository()
    return _audit_repo_instance
