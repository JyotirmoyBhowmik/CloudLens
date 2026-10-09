"""In-Memory Test Fake for Analytics Repository."""

from __future__ import annotations

import threading
from typing import Any

from domain.analytics.models import AnalyticsExtractJob, FactCostAndUsageRecord
from domain.tenant.context import TenantContext, require_tenant_context


class InMemoryAnalyticsRepository:
    """Thread-safe tenant-partitioned in-memory fake repository for analytical jobs."""

    is_in_memory: bool = True

    def __init__(self) -> None:
        self._jobs: dict[tuple[str, str], AnalyticsExtractJob] = {}
        self._snapshots: dict[
            tuple[str, str], tuple[list[FactCostAndUsageRecord], dict[str, list[Any]]]
        ] = {}
        self._lock = threading.Lock()

    def save_job(
        self, job: AnalyticsExtractJob, *, tenant_context: TenantContext
    ) -> AnalyticsExtractJob:
        tc = require_tenant_context(tenant_context)
        with self._lock:
            self._jobs[(tc.tenant_id, job.id)] = job.model_copy()
            return job

    def get_job(
        self, extract_id: str, *, tenant_context: TenantContext
    ) -> AnalyticsExtractJob | None:
        tc = require_tenant_context(tenant_context)
        with self._lock:
            job = self._jobs.get((tc.tenant_id, extract_id))
            return job.model_copy() if job else None

    def list_jobs(
        self, *, tenant_context: TenantContext, limit: int = 50, offset: int = 0
    ) -> list[AnalyticsExtractJob]:
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
        tc = require_tenant_context(tenant_context)
        with self._lock:
            self._snapshots[(tc.tenant_id, period)] = (list(facts), dict(dimensions))

    def get_snapshot(
        self, period: str, *, tenant_context: TenantContext
    ) -> tuple[list[FactCostAndUsageRecord], dict[str, list[Any]]] | None:
        tc = require_tenant_context(tenant_context)
        with self._lock:
            snap = self._snapshots.get((tc.tenant_id, period))
            if not snap:
                return None
            return list(snap[0]), dict(snap[1])
