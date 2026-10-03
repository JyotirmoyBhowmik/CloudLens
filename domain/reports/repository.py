"""Tenant-Aware Repository for Report Jobs, Artifacts, and Schedules (Prompt 35).

Enforces:
- Strict tenant boundary isolation (Item 83 / M1).
- Thread-safe storage for asynchronous report jobs and generated artifacts.
- Flag-gated recurring report schedules.
"""

from __future__ import annotations

import threading

from domain.reports.models import ReportJob, ScheduledReport
from domain.tenant.context import TenantContext, require_tenant_context


class ReportRepository:
    """Thread-safe, tenant-isolated repository for reports and jobs."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # (tenant_id, job_id) -> ReportJob
        self._jobs: dict[tuple[str, str], ReportJob] = {}
        # (tenant_id, report_id) -> bytes
        self._artifacts: dict[tuple[str, str], bytes] = {}
        # (tenant_id, schedule_id) -> ScheduledReport
        self._schedules: dict[tuple[str, str], ScheduledReport] = {}

    def save_job(self, job: ReportJob, *, tenant_context: TenantContext) -> ReportJob:
        """Stores or updates an asynchronous report job."""
        tc = require_tenant_context(tenant_context)
        with self._lock:
            self._jobs[(tc.tenant_id, job.id)] = job
        return job

    def get_job(self, job_id: str, *, tenant_context: TenantContext) -> ReportJob | None:
        """Retrieves an asynchronous report job by ID within the tenant partition."""
        tc = require_tenant_context(tenant_context)
        with self._lock:
            return self._jobs.get((tc.tenant_id, job_id))

    def list_jobs(
        self, *, tenant_context: TenantContext, limit: int = 50, offset: int = 0
    ) -> list[ReportJob]:
        """Lists generated report jobs for the caller's tenant."""
        tc = require_tenant_context(tenant_context)
        with self._lock:
            tenant_jobs = [j for (tid, _), j in self._jobs.items() if tid == tc.tenant_id]
        sorted_jobs = sorted(tenant_jobs, key=lambda j: j.created_at, reverse=True)
        return sorted_jobs[offset : offset + limit]

    def save_artifact(
        self, report_id: str, content: bytes, *, tenant_context: TenantContext
    ) -> None:
        """Stores binary or text report export artifact bytes."""
        tc = require_tenant_context(tenant_context)
        with self._lock:
            self._artifacts[(tc.tenant_id, report_id)] = content

    def get_artifact(self, report_id: str, *, tenant_context: TenantContext) -> bytes | None:
        """Retrieves raw export artifact bytes."""
        tc = require_tenant_context(tenant_context)
        with self._lock:
            return self._artifacts.get((tc.tenant_id, report_id))

    def save_schedule(
        self, schedule: ScheduledReport, *, tenant_context: TenantContext
    ) -> ScheduledReport:
        """Saves a recurring report schedule."""
        tc = require_tenant_context(tenant_context)
        with self._lock:
            self._schedules[(tc.tenant_id, schedule.id)] = schedule
        return schedule

    def list_schedules(self, *, tenant_context: TenantContext) -> list[ScheduledReport]:
        """Lists all recurring report schedules for the calling tenant."""
        tc = require_tenant_context(tenant_context)
        with self._lock:
            return [s for (tid, _), s in self._schedules.items() if tid == tc.tenant_id]

    def get_schedule(
        self, schedule_id: str, *, tenant_context: TenantContext
    ) -> ScheduledReport | None:
        """Retrieves a scheduled report definition."""
        tc = require_tenant_context(tenant_context)
        with self._lock:
            return self._schedules.get((tc.tenant_id, schedule_id))


_global_report_repository: ReportRepository | None = None
_repo_lock = threading.Lock()


def get_report_repository() -> ReportRepository:
    """Returns the singleton instance of ReportRepository."""
    global _global_report_repository
    if _global_report_repository is None:
        with _repo_lock:
            if _global_report_repository is None:
                _global_report_repository = ReportRepository()
    return _global_report_repository
