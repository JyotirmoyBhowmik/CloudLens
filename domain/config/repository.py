"""CloudLens Tenant Settings Repository Interface & Real SQL Implementation (Prompt P03).

Enforces:
- Pattern P1: Protocol + SqlTenantSettingsRepository (SQLAlchemy 2.0 async).
- Pattern P3: Injected dependency, no module-level singletons holding dicts.
- Pattern P4: Transactional RLS isolation via get_tenant_session().
- Pattern P6: Startup guard preventing InMemory repository in staging/production.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_tenant_session
from domain.config.tenant_settings import TenantSettings

logger = logging.getLogger("cloudlens.domain.config.repository")


@runtime_checkable
class TenantSettingsRepository(Protocol):
    """Authoritative protocol for tenant configuration persistence."""

    async def get(self, tenant_id: str, session: AsyncSession | None = None) -> TenantSettings:
        """Retrieves tenant settings profile, returning default configuration if record absent."""
        ...

    async def save(self, settings: TenantSettings, session: AsyncSession | None = None) -> TenantSettings:
        """Persists or replaces full tenant settings profile."""
        ...

    async def update(self, tenant_id: str, new_settings: dict[str, Any], session: AsyncSession | None = None) -> TenantSettings:
        """Deep-merges update dictionary into tenant settings and persists updated record."""
        ...

    def get_sync(self, tenant_id: str) -> TenantSettings:
        """Synchronous accessor for legacy service layers."""
        ...

    def save_sync(self, settings: TenantSettings) -> TenantSettings:
        """Synchronous persistence for legacy service layers."""
        ...

    def update_sync(self, tenant_id: str, new_settings: dict[str, Any]) -> TenantSettings:
        """Synchronous update for legacy service layers."""
        ...


class SqlTenantSettingsRepository:
    """Production PostgreSQL-backed repository for tenant settings with RLS isolation."""

    is_in_memory: bool = False

    async def _get_with_session(self, tenant_id: str, session: AsyncSession) -> TenantSettings:
        query = text("""
            SELECT settings
            FROM tenant_settings
            WHERE tenant_id = :tid
            LIMIT 1;
        """)
        result = await session.execute(query, {"tid": tenant_id})
        row = result.fetchone()
        if row and row[0]:
            raw_data = row[0]
            if isinstance(raw_data, str):
                raw_data = json.loads(raw_data)
            raw_data["tenant_id"] = tenant_id
            return TenantSettings.model_validate(raw_data)

        # Record absent -> default settings
        return TenantSettings(tenant_id=tenant_id)

    async def get(self, tenant_id: str, session: AsyncSession | None = None) -> TenantSettings:
        if session is not None:
            return await self._get_with_session(tenant_id, session)
        async with get_tenant_session(tenant_id) as sess:
            return await self._get_with_session(tenant_id, sess)

    async def _save_with_session(self, settings: TenantSettings, session: AsyncSession) -> TenantSettings:
        settings_json = json.dumps(settings.model_dump(mode="json"))
        query = text("""
            INSERT INTO tenant_settings (tenant_id, settings, updated_at)
            VALUES (:tid, CAST(:settings AS jsonb), NOW())
            ON CONFLICT (tenant_id)
            DO UPDATE SET
                settings = EXCLUDED.settings,
                updated_at = NOW();
        """)
        await session.execute(query, {"tid": settings.tenant_id, "settings": settings_json})
        return settings

    async def save(self, settings: TenantSettings, session: AsyncSession | None = None) -> TenantSettings:
        if session is not None:
            return await self._save_with_session(settings, session)
        async with get_tenant_session(settings.tenant_id) as sess:
            res = await self._save_with_session(settings, sess)
            await sess.commit()
            return res

    async def update(
        self, tenant_id: str, new_settings: dict[str, Any], session: AsyncSession | None = None
    ) -> TenantSettings:
        current = await self.get(tenant_id, session=session)
        current_data = current.model_dump()

        # Deep merge updates
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
        return await self.save(updated, session=session)

    def _run_async(self, coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        # When running inside active event loop from sync context
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro)).result()

    def get_sync(self, tenant_id: str) -> TenantSettings:
        return self._run_async(self.get(tenant_id))

    def save_sync(self, settings: TenantSettings) -> TenantSettings:
        return self._run_async(self.save(settings))

    def update_sync(self, tenant_id: str, new_settings: dict[str, Any]) -> TenantSettings:
        return self._run_async(self.update(tenant_id, new_settings))


_sql_repo_instance: SqlTenantSettingsRepository | None = None


def get_tenant_settings_repository() -> TenantSettingsRepository:
    """Dependency provider for TenantSettingsRepository.

    Enforces Prompt P03 Item 4: Staging and production strictly require SqlTenantSettingsRepository.
    """
    global _sql_repo_instance
    if _sql_repo_instance is None:
        _sql_repo_instance = SqlTenantSettingsRepository()
        verify_persistence_startup_guard(_sql_repo_instance)
    return _sql_repo_instance


def reset_tenant_settings_repository(repo: TenantSettingsRepository | None = None) -> TenantSettingsRepository:
    """Resets tenant settings repository singleton for testing."""
    global _sql_repo_instance
    _sql_repo_instance = repo
    return _sql_repo_instance or get_tenant_settings_repository()
