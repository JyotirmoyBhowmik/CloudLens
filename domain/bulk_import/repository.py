"""Thread-Safe, Tenant-Isolated Bulk Import Repository (Prompt 53, Prompt P07).

Enforces:
- Strict TenantContext requirement on all repository operations (Prompt 13 / Item 84).
- Mechanical tenant isolation via PostgreSQL RLS across profiles, dry runs, runs, and jobs.
- Protocol + SqlBulkImportRepository per docs/persistence-pattern.md.
- Production startup guard verifying no in-memory repositories in staging/production.
"""

from __future__ import annotations

import json
import threading
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_tenant_session, run_async, verify_persistence_startup_guard
from domain.bulk_import.models import (
    DryRunSummary,
    ImportRunRecord,
    MappingProfile,
    ScheduledImportJob,
)
from domain.tenant.context import TenantContext, require_tenant_context


@runtime_checkable
class BulkImportRepository(Protocol):
    """Authoritative repository protocol for bulk import entities."""

    def save_mapping_profile(
        self, profile: MappingProfile, *, tenant_context: TenantContext
    ) -> MappingProfile: ...
    def get_mapping_profile(
        self, profile_id: str, *, tenant_context: TenantContext
    ) -> MappingProfile | None: ...
    def list_mapping_profiles(
        self,
        *,
        tenant_context: TenantContext,
        entity_type: str | None = None,
    ) -> list[MappingProfile]: ...
    def delete_mapping_profile(self, profile_id: str, *, tenant_context: TenantContext) -> bool: ...
    def save_dry_run(
        self, dry_run: DryRunSummary, *, tenant_context: TenantContext
    ) -> DryRunSummary: ...
    def get_dry_run(
        self, dry_run_id: str, *, tenant_context: TenantContext
    ) -> DryRunSummary | None: ...
    def save_import_run(
        self, run: ImportRunRecord, *, tenant_context: TenantContext
    ) -> ImportRunRecord: ...
    def get_import_run(
        self, run_id: str, *, tenant_context: TenantContext
    ) -> ImportRunRecord | None: ...
    def list_import_runs(
        self,
        *,
        tenant_context: TenantContext,
        entity_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ImportRunRecord]: ...
    def save_scheduled_job(
        self, job: ScheduledImportJob, *, tenant_context: TenantContext
    ) -> ScheduledImportJob: ...
    def get_scheduled_job(
        self, job_id: str, *, tenant_context: TenantContext
    ) -> ScheduledImportJob | None: ...
    def list_scheduled_jobs(self, *, tenant_context: TenantContext) -> list[ScheduledImportJob]: ...
    def delete_scheduled_job(self, job_id: str, *, tenant_context: TenantContext) -> bool: ...
    def clear(self) -> None: ...


