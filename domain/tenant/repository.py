"""Tenant-Aware Repository Interface and Base Abstraction (Prompt 13 Item 84).

Enforces:
- Mandatory TenantContext in every repository method signature.
- Fails queries without tenant context at test/build time rather than silent runtime leakage.
- Strict mechanical partitioning per BBP Section 41 and SEC-015.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from domain.models.base import CanonicalEntity
from domain.tenant.context import TenantContext, require_tenant_context

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
