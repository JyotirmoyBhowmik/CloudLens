"""Append-Only Audit Repository (Prompt 13 Items 84, 86).

Enforces:
- Tenant-scoped repository methods requiring explicit TenantContext (Item 84).
- Append-only database / in-memory semantics: UPDATE and DELETE operations strictly raise
  AuditTamperForbiddenException and fail mechanically (Item 86, Prompt 06 Item 45).
"""

from __future__ import annotations

import threading
from typing import Any

from domain.audit.models import AuditEvent, AuditEventFilter
from domain.models.exceptions import (
    AuditTamperForbiddenException,
    CrossTenantAccessForbiddenException,
)
from domain.tenant.context import TenantContext
from domain.tenant.repository import TenantAwareRepository


class AuditRepository(TenantAwareRepository[AuditEvent]):
    """Thread-safe, append-only repository for audit events partitioned by tenant."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # tenant_id -> list of AuditEvent
        self._tenant_streams: dict[str, list[AuditEvent]] = {}
        # (tenant_id, event_id) -> AuditEvent
        self._index: dict[tuple[str, str], AuditEvent] = {}

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> AuditEvent | None:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            return self._index.get((tenant_context.tenant_id, entity_id))

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditEvent]:
        self._validate_tenant_context(tenant_context)
        filters: AuditEventFilter | None = (
            filter_params if isinstance(filter_params, AuditEventFilter) else None
        )

        with self._lock:
            stream = list(self._tenant_streams.get(tenant_context.tenant_id, []))

        # Apply filtering
        results: list[AuditEvent] = []
        for event in stream:
            if filters:
                if filters.event_type and event.event_type != filters.event_type:
                    continue
                if filters.actor_id and event.actor_id != filters.actor_id:
                    continue
                if filters.resource_type and event.resource_type != filters.resource_type:
                    continue
                if filters.resource_id and event.resource_id != filters.resource_id:
                    continue
                if filters.correlation_id and event.correlation_id != filters.correlation_id:
                    continue
                if filters.since and event.timestamp < filters.since:
                    continue
                if filters.until and event.timestamp > filters.until:
                    continue
            results.append(event)

        return results[offset : offset + limit]

    def save(self, entity: AuditEvent, *, tenant_context: TenantContext) -> AuditEvent:
        """Appends audit event to tenant stream. Updates are forbidden."""
        self._validate_tenant_context(tenant_context)
        if entity.tenant_id != tenant_context.tenant_id:
            raise CrossTenantAccessForbiddenException(
                f"Cannot append audit event: entity tenant '{entity.tenant_id}' does not match "
                f"context tenant '{tenant_context.tenant_id}'."
            )

        with self._lock:
            key = (tenant_context.tenant_id, entity.id)
            if key in self._index:
                # Attempt to overwrite existing record is an illegal mutation!
                raise AuditTamperForbiddenException(
                    f"Audit event '{entity.id}' already exists. Overwrite/mutation is strictly prohibited."
                )

            self._index[key] = entity
            self._tenant_streams.setdefault(tenant_context.tenant_id, []).append(entity)

        return entity

    def get_last_event(self, *, tenant_context: TenantContext) -> AuditEvent | None:
        """Retrieves most recent event in the tenant stream for cryptographic hash chaining."""
        self._validate_tenant_context(tenant_context)
        with self._lock:
            stream = self._tenant_streams.get(tenant_context.tenant_id, [])
            return stream[-1] if stream else None

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            return (tenant_context.tenant_id, entity_id) in self._index

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        """Deletion is strictly prohibited at all privilege levels."""
        _ = entity_id
        self._validate_tenant_context(tenant_context)
        raise AuditTamperForbiddenException(
            "Audit records are immutable and append-only at the database and application level. "
            "Deletion is strictly prohibited per BBP Section 41 and Prompt 06 Item 45."
        )

    def count(self, *, tenant_context: TenantContext) -> int:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            return len(self._tenant_streams.get(tenant_context.tenant_id, []))
