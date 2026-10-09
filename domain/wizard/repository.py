"""Tenant-Aware Repository for Onboarding Wizard Sessions (Prompt P05).

Enforces:
- Pattern P1: Protocol + SqlWizardRepository (SQLAlchemy 2.0 async + asyncpg).
- Pattern P3: Injected dependency, zero mutable dict singletons in production.
- Pattern P4: Transactional RLS isolation via get_tenant_session().
- Pattern P6: Startup guard preventing InMemory repository outside development.
- Save-and-resume persistence across server restarts.
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

from db.session import get_tenant_session, verify_persistence_startup_guard
from domain.models.enums import ProviderType, WizardStep
from domain.tenant.context import TenantContext
from domain.wizard.models import WizardSession

logger = logging.getLogger("cloudlens.domain.wizard.repository")


@runtime_checkable
class WizardRepository(Protocol):
    """Authoritative protocol for Onboarding Wizard session persistence."""

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> WizardSession | None:
        ...

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WizardSession]:
        ...

    def save(self, entity: WizardSession, *, tenant_context: TenantContext) -> WizardSession:
        ...

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        ...

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        ...

    def get_active_for_user(
        self, user_id: str, *, tenant_context: TenantContext
    ) -> WizardSession | None:
        ...

    async def get_async(
        self, entity_id: str, *, tenant_context: TenantContext, session: AsyncSession | None = None
    ) -> WizardSession | None:
        ...

    async def save_async(
        self, entity: WizardSession, *, tenant_context: TenantContext, session: AsyncSession | None = None
    ) -> WizardSession:
        ...

    async def get_active_for_user_async(
        self, user_id: str, *, tenant_context: TenantContext, session: AsyncSession | None = None
    ) -> WizardSession | None:
        ...


class SqlWizardRepository:
    """PostgreSQL production implementation for WizardSession entities with RLS."""

    is_in_memory: bool = False

    def _run_async(self, coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro)).result()

    def _row_to_session(self, row: Any) -> WizardSession:
        raw_wdata = row[6] or {}
        if isinstance(raw_wdata, str):
            raw_wdata = json.loads(raw_wdata)
        wdata = dict(raw_wdata)
        conn_method = wdata.pop("_connection_method", None)
        sel_scopes = wdata.pop("_selected_scopes", [])
        inc_future = wdata.pop("_include_future_scopes", True)
        created_conn = wdata.pop("_created_connector_id", None)

        raw_completed = row[5] or []
        if isinstance(raw_completed, str):
            raw_completed = json.loads(raw_completed)
        completed_steps = []
        for s in raw_completed:
            try:
                completed_steps.append(WizardStep(s))
            except ValueError:
                pass

        prov = None
        if row[3]:
            try:
                prov = ProviderType(row[3])
            except ValueError:
                try:
                    prov = ProviderType(row[3].lower())
                except ValueError:
                    pass

        step = WizardStep.SELECT_PROVIDER
        if row[4]:
            try:
                step = WizardStep(row[4])
            except ValueError:
                pass

        return WizardSession(
            id=row[0],
            tenant_id=row[1],
            user_id=row[2],
            provider=prov,
            connection_method=conn_method,
            current_step=step,
            completed_steps=completed_steps,
            wizard_data=wdata,
            selected_scopes=sel_scopes,
            include_future_scopes=inc_future,
            status=row[7],
            created_connector_id=created_conn,
            created_at=row[8],
            updated_at=row[9],
        )

    # Async methods
    async def get_async(
        self, entity_id: str, *, tenant_context: TenantContext, session: AsyncSession | None = None
    ) -> WizardSession | None:
        if session is not None:
            return await self._get_with_session(entity_id, tenant_context, session)
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            return await self._get_with_session(entity_id, tenant_context, sess)

    async def _get_with_session(
        self, entity_id: str, tenant_context: TenantContext, session: AsyncSession
    ) -> WizardSession | None:
        query = text("""
            SELECT id, tenant_id, user_id, provider, current_step, completed_steps,
                   wizard_data, status, created_at, updated_at
            FROM wizard_sessions
            WHERE tenant_id = :tid AND id = :id
            LIMIT 1;
        """)
        result = await session.execute(query, {"tid": tenant_context.tenant_id, "id": entity_id})
        row = result.fetchone()
        if not row:
            return None
        return self._row_to_session(row)

    async def get_active_for_user_async(
        self, user_id: str, *, tenant_context: TenantContext, session: AsyncSession | None = None
    ) -> WizardSession | None:
        if session is not None:
            return await self._get_active_with_session(user_id, tenant_context, session)
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            return await self._get_active_with_session(user_id, tenant_context, sess)

    async def _get_active_with_session(
        self, user_id: str, tenant_context: TenantContext, session: AsyncSession
    ) -> WizardSession | None:
        query = text("""
            SELECT id, tenant_id, user_id, provider, current_step, completed_steps,
                   wizard_data, status, created_at, updated_at
            FROM wizard_sessions
            WHERE tenant_id = :tid AND user_id = :uid AND status = 'IN_PROGRESS'
            ORDER BY updated_at DESC
            LIMIT 1;
        """)
        result = await session.execute(query, {"tid": tenant_context.tenant_id, "uid": user_id})
        row = result.fetchone()
        if not row:
            return None
        return self._row_to_session(row)

    async def save_async(
        self, entity: WizardSession, *, tenant_context: TenantContext, session: AsyncSession | None = None
    ) -> WizardSession:
        entity.tenant_id = tenant_context.tenant_id
        if session is not None:
            return await self._save_with_session(entity, tenant_context, session)
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await self._save_with_session(entity, tenant_context, sess)
            await sess.commit()
            return res

    async def _save_with_session(
        self, entity: WizardSession, tenant_context: TenantContext, session: AsyncSession
    ) -> WizardSession:
        wdata = dict(entity.wizard_data or {})
        if entity.connection_method is not None:
            wdata["_connection_method"] = entity.connection_method
        if entity.selected_scopes:
            wdata["_selected_scopes"] = entity.selected_scopes
        wdata["_include_future_scopes"] = entity.include_future_scopes
        if entity.created_connector_id is not None:
            wdata["_created_connector_id"] = entity.created_connector_id

        steps_json = json.dumps([s.value if hasattr(s, "value") else str(s) for s in entity.completed_steps])
        wdata_json = json.dumps(wdata)
        step_val = entity.current_step.value if hasattr(entity.current_step, "value") else str(entity.current_step)
        prov_val = entity.provider.value if (entity.provider and hasattr(entity.provider, "value")) else (str(entity.provider) if entity.provider else None)
        now = datetime.now(UTC)
        entity.updated_at = now

        query = text("""
            INSERT INTO wizard_sessions (
                id, tenant_id, user_id, provider, current_step, completed_steps,
                wizard_data, status, created_at, updated_at
            )
            VALUES (
                :id, :tenant_id, :user_id, :provider, :current_step,
                CAST(:completed_steps AS jsonb), CAST(:wizard_data AS jsonb),
                :status, :created_at, :updated_at
            )
            ON CONFLICT (id) DO UPDATE SET
                provider = EXCLUDED.provider,
                current_step = EXCLUDED.current_step,
                completed_steps = EXCLUDED.completed_steps,
                wizard_data = EXCLUDED.wizard_data,
                status = EXCLUDED.status,
                updated_at = EXCLUDED.updated_at;
        """)
        await session.execute(
            query,
            {
                "id": entity.id,
                "tenant_id": tenant_context.tenant_id,
                "user_id": entity.user_id,
                "provider": prov_val,
                "current_step": step_val,
                "completed_steps": steps_json,
                "wizard_data": wdata_json,
                "status": entity.status,
                "created_at": entity.created_at or now,
                "updated_at": now,
            },
        )
        return entity

    async def list_async(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
        session: AsyncSession | None = None,
    ) -> list[WizardSession]:
        if session is not None:
            return await self._list_with_session(tenant_context, filter_params, limit, offset, session)
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            return await self._list_with_session(tenant_context, filter_params, limit, offset, sess)

    async def _list_with_session(
        self,
        tenant_context: TenantContext,
        filter_params: Any,
        limit: int,
        offset: int,
        session: AsyncSession,
    ) -> list[WizardSession]:
        status_filter = filter_params.get("status") if isinstance(filter_params, dict) else None
        user_filter = filter_params.get("user_id") if isinstance(filter_params, dict) else None

        conditions = ["tenant_id = :tid"]
        params: dict[str, Any] = {"tid": tenant_context.tenant_id, "limit": limit, "offset": offset}

        if status_filter:
            conditions.append("status = :status")
            params["status"] = status_filter
        if user_filter:
            conditions.append("user_id = :uid")
            params["uid"] = user_filter

        where_clause = " AND ".join(conditions)
        query = text(f"""
            SELECT id, tenant_id, user_id, provider, current_step, completed_steps,
                   wizard_data, status, created_at, updated_at
            FROM wizard_sessions
            WHERE {where_clause}
            ORDER BY updated_at DESC
            LIMIT :limit OFFSET :offset;
        """)
        result = await session.execute(query, params)
        rows = result.fetchall()
        return [self._row_to_session(r) for r in rows]

    async def delete_async(
        self, entity_id: str, *, tenant_context: TenantContext, session: AsyncSession | None = None
    ) -> bool:
        if session is not None:
            return await self._delete_with_session(entity_id, tenant_context, session)
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await self._delete_with_session(entity_id, tenant_context, sess)
            await sess.commit()
            return res

    async def _delete_with_session(
        self, entity_id: str, tenant_context: TenantContext, session: AsyncSession
    ) -> bool:
        query = text("DELETE FROM wizard_sessions WHERE tenant_id = :tid AND id = :id;")
        res = await session.execute(query, {"tid": tenant_context.tenant_id, "id": entity_id})
        return res.rowcount > 0

    # Sync interfaces for synchronous callers
    def get(self, entity_id: str, *, tenant_context: TenantContext) -> WizardSession | None:
        return self._run_async(self.get_async(entity_id, tenant_context=tenant_context))

    def save(self, entity: WizardSession, *, tenant_context: TenantContext) -> WizardSession:
        return self._run_async(self.save_async(entity, tenant_context=tenant_context))

    def get_active_for_user(
        self, user_id: str, *, tenant_context: TenantContext
    ) -> WizardSession | None:
        return self._run_async(self.get_active_for_user_async(user_id, tenant_context=tenant_context))

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WizardSession]:
        return self._run_async(
            self.list_async(tenant_context=tenant_context, filter_params=filter_params, limit=limit, offset=offset)
        )

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return self._run_async(self.delete_async(entity_id, tenant_context=tenant_context))

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        res = self.get(entity_id, tenant_context=tenant_context)
        return res is not None


_wizard_repo_instance: Any = None


def get_wizard_repository() -> Any:
    """Dependency provider with production startup guard."""
    global _wizard_repo_instance
    if _wizard_repo_instance is None:
        _wizard_repo_instance = SqlWizardRepository()
        verify_persistence_startup_guard(_wizard_repo_instance)
    return _wizard_repo_instance


def reset_wizard_repository(repo: Any = None) -> Any:
    """Resets repository singleton for test harnesses."""
    global _wizard_repo_instance
    _wizard_repo_instance = repo
    return _wizard_repo_instance or get_wizard_repository()
