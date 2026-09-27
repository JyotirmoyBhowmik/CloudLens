"""Tenant-Isolated Repository for Notification Dispatch Logs (Prompt 15B Item 25).

Enforces:
- Prompt 13 Item 84: Mandatory TenantContext parameter on every public repository method.
- Mechanical isolation: Queries fail at build/test time without tenant context.
- Thread-safe storage with support for in-memory and database persistence.
"""

from __future__ import annotations

import builtins
import threading
from typing import Any

from domain.notification.models import NotificationLogRecord
from domain.tenant.context import TenantContext
from domain.tenant.repository import TenantAwareRepository


class NotificationLogRepository(TenantAwareRepository[NotificationLogRecord]):
    """Tenant-isolated repository for outbound notification logs and test alerts."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # (tenant_id, notification_id) -> NotificationLogRecord
        self._logs: dict[tuple[str, str], NotificationLogRecord] = {}

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> NotificationLogRecord | None:
        """Retrieves a notification record by ID within the authenticated tenant context."""
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
        """Lists notification records for the authenticated tenant with optional test filtering."""
        self._validate_tenant_context(tenant_context)
        with self._lock:
            items = [
                record for (tid, _), record in self._logs.items() if tid == tenant_context.tenant_id
            ]

        # Filter out tests if requested
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
        """Saves or updates a notification record in tenant storage."""
        self._validate_tenant_context(tenant_context)
        with self._lock:
            key = (tenant_context.tenant_id, entity.id)
            self._logs[key] = entity
            return entity

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        """Deletes a notification record by ID."""
        self._validate_tenant_context(tenant_context)
        with self._lock:
            key = (tenant_context.tenant_id, entity_id)
            if key in self._logs:
                del self._logs[key]
                return True
            return False

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        """Checks if a notification record exists in the tenant namespace."""
        self._validate_tenant_context(tenant_context)
        with self._lock:
            return (tenant_context.tenant_id, entity_id) in self._logs


# Singleton accessor
_notification_log_repository = NotificationLogRepository()


def get_notification_log_repository() -> NotificationLogRepository:
    return _notification_log_repository


__all__ = [
    "NotificationLogRepository",
    "get_notification_log_repository",
]
