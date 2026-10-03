"""Tenant-Isolated Analytics & Semantic Layer Repository (Prompt 56 / BBP Section 39).

Enforces:
- 100% strict TenantContext enforcement across all repository access methods.
- Thread-safe storage for extract job lifecycle records, manifests, and star-schema snapshots.
- Architectural boundary: completely decoupled from transactional OLTP tables.
"""

from __future__ import annotations

import threading
from typing import Any

from domain.analytics.models import (
    AnalyticsExtractJob,
    FactCostAndUsageRecord,
)
from domain.tenant.context import TenantContext, require_tenant_context


class AnalyticsRepository:
    """Thread-safe tenant-partitioned repository for analytical jobs and star-schema snapshots."""

    def __init__(self) -> None:
        self._jobs: dict[tuple[str, str], AnalyticsExtractJob] = {}
        self._snapshots: dict[
            tuple[str, str], tuple[list[FactCostAndUsageRecord], dict[str, list[Any]]]
        ] = {}
        self._lock = threading.Lock()

    def save_job(
        self, job: AnalyticsExtractJob, *, tenant_context: TenantContext
    ) -> AnalyticsExtractJob:
        """Persists or updates an analytical extract execution record."""
        tc = require_tenant_context(tenant_context)
        with self._lock:
            self._jobs[(tc.tenant_id, job.id)] = job.model_copy()
            return job

    def get_job(
        self, extract_id: str, *, tenant_context: TenantContext
    ) -> AnalyticsExtractJob | None:
        """Retrieves an extract job by identifier with strict tenant isolation."""
        tc = require_tenant_context(tenant_context)
        with self._lock:
            job = self._jobs.get((tc.tenant_id, extract_id))
            return job.model_copy() if job else None

    def list_jobs(
        self, *, tenant_context: TenantContext, limit: int = 50, offset: int = 0
    ) -> list[AnalyticsExtractJob]:
        """Lists extract jobs for the tenant, ordered newest first."""
        tc = require_tenant_context(tenant_context)
        with self._lock:
            tenant_jobs = [j for (tid, _), j in self._jobs.items() if tid == tc.tenant_id]
        sorted_jobs = sorted(tenant_jobs, key=lambda j: j.created_at, reverse=True)
        return sorted_jobs[offset : offset + limit]

    def save_snapshot(
        self,
        period: str,
        facts: list[FactCostAndUsageRecord],
        dimensions: dict[str, list[Any]],
        *,
        tenant_context: TenantContext,
    ) -> None:
        """Persists the in-memory star-schema snapshot for the isolated analytical query path."""
        tc = require_tenant_context(tenant_context)
        with self._lock:
            self._snapshots[(tc.tenant_id, period)] = (list(facts), dict(dimensions))

    def get_snapshot(
        self, period: str, *, tenant_context: TenantContext
    ) -> tuple[list[FactCostAndUsageRecord], dict[str, list[Any]]] | None:
        """Retrieves star-schema snapshot for isolated analytical queries."""
        tc = require_tenant_context(tenant_context)
        with self._lock:
            snap = self._snapshots.get((tc.tenant_id, period))
            if not snap:
                return None
            return list(snap[0]), dict(snap[1])


_global_analytics_repository: AnalyticsRepository | None = None
_repo_lock = threading.Lock()


def get_analytics_repository() -> AnalyticsRepository:
    """Returns singleton instance of AnalyticsRepository."""
    global _global_analytics_repository
    if _global_analytics_repository is None:
        with _repo_lock:
            if _global_analytics_repository is None:
                _global_analytics_repository = AnalyticsRepository()
    return _global_analytics_repository


def reset_analytics_repository() -> None:
    """Resets singleton instance of AnalyticsRepository for testing isolation."""
    global _global_analytics_repository
    with _repo_lock:
        _global_analytics_repository = None
