"""Tenant-Aware SQL Repository for Report Jobs, Artifacts, and Schedules (Prompt P08).

Enforces:
- Pattern P1: PostgreSQL persistence with RLS tenant isolation.
- Persistent report jobs, artifacts, and schedules surviving process restarts.
- Strict tenant boundary isolation (Item 83 / M1).
- Thread-safe storage via db.session.run_async and get_tenant_session.
- Zero mutable dict singletons in domain layer.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from db.session import get_tenant_session, run_async, verify_persistence_startup_guard
from domain.reports.models import ReportJob, ScheduledReport
from domain.tenant.context import TenantContext, require_tenant_context

logger = logging.getLogger("cloudlens.reports.repository")


class SqlReportRepository:
    """Production SQL-backed repository for reports, jobs, artifacts, and schedules."""

    is_in_memory: bool = False

    def save_job(self, job: ReportJob, *, tenant_context: TenantContext) -> ReportJob:
        """Stores or updates an asynchronous report job in PostgreSQL."""
        tc = require_tenant_context(tenant_context)

        async def _save():
            async with get_tenant_session(tc.tenant_id) as sess:
                payload = job.model_dump_json()
                await sess.execute(
                    text("""
                        INSERT INTO report_jobs (
                            id, tenant_id, name, report_type, status, parameters,
                            artifact_id, created_by, created_at, completed_at,
                            error_message, job_payload
                        )
                        VALUES (
                            :id, :tenant_id, :name, :report_type, :status, :parameters,
                            :artifact_id, :created_by, :created_at, :completed_at,
                            :error_message, :job_payload
                        )
                        ON CONFLICT (id) DO UPDATE SET
                            name = EXCLUDED.name,
                            report_type = EXCLUDED.report_type,
                            status = EXCLUDED.status,
                            parameters = EXCLUDED.parameters,
                            artifact_id = EXCLUDED.artifact_id,
                            completed_at = EXCLUDED.completed_at,
                            error_message = EXCLUDED.error_message,
                            job_payload = EXCLUDED.job_payload;
                    """),
                    {
                        "id": job.id,
                        "tenant_id": tc.tenant_id,
                        "name": job.output_filename or job.template_id,
                        "report_type": job.format.value if hasattr(job.format, "value") else str(job.format),
                        "status": job.status,
                        "parameters": json.dumps(job.parameters.model_dump()),
                        "artifact_id": job.download_token or job.id,
                        "created_by": job.provenance.requester_identity if job.provenance else "system",
                        "created_at": job.created_at,
                        "completed_at": job.completed_at,
                        "error_message": job.error_message,
                        "job_payload": payload,
                    },
                )
                await sess.commit()
            return job

        return run_async(_save())

    def get_job(self, job_id: str, *, tenant_context: TenantContext) -> ReportJob | None:
        """Retrieves an asynchronous report job by ID within the tenant partition."""
        tc = require_tenant_context(tenant_context)

        async def _get():
            async with get_tenant_session(tc.tenant_id) as sess:
                res = await sess.execute(
                    text("""
                        SELECT job_payload
                        FROM report_jobs
                        WHERE tenant_id = :tenant_id AND id = :id
                        LIMIT 1;
                    """),
                    {"tenant_id": tc.tenant_id, "id": job_id},
                )
                row = res.fetchone()
                if not row:
                    return None
                payload = row[0]
                if isinstance(payload, str):
                    return ReportJob.model_validate_json(payload)
                return ReportJob.model_validate(payload)

        return run_async(_get())

    def list_jobs(
        self, *, tenant_context: TenantContext, limit: int = 50, offset: int = 0
    ) -> list[ReportJob]:
        """Lists generated report jobs for the caller's tenant."""
        tc = require_tenant_context(tenant_context)

        async def _list():
            async with get_tenant_session(tc.tenant_id) as sess:
                res = await sess.execute(
                    text("""
                        SELECT job_payload
                        FROM report_jobs
                        WHERE tenant_id = :tenant_id
                        ORDER BY created_at DESC
                        LIMIT :limit OFFSET :offset;
                    """),
                    {"tenant_id": tc.tenant_id, "limit": limit, "offset": offset},
                )
                items: list[ReportJob] = []
                for row in res.fetchall():
                    payload = row[0]
                    if isinstance(payload, str):
                        items.append(ReportJob.model_validate_json(payload))
                    else:
                        items.append(ReportJob.model_validate(payload))
                return items

        return run_async(_list())

    def save_artifact(
        self, report_id: str, content: bytes, *, tenant_context: TenantContext
    ) -> None:
        """Stores binary or text report export artifact bytes."""
        tc = require_tenant_context(tenant_context)

        async def _save():
            artifact_id = f"art-{uuid.uuid4().hex[:12]}"
            async with get_tenant_session(tc.tenant_id) as sess:
                await sess.execute(
                    text("""
                        INSERT INTO report_artifacts (
                            id, tenant_id, report_id, content_type, artifact_bytes, created_at
                        )
                        VALUES (
                            :id, :tenant_id, :report_id, :content_type, :artifact_bytes, :created_at
                        )
                        ON CONFLICT (id) DO UPDATE SET
                            artifact_bytes = EXCLUDED.artifact_bytes;
                    """),
                    {
                        "id": artifact_id,
                        "tenant_id": tc.tenant_id,
                        "report_id": report_id,
                        "content_type": "application/octet-stream",
                        "artifact_bytes": content,
                        "created_at": datetime.now(UTC),
                    },
                )
                await sess.commit()

        run_async(_save())

    def get_artifact(self, report_id: str, *, tenant_context: TenantContext) -> bytes | None:
        """Retrieves raw export artifact bytes."""
        tc = require_tenant_context(tenant_context)

        async def _get():
            async with get_tenant_session(tc.tenant_id) as sess:
                res = await sess.execute(
                    text("""
                        SELECT artifact_bytes
                        FROM report_artifacts
                        WHERE tenant_id = :tenant_id AND report_id = :report_id
                        ORDER BY created_at DESC
                        LIMIT 1;
                    """),
                    {"tenant_id": tc.tenant_id, "report_id": report_id},
                )
                row = res.fetchone()
                if not row:
                    return None
                return bytes(row[0])

        return run_async(_get())

    def save_schedule(
        self, schedule: ScheduledReport, *, tenant_context: TenantContext
    ) -> ScheduledReport:
        """Saves a recurring report schedule."""
        tc = require_tenant_context(tenant_context)

        async def _save():
            async with get_tenant_session(tc.tenant_id) as sess:
                payload = schedule.model_dump_json()
                now = datetime.now(UTC)
                await sess.execute(
                    text("""
                        INSERT INTO report_schedules (
                            id, tenant_id, name, report_type, cron_expression,
                            parameters, enabled, created_at, updated_at, schedule_payload
                        )
                        VALUES (
                            :id, :tenant_id, :name, :report_type, :cron_expression,
                            :parameters, :enabled, :created_at, :updated_at, :schedule_payload
                        )
                        ON CONFLICT (id) DO UPDATE SET
                            name = EXCLUDED.name,
                            report_type = EXCLUDED.report_type,
                            cron_expression = EXCLUDED.cron_expression,
                            parameters = EXCLUDED.parameters,
                            enabled = EXCLUDED.enabled,
                            updated_at = EXCLUDED.updated_at,
                            schedule_payload = EXCLUDED.schedule_payload;
                    """),
                    {
                        "id": schedule.id,
                        "tenant_id": tc.tenant_id,
                        "name": schedule.template_id,
                        "report_type": schedule.format.value if hasattr(schedule.format, "value") else str(schedule.format),
                        "cron_expression": schedule.cron_expression,
                        "parameters": json.dumps(schedule.parameters.model_dump()),
                        "enabled": schedule.is_active,
                        "created_at": schedule.created_at,
                        "updated_at": now,
                        "schedule_payload": payload,
                    },
                )
                await sess.commit()
            return schedule

        return run_async(_save())

    def list_schedules(self, *, tenant_context: TenantContext) -> list[ScheduledReport]:
        """Lists all recurring report schedules for the calling tenant."""
        tc = require_tenant_context(tenant_context)

        async def _list():
            async with get_tenant_session(tc.tenant_id) as sess:
                res = await sess.execute(
                    text("""
                        SELECT schedule_payload
                        FROM report_schedules
                        WHERE tenant_id = :tenant_id
                        ORDER BY created_at DESC;
                    """),
                    {"tenant_id": tc.tenant_id},
                )
                items: list[ScheduledReport] = []
                for row in res.fetchall():
                    payload = row[0]
                    if isinstance(payload, str):
                        items.append(ScheduledReport.model_validate_json(payload))
                    else:
                        items.append(ScheduledReport.model_validate(payload))
                return items

        return run_async(_list())

    def get_schedule(
        self, schedule_id: str, *, tenant_context: TenantContext
    ) -> ScheduledReport | None:
        """Retrieves a scheduled report definition."""
        tc = require_tenant_context(tenant_context)

        async def _get():
            async with get_tenant_session(tc.tenant_id) as sess:
                res = await sess.execute(
                    text("""
                        SELECT schedule_payload
                        FROM report_schedules
                        WHERE tenant_id = :tenant_id AND id = :id
                        LIMIT 1;
                    """),
                    {"tenant_id": tc.tenant_id, "id": schedule_id},
                )
                row = res.fetchone()
                if not row:
                    return None
                payload = row[0]
                if isinstance(payload, str):
                    return ScheduledReport.model_validate_json(payload)
                return ScheduledReport.model_validate(payload)

        return run_async(_get())


ReportRepository = SqlReportRepository

_global_report_repository: SqlReportRepository | None = None


def get_report_repository() -> SqlReportRepository:
    """Returns the singleton instance of ReportRepository with startup guard."""
    global _global_report_repository
    if _global_report_repository is None:
        _global_report_repository = SqlReportRepository()
        verify_persistence_startup_guard(_global_report_repository)
    return _global_report_repository


def reset_report_repository(repo: Any = None) -> Any:
    """Resets the singleton instance of ReportRepository for test isolation."""
    global _global_report_repository
    _global_report_repository = repo
    return _global_report_repository or get_report_repository()
