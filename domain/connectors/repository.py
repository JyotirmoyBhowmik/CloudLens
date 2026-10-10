"""Tenant-Aware Connector Repository and Protocol (Prompt P05).

Enforces:
- Pattern P1: Protocol + SqlConnectorRepository (SQLAlchemy 2.0 async + asyncpg).
- Pattern P3: Injected dependency, zero mutable dict singletons in production.
- Pattern P4: Transactional RLS isolation via get_tenant_session().
- Pattern P6: Startup guard preventing InMemory repository outside development.
- Full connector registration and capability profile persistence across restarts.
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
from domain.connectors.models import ConnectorEntity
from domain.models.enums import ConnectorLifecycleState, ProviderType
from domain.tenant.context import TenantContext

logger = logging.getLogger("cloudlens.domain.connectors.repository")


@runtime_checkable
class ConnectorRepository(Protocol):
    """Authoritative protocol for Cloud Connector persistence."""

    def get(self, connector_id: str, *, tenant_context: TenantContext) -> ConnectorEntity | None:
        ...

    def list(
        self,
        *,
        tenant_context: TenantContext,
        provider: ProviderType | None = None,
        lifecycle_state: ConnectorLifecycleState | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ConnectorEntity]:
        ...

    def save(self, entity: ConnectorEntity, *, tenant_context: TenantContext) -> ConnectorEntity:
        ...

    def update_lifecycle_state(
        self, connector_id: str, new_state: ConnectorLifecycleState, *, tenant_context: TenantContext
    ) -> bool:
        ...

    def update_capabilities(
        self,
        connector_id: str,
        declared: list[str] | None = None,
        verified: list[str] | None = None,
        *,
        tenant_context: TenantContext,
    ) -> bool:
        ...

    def delete(self, connector_id: str, *, tenant_context: TenantContext) -> bool:
        ...

    async def get_async(
        self, connector_id: str, *, tenant_context: TenantContext, session: AsyncSession | None = None
    ) -> ConnectorEntity | None:
        ...

    async def save_async(
        self, entity: ConnectorEntity, *, tenant_context: TenantContext, session: AsyncSession | None = None
    ) -> ConnectorEntity:
        ...


class SqlConnectorRepository:
    """PostgreSQL production implementation for Connector entities with RLS."""

    is_in_memory: bool = False

    def _run_async(self, coro: Any) -> Any:
        return run_async(coro)

    def _row_to_entity(self, row: Any) -> ConnectorEntity:
        prov_val = row[3]
        try:
            prov = ProviderType(prov_val)
        except ValueError:
            try:
                prov = ProviderType(prov_val.lower())
            except ValueError:
                prov = prov_val

        state_val = row[4]
        try:
            state = ConnectorLifecycleState(state_val)
        except ValueError:
            state = state_val

        raw_decl = row[6] or []
        if isinstance(raw_decl, str):
            raw_decl = json.loads(raw_decl)

        raw_ver = row[7] or []
        if isinstance(raw_ver, str):
            raw_ver = json.loads(raw_ver)

        raw_cfg = row[8] or {}
        if isinstance(raw_cfg, str):
            raw_cfg = json.loads(raw_cfg)

        return ConnectorEntity(
            id=row[0],
            tenant_id=row[1],
            name=row[2],
            provider=prov,
            lifecycle_state=state,
            credential_profile_id=row[5],
            declared_capabilities=raw_decl,
            verified_capabilities=raw_ver,
            config=raw_cfg,
            created_at=row[9],
            updated_at=row[10],
        )

    async def get_async(
        self, connector_id: str, *, tenant_context: TenantContext, session: AsyncSession | None = None
    ) -> ConnectorEntity | None:
        if session is not None:
            return await self._get_with_session(connector_id, tenant_context, session)
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            return await self._get_with_session(connector_id, tenant_context, sess)

    async def _get_with_session(
        self, connector_id: str, tenant_context: TenantContext, session: AsyncSession
    ) -> ConnectorEntity | None:
        query = text("""
            SELECT id, tenant_id, name, provider, lifecycle_state, credential_profile_id,
                   declared_capabilities, verified_capabilities, config, created_at, updated_at
            FROM connectors
            WHERE tenant_id = :tid AND id = :id
            LIMIT 1;
        """)
        res = await session.execute(query, {"tid": tenant_context.tenant_id, "id": connector_id})
        row = res.fetchone()
        return self._row_to_entity(row) if row else None

    async def save_async(
        self, entity: ConnectorEntity, *, tenant_context: TenantContext, session: AsyncSession | None = None
    ) -> ConnectorEntity:
        entity.tenant_id = tenant_context.tenant_id
        if session is not None:
            return await self._save_with_session(entity, tenant_context, session)
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await self._save_with_session(entity, tenant_context, sess)
            await sess.commit()
            return res

    async def _save_with_session(
        self, entity: ConnectorEntity, tenant_context: TenantContext, session: AsyncSession
    ) -> ConnectorEntity:
        now = datetime.now(UTC)
        entity.updated_at = now
        prov_val = entity.provider.value if hasattr(entity.provider, "value") else str(entity.provider)
        state_val = entity.lifecycle_state.value if hasattr(entity.lifecycle_state, "value") else str(entity.lifecycle_state)
        decl_json = json.dumps(entity.declared_capabilities)
        ver_json = json.dumps(entity.verified_capabilities)
        cfg_json = json.dumps(entity.config)

        query = text("""
            INSERT INTO connectors (
                id, tenant_id, name, provider, lifecycle_state, credential_profile_id,
                declared_capabilities, verified_capabilities, config, created_at, updated_at
            )
            VALUES (
                :id, :tenant_id, :name, :provider, :lifecycle_state, :credential_profile_id,
                CAST(:declared_capabilities AS jsonb), CAST(:verified_capabilities AS jsonb),
                CAST(:config AS jsonb), :created_at, :updated_at
            )
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                provider = EXCLUDED.provider,
                lifecycle_state = EXCLUDED.lifecycle_state,
                credential_profile_id = EXCLUDED.credential_profile_id,
                declared_capabilities = EXCLUDED.declared_capabilities,
                verified_capabilities = EXCLUDED.verified_capabilities,
                config = EXCLUDED.config,
                updated_at = EXCLUDED.updated_at;
        """)
        await session.execute(
            query,
            {
                "id": entity.id,
                "tenant_id": tenant_context.tenant_id,
                "name": entity.name,
                "provider": prov_val,
                "lifecycle_state": state_val,
                "credential_profile_id": entity.credential_profile_id,
                "declared_capabilities": decl_json,
                "verified_capabilities": ver_json,
                "config": cfg_json,
                "created_at": entity.created_at or now,
                "updated_at": now,
            },
        )
        return entity

    async def list_async(
        self,
        *,
        tenant_context: TenantContext,
        provider: ProviderType | None = None,
        lifecycle_state: ConnectorLifecycleState | None = None,
        limit: int = 50,
        offset: int = 0,
        session: AsyncSession | None = None,
    ) -> list[ConnectorEntity]:
        if session is not None:
            return await self._list_with_session(tenant_context, provider, lifecycle_state, limit, offset, session)
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            return await self._list_with_session(tenant_context, provider, lifecycle_state, limit, offset, sess)

    async def _list_with_session(
        self,
        tenant_context: TenantContext,
        provider: ProviderType | None,
        lifecycle_state: ConnectorLifecycleState | None,
        limit: int,
        offset: int,
        session: AsyncSession,
    ) -> list[ConnectorEntity]:
        conditions = ["tenant_id = :tid"]
        params: dict[str, Any] = {"tid": tenant_context.tenant_id, "limit": limit, "offset": offset}

        if provider:
            prov_val = provider.value if hasattr(provider, "value") else str(provider)
            conditions.append("provider = :prov")
            params["prov"] = prov_val
        if lifecycle_state:
            state_val = lifecycle_state.value if hasattr(lifecycle_state, "value") else str(lifecycle_state)
            conditions.append("lifecycle_state = :state")
            params["state"] = state_val
        else:
            conditions.append("lifecycle_state != 'DELETED'")

        where_clause = " AND ".join(conditions)
        query = text(f"""
            SELECT id, tenant_id, name, provider, lifecycle_state, credential_profile_id,
                   declared_capabilities, verified_capabilities, config, created_at, updated_at
            FROM connectors
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset;
        """)
        res = await session.execute(query, params)
        rows = res.fetchall()
        return [self._row_to_entity(r) for r in rows]

    async def update_lifecycle_state_async(
        self,
        connector_id: str,
        new_state: ConnectorLifecycleState,
        *,
        tenant_context: TenantContext,
        session: AsyncSession | None = None,
    ) -> bool:
        state_val = new_state.value if hasattr(new_state, "value") else str(new_state)
        query = text("""
            UPDATE connectors
            SET lifecycle_state = :state, updated_at = NOW()
            WHERE tenant_id = :tid AND id = :id;
        """)
        params = {"tid": tenant_context.tenant_id, "id": connector_id, "state": state_val}

        if session is not None:
            res = await session.execute(query, params)
            return res.rowcount > 0

        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(query, params)
            await sess.commit()
            return res.rowcount > 0

    async def update_capabilities_async(
        self,
        connector_id: str,
        declared: list[str] | None = None,
        verified: list[str] | None = None,
        *,
        tenant_context: TenantContext,
        session: AsyncSession | None = None,
    ) -> bool:
        sets = ["updated_at = NOW()"]
        params: dict[str, Any] = {"tid": tenant_context.tenant_id, "id": connector_id}

        if declared is not None:
            sets.append("declared_capabilities = CAST(:decl AS jsonb)")
            params["decl"] = json.dumps(declared)
        if verified is not None:
            sets.append("verified_capabilities = CAST(:ver AS jsonb)")
            params["ver"] = json.dumps(verified)

        set_clause = ", ".join(sets)
        query = text(f"""
            UPDATE connectors
            SET {set_clause}
            WHERE tenant_id = :tid AND id = :id;
        """)

        if session is not None:
            res = await session.execute(query, params)
            return res.rowcount > 0

        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(query, params)
            await sess.commit()
            return res.rowcount > 0

    async def delete_async(
        self, connector_id: str, *, tenant_context: TenantContext, session: AsyncSession | None = None
    ) -> bool:
        query = text("DELETE FROM connectors WHERE tenant_id = :tid AND id = :id;")
        params = {"tid": tenant_context.tenant_id, "id": connector_id}

        if session is not None:
            res = await session.execute(query, params)
            return res.rowcount > 0

        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(query, params)
            await sess.commit()
            return res.rowcount > 0

    # Sync interfaces
    def get(self, connector_id: str, *, tenant_context: TenantContext) -> ConnectorEntity | None:
        return self._run_async(self.get_async(connector_id, tenant_context=tenant_context))

    def list(
        self,
        *,
        tenant_context: TenantContext,
        provider: ProviderType | None = None,
        lifecycle_state: ConnectorLifecycleState | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ConnectorEntity]:
        return self._run_async(
            self.list_async(
                tenant_context=tenant_context,
                provider=provider,
                lifecycle_state=lifecycle_state,
                limit=limit,
                offset=offset,
            )
        )

    def save(self, entity: ConnectorEntity, *, tenant_context: TenantContext) -> ConnectorEntity:
        return self._run_async(self.save_async(entity, tenant_context=tenant_context))

    def update_lifecycle_state(
        self, connector_id: str, new_state: ConnectorLifecycleState, *, tenant_context: TenantContext
    ) -> bool:
        return self._run_async(
            self.update_lifecycle_state_async(connector_id, new_state, tenant_context=tenant_context)
        )

    def update_capabilities(
        self,
        connector_id: str,
        declared: list[str] | None = None,
        verified: list[str] | None = None,
        *,
        tenant_context: TenantContext,
    ) -> bool:
        return self._run_async(
            self.update_capabilities_async(
                connector_id, declared=declared, verified=verified, tenant_context=tenant_context
            )
        )

    def delete(self, connector_id: str, *, tenant_context: TenantContext) -> bool:
        return self._run_async(self.delete_async(connector_id, tenant_context=tenant_context))


_connector_repo_instance: Any = None


def get_connector_repository() -> Any:
    """Dependency provider with production startup guard."""
    global _connector_repo_instance
    if _connector_repo_instance is None:
        _connector_repo_instance = SqlConnectorRepository()
        verify_persistence_startup_guard(_connector_repo_instance)
    return _connector_repo_instance


def reset_connector_repository(repo: Any = None) -> Any:
    global _connector_repo_instance
    _connector_repo_instance = repo
    return _connector_repo_instance or get_connector_repository()


__all__ = [
    "ConnectorRepository",
    "SqlConnectorRepository",
    "get_connector_repository",
    "reset_connector_repository",
]
