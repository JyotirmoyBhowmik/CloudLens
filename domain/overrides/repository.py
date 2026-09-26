"""Override Repository Interface and Implementation (Prompt 13 Items 84, 87).

Enforces:
- TenantContext required on every repository method (Item 84).
- Partitioned storage of active, reverted, and expired overrides per tenant.
"""

from __future__ import annotations

import builtins
import threading
from typing import Any

from domain.models.enums import OverrideStatus
from domain.models.exceptions import CrossTenantAccessForbiddenException
from domain.overrides.models import OverrideRecord
from domain.tenant.context import TenantContext
from domain.tenant.repository import TenantAwareRepository


class OverrideRepository(TenantAwareRepository[OverrideRecord]):
    """Thread-safe repository for tenant-scoped override records."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # (tenant_id, override_id) -> OverrideRecord
        self._records: dict[tuple[str, str], OverrideRecord] = {}

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> OverrideRecord | None:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            return self._records.get((tenant_context.tenant_id, entity_id))

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[OverrideRecord]:
        _ = filter_params
        self._validate_tenant_context(tenant_context)
        with self._lock:
            tenant_items = [
                rec for (tid, _), rec in self._records.items() if tid == tenant_context.tenant_id
            ]

        # Sort by when descending
        sorted_items = sorted(tenant_items, key=lambda r: r.when, reverse=True)
        return sorted_items[offset : offset + limit]

    def list_active(self, *, tenant_context: TenantContext) -> builtins.list[OverrideRecord]:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            return [
                rec
                for (tid, _), rec in self._records.items()
                if tid == tenant_context.tenant_id and rec.status == OverrideStatus.ACTIVE
            ]

    def save(self, entity: OverrideRecord, *, tenant_context: TenantContext) -> OverrideRecord:
        self._validate_tenant_context(tenant_context)
        if entity.tenant_id != tenant_context.tenant_id:
            raise CrossTenantAccessForbiddenException(
                f"Cannot save override: entity tenant '{entity.tenant_id}' does not match "
                f"context tenant '{tenant_context.tenant_id}'."
            )

        with self._lock:
            self._records[(tenant_context.tenant_id, entity.id)] = entity
        return entity

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            key = (tenant_context.tenant_id, entity_id)
            if key in self._records:
                del self._records[key]
                return True
            return False

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            return (tenant_context.tenant_id, entity_id) in self._records
