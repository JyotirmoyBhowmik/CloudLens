"""Tenant-Scoped Repository for Budget Entities and Amendment Audit Trail (Prompt 28).

Enforces:
- Prompt 13 Item 84: 100% TenantContext validation across all repository operations.
- Tenant isolation per BBP Section 41 and SEC-015.
- Prompt 28: Budgets at all seventeen scope types with immutable amendment history.
"""

from __future__ import annotations

import builtins
import logging
from typing import Any

from domain.budgets.models import BudgetEntity
from domain.models.enums import BudgetScopeType
from domain.tenant.context import TenantContext
from domain.tenant.repository import TenantAwareRepository

logger = logging.getLogger(__name__)


class BudgetRepository(TenantAwareRepository[BudgetEntity]):
    """In-memory tenant-isolated repository for budgets and amendment histories."""

    def __init__(self) -> None:
        # Key: (tenant_id, budget_id) -> BudgetEntity
        self._budgets: dict[tuple[str, str], BudgetEntity] = {}

    # ==========================================================================
    # 1. Base TenantAwareRepository Implementation
    # ==========================================================================

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> BudgetEntity | None:
        """Retrieves a single budget by ID within tenant boundary."""
        self._validate_tenant_context(tenant_context)
        return self._budgets.get((tenant_context.tenant_id, entity_id))

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[BudgetEntity]:
        """Lists budgets belonging strictly to the tenant with optional pagination."""
        self._validate_tenant_context(tenant_context)
        tenant_id = tenant_context.tenant_id

        results = [b for (t_id, _), b in self._budgets.items() if t_id == tenant_id]

        if filter_params and isinstance(filter_params, dict):
            if "scope_type" in filter_params and filter_params["scope_type"]:
                st = filter_params["scope_type"]
                results = [
                    b
                    for b in results
                    if b.scope_type == st
                    or b.scope_type.value == str(st)
                    or b.scope_type.value.upper() == str(st).upper()
                ]
            if "scope_id" in filter_params and filter_params["scope_id"]:
                results = [b for b in results if b.scope_id == filter_params["scope_id"]]
            if "approval_status" in filter_params and filter_params["approval_status"]:
                stat = filter_params["approval_status"]
                results = [
                    b
                    for b in results
                    if b.approval_status == stat or b.approval_status.value == str(stat)
                ]
            if "is_native" in filter_params and filter_params["is_native"] is not None:
                results = [b for b in results if b.is_native is filter_params["is_native"]]

        # Order by created_at desc
        results.sort(key=lambda b: b.created_at, reverse=True)
        return results[offset : offset + limit]

    def list_all(
        self,
        *,
        tenant_context: TenantContext,
    ) -> builtins.list[BudgetEntity]:
        """Returns all budgets for the tenant without pagination limits."""
        self._validate_tenant_context(tenant_context)
        tenant_id = tenant_context.tenant_id
        return [b for (t_id, _), b in self._budgets.items() if t_id == tenant_id]

    def save(self, entity: BudgetEntity, *, tenant_context: TenantContext) -> BudgetEntity:
        """Stores or updates a budget entity within the tenant partition."""
        self._validate_tenant_context(tenant_context)
        if entity.tenant_id != tenant_context.tenant_id:
            raise ValueError(
                f"Cross-tenant isolation violation: Entity tenant {entity.tenant_id} "
                f"does not match context tenant {tenant_context.tenant_id}."
            )
        self._budgets[(tenant_context.tenant_id, entity.id)] = entity
        return entity

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        """Removes a budget entity from tenant partition."""
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, entity_id)
        if key in self._budgets:
            del self._budgets[key]
            return True
        return False

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        """Checks if a budget entity exists within the tenant boundary."""
        self._validate_tenant_context(tenant_context)
        return (tenant_context.tenant_id, entity_id) in self._budgets

    def count(self, *, tenant_context: TenantContext, filter_params: Any = None) -> int:
        """Returns count of budgets matching tenant and optional filter."""
        self._validate_tenant_context(tenant_context)
        return len(
            self.list(tenant_context=tenant_context, filter_params=filter_params, limit=10000)
        )

    def get_children(
        self,
        parent_budget_id: str,
        *,
        tenant_context: TenantContext,
    ) -> builtins.list[BudgetEntity]:
        """Retrieves direct child budgets allocated under a parent budget."""
        self._validate_tenant_context(tenant_context)
        tenant_id = tenant_context.tenant_id
        return [
            b
            for (t_id, _), b in self._budgets.items()
            if t_id == tenant_id and b.parent_budget_id == parent_budget_id
        ]

    def find_by_scope(
        self,
        scope_type: BudgetScopeType,
        scope_id: str,
        *,
        tenant_context: TenantContext,
    ) -> builtins.list[BudgetEntity]:
        """Finds all budgets attached to a specific scope node."""
        self._validate_tenant_context(tenant_context)
        tenant_id = tenant_context.tenant_id
        return [
            b
            for (t_id, _), b in self._budgets.items()
            if t_id == tenant_id and b.scope_type == scope_type and b.scope_id == scope_id
        ]


# Singleton repository instance
_budget_repository: BudgetRepository | None = None


def get_budget_repository() -> BudgetRepository:
    """Returns the singleton BudgetRepository instance."""
    global _budget_repository
    if _budget_repository is None:
        _budget_repository = BudgetRepository()
    return _budget_repository


def reset_budget_repository() -> None:
    """Resets the singleton BudgetRepository instance for testing."""
    global _budget_repository
    _budget_repository = None
