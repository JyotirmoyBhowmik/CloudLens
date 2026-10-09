"""Tenant-Aware Repository Interface, Base Abstraction & Real SQL Implementation (Prompt P04).

Enforces:
- Mandatory TenantContext in every repository method signature for tenant-scoped repos.
- TenantRepository protocol and SqlTenantRepository for managing tenant entities.
- Direct PostgreSQL integration with SQLAlchemy 2.0 async.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
import sys
from abc import ABC, abstractmethod
from typing import Any, Generic, Protocol, TypeVar, runtime_checkable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_tenant_session, run_async, verify_persistence_startup_guard
from domain.models.base import CanonicalEntity
from domain.tenant.context import TenantContext, require_tenant_context
from domain.tenant.models import Tenant

logger = logging.getLogger("cloudlens.domain.tenant.repository")

T = TypeVar("T", bound=CanonicalEntity)


class TenantAwareRepository(ABC, Generic[T]):
    """Base repository interface enforcing mandatory TenantContext on every operation.

    Prompt 13 Item 84:
    "Require a tenant context in every repository method. Make a query without
     tenant context fail at build or test time rather than at runtime."
    """

    def _validate_tenant_context(self, tenant_context: TenantContext) -> TenantContext:
        """Validates that the provided context is a valid, non-null TenantContext."""
        return require_tenant_context(tenant_context)

    @abstractmethod
    def get(self, entity_id: str, *, tenant_context: TenantContext) -> T | None:
        """Retrieves a single entity by ID within the tenant scope."""
        raise NotImplementedError

    @abstractmethod
    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[T]:
        """Lists entities belonging strictly to the tenant."""
        raise NotImplementedError

    @abstractmethod
    def save(self, entity: T, *, tenant_context: TenantContext) -> T:
        """Persists or updates an entity, ensuring tenant ownership integrity."""
        raise NotImplementedError

    @abstractmethod
    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        """Deletes an entity within the tenant scope."""
        raise NotImplementedError

    @abstractmethod
    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        """Checks if an entity exists within the tenant scope."""
        raise NotImplementedError


@runtime_checkable
class TenantRepository(Protocol):
    """Protocol for tenant organization entity persistence."""

    async def get(self, tenant_id: str, session: AsyncSession | None = None) -> Tenant | None:
        """Retrieves tenant record by ID."""
        ...

    async def list(self, session: AsyncSession | None = None) -> list[Tenant]:
        """Lists all tenant records."""
        ...

    async def save(self, tenant: Tenant, session: AsyncSession | None = None) -> Tenant:
        """Persists or updates a tenant record."""
        ...

    async def delete(self, tenant_id: str, session: AsyncSession | None = None) -> bool:
        """Deletes a tenant record."""
        ...

    def get_sync(self, tenant_id: str) -> Tenant | None:
        ...

    def list_sync(self) -> list[Tenant]:
        ...

    def save_sync(self, tenant: Tenant) -> Tenant:
        ...

    def delete_sync(self, tenant_id: str) -> bool:
        ...


class SqlTenantRepository:
    """PostgreSQL production implementation for Tenant entities."""

    is_in_memory: bool = False

    def _run_async(self, coro: Any) -> Any:
        return run_async(coro)

    async def get(self, tenant_id: str, session: AsyncSession | None = None) -> Tenant | None:
        if session is not None:
            return await self._get_with_session(tenant_id, session)
        async with get_tenant_session() as sess:
            return await self._get_with_session(tenant_id, sess)

    async def _get_with_session(self, tenant_id: str, session: AsyncSession) -> Tenant | None:
        query = text("""
            SELECT id, name, reporting_currency, created_at, updated_at
            FROM tenants
            WHERE id = :tid
            LIMIT 1;
        """)
        result = await session.execute(query, {"tid": tenant_id})
        row = result.fetchone()
        if not row:
            return None
        return Tenant(
            id=row[0],
            name=row[1],
            reporting_currency=row[2],
            created_at=row[3],
            updated_at=row[4],
        )

    async def list(self, session: AsyncSession | None = None) -> list[Tenant]:
        if session is not None:
            return await self._list_with_session(session)
        async with get_tenant_session() as sess:
            return await self._list_with_session(sess)

    async def _list_with_session(self, session: AsyncSession) -> list[Tenant]:
        query = text("""
            SELECT id, name, reporting_currency, created_at, updated_at
            FROM tenants
            ORDER BY name;
        """)
        result = await session.execute(query)
        rows = result.fetchall()
        return [
            Tenant(
                id=r[0],
                name=r[1],
                reporting_currency=r[2],
                created_at=r[3],
                updated_at=r[4],
            )
            for r in rows
        ]

    async def save(self, tenant: Tenant, session: AsyncSession | None = None) -> Tenant:
        if session is not None:
            return await self._save_with_session(tenant, session)
        async with get_tenant_session() as sess:
            res = await self._save_with_session(tenant, sess)
            await sess.commit()
            return res

    async def _save_with_session(self, tenant: Tenant, session: AsyncSession) -> Tenant:
        query = text("""
            INSERT INTO tenants (id, name, reporting_currency, created_at, updated_at)
            VALUES (:id, :name, :currency, NOW(), NOW())
            ON CONFLICT (id)
            DO UPDATE SET
                name = EXCLUDED.name,
                reporting_currency = EXCLUDED.reporting_currency,
                updated_at = NOW();
        """)
        await session.execute(
            query,
            {
                "id": tenant.id,
                "name": tenant.name,
                "currency": tenant.reporting_currency,
            },
        )
        return tenant

    async def delete(self, tenant_id: str, session: AsyncSession | None = None) -> bool:
        if session is not None:
            return await self._delete_with_session(tenant_id, session)
        async with get_tenant_session() as sess:
            res = await self._delete_with_session(tenant_id, sess)
            await sess.commit()
            return res

    async def _delete_with_session(self, tenant_id: str, session: AsyncSession) -> bool:
        query = text("DELETE FROM tenants WHERE id = :tid;")
        res = await session.execute(query, {"tid": tenant_id})
        return res.rowcount > 0

    def get_sync(self, tenant_id: str) -> Tenant | None:
        return self._run_async(self.get(tenant_id))

    def list_sync(self) -> list[Tenant]:
        return self._run_async(self.list())

    def save_sync(self, tenant: Tenant) -> Tenant:
        return self._run_async(self.save(tenant))

    def delete_sync(self, tenant_id: str) -> bool:
        return self._run_async(self.delete(tenant_id))


_tenant_repo_instance: TenantRepository | None = None


def get_tenant_repository() -> TenantRepository:
    """Dependency provider for TenantRepository."""
    global _tenant_repo_instance
    if _tenant_repo_instance is None:
        _tenant_repo_instance = SqlTenantRepository()
        verify_persistence_startup_guard(_tenant_repo_instance)
    return _tenant_repo_instance


def reset_tenant_repository(repo: TenantRepository | None = None) -> TenantRepository:
    """Resets tenant repository singleton for testing."""
    global _tenant_repo_instance
    _tenant_repo_instance = repo
    return _tenant_repo_instance or get_tenant_repository()
