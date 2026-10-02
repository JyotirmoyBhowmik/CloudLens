"""Tenant-Scoped Repository for Quota Entities, History, and Increase Requests (Prompt 54).

Enforces:
- Prompt 13 Item 84: 100% TenantContext validation across all repository operations.
- Tenant isolation per BBP Section 41 and SEC-015.
- Prompt 54: Headroom trend persistence for >= 3 months, increase request and remediation task tracking.
"""

from __future__ import annotations

import builtins
import logging
from typing import Any

from domain.models.enums import CloudProvider
from domain.quotas.models import (
    QuotaEntity,
    QuotaIncreaseRequest,
    QuotaRemediationTask,
)
from domain.tenant.context import TenantContext
from domain.tenant.repository import TenantAwareRepository

logger = logging.getLogger(__name__)


class QuotaRepository(TenantAwareRepository[QuotaEntity]):
    """In-memory tenant-isolated repository for quotas, increase requests, and remediation tasks."""

    def __init__(self) -> None:
        # Key: (tenant_id, quota_id) -> QuotaEntity
        self._quotas: dict[tuple[str, str], QuotaEntity] = {}
        # Key: (tenant_id, request_id) -> QuotaIncreaseRequest
        self._increase_requests: dict[tuple[str, str], QuotaIncreaseRequest] = {}
        # Key: (tenant_id, task_id) -> QuotaRemediationTask
        self._remediation_tasks: dict[tuple[str, str], QuotaRemediationTask] = {}

    # ==========================================================================
    # 1. Base TenantAwareRepository Implementation (QuotaEntity)
    # ==========================================================================

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> QuotaEntity | None:
        """Retrieves a single quota entity by ID within tenant scope."""
        self._validate_tenant_context(tenant_context)
        return self._quotas.get((tenant_context.tenant_id, entity_id))

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[QuotaEntity]:
        """Lists quotas belonging strictly to the tenant with optional filtering."""
        self._validate_tenant_context(tenant_context)
        tenant_id = tenant_context.tenant_id

        results = [quota for (t_id, _), quota in self._quotas.items() if t_id == tenant_id]

        if filter_params and isinstance(filter_params, dict):
            provider = filter_params.get("provider")
            if provider:
                results = [q for q in results if q.provider == provider]

            service_code = filter_params.get("service_code")
            if service_code:
                results = [q for q in results if q.service_code == service_code]

            scope_type = filter_params.get("scope_type")
            if scope_type:
                results = [q for q in results if q.scope_type == scope_type]

            scope_id = filter_params.get("scope_id")
            if scope_id:
                results = [q for q in results if q.scope_id == scope_id]

            status = filter_params.get("status")
            if status:
                results = [q for q in results if q.status == status]

            is_manual = filter_params.get("is_manual")
            if is_manual is not None:
                results = [q for q in results if q.is_manual == is_manual]

        # Order consistently by quota_code
        results.sort(key=lambda q: (q.provider, q.service_code, q.quota_code))
        return results[offset : offset + limit]

    def save(self, entity: QuotaEntity, *, tenant_context: TenantContext) -> QuotaEntity:
        """Persists or updates a quota entity, enforcing tenant ownership integrity."""
        self._validate_tenant_context(tenant_context)
        entity.tenant_id = tenant_context.tenant_id
        self._quotas[(tenant_context.tenant_id, entity.id)] = entity
        return entity

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        """Deletes a quota entity within the tenant scope."""
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, entity_id)
        if key in self._quotas:
            del self._quotas[key]
            return True
        return False

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        """Checks if a quota entity exists within the tenant scope."""
        self._validate_tenant_context(tenant_context)
        return (tenant_context.tenant_id, entity_id) in self._quotas

    def count(self, *, tenant_context: TenantContext, filter_params: Any = None) -> int:
        """Returns count of quotas matching tenant and optional filter."""
        self._validate_tenant_context(tenant_context)
        return len(
            self.list(
                tenant_context=tenant_context, filter_params=filter_params, limit=100000, offset=0
            )
        )

    # ==========================================================================
    # 2. Quota Lookups
    # ==========================================================================

    def find_by_code(
        self,
        *,
        provider: CloudProvider,
        quota_code: str,
        scope_id: str,
        tenant_context: TenantContext,
    ) -> QuotaEntity | None:
        """Locates an existing quota by provider, quota code, and scope ID."""
        self._validate_tenant_context(tenant_context)
        tenant_id = tenant_context.tenant_id
        for (t_id, _), quota in self._quotas.items():
            if (
                t_id == tenant_id
                and quota.provider == provider
                and quota.quota_code == quota_code
                and quota.scope_id == scope_id
            ):
                return quota
        return None

    # ==========================================================================
    # 3. Increase Request Management
    # ==========================================================================

    def save_increase_request(
        self,
        request: QuotaIncreaseRequest,
        *,
        tenant_context: TenantContext,
    ) -> QuotaIncreaseRequest:
        """Persists a quota increase request."""
        self._validate_tenant_context(tenant_context)
        request.tenant_id = tenant_context.tenant_id
        self._increase_requests[(tenant_context.tenant_id, request.id)] = request
        return request

    def get_increase_request(
        self,
        request_id: str,
        *,
        tenant_context: TenantContext,
    ) -> QuotaIncreaseRequest | None:
        """Retrieves a quota increase request by ID."""
        self._validate_tenant_context(tenant_context)
        return self._increase_requests.get((tenant_context.tenant_id, request_id))

    def list_increase_requests(
        self,
        *,
        tenant_context: TenantContext,
        quota_id: str | None = None,
    ) -> builtins.list[QuotaIncreaseRequest]:
        """Lists quota increase requests for a tenant, optionally filtered by quota ID."""
        self._validate_tenant_context(tenant_context)
        tenant_id = tenant_context.tenant_id
        results = [req for (t_id, _), req in self._increase_requests.items() if t_id == tenant_id]
        if quota_id:
            results = [r for r in results if r.quota_id == quota_id]
        results.sort(key=lambda r: r.requested_date, reverse=True)
        return results

    # ==========================================================================
    # 4. Remediation Tasks
    # ==========================================================================

    def save_remediation_task(
        self,
        task: QuotaRemediationTask,
        *,
        tenant_context: TenantContext,
    ) -> QuotaRemediationTask:
        """Persists a quota remediation task."""
        self._validate_tenant_context(tenant_context)
        task.tenant_id = tenant_context.tenant_id
        self._remediation_tasks[(tenant_context.tenant_id, task.id)] = task
        return task

    def get_remediation_task(
        self,
        task_id: str,
        *,
        tenant_context: TenantContext,
    ) -> QuotaRemediationTask | None:
        """Retrieves a quota remediation task by ID."""
        self._validate_tenant_context(tenant_context)
        return self._remediation_tasks.get((tenant_context.tenant_id, task_id))

    def list_remediation_tasks(
        self,
        *,
        tenant_context: TenantContext,
        quota_id: str | None = None,
    ) -> builtins.list[QuotaRemediationTask]:
        """Lists remediation tasks for a tenant, optionally filtered by quota ID."""
        self._validate_tenant_context(tenant_context)
        tenant_id = tenant_context.tenant_id
        results = [task for (t_id, _), task in self._remediation_tasks.items() if t_id == tenant_id]
        if quota_id:
            results = [t for t in results if t.quota_id == quota_id]
        results.sort(key=lambda t: t.created_at, reverse=True)
        return results


# Global singleton instance
_quota_repository: QuotaRepository | None = None


def get_quota_repository() -> QuotaRepository:
    """Returns the singleton QuotaRepository instance."""
    global _quota_repository
    if _quota_repository is None:
        _quota_repository = QuotaRepository()
    return _quota_repository


def reset_quota_repository() -> None:
    """Resets the singleton QuotaRepository for isolated test runs."""
    global _quota_repository
    _quota_repository = None
