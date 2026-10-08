"""In-memory fake connector repository for test harnesses."""

from __future__ import annotations

import threading
from typing import Any

from domain.connectors.models import ConnectorEntity
from domain.models.enums import ConnectorLifecycleState, ProviderType
from domain.tenant.context import TenantContext


class InMemoryConnectorRepository:
    """Tenant-isolated in-memory fake connector repository."""

    is_in_memory: bool = True

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._connectors: dict[tuple[str, str], ConnectorEntity] = {}

    def get(self, connector_id: str, *, tenant_context: TenantContext) -> ConnectorEntity | None:
        with self._lock:
            return self._connectors.get((tenant_context.tenant_id, connector_id))

    def list(
        self,
        *,
        tenant_context: TenantContext,
        provider: ProviderType | None = None,
        lifecycle_state: ConnectorLifecycleState | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ConnectorEntity]:
        with self._lock:
            items = [c for (tid, _), c in self._connectors.items() if tid == tenant_context.tenant_id]

        if provider:
            items = [c for c in items if c.provider == provider]
        if lifecycle_state:
            items = [c for c in items if c.lifecycle_state == lifecycle_state]

        sorted_items = sorted(items, key=lambda c: c.created_at, reverse=True)
        return sorted_items[offset : offset + limit]

    def save(self, entity: ConnectorEntity, *, tenant_context: TenantContext) -> ConnectorEntity:
        entity.tenant_id = tenant_context.tenant_id
        with self._lock:
            self._connectors[(tenant_context.tenant_id, entity.id)] = entity
            return entity

    def update_lifecycle_state(
        self, connector_id: str, new_state: ConnectorLifecycleState, *, tenant_context: TenantContext
    ) -> bool:
        with self._lock:
            key = (tenant_context.tenant_id, connector_id)
            if key in self._connectors:
                self._connectors[key].lifecycle_state = new_state
                return True
            return False

    def update_capabilities(
        self,
        connector_id: str,
        declared: list[str] | None = None,
        verified: list[str] | None = None,
        *,
        tenant_context: TenantContext,
    ) -> bool:
        with self._lock:
            key = (tenant_context.tenant_id, connector_id)
            if key in self._connectors:
                if declared is not None:
                    self._connectors[key].declared_capabilities = declared
                if verified is not None:
                    self._connectors[key].verified_capabilities = verified
                return True
            return False

    def delete(self, connector_id: str, *, tenant_context: TenantContext) -> bool:
        with self._lock:
            key = (tenant_context.tenant_id, connector_id)
            if key in self._connectors:
                del self._connectors[key]
                return True
            return False
