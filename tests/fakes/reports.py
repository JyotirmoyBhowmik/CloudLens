"""In-Memory Test Fake for Report Repository."""

from __future__ import annotations

import threading

from domain.reports.models import ReportJob, ScheduledReport
from domain.tenant.context import TenantContext, require_tenant_context


class InMemoryReportRepository:
    """Thread-safe, tenant-isolated in-memory test fake for report repository."""

    is_in_memory: bool = True

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[tuple[str, str], ReportJob] = {}
        self._artifacts: dict[tuple[str, str], bytes] = {}
        self._schedules: dict[tuple[str, str], ScheduledReport] = {}

    def save_job(self, job: ReportJob, *, tenant_context: TenantContext) -> ReportJob:
        tc = require_tenant_context(tenant_context)
        with self._lock:
            self._jobs[(tc.tenant_id, job.id)] = job
        return job

    def get_job(self, job_id: str, *, tenant_context: TenantContext) -> ReportJob | None:
        tc = require_tenant_context(tenant_context)
        with self._lock:
            return self._jobs.get((tc.tenant_id, job_id))

    def list_jobs(
        self, *, tenant_context: TenantContext, limit: int = 50, offset: int = 0
    ) -> list[ReportJob]:
        tc = require_tenant_context(tenant_context)
        with self._lock:
            tenant_jobs = [j for (tid, _), j in self._jobs.items() if tid == tc.tenant_id]
        sorted_jobs = sorted(tenant_jobs, key=lambda j: j.created_at, reverse=True)
        return sorted_jobs[offset : offset + limit]

    def save_artifact(
        self, report_id: str, content: bytes, *, tenant_context: TenantContext
    ) -> None:
        tc = require_tenant_context(tenant_context)
        with self._lock:
            self._artifacts[(tc.tenant_id, report_id)] = content

    def get_artifact(self, report_id: str, *, tenant_context: TenantContext) -> bytes | None:
        tc = require_tenant_context(tenant_context)
        with self._lock:
            return self._artifacts.get((tc.tenant_id, report_id))

    def save_schedule(
        self, schedule: ScheduledReport, *, tenant_context: TenantContext
    ) -> ScheduledReport:
        tc = require_tenant_context(tenant_context)
        with self._lock:
            self._schedules[(tc.tenant_id, schedule.id)] = schedule
        return schedule

    def list_schedules(self, *, tenant_context: TenantContext) -> list[ScheduledReport]:
        tc = require_tenant_context(tenant_context)
        with self._lock:
            return [s for (tid, _), s in self._schedules.items() if tid == tc.tenant_id]

    def get_schedule(
        self, schedule_id: str, *, tenant_context: TenantContext
    ) -> ScheduledReport | None:
        tc = require_tenant_context(tenant_context)
        with self._lock:
            return self._schedules.get((tc.tenant_id, schedule_id))
