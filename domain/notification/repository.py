"""Tenant-Isolated Repository for Notification Dispatch Logs (Prompt P05).

Enforces:
- Pattern P1: Protocol + SqlNotificationLogRepository (SQLAlchemy 2.0 async + asyncpg).
- Pattern P3: Injected dependency, zero mutable dict singletons in production.
- Pattern P4: Transactional RLS isolation via get_tenant_session().
- Pattern P6: Startup guard preventing InMemory repository outside development.
- Outbound notification and synthetic test alert persistence across restarts.
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

from db.session import get_tenant_session, run_async, verify_persistence_startup_guard
from domain.models.enums import NotificationChannel, NotificationStatus
from domain.notification.models import NotificationLogRecord
from domain.tenant.context import TenantContext

logger = logging.getLogger("cloudlens.domain.notification.repository")


@runtime_checkable
class NotificationLogRepository(Protocol):
    """Authoritative protocol for Notification Log persistence."""

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> NotificationLogRecord | None:
        ...

    def list(
        self,
        *,
        tenant_context: TenantContext,
        include_tests: bool = True,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[NotificationLogRecord]:
        ...

    def save(
        self, entity: NotificationLogRecord, *, tenant_context: TenantContext
    ) -> NotificationLogRecord:
        ...

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        ...

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        ...

    async def get_async(
        self, entity_id: str, *, tenant_context: TenantContext, session: AsyncSession | None = None
    ) -> NotificationLogRecord | None:
        ...

    async def save_async(
        self, entity: NotificationLogRecord, *, tenant_context: TenantContext, session: AsyncSession | None = None
    ) -> NotificationLogRecord:
        ...


class SqlNotificationLogRepository:
    """PostgreSQL production implementation for notification logs with RLS."""

    is_in_memory: bool = False

    def _run_async(self, coro: Any) -> Any:
        return run_async(coro)

    def _row_to_record(self, row: Any) -> NotificationLogRecord:
        chan_val = row[3]
        try:
            chan = NotificationChannel(chan_val)
        except ValueError:
            chan = chan_val

        stat_val = row[5]
        try:
            stat = NotificationStatus(stat_val)
        except ValueError:
            stat = stat_val

        raw_meta = row[10] or {}
        if isinstance(raw_meta, str):
            raw_meta = json.loads(raw_meta)

        return NotificationLogRecord(
            id=row[0],
            tenant_id=row[1],
            alert_id=row[2],
            channel=chan,
            recipient=row[4],
            status=stat,
            message=row[6],
            is_test=row[7],
            latency_ms=row[8],
            error_message=row[9],
            metadata=raw_meta,
            sent_at=row[11],
            created_at=row[12],
            updated_at=row[13],
        )

    async def get_async(
        self, entity_id: str, *, tenant_context: TenantContext, session: AsyncSession | None = None
    ) -> NotificationLogRecord | None:
        if session is not None:
            return await self._get_with_session(entity_id, tenant_context, session)
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            return await self._get_with_session(entity_id, tenant_context, sess)

    async def _get_with_session(
        self, entity_id: str, tenant_context: TenantContext, session: AsyncSession
    ) -> NotificationLogRecord | None:
        query = text("""
            SELECT id, tenant_id, alert_id, channel, recipient, status, message,
                   is_test, latency_ms, error_message, metadata_payload, sent_at,
                   created_at, updated_at
            FROM notification_logs
            WHERE tenant_id = :tid AND id = :id
            LIMIT 1;
        """)
        res = await session.execute(query, {"tid": tenant_context.tenant_id, "id": entity_id})
        row = res.fetchone()
        return self._row_to_record(row) if row else None

    async def save_async(
        self, entity: NotificationLogRecord, *, tenant_context: TenantContext, session: AsyncSession | None = None
    ) -> NotificationLogRecord:
        entity.tenant_id = tenant_context.tenant_id
        if session is not None:
            return await self._save_with_session(entity, tenant_context, session)
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await self._save_with_session(entity, tenant_context, sess)
            await sess.commit()
            return res

    async def _save_with_session(
        self, entity: NotificationLogRecord, tenant_context: TenantContext, session: AsyncSession
    ) -> NotificationLogRecord:
        now = datetime.now(UTC)
        entity.updated_at = now
        chan_val = entity.channel.value if hasattr(entity.channel, "value") else str(entity.channel)
        stat_val = entity.status.value if hasattr(entity.status, "value") else str(entity.status)
        meta_json = json.dumps(entity.metadata)

        query = text("""
            INSERT INTO notification_logs (
                id, tenant_id, alert_id, channel, recipient, status, message,
                is_test, latency_ms, error_message, metadata_payload, sent_at,
                created_at, updated_at
            )
            VALUES (
                :id, :tenant_id, :alert_id, :channel, :recipient, :status, :message,
                :is_test, :latency_ms, :error_message, CAST(:meta AS jsonb), :sent_at,
                :created_at, :updated_at
            )
            ON CONFLICT (id) DO UPDATE SET
                alert_id = EXCLUDED.alert_id,
                channel = EXCLUDED.channel,
                recipient = EXCLUDED.recipient,
                status = EXCLUDED.status,
                message = EXCLUDED.message,
                is_test = EXCLUDED.is_test,
                latency_ms = EXCLUDED.latency_ms,
                error_message = EXCLUDED.error_message,
                metadata_payload = EXCLUDED.metadata_payload,
                sent_at = EXCLUDED.sent_at,
                updated_at = EXCLUDED.updated_at;
        """)
        await session.execute(
            query,
            {
                "id": entity.id,
                "tenant_id": tenant_context.tenant_id,
                "alert_id": entity.alert_id,
                "channel": chan_val,
                "recipient": entity.recipient,
                "status": stat_val,
                "message": entity.message,
                "is_test": entity.is_test,
                "latency_ms": entity.latency_ms,
                "error_message": entity.error_message,
                "meta": meta_json,
                "sent_at": entity.sent_at,
                "created_at": entity.created_at or now,
                "updated_at": now,
            },
        )
        return entity

    async def list_async(
        self,
        *,
        tenant_context: TenantContext,
        include_tests: bool = True,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
        session: AsyncSession | None = None,
    ) -> list[NotificationLogRecord]:
        if session is not None:
            return await self._list_with_session(tenant_context, include_tests, filter_params, limit, offset, session)
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            return await self._list_with_session(tenant_context, include_tests, filter_params, limit, offset, sess)

    async def _list_with_session(
        self,
        tenant_context: TenantContext,
        include_tests: bool,
        filter_params: Any,
        limit: int,
        offset: int,
        session: AsyncSession,
    ) -> list[NotificationLogRecord]:
        conditions = ["tenant_id = :tid"]
        params: dict[str, Any] = {"tid": tenant_context.tenant_id, "limit": limit, "offset": offset}

        if not include_tests:
            conditions.append("is_test = false")

        if isinstance(filter_params, dict):
            chan = filter_params.get("channel")
            if chan:
                chan_val = chan.value if hasattr(chan, "value") else str(chan)
                conditions.append("channel = :chan")
                params["chan"] = chan_val
            stat = filter_params.get("status")
            if stat:
                stat_val = stat.value if hasattr(stat, "value") else str(stat)
                conditions.append("status = :stat")
                params["stat"] = stat_val

        where_clause = " AND ".join(conditions)
        query = text(f"""
            SELECT id, tenant_id, alert_id, channel, recipient, status, message,
                   is_test, latency_ms, error_message, metadata_payload, sent_at,
                   created_at, updated_at
            FROM notification_logs
            WHERE {where_clause}
            ORDER BY COALESCE(sent_at, created_at) DESC
            LIMIT :limit OFFSET :offset;
        """)
        res = await session.execute(query, params)
        rows = res.fetchall()
        return [self._row_to_record(r) for r in rows]

    async def delete_async(
        self, entity_id: str, *, tenant_context: TenantContext, session: AsyncSession | None = None
    ) -> bool:
        query = text("DELETE FROM notification_logs WHERE tenant_id = :tid AND id = :id;")
        params = {"tid": tenant_context.tenant_id, "id": entity_id}
        if session is not None:
            res = await session.execute(query, params)
            return res.rowcount > 0

        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(query, params)
            await sess.commit()
            return res.rowcount > 0

    # Sync interfaces
    def get(self, entity_id: str, *, tenant_context: TenantContext) -> NotificationLogRecord | None:
        return self._run_async(self.get_async(entity_id, tenant_context=tenant_context))

    def list(
        self,
        *,
        tenant_context: TenantContext,
        include_tests: bool = True,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[NotificationLogRecord]:
        return self._run_async(
            self.list_async(
                tenant_context=tenant_context,
                include_tests=include_tests,
                filter_params=filter_params,
                limit=limit,
                offset=offset,
            )
        )

    def save(
        self, entity: NotificationLogRecord, *, tenant_context: TenantContext
    ) -> NotificationLogRecord:
        return self._run_async(self.save_async(entity, tenant_context=tenant_context))

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return self._run_async(self.delete_async(entity_id, tenant_context=tenant_context))

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        res = self.get(entity_id, tenant_context=tenant_context)
        return res is not None


_notification_log_repo_instance: Any = None


def get_notification_log_repository() -> Any:
    """Dependency provider with production startup guard."""
    global _notification_log_repo_instance
    if _notification_log_repo_instance is None:
        _notification_log_repo_instance = SqlNotificationLogRepository()
        verify_persistence_startup_guard(_notification_log_repo_instance)
    return _notification_log_repo_instance


def reset_notification_log_repository(repo: Any = None) -> Any:
    global _notification_log_repo_instance
    _notification_log_repo_instance = repo
    return _notification_log_repo_instance or get_notification_log_repository()


__all__ = [
    "NotificationLogRepository",
    "SqlNotificationLogRepository",
    "get_notification_log_repository",
    "reset_notification_log_repository",
]
