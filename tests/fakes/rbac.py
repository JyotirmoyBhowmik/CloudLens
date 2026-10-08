"""In-memory fake for RBAC scope grants and custom roles unit testing."""

from __future__ import annotations

from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

from domain.rbac.models import RoleDefinition, ScopeGrant


class InMemoryRBACRepository:
    """In-memory test fake for RBAC repository."""

    is_in_memory: bool = True

    def __init__(self) -> None:
        self._grants: dict[str, ScopeGrant] = {}
        self._custom_roles: dict[tuple[str, str], RoleDefinition] = {}

    async def get_scope_grant(self, grant_id: str, session: AsyncSession | None = None) -> ScopeGrant | None:
        return self._grants.get(grant_id)

    async def save_scope_grant(self, grant: ScopeGrant, session: AsyncSession | None = None) -> ScopeGrant:
        self._grants[grant.id] = grant
        return grant

    async def list_scope_grants(
        self, tenant_id: str | None = None, grantee_id: str | None = None, session: AsyncSession | None = None
    ) -> list[ScopeGrant]:
        grants = list(self._grants.values())
        if tenant_id and tenant_id != "*":
            grants = [g for g in grants if g.tenant_id in (tenant_id, "*")]
        if grantee_id:
            grants = [g for g in grants if g.grantee_id == grantee_id]
        return grants

    async def delete_scope_grant(self, grant_id: str, session: AsyncSession | None = None) -> bool:
        if grant_id in self._grants:
            del self._grants[grant_id]
            return True
        return False

    async def get_custom_role(
        self, tenant_id: str, role_code: str, session: AsyncSession | None = None
    ) -> RoleDefinition | None:
        return self._custom_roles.get((tenant_id, role_code))

    async def save_custom_role(
        self, role_def: RoleDefinition, session: AsyncSession | None = None
    ) -> RoleDefinition:
        tenant_id = role_def.tenant_id or "global"
        self._custom_roles[(tenant_id, role_def.code)] = role_def
        return role_def

    async def list_custom_roles(
        self, tenant_id: str, session: AsyncSession | None = None
    ) -> list[RoleDefinition]:
        return [r for (tid, _), r in self._custom_roles.items() if tid == tenant_id]

    async def delete_custom_role(
        self, tenant_id: str, role_code: str, session: AsyncSession | None = None
    ) -> bool:
        return bool(self._custom_roles.pop((tenant_id, role_code), None))

    def get_scope_grant_sync(self, grant_id: str) -> ScopeGrant | None:
        return self._grants.get(grant_id)

    def save_scope_grant_sync(self, grant: ScopeGrant) -> ScopeGrant:
        self._grants[grant.id] = grant
        return grant

    def list_scope_grants_sync(
        self, tenant_id: str | None = None, grantee_id: str | None = None
    ) -> list[ScopeGrant]:
        grants = list(self._grants.values())
        if tenant_id and tenant_id != "*":
            grants = [g for g in grants if g.tenant_id in (tenant_id, "*")]
        if grantee_id:
            grants = [g for g in grants if g.grantee_id == grantee_id]
        return grants

    def delete_scope_grant_sync(self, grant_id: str) -> bool:
        if grant_id in self._grants:
            del self._grants[grant_id]
            return True
        return False

    def get_custom_role_sync(self, tenant_id: str, role_code: str) -> RoleDefinition | None:
        return self._custom_roles.get((tenant_id, role_code))

    def save_custom_role_sync(self, role_def: RoleDefinition) -> RoleDefinition:
        tenant_id = role_def.tenant_id or "global"
        self._custom_roles[(tenant_id, role_def.code)] = role_def
        return role_def

    def list_custom_roles_sync(self, tenant_id: str) -> list[RoleDefinition]:
        return [r for (tid, _), r in self._custom_roles.items() if tid == tenant_id]

    def delete_custom_role_sync(self, tenant_id: str, role_code: str) -> bool:
        return bool(self._custom_roles.pop((tenant_id, role_code), None))