class SqlBulkImportRepository:
    """PostgreSQL production implementation with Row-Level Security enforcement."""

    is_in_memory: bool = False

    def _run_async(self, coro: Any) -> Any:
        return run_async(coro)

    def _row_to_profile(self, row: Any) -> MappingProfile:
        m = dict(row._mapping)
        raw = m.get("profile_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "id" in raw:
            return MappingProfile.model_validate(raw)
        return MappingProfile.model_validate(m)

    def _row_to_dry_run(self, row: Any) -> DryRunSummary:
        m = dict(row._mapping)
        raw = m.get("dry_run_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "dry_run_id" in raw:
            return DryRunSummary.model_validate(raw)
        return DryRunSummary.model_validate(m)

    def _row_to_run(self, row: Any) -> ImportRunRecord:
        m = dict(row._mapping)
        raw = m.get("run_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "id" in raw:
            return ImportRunRecord.model_validate(raw)
        return ImportRunRecord.model_validate(m)

    def _row_to_job(self, row: Any) -> ScheduledImportJob:
        m = dict(row._mapping)
        raw = m.get("job_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "id" in raw:
            return ScheduledImportJob.model_validate(raw)
        return ScheduledImportJob.model_validate(m)

    def clear(self) -> None:
        pass

    # Profiles
    async def save_mapping_profile_async(
        self, profile: MappingProfile, *, tenant_context: TenantContext
    ) -> MappingProfile:
        tc = require_tenant_context(tenant_context)
        async with get_tenant_session(tc.tenant_id) as sess:
            query = text("""
                INSERT INTO bulk_import_profiles (
                    id, tenant_id, name, entity_type, profile_payload, created_at
                ) VALUES (
                    :id, :tid, :name, :entity_type, CAST(:payload AS JSONB), NOW()
                )
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    entity_type = EXCLUDED.entity_type,
                    profile_payload = EXCLUDED.profile_payload;
            """)
            await sess.execute(
                query,
                {
                    "id": profile.id,
                    "tid": tc.tenant_id,
                    "name": profile.name,
                    "entity_type": profile.entity_type.upper(),
                    "payload": json.dumps(profile.model_dump(mode="json")),
                },
            )
            await sess.commit()
            return profile

    def save_mapping_profile(
        self, profile: MappingProfile, *, tenant_context: TenantContext
    ) -> MappingProfile:
        return self._run_async(self.save_mapping_profile_async(profile, tenant_context=tenant_context))

    async def get_mapping_profile_async(
        self, profile_id: str, *, tenant_context: TenantContext
    ) -> MappingProfile | None:
        tc = require_tenant_context(tenant_context)
        async with get_tenant_session(tc.tenant_id) as sess:
            query = text("""
                SELECT * FROM bulk_import_profiles
                WHERE id = :id AND tenant_id = :tid
                LIMIT 1;
            """)
            res = await sess.execute(query, {"id": profile_id, "tid": tc.tenant_id})
            row = res.fetchone()
            if not row:
                return None
            return self._row_to_profile(row)

    def get_mapping_profile(
        self, profile_id: str, *, tenant_context: TenantContext
    ) -> MappingProfile | None:
        return self._run_async(self.get_mapping_profile_async(profile_id, tenant_context=tenant_context))

    async def list_mapping_profiles_async(
        self,
        *,
        tenant_context: TenantContext,
        entity_type: str | None = None,
    ) -> list[MappingProfile]:
        tc = require_tenant_context(tenant_context)
        async with get_tenant_session(tc.tenant_id) as sess:
            sql = ["SELECT * FROM bulk_import_profiles WHERE tenant_id = :tid"]
            params: dict[str, Any] = {"tid": tc.tenant_id}
            if entity_type:
                sql.append("AND UPPER(entity_type) = :etype")
                params["etype"] = entity_type.upper()
            sql.append("ORDER BY name ASC;")
            res = await sess.execute(text(" ".join(sql)), params)
            rows = res.fetchall()
            return [self._row_to_profile(r) for r in rows]

    def list_mapping_profiles(
        self,
        *,
        tenant_context: TenantContext,
        entity_type: str | None = None,
    ) -> list[MappingProfile]:
        return self._run_async(self.list_mapping_profiles_async(tenant_context=tenant_context, entity_type=entity_type))

    async def delete_mapping_profile_async(self, profile_id: str, *, tenant_context: TenantContext) -> bool:
        tc = require_tenant_context(tenant_context)
        async with get_tenant_session(tc.tenant_id) as sess:
            res = await sess.execute(
                text("DELETE FROM bulk_import_profiles WHERE id = :id AND tenant_id = :tid;"),
                {"id": profile_id, "tid": tc.tenant_id},
            )
            await sess.commit()
            return (res.rowcount or 0) > 0

    def delete_mapping_profile(self, profile_id: str, *, tenant_context: TenantContext) -> bool:
        return self._run_async(self.delete_mapping_profile_async(profile_id, tenant_context=tenant_context))

    # Dry Runs
    async def save_dry_run_async(
        self, dry_run: DryRunSummary, *, tenant_context: TenantContext
    ) -> DryRunSummary:
        tc = require_tenant_context(tenant_context)
        async with get_tenant_session(tc.tenant_id) as sess:
            query = text("""
                INSERT INTO bulk_import_dry_runs (
                    id, tenant_id, entity_type, dry_run_payload, created_at
                ) VALUES (
                    :id, :tid, :entity_type, CAST(:payload AS JSONB), :created_at
                )
                ON CONFLICT (id) DO UPDATE SET
                    dry_run_payload = EXCLUDED.dry_run_payload;
            """)
            await sess.execute(
                query,
                {
                    "id": dry_run.dry_run_id,
                    "tid": tc.tenant_id,
                    "entity_type": dry_run.entity_type,
                    "payload": json.dumps(dry_run.model_dump(mode="json")),
                    "created_at": dry_run.executed_at,
                },
            )
            await sess.commit()
            return dry_run

    def save_dry_run(
        self, dry_run: DryRunSummary, *, tenant_context: TenantContext
    ) -> DryRunSummary:
        return self._run_async(self.save_dry_run_async(dry_run, tenant_context=tenant_context))

    async def get_dry_run_async(
        self, dry_run_id: str, *, tenant_context: TenantContext
    ) -> DryRunSummary | None:
        tc = require_tenant_context(tenant_context)
        async with get_tenant_session(tc.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT * FROM bulk_import_dry_runs WHERE id = :id AND tenant_id = :tid LIMIT 1;"),
                {"id": dry_run_id, "tid": tc.tenant_id},
            )
            row = res.fetchone()
            if not row:
                return None
            return self._row_to_dry_run(row)

    def get_dry_run(
        self, dry_run_id: str, *, tenant_context: TenantContext
    ) -> DryRunSummary | None:
        return self._run_async(self.get_dry_run_async(dry_run_id, tenant_context=tenant_context))

    # Import Runs
    async def save_import_run_async(
        self, run: ImportRunRecord, *, tenant_context: TenantContext
    ) -> ImportRunRecord:
        tc = require_tenant_context(tenant_context)
        stat_val = run.status.value if hasattr(run.status, "value") else str(run.status)
        async with get_tenant_session(tc.tenant_id) as sess:
            query = text("""
                INSERT INTO bulk_import_runs (
                    id, tenant_id, entity_type, status, run_payload, started_at, completed_at
                ) VALUES (
                    :id, :tid, :entity_type, :status, CAST(:payload AS JSONB), :started_at, :completed_at
                )
                ON CONFLICT (id) DO UPDATE SET
                    status = EXCLUDED.status,
                    run_payload = EXCLUDED.run_payload,
                    completed_at = EXCLUDED.completed_at;
            """)
            await sess.execute(
                query,
                {
                    "id": run.id,
                    "tid": tc.tenant_id,
                    "entity_type": run.entity_type,
                    "status": stat_val,
                    "payload": json.dumps(run.model_dump(mode="json")),
                    "started_at": run.started_at,
                    "completed_at": run.completed_at,
                },
            )
            await sess.commit()
            return run

    def save_import_run(
        self, run: ImportRunRecord, *, tenant_context: TenantContext
    ) -> ImportRunRecord:
        return self._run_async(self.save_import_run_async(run, tenant_context=tenant_context))

    async def get_import_run_async(
        self, run_id: str, *, tenant_context: TenantContext
    ) -> ImportRunRecord | None:
        tc = require_tenant_context(tenant_context)
        async with get_tenant_session(tc.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT * FROM bulk_import_runs WHERE id = :id AND tenant_id = :tid LIMIT 1;"),
                {"id": run_id, "tid": tc.tenant_id},
            )
            row = res.fetchone()
            if not row:
                return None
            return self._row_to_run(row)

    def get_import_run(
        self, run_id: str, *, tenant_context: TenantContext
    ) -> ImportRunRecord | None:
        return self._run_async(self.get_import_run_async(run_id, tenant_context=tenant_context))

    async def list_import_runs_async(
        self,
        *,
        tenant_context: TenantContext,
        entity_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ImportRunRecord]:
        tc = require_tenant_context(tenant_context)
        async with get_tenant_session(tc.tenant_id) as sess:
            sql = ["SELECT * FROM bulk_import_runs WHERE tenant_id = :tid"]
            params: dict[str, Any] = {"tid": tc.tenant_id}
            if entity_type:
                sql.append("AND UPPER(entity_type) = :etype")
                params["etype"] = entity_type.upper()
            sql.append("ORDER BY started_at DESC LIMIT :limit OFFSET :offset;")
            params["limit"] = limit
            params["offset"] = offset

            res = await sess.execute(text(" ".join(sql)), params)
            rows = res.fetchall()
            return [self._row_to_run(r) for r in rows]

    def list_import_runs(
        self,
        *,
        tenant_context: TenantContext,
        entity_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ImportRunRecord]:
        return self._run_async(
            self.list_import_runs_async(
                tenant_context=tenant_context, entity_type=entity_type, limit=limit, offset=offset
            )
        )

    # Scheduled Jobs
    async def save_scheduled_job_async(
        self, job: ScheduledImportJob, *, tenant_context: TenantContext
    ) -> ScheduledImportJob:
        tc = require_tenant_context(tenant_context)
        async with get_tenant_session(tc.tenant_id) as sess:
            query = text("""
                INSERT INTO bulk_import_scheduled_jobs (
                    id, tenant_id, name, job_payload, created_at
                ) VALUES (
                    :id, :tid, :name, CAST(:payload AS JSONB), :created_at
                )
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    job_payload = EXCLUDED.job_payload;
            """)
            await sess.execute(
                query,
                {
                    "id": job.id,
                    "tid": tc.tenant_id,
                    "name": job.name,
                    "payload": json.dumps(job.model_dump(mode="json")),
                    "created_at": job.created_at,
                },
            )
            await sess.commit()
            return job

    def save_scheduled_job(
        self, job: ScheduledImportJob, *, tenant_context: TenantContext
    ) -> ScheduledImportJob:
        return self._run_async(self.save_scheduled_job_async(job, tenant_context=tenant_context))

    async def get_scheduled_job_async(
        self, job_id: str, *, tenant_context: TenantContext
    ) -> ScheduledImportJob | None:
        tc = require_tenant_context(tenant_context)
        async with get_tenant_session(tc.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT * FROM bulk_import_scheduled_jobs WHERE id = :id AND tenant_id = :tid LIMIT 1;"),
                {"id": job_id, "tid": tc.tenant_id},
            )
            row = res.fetchone()
            if not row:
                return None
            return self._row_to_job(row)

    def get_scheduled_job(
        self, job_id: str, *, tenant_context: TenantContext
    ) -> ScheduledImportJob | None:
        return self._run_async(self.get_scheduled_job_async(job_id, tenant_context=tenant_context))

    async def list_scheduled_jobs_async(self, *, tenant_context: TenantContext) -> list[ScheduledImportJob]:
        tc = require_tenant_context(tenant_context)
        async with get_tenant_session(tc.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT * FROM bulk_import_scheduled_jobs WHERE tenant_id = :tid ORDER BY name ASC;"),
                {"tid": tc.tenant_id},
            )
            rows = res.fetchall()
            return [self._row_to_job(r) for r in rows]

    def list_scheduled_jobs(self, *, tenant_context: TenantContext) -> list[ScheduledImportJob]:
        return self._run_async(self.list_scheduled_jobs_async(tenant_context=tenant_context))

    async def delete_scheduled_job_async(self, job_id: str, *, tenant_context: TenantContext) -> bool:
        tc = require_tenant_context(tenant_context)
        async with get_tenant_session(tc.tenant_id) as sess:
            res = await sess.execute(
                text("DELETE FROM bulk_import_scheduled_jobs WHERE id = :id AND tenant_id = :tid;"),
                {"id": job_id, "tid": tc.tenant_id},
            )
            await sess.commit()
            return (res.rowcount or 0) > 0

    def delete_scheduled_job(self, job_id: str, *, tenant_context: TenantContext) -> bool:
        return self._run_async(self.delete_scheduled_job_async(job_id, tenant_context=tenant_context))


_repository_instance: BulkImportRepository | None = None
_bulk_lock = threading.Lock()


def get_bulk_import_repository() -> BulkImportRepository:
    """Returns the singleton BulkImportRepository (SqlBulkImportRepository by default)."""
    global _repository_instance
    with _bulk_lock:
        if _repository_instance is None:
            repo = SqlBulkImportRepository()
            verify_persistence_startup_guard(repo)
            _repository_instance = repo
        return _repository_instance


def reset_bulk_import_repository(repo: BulkImportRepository | None = None) -> BulkImportRepository:
    """Resets the singleton BulkImportRepository."""
    global _repository_instance
    with _bulk_lock:
        _repository_instance = repo
        if _repository_instance is None:
            _repository_instance = SqlBulkImportRepository()
        return _repository_instance
