"""Tenant-Scoped Repository for Workflows, Definitions, and Delegations (Prompt 50).

Enforces:
- Prompt 13 Item 84: 100% TenantContext validation across all repository operations.
- Tenant isolation per BBP Section 41 and SEC-015.
- Mechanical scoping and audit integrity.
"""

from __future__ import annotations

import builtins
import logging
import threading
from typing import Any

from domain.tenant.context import TenantContext
from domain.tenant.repository import TenantAwareRepository
from domain.workflows.definitions import get_default_workflow_definitions
from domain.workflows.models import (
    DelegationRule,
    WorkflowDefinition,
    WorkflowRequest,
)

logger = logging.getLogger(__name__)


class WorkflowRepository(TenantAwareRepository[WorkflowRequest]):
    """Thread-safe, tenant-isolated repository for workflow requests, definitions, and delegations."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # Key: (tenant_id, request_id) -> WorkflowRequest
        self._requests: dict[tuple[str, str], WorkflowRequest] = {}
        # Key: (tenant_id or "SYSTEM", def_id) -> WorkflowDefinition
        self._definitions: dict[tuple[str, str], WorkflowDefinition] = {}
        # Key: (tenant_id, delegation_id) -> DelegationRule
        self._delegations: dict[tuple[str, str], DelegationRule] = {}

        # Seed system definitions
        for d in get_default_workflow_definitions():
            self._definitions[("SYSTEM", d.id)] = d
            self._definitions[("SYSTEM", d.request_type.upper())] = d

    # ==========================================================================
    # 1. WorkflowRequest CRUD (TenantAwareRepository Implementation)
    # ==========================================================================

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> WorkflowRequest | None:
        """Retrieves a single workflow request by ID within tenant boundary."""
        self._validate_tenant_context(tenant_context)
        with self._lock:
            req = self._requests.get((tenant_context.tenant_id, entity_id))
            return req.model_copy(deep=True) if req else None

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowRequest]:
        """Lists workflow requests belonging strictly to the tenant with optional pagination."""
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id

        with self._lock:
            items = [r for (tid, _), r in self._requests.items() if tid == t_id]

            if filter_params and isinstance(filter_params, dict):
                if "state" in filter_params and filter_params["state"]:
                    st = filter_params["state"]
                    items = [r for r in items if r.state == st or r.state.value == str(st)]
                if "request_type" in filter_params and filter_params["request_type"]:
                    rt = filter_params["request_type"]
                    items = [
                        r
                        for r in items
                        if r.request_type == rt or r.request_type.upper() == str(rt).upper()
                    ]
                if "requester_id" in filter_params and filter_params["requester_id"]:
                    items = [
                        r
                        for r in items
                        if r.requester.requester_id == filter_params["requester_id"]
                    ]

            # Sort latest first
            items.sort(key=lambda r: r.created_at, reverse=True)
            page = items[offset : offset + limit]
            return [r.model_copy(deep=True) for r in page]

    def save(self, entity: WorkflowRequest, *, tenant_context: TenantContext) -> WorkflowRequest:
        """Saves or updates a workflow request, enforcing tenant ownership."""
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id

        entity.tenant_id = t_id
        with self._lock:
            self._requests[(t_id, entity.id)] = entity.model_copy(deep=True)
            return entity.model_copy(deep=True)

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        """Deletes a workflow request within tenant boundary."""
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, entity_id)
        with self._lock:
            if key in self._requests:
                del self._requests[key]
                return True
            return False

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        """Checks if a workflow request exists in the tenant scope."""
        self._validate_tenant_context(tenant_context)
        with self._lock:
            return (tenant_context.tenant_id, entity_id) in self._requests

    # ==========================================================================
    # 2. Master Data Workflow Definitions
    # ==========================================================================

    def save_definition(
        self, definition: WorkflowDefinition, *, tenant_context: TenantContext
    ) -> WorkflowDefinition:
        """Stores a tenant-scoped or global master workflow definition."""
        self._validate_tenant_context(tenant_context)
        scope = definition.tenant_id or tenant_context.tenant_id
        with self._lock:
            self._definitions[(scope, definition.id)] = definition.model_copy(deep=True)
            self._definitions[(scope, definition.request_type.upper())] = definition.model_copy(
                deep=True
            )
            return definition.model_copy(deep=True)

    def get_definition(
        self, definition_id: str, *, tenant_context: TenantContext
    ) -> WorkflowDefinition | None:
        """Retrieves a workflow definition by ID, resolving tenant override over global master."""
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id
        with self._lock:
            # 1. Tenant override
            if (t_id, definition_id) in self._definitions:
                return self._definitions[(t_id, definition_id)].model_copy(deep=True)
            # 2. System global master
            if ("SYSTEM", definition_id) in self._definitions:
                return self._definitions[("SYSTEM", definition_id)].model_copy(deep=True)
            return None

    def get_definition_by_type(
        self, request_type: str, *, tenant_context: TenantContext
    ) -> WorkflowDefinition | None:
        """Retrieves a workflow definition by request type code."""
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id
        rt = request_type.strip().upper()
        with self._lock:
            if (t_id, rt) in self._definitions:
                return self._definitions[(t_id, rt)].model_copy(deep=True)
            if ("SYSTEM", rt) in self._definitions:
                return self._definitions[("SYSTEM", rt)].model_copy(deep=True)
            return None

    def list_definitions(
        self, *, tenant_context: TenantContext
    ) -> builtins.list[WorkflowDefinition]:
        """Lists active workflow definitions for the tenant, merging global and overrides."""
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id
        with self._lock:
            defs_by_type: dict[str, WorkflowDefinition] = {}
            # Global first
            for (scope, _), d in self._definitions.items():
                if scope == "SYSTEM" and d.is_active:
                    defs_by_type[d.request_type.upper()] = d.model_copy(deep=True)
            # Tenant override second
            for (scope, _), d in self._definitions.items():
                if scope == t_id and d.is_active:
                    defs_by_type[d.request_type.upper()] = d.model_copy(deep=True)

            return builtins.list(defs_by_type.values())

    # ==========================================================================
    # 3. Delegations & Out-of-Office Rules
    # ==========================================================================

    def save_delegation(
        self, rule: DelegationRule, *, tenant_context: TenantContext
    ) -> DelegationRule:
        """Persists a delegation rule within tenant scope."""
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id
        rule.tenant_id = t_id
        with self._lock:
            self._delegations[(t_id, rule.id)] = rule.model_copy(deep=True)
            return rule.model_copy(deep=True)

    def list_delegations(
        self, *, tenant_context: TenantContext, user_id: str | None = None
    ) -> builtins.list[DelegationRule]:
        """Lists active delegation rules in the tenant boundary."""
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id
        with self._lock:
            rules = [r for (tid, _), r in self._delegations.items() if tid == t_id]
            if user_id:
                rules = [
                    r
                    for r in rules
                    if r.original_approver_id == user_id or r.delegate_approver_id == user_id
                ]
            return [r.model_copy(deep=True) for r in rules]

    def get_delegation(
        self, delegation_id: str, *, tenant_context: TenantContext
    ) -> DelegationRule | None:
        """Retrieves a delegation rule by ID."""
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, delegation_id)
        with self._lock:
            rule = self._delegations.get(key)
            return rule.model_copy(deep=True) if rule else None

    def delete_delegation(self, delegation_id: str, *, tenant_context: TenantContext) -> bool:
        """Deletes a delegation rule."""
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, delegation_id)
        with self._lock:
            if key in self._delegations:
                del self._delegations[key]
                return True
            return False


_workflow_repository_instance: WorkflowRepository | None = None


def get_workflow_repository() -> WorkflowRepository:
    """Returns singleton WorkflowRepository instance."""
    global _workflow_repository_instance
    if _workflow_repository_instance is None:
        _workflow_repository_instance = WorkflowRepository()
    return _workflow_repository_instance


def reset_workflow_repository() -> None:
    """Resets repository singleton for test isolation."""
    global _workflow_repository_instance
    _workflow_repository_instance = None
