"""In-Memory Tenant Settings Fake Repository for Isolated Testing (Prompt P03 Item 2).

Restricted exclusively to tests/fakes. Staging and production startup guards strictly refuse
this implementation.
"""

from __future__ import annotations

from typing import Any

from domain.config.tenant_settings import TenantSettings
from sqlalchemy.ext.asyncio import AsyncSession


class InMemoryTenantSettingsRepository:
    """In-memory test fake implementing TenantSettingsRepository protocol."""

    is_in_memory: bool = True

    def __init__(self) -> None:
        self._tenants: dict[str, TenantSettings] = {}

    async def get(self, tenant_id: str, session: AsyncSession | None = None) -> TenantSettings:
        if tenant_id not in self._tenants:
            self._tenants[tenant_id] = TenantSettings(tenant_id=tenant_id)
        return self._tenants[tenant_id]

    async def save(self, settings: TenantSettings, session: AsyncSession | None = None) -> TenantSettings:
        self._tenants[settings.tenant_id] = settings
        return settings

    async def update(
        self, tenant_id: str, new_settings: dict[str, Any], session: AsyncSession | None = None
    ) -> TenantSettings:
        current = await self.get(tenant_id, session=session)
        current_data = current.model_dump()

        for key, value in new_settings.items():
            if (
                key in current_data
                and isinstance(current_data[key], dict)
                and isinstance(value, dict)
            ):
                current_data[key].update(value)
            else:
                current_data[key] = value

        updated = TenantSettings.model_validate(current_data)
        self._tenants[tenant_id] = updated
        return updated

    def get_sync(self, tenant_id: str) -> TenantSettings:
        if tenant_id not in self._tenants:
            self._tenants[tenant_id] = TenantSettings(tenant_id=tenant_id)
        return self._tenants[tenant_id]

    def save_sync(self, settings: TenantSettings) -> TenantSettings:
        self._tenants[settings.tenant_id] = settings
        return settings

    def update_sync(self, tenant_id: str, new_settings: dict[str, Any]) -> TenantSettings:
        current = self.get_sync(tenant_id)
        current_data = current.model_dump()

        for key, value in new_settings.items():
            if (
                key in current_data
                and isinstance(current_data[key], dict)
                and isinstance(value, dict)
            ):
                current_data[key].update(value)
            else:
                current_data[key] = value

        updated = TenantSettings.model_validate(current_data)
        self._tenants[tenant_id] = updated
        return updated

    def reset(self, tenant_id: str | None = None) -> None:
        """Helper for test cleanup."""
        if tenant_id:
            self._tenants.pop(tenant_id, None)
        else:
            self._tenants.clear()
