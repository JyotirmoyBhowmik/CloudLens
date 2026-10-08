"""In-memory fake notification log repository for test harnesses."""

from __future__ import annotations

import builtins
import threading
from typing import Any

from domain.notification.models import NotificationLogRecord
from domain.tenant.context import TenantContext
from domain.tenant.repository import TenantAwareRepository


class InMemoryNotificationLogRepository(TenantAwareRepository[NotificationLogRecord]):
    """Tenant-isolated in-memory fake notification log repository."""

    is_in_memory: bool = True

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._logs: dict[tuple[str, str], NotificationLogRecord] = {}

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> NotificationLogRecord | None:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            return self._logs.get((tenant_context.tenant_id, entity_id))

    def list(
        self,
        *,
        tenant_context: TenantContext,
        include_tests: bool = True,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[NotificationLogRecord]:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            items = [
                record for (tid, _), record in self._logs.items() if tid == tenant_context.tenant_id
            ]

        if not include_tests:
            items = [r for r in items if not r.is_test]

        if isinstance(filter_params, dict):
            channel_filter = filter_params.get("channel")
            if channel_filter:
                items = [r for r in items if r.channel == channel_filter]
            status_filter = filter_params.get("status")
            if status_filter:
                items = [r for r in items if r.status == status_filter]

        sorted_items = sorted(
            items,
            key=lambda r: r.sent_at or r.created_at,
            reverse=True,
        )
        return sorted_items[offset : offset + limit]

    def save(
        self, entity: NotificationLogRecord, *, tenant_context: TenantContext
    ) -> NotificationLogRecord:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            key = (tenant_context.tenant_id, entity.id)
            self._logs[key] = entity
            return entity

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            key = (tenant_context.tenant_id, entity_id)
            if key in self._logs:
                del self._logs[key]
                return True
            return False

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            return (tenant_context.tenant_id, entity_id) in self._logs
