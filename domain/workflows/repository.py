"""Tenant-Scoped Repository for Workflows, Definitions, and Delegations (Prompt 50, Prompt P07).

Enforces:
- Prompt 13 Item 84: 100% TenantContext validation across all repository operations.
- Pattern P1 & P4: Protocol contract and PostgreSQL RLS persistence via SqlWorkflowRepository.
- Production startup guard verifying no in-memory repositories in staging/production.
"""

from __future__ import annotations

import json
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import text

from db.session import get_tenant_session, run_async, verify_persistence_startup_guard
from domain.tenant.context import TenantContext
from domain.workflows.definitions import get_default_workflow_definitions
from domain.workflows.models import (
    DelegationRule,
    WorkflowDefinition,
    WorkflowRequest,
)


@runtime_checkable
class WorkflowRepository(Protocol):
    """Authoritative repository protocol for workflow requests, definitions, and delegations."""

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> WorkflowRequest | None: ...
    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowRequest]: ...
    def save(self, entity: WorkflowRequest, *, tenant_context: TenantContext) -> WorkflowRequest: ...
    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool: ...
    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool: ...
    def save_request(self, req: WorkflowRequest, *, tenant_context: TenantContext) -> WorkflowRequest: ...
    def get_request(self, req_id: str, *, tenant_context: TenantContext) -> WorkflowRequest | None: ...
    def list_requests(
        self,
        *,
        tenant_context: TenantContext,
        state: Any = None,
        request_type: Any = None,
        requester_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowRequest]: ...
    def save_definition(
        self, definition: WorkflowDefinition, *, tenant_context: TenantContext
    ) -> WorkflowDefinition: ...
    def get_definition(
        self, def_id: str, *, tenant_context: TenantContext
    ) -> WorkflowDefinition | None: ...
    def list_definitions(self, *, tenant_context: TenantContext) -> list[WorkflowDefinition]: ...
    def save_delegation(
        self, delegation: DelegationRule, *, tenant_context: TenantContext
    ) -> DelegationRule: ...
    def get_delegation(
        self, delegation_id: str, *, tenant_context: TenantContext
    ) -> DelegationRule | None: ...
    def list_delegations(
        self,
        *,
        tenant_context: TenantContext,
        delegator_id: str | None = None,
        delegatee_id: str | None = None,
    ) -> list[DelegationRule]: ...
    def delete_delegation(self, delegation_id: str, *, tenant_context: TenantContext) -> bool: ...


