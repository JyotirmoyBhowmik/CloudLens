"""Tenant-Aware Repository for Onboarding Wizard Sessions (Prompt 15 Item 100).

Enforces:
- Prompt 13 Item 84: Mandatory TenantContext on every public method.
- Mechanical isolation: Queries fail at build/test time without tenant context.
- Thread-safe storage supporting save-and-resume across disconnects.
"""

from __future__ import annotations

import builtins
import threading
from typing import Any

from domain.tenant.context import TenantContext
from domain.tenant.repository import TenantAwareRepository
from domain.wizard.models import WizardSession


class WizardRepository(TenantAwareRepository[WizardSession]):
    """Tenant-isolated repository for onboarding wizard draft sessions."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # (tenant_id, session_id) -> WizardSession
        self._sessions: dict[tuple[str, str], WizardSession] = {}

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> WizardSession | None:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            return self._sessions.get((tenant_context.tenant_id, entity_id))

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[WizardSession]:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            tenant_items = [
                s for (tid, _), s in self._sessions.items() if tid == tenant_context.tenant_id
            ]

        if isinstance(filter_params, dict):
            status_filter = filter_params.get("status")
            if status_filter:
                tenant_items = [s for s in tenant_items if s.status == status_filter]
            user_filter = filter_params.get("user_id")
            if user_filter:
                tenant_items = [s for s in tenant_items if s.user_id == user_filter]

        sorted_items = sorted(tenant_items, key=lambda s: s.updated_at, reverse=True)
        return sorted_items[offset : offset + limit]

    def save(self, entity: WizardSession, *, tenant_context: TenantContext) -> WizardSession:
        self._validate_tenant_context(tenant_context)
        entity.tenant_id = tenant_context.tenant_id
        with self._lock:
            self._sessions[(tenant_context.tenant_id, entity.id)] = entity
        return entity

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            key = (tenant_context.tenant_id, entity_id)
            if key in self._sessions:
                del self._sessions[key]
                return True
            return False

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            return (tenant_context.tenant_id, entity_id) in self._sessions

    def get_active_for_user(
        self, user_id: str, *, tenant_context: TenantContext
    ) -> WizardSession | None:
        """Retrieves the latest in-progress wizard session for a user in this tenant."""
        self._validate_tenant_context(tenant_context)
        with self._lock:
            active = [
                s
                for (tid, _), s in self._sessions.items()
                if tid == tenant_context.tenant_id
                and s.user_id == user_id
                and s.status == "IN_PROGRESS"
            ]
        if not active:
            return None
        return max(active, key=lambda s: s.updated_at)


# Global singleton wizard repository
_wizard_repository = WizardRepository()


def get_wizard_repository() -> WizardRepository:
    return _wizard_repository
