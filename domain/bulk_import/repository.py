"""Thread-Safe, Tenant-Isolated Bulk Import Repository (Prompt 53).

Enforces:
- Strict TenantContext requirement on all repository operations (Prompt 13 / Item 84).
- Mechanical tenant isolation across mapping profiles, dry runs, import runs, and scheduled jobs.
- Thread-safe in-memory storage with point-in-time state cloning.
"""

from __future__ import annotations

import threading

from domain.bulk_import.models import (
    DryRunSummary,
    ImportRunRecord,
    MappingProfile,
    ScheduledImportJob,
)
from domain.tenant.context import TenantContext, require_tenant_context


class BulkImportRepository:
    """Thread-safe, tenant-isolated repository for bulk import entities."""

    def __init__(self) -> None:
        self._profiles: dict[tuple[str, str], MappingProfile] = {}
        self._dry_runs: dict[tuple[str, str], DryRunSummary] = {}
        self._runs: dict[tuple[str, str], ImportRunRecord] = {}
        self._scheduled_jobs: dict[tuple[str, str], ScheduledImportJob] = {}
        self._lock = threading.RLock()

    # ==========================================================================
    # Mapping Profiles
    # ==========================================================================

    def save_mapping_profile(
        self, profile: MappingProfile, *, tenant_context: TenantContext
    ) -> MappingProfile:
        """Persists or updates a saved mapping profile."""
        tc = require_tenant_context(tenant_context)
        with self._lock:
            self._profiles[(tc.tenant_id, profile.id)] = profile.model_copy()
            return profile

    def get_mapping_profile(
        self, profile_id: str, *, tenant_context: TenantContext
    ) -> MappingProfile | None:
        """Retrieves a mapping profile by ID within tenant scope."""
        tc = require_tenant_context(tenant_context)
        with self._lock:
            prof = self._profiles.get((tc.tenant_id, profile_id))
            return prof.model_copy() if prof else None

    def list_mapping_profiles(
        self,
        *,
        tenant_context: TenantContext,
        entity_type: str | None = None,
    ) -> list[MappingProfile]:
        """Lists mapping profiles for a tenant, optionally filtered by entity type."""
        tc = require_tenant_context(tenant_context)
        with self._lock:
            items = [
                p.model_copy()
                for (tid, _), p in self._profiles.items()
                if tid == tc.tenant_id
                and (entity_type is None or p.entity_type.upper() == entity_type.upper())
            ]
            return sorted(items, key=lambda x: x.name)

    def delete_mapping_profile(self, profile_id: str, *, tenant_context: TenantContext) -> bool:
        """Deletes a mapping profile within tenant scope."""
        tc = require_tenant_context(tenant_context)
        with self._lock:
            key = (tc.tenant_id, profile_id)
            if key in self._profiles:
                del self._profiles[key]
                return True
            return False

    # ==========================================================================
    # Dry Runs
    # ==========================================================================

    def save_dry_run(
        self, dry_run: DryRunSummary, *, tenant_context: TenantContext
    ) -> DryRunSummary:
        """Persists a dry-run validation result."""
        tc = require_tenant_context(tenant_context)
        with self._lock:
            self._dry_runs[(tc.tenant_id, dry_run.dry_run_id)] = dry_run.model_copy()
            return dry_run

    def get_dry_run(
        self, dry_run_id: str, *, tenant_context: TenantContext
    ) -> DryRunSummary | None:
        """Retrieves a dry-run result by token."""
        tc = require_tenant_context(tenant_context)
        with self._lock:
            dr = self._dry_runs.get((tc.tenant_id, dry_run_id))
            return dr.model_copy() if dr else None

    # ==========================================================================
    # Import Run Records (History & Audit)
    # ==========================================================================

    def save_import_run(
        self, run: ImportRunRecord, *, tenant_context: TenantContext
    ) -> ImportRunRecord:
        """Persists or updates an import execution record."""
        tc = require_tenant_context(tenant_context)
        with self._lock:
            self._runs[(tc.tenant_id, run.id)] = run.model_copy()
            return run

    def get_import_run(
        self, run_id: str, *, tenant_context: TenantContext
    ) -> ImportRunRecord | None:
        """Retrieves an import execution record by ID."""
        tc = require_tenant_context(tenant_context)
        with self._lock:
            rec = self._runs.get((tc.tenant_id, run_id))
            return rec.model_copy() if rec else None

    def list_import_runs(
        self,
        *,
        tenant_context: TenantContext,
        entity_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ImportRunRecord]:
        """Lists historical import runs for a tenant."""
        tc = require_tenant_context(tenant_context)
        with self._lock:
            items = [
                r.model_copy()
                for (tid, _), r in self._runs.items()
                if tid == tc.tenant_id
                and (entity_type is None or r.entity_type.upper() == entity_type.upper())
            ]
            items.sort(key=lambda x: x.started_at, reverse=True)
            return items[offset : offset + limit]

    # ==========================================================================
    # Scheduled Import Jobs
    # ==========================================================================

    def save_scheduled_job(
        self, job: ScheduledImportJob, *, tenant_context: TenantContext
    ) -> ScheduledImportJob:
        """Persists or updates a scheduled import configuration."""
        tc = require_tenant_context(tenant_context)
        with self._lock:
            self._scheduled_jobs[(tc.tenant_id, job.id)] = job.model_copy()
            return job

    def get_scheduled_job(
        self, job_id: str, *, tenant_context: TenantContext
    ) -> ScheduledImportJob | None:
        """Retrieves a scheduled import job by ID."""
        tc = require_tenant_context(tenant_context)
        with self._lock:
            job = self._scheduled_jobs.get((tc.tenant_id, job_id))
            return job.model_copy() if job else None

    def list_scheduled_jobs(self, *, tenant_context: TenantContext) -> list[ScheduledImportJob]:
        """Lists all scheduled import jobs for a tenant."""
        tc = require_tenant_context(tenant_context)
        with self._lock:
            items = [
                j.model_copy()
                for (tid, _), j in self._scheduled_jobs.items()
                if tid == tc.tenant_id
            ]
            return sorted(items, key=lambda x: x.name)

    def delete_scheduled_job(self, job_id: str, *, tenant_context: TenantContext) -> bool:
        """Deletes a scheduled import job."""
        tc = require_tenant_context(tenant_context)
        with self._lock:
            key = (tc.tenant_id, job_id)
            if key in self._scheduled_jobs:
                del self._scheduled_jobs[key]
                return True
            return False

    def clear(self) -> None:
        """Resets all in-memory collections (for testing)."""
        with self._lock:
            self._profiles.clear()
            self._dry_runs.clear()
            self._runs.clear()
            self._scheduled_jobs.clear()


# Global singleton instance
_repository_instance = BulkImportRepository()


def get_bulk_import_repository() -> BulkImportRepository:
    """Returns the singleton BulkImportRepository."""
    return _repository_instance


def reset_bulk_import_repository() -> BulkImportRepository:
    """Resets the singleton BulkImportRepository in-place."""
    _repository_instance.clear()
    return _repository_instance


