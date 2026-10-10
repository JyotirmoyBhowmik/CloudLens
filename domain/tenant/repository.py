"""Tenant Entity Repository (Prompt P04 / Prompt P12).

Provides PostgreSQL and In-Memory persistence adapters for Tenant entities,
enforcing mechanical isolation and startup verification.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Generic, Protocol, TypeVar, runtime_checkable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_tenant_session, run_async, verify_persistence_startup_guard
from domain.tenant.context import TenantContext
from domain.tenant.models import Tenant, TenantStatus, TenantType

logger = logging.getLogger(__name__)

T = TypeVar("T")


class TenantAwareRepository(ABC, Generic[T]):
    """Abstract base repository enforcing mechanical tenant boundary isolation (Item 84)."""

    def __init__(self, tenant_id: str | None = None) -> None:
        self._tenant_id = tenant_id

    @property
    def tenant_id(self) -> str | None:
        return self._tenant_id

    def _validate_tenant(self, tenant_context: TenantContext) -> None:
        if not tenant_context or not tenant_context.tenant_id:
            from domain.models.exceptions import MissingTenantContextException

            raise MissingTenantContextException("Missing required tenant context in repository call.")
        if self._tenant_id and self._tenant_id != tenant_context.tenant_id:
            from domain.models.exceptions import CrossTenantViolationException

            raise CrossTenantViolationException(
                f"Repository bound to tenant '{self._tenant_id}' cannot execute for tenant '{tenant_context.tenant_id}'."
            )

    @abstractmethod
    def get(self, entity_id: str, *, tenant_context: TenantContext) -> T | None:
        """Retrieves an entity within the tenant scope."""
        raise NotImplementedError

    @abstractmethod
    def list(self, *, tenant_context: TenantContext) -> list[T]:
        """Lists all entities within the tenant scope."""
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
    """Protocol for tenant organization entity persistence (Prompt P12)."""

    async def get(self, tenant_id: str, session: AsyncSession | None = None) -> Tenant | None:
        """Retrieves tenant record by ID."""
        ...

    async def get_by_code(self, code: str, session: AsyncSession | None = None) -> Tenant | None:
        """Retrieves tenant record by unique code."""
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

    def get_by_code_sync(self, code: str) -> Tenant | None:
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

    def _row_to_entity(self, row: Any) -> Tenant:
        return Tenant(
            id=row[0],
            name=row[1],
            reporting_currency=row[2],
            created_at=row[3],
            updated_at=row[4],
            code=row[5] or row[0].replace("tenant-", "").upper(),
            type=TenantType(row[6]) if row[6] else TenantType.PRODUCTION,
            fiscal_year_start=row[7] if row[7] is not None else 1,
            iana_timezone=row[8] or "UTC",
            retention_profile=row[9] or "STANDARD",
            status=TenantStatus(row[10]) if row[10] else TenantStatus.ACTIVE,
            suspension_reason=row[11],
        )

    async def get(self, tenant_id: str, session: AsyncSession | None = None) -> Tenant | None:
        if session is not None:
            return await self._get_with_session(tenant_id, session)
        async with get_tenant_session() as sess:
            return await self._get_with_session(tenant_id, sess)

    async def _get_with_session(self, tenant_id: str, session: AsyncSession) -> Tenant | None:
        query = text("""
            SELECT id, name, reporting_currency, created_at, updated_at,
                   code, type, fiscal_year_start, iana_timezone, retention_profile,
                   status, suspension_reason
            FROM tenants
            WHERE id = :tid
            LIMIT 1;
        """)
        result = await session.execute(query, {"tid": tenant_id})
        row = result.fetchone()
        if not row:
            return None
        return self._row_to_entity(row)

    async def get_by_code(self, code: str, session: AsyncSession | None = None) -> Tenant | None:
        if session is not None:
            return await self._get_by_code_with_session(code, session)
        async with get_tenant_session() as sess:
            return await self._get_by_code_with_session(code, sess)

    async def _get_by_code_with_session(self, code: str, session: AsyncSession) -> Tenant | None:
        query = text("""
            SELECT id, name, reporting_currency, created_at, updated_at,
                   code, type, fiscal_year_start, iana_timezone, retention_profile,
                   status, suspension_reason
            FROM tenants
            WHERE UPPER(code) = :code
            LIMIT 1;
        """)
        result = await session.execute(query, {"code": code.strip().upper()})
        row = result.fetchone()
        if not row:
            return None
        return self._row_to_entity(row)

    async def list(self, session: AsyncSession | None = None) -> list[Tenant]:
        if session is not None:
            return await self._list_with_session(session)
        async with get_tenant_session() as sess:
            return await self._list_with_session(sess)

    async def _list_with_session(self, session: AsyncSession) -> list[Tenant]:
        query = text("""
            SELECT id, name, reporting_currency, created_at, updated_at,
                   code, type, fiscal_year_start, iana_timezone, retention_profile,
                   status, suspension_reason
            FROM tenants
            ORDER BY name;
        """)
        result = await session.execute(query)
        rows = result.fetchall()
        return [self._row_to_entity(r) for r in rows]

    async def save(self, tenant: Tenant, session: AsyncSession | None = None) -> Tenant:
        if session is not None:
            return await self._save_with_session(tenant, session)
        async with get_tenant_session() as sess:
            res = await self._save_with_session(tenant, sess)
            await sess.commit()
            return res

    async def _save_with_session(self, tenant: Tenant, session: AsyncSession) -> Tenant:
        query = text("""
            INSERT INTO tenants (
                id, code, name, type, reporting_currency,
                fiscal_year_start, iana_timezone, retention_profile,
                status, suspension_reason, created_at, updated_at
            )
            VALUES (
                :id, :code, :name, :type, :currency,
                :fiscal_year_start, :iana_timezone, :retention_profile,
                :status, :suspension_reason, NOW(), NOW()
            )
            ON CONFLICT (id)
            DO UPDATE SET
                code = EXCLUDED.code,
                name = EXCLUDED.name,
                type = EXCLUDED.type,
                reporting_currency = EXCLUDED.reporting_currency,
                fiscal_year_start = EXCLUDED.fiscal_year_start,
                iana_timezone = EXCLUDED.iana_timezone,
                retention_profile = EXCLUDED.retention_profile,
                status = EXCLUDED.status,
                suspension_reason = EXCLUDED.suspension_reason,
                updated_at = NOW();
        """)
        await session.execute(
            query,
            {
                "id": tenant.id,
                "code": tenant.code or tenant.id.replace("tenant-", "").upper(),
                "name": tenant.name,
                "type": tenant.type.value if hasattr(tenant.type, "value") else str(tenant.type),
                "currency": tenant.reporting_currency,
                "fiscal_year_start": tenant.fiscal_year_start,
                "iana_timezone": tenant.iana_timezone,
                "retention_profile": tenant.retention_profile,
                "status": tenant.status.value if hasattr(tenant.status, "value") else str(tenant.status),
                "suspension_reason": tenant.suspension_reason,
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

    def get_by_code_sync(self, code: str) -> Tenant | None:
        return self._run_async(self.get_by_code(code))

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