class SqlWorkflowRepository:
    """PostgreSQL production implementation with Row-Level Security."""

    is_in_memory: bool = False

    def _run_async(self, coro: Any) -> Any:
        return run_async(coro)

    def _row_to_request(self, row: Any) -> WorkflowRequest:
        m = dict(row._mapping)
        raw = m.get("request_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "id" in raw:
            return WorkflowRequest.model_validate(raw)
        return WorkflowRequest.model_validate(m)

    def _row_to_definition(self, row: Any) -> WorkflowDefinition:
        m = dict(row._mapping)
        raw = m.get("definition_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "id" in raw:
            return WorkflowDefinition.model_validate(raw)
        return WorkflowDefinition.model_validate(m)

    def _row_to_delegation(self, row: Any) -> DelegationRule:
        m = dict(row._mapping)
        raw = m.get("delegation_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "id" in raw:
            return DelegationRule.model_validate(raw)
        return DelegationRule.model_validate(m)

    # --------------------------------------------------------------------------
    # Requests
    # --------------------------------------------------------------------------

    async def get_async(self, entity_id: str, *, tenant_context: TenantContext) -> WorkflowRequest | None:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT * FROM workflow_requests WHERE id = :id AND tenant_id = :tid LIMIT 1;"),
                {"id": entity_id, "tid": tenant_context.tenant_id},
            )
            row = res.first()
            return self._row_to_request(row) if row else None

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> WorkflowRequest | None:
        return self._run_async(self.get_async(entity_id, tenant_context=tenant_context))

    def get_request(self, req_id: str, *, tenant_context: TenantContext) -> WorkflowRequest | None:
        return self.get(req_id, tenant_context=tenant_context)

    async def save_async(self, entity: WorkflowRequest, *, tenant_context: TenantContext) -> WorkflowRequest:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            entity.tenant_id = tenant_context.tenant_id
            query = text("""
                INSERT INTO workflow_requests (
                    id, tenant_id, request_type, state, requester_id, request_payload, created_at, updated_at
                ) VALUES (
                    :id, :tid, :rtype, :state, :req_id, CAST(:payload AS jsonb), :created_at, NOW()
                )
                ON CONFLICT (id) DO UPDATE SET
                    state = EXCLUDED.state,
                    request_payload = EXCLUDED.request_payload,
                    updated_at = NOW();
            """)
            await sess.execute(
                query,
                {
                    "id": entity.id,
                    "tid": tenant_context.tenant_id,
                    "rtype": entity.request_type,
                    "state": entity.state.value if hasattr(entity.state, "value") else str(entity.state),
                    "req_id": entity.requester.requester_id,
                    "payload": json.dumps(entity.model_dump(mode="json")),
                    "created_at": entity.created_at,
                },
            )
            await sess.commit()
            return entity

    def save(self, entity: WorkflowRequest, *, tenant_context: TenantContext) -> WorkflowRequest:
        return self._run_async(self.save_async(entity, tenant_context=tenant_context))

    def save_request(self, req: WorkflowRequest, *, tenant_context: TenantContext) -> WorkflowRequest:
        return self.save(req, tenant_context=tenant_context)

    async def list_async(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowRequest]:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            sql = "SELECT * FROM workflow_requests WHERE tenant_id = :tid"
            params: dict[str, Any] = {"tid": tenant_context.tenant_id, "lim": limit, "off": offset}
            if filter_params and isinstance(filter_params, dict):
                if "state" in filter_params and filter_params["state"]:
                    sql += " AND state = :st"
                    st = filter_params["state"]
                    params["st"] = st.value if hasattr(st, "value") else str(st)
                if "request_type" in filter_params and filter_params["request_type"]:
                    sql += " AND request_type = :rt"
                    params["rt"] = str(filter_params["request_type"])
                if "requester_id" in filter_params and filter_params["requester_id"]:
                    sql += " AND requester_id = :req"
                    params["req"] = str(filter_params["requester_id"])

            sql += " ORDER BY created_at DESC LIMIT :lim OFFSET :off;"
            res = await sess.execute(text(sql), params)
            rows = res.fetchall()
            return [self._row_to_request(r) for r in rows]

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowRequest]:
        return self._run_async(self.list_async(tenant_context=tenant_context, filter_params=filter_params, limit=limit, offset=offset))

    def list_requests(
        self,
        *,
        tenant_context: TenantContext,
        state: Any = None,
        request_type: Any = None,
        requester_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowRequest]:
        fp = {}
        if state:
            fp["state"] = state
        if request_type:
            fp["request_type"] = request_type
        if requester_id:
            fp["requester_id"] = requester_id
        return self.list(tenant_context=tenant_context, filter_params=fp, limit=limit, offset=offset)

    async def delete_async(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("DELETE FROM workflow_requests WHERE id = :id AND tenant_id = :tid;"),
                {"id": entity_id, "tid": tenant_context.tenant_id},
            )
            await sess.commit()
            return res.rowcount > 0

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return self._run_async(self.delete_async(entity_id, tenant_context=tenant_context))

    async def exists_async(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT 1 FROM workflow_requests WHERE id = :id AND tenant_id = :tid LIMIT 1;"),
                {"id": entity_id, "tid": tenant_context.tenant_id},
            )
            return res.first() is not None

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return self._run_async(self.exists_async(entity_id, tenant_context=tenant_context))

    # --------------------------------------------------------------------------
    # Definitions
    # --------------------------------------------------------------------------

    async def save_definition_async(
        self, definition: WorkflowDefinition, *, tenant_context: TenantContext
    ) -> WorkflowDefinition:
        tid = tenant_context.tenant_id if tenant_context else "SYSTEM"
        async with get_tenant_session(tid) as sess:
            query = text("""
                INSERT INTO workflow_definitions (id, tenant_id, request_type, name, definition_payload, created_at)
                VALUES (:id, :tid, :rtype, :name, CAST(:payload AS jsonb), NOW())
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    definition_payload = EXCLUDED.definition_payload;
            """)
            await sess.execute(
                query,
                {
                    "id": definition.id,
                    "tid": tid,
                    "rtype": definition.request_type,
                    "name": definition.name,
                    "payload": json.dumps(definition.model_dump(mode="json")),
                },
            )
            await sess.commit()
            return definition

    def save_definition(
        self, definition: WorkflowDefinition, *, tenant_context: TenantContext
    ) -> WorkflowDefinition:
        return self._run_async(self.save_definition_async(definition, tenant_context=tenant_context))

    async def get_definition_async(
        self, def_id: str, *, tenant_context: TenantContext
    ) -> WorkflowDefinition | None:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT * FROM workflow_definitions WHERE (id = :id OR UPPER(request_type) = UPPER(:id)) AND (tenant_id = :tid OR tenant_id = 'SYSTEM') LIMIT 1;"),
                {"id": def_id, "tid": tenant_context.tenant_id},
            )
            row = res.first()
            if row:
                return self._row_to_definition(row)
        for d in get_default_workflow_definitions():
            if d.id == def_id or d.request_type.upper() == def_id.upper():
                return d
        return None

    def get_definition(
        self, def_id: str, *, tenant_context: TenantContext
    ) -> WorkflowDefinition | None:
        return self._run_async(self.get_definition_async(def_id, tenant_context=tenant_context))

    async def list_definitions_async(self, *, tenant_context: TenantContext) -> list[WorkflowDefinition]:
        defaults_map = {d.id: d for d in get_default_workflow_definitions()}
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT * FROM workflow_definitions WHERE tenant_id = :tid OR tenant_id = 'SYSTEM';"),
                {"tid": tenant_context.tenant_id},
            )
            rows = res.fetchall()
            for r in rows:
                d = self._row_to_definition(r)
                defaults_map[d.id] = d
        return list(defaults_map.values())

    def list_definitions(self, *, tenant_context: TenantContext) -> list[WorkflowDefinition]:
        return self._run_async(self.list_definitions_async(tenant_context=tenant_context))

    # --------------------------------------------------------------------------
    # Delegations
    # --------------------------------------------------------------------------

    async def save_delegation_async(
        self, delegation: DelegationRule, *, tenant_context: TenantContext
    ) -> DelegationRule:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            query = text("""
                INSERT INTO workflow_delegations (id, tenant_id, delegator_id, delegatee_id, delegation_payload, created_at)
                VALUES (:id, :tid, :del_id, :dee_id, CAST(:payload AS jsonb), NOW())
                ON CONFLICT (id) DO UPDATE SET
                    delegation_payload = EXCLUDED.delegation_payload;
            """)
            await sess.execute(
                query,
                {
                    "id": delegation.id,
                    "tid": tenant_context.tenant_id,
                    "del_id": delegation.delegator_id,
                    "dee_id": delegation.delegatee_id,
                    "payload": json.dumps(delegation.model_dump(mode="json")),
                },
            )
            await sess.commit()
            return delegation

    def save_delegation(
        self, delegation: DelegationRule, *, tenant_context: TenantContext
    ) -> DelegationRule:
        return self._run_async(self.save_delegation_async(delegation, tenant_context=tenant_context))

    async def get_delegation_async(
        self, delegation_id: str, *, tenant_context: TenantContext
    ) -> DelegationRule | None:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT * FROM workflow_delegations WHERE id = :id AND tenant_id = :tid LIMIT 1;"),
                {"id": delegation_id, "tid": tenant_context.tenant_id},
            )
            row = res.first()
            return self._row_to_delegation(row) if row else None

    def get_delegation(
        self, delegation_id: str, *, tenant_context: TenantContext
    ) -> DelegationRule | None:
        return self._run_async(self.get_delegation_async(delegation_id, tenant_context=tenant_context))

    async def list_delegations_async(
        self,
        *,
        tenant_context: TenantContext,
        delegator_id: str | None = None,
        delegatee_id: str | None = None,
    ) -> list[DelegationRule]:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            sql = "SELECT * FROM workflow_delegations WHERE tenant_id = :tid"
            params: dict[str, Any] = {"tid": tenant_context.tenant_id}
            if delegator_id:
                sql += " AND delegator_id = :del"
                params["del"] = delegator_id
            if delegatee_id:
                sql += " AND delegatee_id = :dee"
                params["dee"] = delegatee_id
            sql += " ORDER BY created_at DESC;"
            res = await sess.execute(text(sql), params)
            rows = res.fetchall()
            return [self._row_to_delegation(r) for r in rows]

    def list_delegations(
        self,
        *,
        tenant_context: TenantContext,
        delegator_id: str | None = None,
        delegatee_id: str | None = None,
    ) -> list[DelegationRule]:
        return self._run_async(
            self.list_delegations_async(
                tenant_context=tenant_context, delegator_id=delegator_id, delegatee_id=delegatee_id
            )
        )

    async def delete_delegation_async(self, delegation_id: str, *, tenant_context: TenantContext) -> bool:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("DELETE FROM workflow_delegations WHERE id = :id AND tenant_id = :tid;"),
                {"id": delegation_id, "tid": tenant_context.tenant_id},
            )
            await sess.commit()
            return res.rowcount > 0

    def delete_delegation(self, delegation_id: str, *, tenant_context: TenantContext) -> bool:
        return self._run_async(self.delete_delegation_async(delegation_id, tenant_context=tenant_context))


# Singleton instance & factory
_workflow_repository_instance: WorkflowRepository | None = None


def get_workflow_repository() -> WorkflowRepository:
    """Returns singleton WorkflowRepository with production startup guard."""
    global _workflow_repository_instance
    if _workflow_repository_instance is None:
        _workflow_repository_instance = SqlWorkflowRepository()
        verify_persistence_startup_guard(_workflow_repository_instance)
    return _workflow_repository_instance


def reset_workflow_repository(repo: WorkflowRepository | None = None) -> None:
    """Resets singleton WorkflowRepository for testing."""
    global _workflow_repository_instance
    _workflow_repository_instance = repo
