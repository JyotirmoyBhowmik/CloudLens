"""Tenant-Isolated SQL Repository for Analytics & Semantic Layer (Prompt P08).

Enforces:
- Pattern P1: PostgreSQL persistence with RLS tenant isolation.
- Persistent analytical extract jobs and star-schema snapshots surviving process restart.
- 100% strict TenantContext enforcement across all repository access methods.
- Thread-safe storage via db.session.run_async and get_tenant_session.
- Zero mutable dict singletons in domain layer.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from db.session import get_tenant_session, run_async, verify_persistence_startup_guard
from domain.analytics.models import (
    AnalyticsExtractJob,
    FactCostAndUsageRecord,
)
from domain.tenant.context import TenantContext, require_tenant_context

logger = logging.getLogger("cloudlens.analytics.repository")


class SqlAnalyticsRepository:
    """Production SQL-backed repository for analytical extract jobs and snapshots."""

    is_in_memory: bool = False

    def save_job(
        self, job: AnalyticsExtractJob, *, tenant_context: TenantContext
    ) -> AnalyticsExtractJob:
        """Persists or updates an analytical extract execution record in PostgreSQL."""
        tc = require_tenant_context(tenant_context)

        async def _save():
            async with get_tenant_session(tc.tenant_id) as sess:
                payload = job.model_dump_json()
                await sess.execute(
                    text("""
                        INSERT INTO analytics_jobs (
                            id, tenant_id, name, status, parameters, row_count,
                            created_at, completed_at, error_message, job_payload
                        )
                        VALUES (
                            :id, :tenant_id, :name, :status, :parameters, :row_count,
                            :created_at, :completed_at, :error_message, :job_payload
                        )
                        ON CONFLICT (id) DO UPDATE SET
                            name = EXCLUDED.name,
                            status = EXCLUDED.status,
                            parameters = EXCLUDED.parameters,
                            row_count = EXCLUDED.row_count,
                            completed_at = EXCLUDED.completed_at,
                            error_message = EXCLUDED.error_message,
                            job_payload = EXCLUDED.job_payload;
                    """),
                    {
                        "id": job.id,
                        "tenant_id": tc.tenant_id,
                        "name": f"extract-{job.period}",
                        "status": job.status,
                        "parameters": json.dumps(job.manifest.model_dump() if job.manifest else {}),
                        "row_count": job.row_count,
                        "created_at": job.created_at,
                        "completed_at": job.completed_at,
                        "error_message": getattr(job, "failure_reason", None) or getattr(job, "error_message", None),
                        "job_payload": payload,
                    },
                )
                await sess.commit()
            return job

        return run_async(_save())

    def get_job(
        self, extract_id: str, *, tenant_context: TenantContext
    ) -> AnalyticsExtractJob | None:
        """Retrieves an extract job by identifier with strict tenant isolation."""
        tc = require_tenant_context(tenant_context)

        async def _get():
            async with get_tenant_session(tc.tenant_id) as sess:
                res = await sess.execute(
                    text("""
                        SELECT job_payload
                        FROM analytics_jobs
                        WHERE tenant_id = :tenant_id AND id = :id
                        LIMIT 1;
                    """),
                    {"tenant_id": tc.tenant_id, "id": extract_id},
                )
                row = res.fetchone()
                if not row:
                    return None
                payload = row[0]
                if isinstance(payload, str):
                    return AnalyticsExtractJob.model_validate_json(payload)
                return AnalyticsExtractJob.model_validate(payload)

        return run_async(_get())

    def list_jobs(
        self, *, tenant_context: TenantContext, limit: int = 50, offset: int = 0
    ) -> list[AnalyticsExtractJob]:
        """Lists extract jobs for the tenant, ordered newest first."""
        tc = require_tenant_context(tenant_context)

        async def _list():
            async with get_tenant_session(tc.tenant_id) as sess:
                res = await sess.execute(
                    text("""
                        SELECT job_payload
                        FROM analytics_jobs
                        WHERE tenant_id = :tenant_id
                        ORDER BY created_at DESC
                        LIMIT :limit OFFSET :offset;
                    """),
                    {"tenant_id": tc.tenant_id, "limit": limit, "offset": offset},
                )
                items: list[AnalyticsExtractJob] = []
                for row in res.fetchall():
                    payload = row[0]
                    if isinstance(payload, str):
                        items.append(AnalyticsExtractJob.model_validate_json(payload))
                    else:
                        items.append(AnalyticsExtractJob.model_validate(payload))
                return items

        return run_async(_list())

    def save_snapshot(
        self,
        period: str,
        facts: list[FactCostAndUsageRecord],
        dimensions: dict[str, list[Any]],
        *,
        tenant_context: TenantContext,
    ) -> None:
        """Persists the star-schema snapshot to PostgreSQL for the isolated analytical query path."""
        tc = require_tenant_context(tenant_context)

        async def _save():
            snapshot_id = f"snap-{tc.tenant_id}-{period}"
            facts_json = json.dumps([f.model_dump() for f in facts], default=str)
            dims_json = json.dumps(dimensions, default=str)
            async with get_tenant_session(tc.tenant_id) as sess:
                await sess.execute(
                    text("""
                        INSERT INTO analytics_snapshots (
                            id, tenant_id, period, facts_payload, dimensions_payload, created_at
                        )
                        VALUES (
                            :id, :tenant_id, :period, :facts, :dims, :created_at
                        )
                        ON CONFLICT (id) DO UPDATE SET
                            facts_payload = EXCLUDED.facts_payload,
                            dimensions_payload = EXCLUDED.dimensions_payload,
                            created_at = EXCLUDED.created_at;
                    """),
                    {
                        "id": snapshot_id,
                        "tenant_id": tc.tenant_id,
                        "period": period,
                        "facts": facts_json,
                        "dims": dims_json,
                        "created_at": datetime.now(UTC),
                    },
                )
                await sess.commit()

        run_async(_save())

    def get_snapshot(
        self, period: str, *, tenant_context: TenantContext
    ) -> tuple[list[FactCostAndUsageRecord], dict[str, list[Any]]] | None:
        """Retrieves star-schema snapshot from PostgreSQL for isolated analytical queries."""
        tc = require_tenant_context(tenant_context)

        async def _get():
            snapshot_id = f"snap-{tc.tenant_id}-{period}"
            async with get_tenant_session(tc.tenant_id) as sess:
                res = await sess.execute(
                    text("""
                        SELECT facts_payload, dimensions_payload
                        FROM analytics_snapshots
                        WHERE tenant_id = :tenant_id AND (id = :id OR period = :period)
                        ORDER BY created_at DESC
                        LIMIT 1;
                    """),
                    {"tenant_id": tc.tenant_id, "id": snapshot_id, "period": period},
                )
                row = res.fetchone()
                if not row:
                    return None
                raw_facts = row[0]
                facts_data = raw_facts if isinstance(raw_facts, list) else json.loads(raw_facts or "[]")
                facts = [FactCostAndUsageRecord.model_validate(f) for f in facts_data]
                raw_dims = row[1]
                dims_data = raw_dims if isinstance(raw_dims, dict) else json.loads(raw_dims or "{}")
                return facts, dims_data

        return run_async(_get())


AnalyticsRepository = SqlAnalyticsRepository

_global_analytics_repository: SqlAnalyticsRepository | None = None


def get_analytics_repository() -> SqlAnalyticsRepository:
    """Returns singleton instance of AnalyticsRepository with startup guard."""
    global _global_analytics_repository
    if _global_analytics_repository is None:
        _global_analytics_repository = SqlAnalyticsRepository()
        verify_persistence_startup_guard(_global_analytics_repository)
    return _global_analytics_repository


def reset_analytics_repository(repo: Any = None) -> Any:
    """Resets singleton instance of AnalyticsRepository for testing isolation."""
    global _global_analytics_repository
    _global_analytics_repository = repo
    return _global_analytics_repository or get_analytics_repository()
