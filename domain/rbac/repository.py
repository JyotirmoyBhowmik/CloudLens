"""RBAC and Scope Grant SQL Repository and Protocol (Prompt P04).

Enforces:
- Pattern P1: Protocol + SqlRBACRepository (SQLAlchemy 2.0 async).
- Pattern P3: Injected dependency, zero mutable dict singletons as sources of truth.
- Pattern P4: Transactional RLS isolation via get_tenant_session().
- Pattern P6: Startup guard preventing InMemory repository outside development.
- Persistent multidimensional scope grants (role_grants) and tenant custom roles (custom_roles).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import os
import sys
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_tenant_session
from domain.models.enums import FinancialSensitivity, GrantEffect, GranteeType
from domain.rbac.models import RoleDefinition, ScopeGrant

logger = logging.getLogger("cloudlens.domain.rbac.repository")


@runtime_checkable
class RBACRepository(Protocol):
    """Authoritative protocol for RBAC scope grants and custom roles."""

    # Scope Grants
    async def get_scope_grant(self, grant_id: str, session: AsyncSession | None = None) -> ScopeGrant | None:
        ...

    async def save_scope_grant(self, grant: ScopeGrant, session: AsyncSession | None = None) -> ScopeGrant:
        ...

    async def list_scope_grants(
        self, tenant_id: str | None = None, grantee_id: str | None = None, session: AsyncSession | None = None
    ) -> list[ScopeGrant]:
        ...

    async def delete_scope_grant(self, grant_id: str, session: AsyncSession | None = None) -> bool:
        ...

    # Custom Roles
    async def get_custom_role(
        self, tenant_id: str, role_code: str, session: AsyncSession | None = None
    ) -> RoleDefinition | None:
        ...

    async def save_custom_role(
        self, role_def: RoleDefinition, session: AsyncSession | None = None
    ) -> RoleDefinition:
        ...

    async def list_custom_roles(
        self, tenant_id: str, session: AsyncSession | None = None
    ) -> list[RoleDefinition]:
        ...

    async def delete_custom_role(
        self, tenant_id: str, role_code: str, session: AsyncSession | None = None
    ) -> bool:
        ...

    # Synchronous helpers for sync execution contexts
    def get_scope_grant_sync(self, grant_id: str) -> ScopeGrant | None:
        ...

    def save_scope_grant_sync(self, grant: ScopeGrant) -> ScopeGrant:
        ...

    def list_scope_grants_sync(
        self, tenant_id: str | None = None, grantee_id: str | None = None
    ) -> list[ScopeGrant]:
        ...

    def delete_scope_grant_sync(self, grant_id: str) -> bool:
        ...

    def get_custom_role_sync(self, tenant_id: str, role_code: str) -> RoleDefinition | None:
        ...

    def save_custom_role_sync(self, role_def: RoleDefinition) -> RoleDefinition:
        ...

    def list_custom_roles_sync(self, tenant_id: str) -> list[RoleDefinition]:
        ...

    def delete_custom_role_sync(self, tenant_id: str, role_code: str) -> bool:
        ...


class SqlRBACRepository:
    """PostgreSQL production implementation for RBAC scope grants and custom roles."""

    is_in_memory: bool = False

    def _run_async(self, coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro)).result()

    # -------------------------------------------------------------------------
    # Scope Grants
    # -------------------------------------------------------------------------

    async def get_scope_grant(self, grant_id: str, session: AsyncSession | None = None) -> ScopeGrant | None:
        if session is not None:
            return await self._get_grant_with_session(grant_id, session)
        async with get_tenant_session() as sess:
            return await self._get_grant_with_session(grant_id, sess)

    async def _get_grant_with_session(self, grant_id: str, session: AsyncSession) -> ScopeGrant | None:
        await session.execute(text("SELECT set_config('cloudlens.bypass_rls', 'on', true);"))
        query = text("""
            SELECT id, tenant_id, grantee_type, grantee_id, effect, data, created_at, updated_at
            FROM role_grants
            WHERE id = :gid
            LIMIT 1;
        """)
        result = await session.execute(query, {"gid": grant_id})
        row = result.fetchone()
        if not row:
            return None
        return self._row_to_grant(row)

    def _row_to_grant(self, row: Any) -> ScopeGrant:
        raw_data = row[5]
        data = raw_data if isinstance(raw_data, dict) else json.loads(raw_data or "{}")
        grantee_type = GranteeType(row[2]) if isinstance(row[2], str) else row[2]
        effect = GrantEffect(row[4]) if isinstance(row[4], str) else row[4]

        # Financial sensitivity from data if present
        raw_fin = data.get("financial_sensitivity", "FULL_FINANCIAL_DETAIL")
        fin_sens = FinancialSensitivity(raw_fin) if isinstance(raw_fin, str) else raw_fin

        return ScopeGrant(
            id=row[0],
            tenant_id=row[1],
            grantee_type=grantee_type,
            grantee_id=row[3],
            effect=effect,
            providers=data.get("providers", []),
            account_ids=data.get("account_ids", []),
            hierarchy_subtree_roots=data.get("hierarchy_subtree_roots", []),
            cascade_hierarchy=data.get("cascade_hierarchy", True),
            project_ids=data.get("project_ids", []),
            cost_centre_ids=data.get("cost_centre_ids", data.get("cost_centre_codes", [])),
            business_unit_ids=data.get("business_unit_ids", data.get("business_unit_codes", [])),
            financial_sensitivity=fin_sens,
            is_administrative=data.get("is_administrative", data.get("administrative", False)),
            resource_exceptions=data.get("resource_exceptions", data.get("resource_exceptions_allow", [])),
            is_active=data.get("is_active", True),
            created_at=row[6],
            updated_at=row[7],
        )

    async def save_scope_grant(self, grant: ScopeGrant, session: AsyncSession | None = None) -> ScopeGrant:
        if session is not None:
            return await self._save_grant_with_session(grant, session)
        async with get_tenant_session(grant.tenant_id) as sess:
            res = await self._save_grant_with_session(grant, sess)
            await sess.commit()
            return res

    async def _save_grant_with_session(self, grant: ScopeGrant, session: AsyncSession) -> ScopeGrant:
        await session.execute(text("SELECT set_config('cloudlens.bypass_rls', 'on', true);"))
        cc_ids = getattr(grant, "cost_centre_ids", getattr(grant, "cost_centre_codes", []))
        bu_ids = getattr(grant, "business_unit_ids", getattr(grant, "business_unit_codes", []))
        is_admin = getattr(grant, "is_administrative", getattr(grant, "administrative", False))
        res_exc = getattr(grant, "resource_exceptions", getattr(grant, "resource_exceptions_allow", []))
        data_dict = {
            "providers": grant.providers,
            "account_ids": grant.account_ids,
            "hierarchy_subtree_roots": grant.hierarchy_subtree_roots,
            "cascade_hierarchy": grant.cascade_hierarchy,
            "project_ids": grant.project_ids,
            "cost_centre_codes": cc_ids,
            "business_unit_codes": bu_ids,
            "cost_centre_ids": cc_ids,
            "business_unit_ids": bu_ids,
            "financial_sensitivity": grant.financial_sensitivity.value if hasattr(grant.financial_sensitivity, "value") else str(grant.financial_sensitivity),
            "is_administrative": is_admin,
            "administrative": is_admin,
            "resource_exceptions": res_exc,
            "resource_exceptions_allow": res_exc,
            "resource_exceptions_deny": getattr(grant, "resource_exceptions_deny", []),
            "is_active": grant.is_active,
        }
        query = text("""
            INSERT INTO role_grants (id, tenant_id, grantee_type, grantee_id, effect, data, created_at, updated_at)
            VALUES (:id, :tenant_id, :grantee_type, :grantee_id, :effect, CAST(:data AS jsonb), NOW(), NOW())
            ON CONFLICT (id)
            DO UPDATE SET
                grantee_type = EXCLUDED.grantee_type,
                grantee_id = EXCLUDED.grantee_id,
                effect = EXCLUDED.effect,
                data = EXCLUDED.data,
                updated_at = NOW();
        """)
        await session.execute(
            query,
            {
                "id": grant.id,
                "tenant_id": grant.tenant_id,
                "grantee_type": grant.grantee_type.value if hasattr(grant.grantee_type, "value") else str(grant.grantee_type),
                "grantee_id": grant.grantee_id,
                "effect": grant.effect.value if hasattr(grant.effect, "value") else str(grant.effect),
                "data": json.dumps(data_dict),
            },
        )
        return grant

    async def list_scope_grants(
        self, tenant_id: str | None = None, grantee_id: str | None = None, session: AsyncSession | None = None
    ) -> list[ScopeGrant]:
        if session is not None:
            return await self._list_grants_with_session(tenant_id, grantee_id, session)
        async with get_tenant_session(tenant_id) as sess:
            return await self._list_grants_with_session(tenant_id, grantee_id, sess)

    async def _list_grants_with_session(
        self, tenant_id: str | None, grantee_id: str | None, session: AsyncSession
    ) -> list[ScopeGrant]:
        if not tenant_id:
            await session.execute(text("SELECT set_config('cloudlens.bypass_rls', 'on', true);"))
        clauses = []
        params: dict[str, Any] = {}
        if tenant_id and tenant_id != "*":
            clauses.append("(tenant_id = :tid OR tenant_id = '*')")
            params["tid"] = tenant_id
        if grantee_id:
            clauses.append("grantee_id = :gid")
            params["gid"] = grantee_id

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = text(f"""
            SELECT id, tenant_id, grantee_type, grantee_id, effect, data, created_at, updated_at
            FROM role_grants
            {where_sql}
            ORDER BY created_at DESC;
        """)
        result = await session.execute(query, params)
        rows = result.fetchall()
        return [self._row_to_grant(r) for r in rows]

    async def delete_scope_grant(self, grant_id: str, session: AsyncSession | None = None) -> bool:
        if session is not None:
            return await self._delete_grant_with_session(grant_id, session)
        async with get_tenant_session() as sess:
            res = await self._delete_grant_with_session(grant_id, sess)
            await sess.commit()
            return res

    async def _delete_grant_with_session(self, grant_id: str, session: AsyncSession) -> bool:
        await session.execute(text("SELECT set_config('cloudlens.bypass_rls', 'on', true);"))
        query = text("DELETE FROM role_grants WHERE id = :gid;")
        res = await session.execute(query, {"gid": grant_id})
        return res.rowcount > 0

    # -------------------------------------------------------------------------
    # Custom Roles
    # -------------------------------------------------------------------------

    async def get_custom_role(
        self, tenant_id: str, role_code: str, session: AsyncSession | None = None
    ) -> RoleDefinition | None:
        if session is not None:
            return await self._get_custom_role_with_session(tenant_id, role_code, session)
        async with get_tenant_session(tenant_id) as sess:
            return await self._get_custom_role_with_session(tenant_id, role_code, sess)

    async def _get_custom_role_with_session(
        self, tenant_id: str, role_code: str, session: AsyncSession
    ) -> RoleDefinition | None:
        query = text("""
            SELECT tenant_id, code, display_name, description, allowed_permissions, max_scope, requires_mfa, created_at, updated_at
            FROM custom_roles
            WHERE tenant_id = :tid AND code = :code
            LIMIT 1;
        """)
        result = await session.execute(query, {"tid": tenant_id, "code": role_code})
        row = result.fetchone()
        if not row:
            return None
        return self._row_to_custom_role(row)

    def _row_to_custom_role(self, row: Any) -> RoleDefinition:
        raw_perms = row[4]
        perms = raw_perms if isinstance(raw_perms, list) else json.loads(raw_perms or "[]")
        return RoleDefinition(
            id=f"role-{row[0]}-{row[1].lower()}",
            tenant_id=row[0],
            code=row[1],
            display_name=row[2],
            description=row[3] or "",
            allowed_permissions=perms,
            is_built_in=False,
            max_scope=row[5] or "SCOPE",
            requires_mfa=row[6] or False,
            created_at=row[7],
            updated_at=row[8],
        )

    async def save_custom_role(
        self, role_def: RoleDefinition, session: AsyncSession | None = None
    ) -> RoleDefinition:
        if session is not None:
            return await self._save_custom_role_with_session(role_def, session)
        async with get_tenant_session(role_def.tenant_id or "global") as sess:
            res = await self._save_custom_role_with_session(role_def, sess)
            await sess.commit()
            return res

    async def _save_custom_role_with_session(
        self, role_def: RoleDefinition, session: AsyncSession
    ) -> RoleDefinition:
        tenant_id = role_def.tenant_id or "global"
        query = text("""
            INSERT INTO custom_roles (
                tenant_id, code, display_name, description, allowed_permissions,
                max_scope, requires_mfa, created_at, updated_at
            )
            VALUES (
                :tenant_id, :code, :display_name, :description, CAST(:perms AS jsonb),
                :max_scope, :requires_mfa, NOW(), NOW()
            )
            ON CONFLICT (tenant_id, code)
            DO UPDATE SET
                display_name = EXCLUDED.display_name,
                description = EXCLUDED.description,
                allowed_permissions = EXCLUDED.allowed_permissions,
                max_scope = EXCLUDED.max_scope,
                requires_mfa = EXCLUDED.requires_mfa,
                updated_at = NOW();
        """)
        await session.execute(
            query,
            {
                "tenant_id": tenant_id,
                "code": role_def.code,
                "display_name": role_def.display_name,
                "description": role_def.description,
                "perms": json.dumps(role_def.allowed_permissions),
                "max_scope": role_def.max_scope,
                "requires_mfa": role_def.requires_mfa,
            },
        )
        return role_def

    async def list_custom_roles(
        self, tenant_id: str, session: AsyncSession | None = None
    ) -> list[RoleDefinition]:
        if session is not None:
            return await self._list_custom_roles_with_session(tenant_id, session)
        async with get_tenant_session(tenant_id) as sess:
            return await self._list_custom_roles_with_session(tenant_id, sess)

    async def _list_custom_roles_with_session(
        self, tenant_id: str, session: AsyncSession
    ) -> list[RoleDefinition]:
        query = text("""
            SELECT tenant_id, code, display_name, description, allowed_permissions, max_scope, requires_mfa, created_at, updated_at
            FROM custom_roles
            WHERE tenant_id = :tid
            ORDER BY code;
        """)
        result = await session.execute(query, {"tid": tenant_id})
        rows = result.fetchall()
        return [self._row_to_custom_role(r) for r in rows]

    async def delete_custom_role(
        self, tenant_id: str, role_code: str, session: AsyncSession | None = None
    ) -> bool:
        if session is not None:
            return await self._delete_custom_role_with_session(tenant_id, role_code, session)
        async with get_tenant_session(tenant_id) as sess:
            res = await self._delete_custom_role_with_session(tenant_id, role_code, sess)
            await sess.commit()
            return res

    async def _delete_custom_role_with_session(
        self, tenant_id: str, role_code: str, session: AsyncSession
    ) -> bool:
        query = text("DELETE FROM custom_roles WHERE tenant_id = :tid AND code = :code;")
        res = await session.execute(query, {"tid": tenant_id, "code": role_code})
        return res.rowcount > 0

    # -------------------------------------------------------------------------
    # Synchronous helpers
    # -------------------------------------------------------------------------

    def get_scope_grant_sync(self, grant_id: str) -> ScopeGrant | None:
        return self._run_async(self.get_scope_grant(grant_id))

    def save_scope_grant_sync(self, grant: ScopeGrant) -> ScopeGrant:
        return self._run_async(self.save_scope_grant(grant))

    def list_scope_grants_sync(
        self, tenant_id: str | None = None, grantee_id: str | None = None
    ) -> list[ScopeGrant]:
        return self._run_async(self.list_scope_grants(tenant_id, grantee_id))

    def delete_scope_grant_sync(self, grant_id: str) -> bool:
        return self._run_async(self.delete_scope_grant(grant_id))

    def get_custom_role_sync(self, tenant_id: str, role_code: str) -> RoleDefinition | None:
        return self._run_async(self.get_custom_role(tenant_id, role_code))

    def save_custom_role_sync(self, role_def: RoleDefinition) -> RoleDefinition:
        return self._run_async(self.save_custom_role(role_def))

    def list_custom_roles_sync(self, tenant_id: str) -> list[RoleDefinition]:
        return self._run_async(self.list_custom_roles(tenant_id))

    def delete_custom_role_sync(self, tenant_id: str, role_code: str) -> bool:
        return self._run_async(self.delete_custom_role(tenant_id, role_code))


_rbac_repo_instance: RBACRepository | None = None


def get_rbac_repository() -> RBACRepository:
    """Dependency provider with production startup guard."""
    global _rbac_repo_instance
    mode = os.getenv("PERSISTENCE_MODE", "sql").strip().lower()
    env = os.getenv("CLOUDLENS_ENV", "development").strip().lower()

    if mode == "inmemory":
        if env in ("staging", "production"):
            logger.critical("FATAL STARTUP GUARD: Staging/production refuses InMemory repository.")
            sys.exit(1)
        from tests.fakes.rbac import InMemoryRBACRepository
        return InMemoryRBACRepository()

    if _rbac_repo_instance is None:
        _rbac_repo_instance = SqlRBACRepository()
    return _rbac_repo_instance
