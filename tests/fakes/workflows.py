"""In-memory fake workflow repository for testing."""

from __future__ import annotations

from typing import Any

from domain.tenant.context import TenantContext
from domain.workflows.definitions import get_default_workflow_definitions
from domain.workflows.models import (
    DelegationRule,
    WorkflowDefinition,
    WorkflowRequest,
)


class InMemoryWorkflowRepository:
    """In-memory implementation of WorkflowRepository for test harnesses."""

    is_in_memory: bool = True

    def __init__(self) -> None:
        self._requests: dict[tuple[str, str], WorkflowRequest] = {}
        self._definitions: dict[tuple[str, str], WorkflowDefinition] = {}
        self._delegations: dict[tuple[str, str], DelegationRule] = {}

        for d in get_default_workflow_definitions():
            self._definitions[("SYSTEM", d.id)] = d
            self._definitions[("SYSTEM", d.request_type.upper())] = d

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> WorkflowRequest | None:
        return self._requests.get((tenant_context.tenant_id, entity_id))

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowRequest]:
        t_id = tenant_context.tenant_id
        items = [r for (tid, _), r in self._requests.items() if tid == t_id]
        if filter_params and isinstance(filter_params, dict):
            if "state" in filter_params and filter_params["state"]:
                st = filter_params["state"]
                items = [r for r in items if r.state == st or r.state.value == str(st)]
            if "request_type" in filter_params and filter_params["request_type"]:
                rt = filter_params["request_type"]
                items = [r for r in items if r.request_type == rt or r.request_type.upper() == str(rt).upper()]
            if "requester_id" in filter_params and filter_params["requester_id"]:
                items = [r for r in items if r.requester.requester_id == filter_params["requester_id"]]
        items.sort(key=lambda r: r.created_at, reverse=True)
        return items[offset : offset + limit]

    def save(self, entity: WorkflowRequest, *, tenant_context: TenantContext) -> WorkflowRequest:
        entity.tenant_id = tenant_context.tenant_id
        self._requests[(tenant_context.tenant_id, entity.id)] = entity
        return entity

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return bool(self._requests.pop((tenant_context.tenant_id, entity_id), None))

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return (tenant_context.tenant_id, entity_id) in self._requests

    def save_request(self, req: WorkflowRequest, *, tenant_context: TenantContext) -> WorkflowRequest:
        return self.save(req, tenant_context=tenant_context)

    def get_request(self, req_id: str, *, tenant_context: TenantContext) -> WorkflowRequest | None:
        return self.get(req_id, tenant_context=tenant_context)

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

    def save_definition(
        self, definition: WorkflowDefinition, *, tenant_context: TenantContext
    ) -> WorkflowDefinition:
        t_id = tenant_context.tenant_id if tenant_context else "SYSTEM"
        self._definitions[(t_id, definition.id)] = definition
        self._definitions[(t_id, definition.request_type.upper())] = definition
        return definition

    def get_definition(
        self, def_id: str, *, tenant_context: TenantContext
    ) -> WorkflowDefinition | None:
        t_id = tenant_context.tenant_id
        d = self._definitions.get((t_id, def_id)) or self._definitions.get((t_id, def_id.upper()))
        if d:
            return d
        return self._definitions.get(("SYSTEM", def_id)) or self._definitions.get(("SYSTEM", def_id.upper()))

    def list_definitions(self, *, tenant_context: TenantContext) -> list[WorkflowDefinition]:
        t_id = tenant_context.tenant_id
        res: dict[str, WorkflowDefinition] = {}
        for (tid, _), d in self._definitions.items():
            if tid == "SYSTEM":
                res[d.id] = d
        for (tid, _), d in self._definitions.items():
            if tid == t_id:
                res[d.id] = d
        return list(res.values())

    def save_delegation(
        self, delegation: DelegationRule, *, tenant_context: TenantContext
    ) -> DelegationRule:
        self._delegations[(tenant_context.tenant_id, delegation.id)] = delegation
        return delegation

    def get_delegation(
        self, delegation_id: str, *, tenant_context: TenantContext
    ) -> DelegationRule | None:
        return self._delegations.get((tenant_context.tenant_id, delegation_id))

    def list_delegations(
        self,
        *,
        tenant_context: TenantContext,
        delegator_id: str | None = None,
        delegatee_id: str | None = None,
    ) -> list[DelegationRule]:
        t_id = tenant_context.tenant_id
        items = [d for (tid, _), d in self._delegations.items() if tid == t_id]
        if delegator_id:
            items = [d for d in items if d.delegator_id == delegator_id]
        if delegatee_id:
            items = [d for d in items if d.delegatee_id == delegatee_id]
        return items

    def delete_delegation(self, delegation_id: str, *, tenant_context: TenantContext) -> bool:
        return bool(self._delegations.pop((tenant_context.tenant_id, delegation_id), None))
