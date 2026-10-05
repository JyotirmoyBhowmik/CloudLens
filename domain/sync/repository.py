"""Tenant-Aware Repositories for Sync Jobs, Schedules, and Quarantine Records (Prompt 15).

Enforces:
- Prompt 13 Item 84: Mandatory TenantContext on every public method.
- Mechanical isolation: Queries fail at build/test time without tenant context.
- Thread-safe storage with support for in-memory and database persistence.
"""

from __future__ import annotations

import builtins
import threading
from typing import Any

from domain.models.enums import ConnectorCapability, QuarantineStatus, SyncJobStatus
from domain.sync.first_sync_models import FirstSyncProgressReport
from domain.sync.models import ConnectorSchedule, QuarantineRecord, SyncJob
from domain.tenant.context import TenantContext
from domain.tenant.repository import TenantAwareRepository


class SyncJobRepository(TenantAwareRepository[SyncJob]):
    """Tenant-isolated repository for SyncJob execution audits."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # (tenant_id, job_id) -> SyncJob
        self._jobs: dict[tuple[str, str], SyncJob] = {}

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> SyncJob | None:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            return self._jobs.get((tenant_context.tenant_id, entity_id))

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[SyncJob]:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            tenant_items = [
                job for (tid, _), job in self._jobs.items() if tid == tenant_context.tenant_id
            ]

        # Filter by status if specified in filter_params
        if isinstance(filter_params, dict):
            status_filter = filter_params.get("status")
            if status_filter:
                tenant_items = [j for j in tenant_items if j.status == status_filter]
            conn_filter = filter_params.get("connector_id")
            if conn_filter:
                tenant_items = [j for j in tenant_items if j.connector_id == conn_filter]

        sorted_items = sorted(tenant_items, key=lambda j: j.started_at, reverse=True)
        return sorted_items[offset : offset + limit]

    def save(self, entity: SyncJob, *, tenant_context: TenantContext) -> SyncJob:
        self._validate_tenant_context(tenant_context)
        entity.tenant_id = tenant_context.tenant_id
        with self._lock:
            self._jobs[(tenant_context.tenant_id, entity.id)] = entity
        return entity

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            key = (tenant_context.tenant_id, entity_id)
            if key in self._jobs:
                del self._jobs[key]
                return True
            return False

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            return (tenant_context.tenant_id, entity_id) in self._jobs

    def get_by_idempotency_key(
        self, idempotency_key: str, *, tenant_context: TenantContext
    ) -> SyncJob | None:
        """Retrieves a previously completed job matching the given idempotency key."""
        self._validate_tenant_context(tenant_context)
        with self._lock:
            for (tid, _), job in self._jobs.items():
                if tid == tenant_context.tenant_id and job.idempotency_key == idempotency_key:
                    return job
        return None

    def get_latest_successful(
        self,
        connector_id: str,
        capability: ConnectorCapability,
        *,
        tenant_context: TenantContext,
    ) -> SyncJob | None:
        """Finds the most recent successful sync job for a specific connector capability."""
        self._validate_tenant_context(tenant_context)
        with self._lock:
            matching = [
                job
                for (tid, _), job in self._jobs.items()
                if tid == tenant_context.tenant_id
                and job.connector_id == connector_id
                and (job.capability == capability or job.capability is None)
                and job.status in (SyncJobStatus.COMPLETED, SyncJobStatus.PARTIAL_SUCCESS)
            ]
        if not matching:
            return None
        return max(matching, key=lambda j: j.completed_at or j.started_at)


class QuarantineRepository(TenantAwareRepository[QuarantineRecord]):
    """Tenant-isolated repository for dead-letter quarantine records."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # (tenant_id, record_id) -> QuarantineRecord
        self._records: dict[tuple[str, str], QuarantineRecord] = {}

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> QuarantineRecord | None:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            return self._records.get((tenant_context.tenant_id, entity_id))

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[QuarantineRecord]:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            tenant_items = [
                rec for (tid, _), rec in self._records.items() if tid == tenant_context.tenant_id
            ]

        if isinstance(filter_params, dict):
            status_filter = filter_params.get("status")
            if status_filter:
                tenant_items = [r for r in tenant_items if r.status == status_filter]
            conn_filter = filter_params.get("connector_id")
            if conn_filter:
                tenant_items = [r for r in tenant_items if r.connector_id == conn_filter]

        sorted_items = sorted(tenant_items, key=lambda r: r.quarantined_at, reverse=True)
        return sorted_items[offset : offset + limit]

    def save(self, entity: QuarantineRecord, *, tenant_context: TenantContext) -> QuarantineRecord:
        self._validate_tenant_context(tenant_context)
        entity.tenant_id = tenant_context.tenant_id
        with self._lock:
            self._records[(tenant_context.tenant_id, entity.id)] = entity
        return entity

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            key = (tenant_context.tenant_id, entity_id)
            if key in self._records:
                del self._records[key]
                return True
            return False

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            return (tenant_context.tenant_id, entity_id) in self._records

    def list_by_status(
        self,
        status: QuarantineStatus,
        *,
        tenant_context: TenantContext,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[QuarantineRecord]:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            tenant_items = [
                rec
                for (tid, _), rec in self._records.items()
                if tid == tenant_context.tenant_id and rec.status == status
            ]
        sorted_items = sorted(tenant_items, key=lambda r: r.quarantined_at, reverse=True)
        return sorted_items[offset : offset + limit]


class ConnectorScheduleRepository(TenantAwareRepository[ConnectorSchedule]):
    """Tenant-isolated repository for connector sync schedules."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # (tenant_id, schedule_id) -> ConnectorSchedule
        self._schedules: dict[tuple[str, str], ConnectorSchedule] = {}

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> ConnectorSchedule | None:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            return self._schedules.get((tenant_context.tenant_id, entity_id))

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[ConnectorSchedule]:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            tenant_items = [
                s for (tid, _), s in self._schedules.items() if tid == tenant_context.tenant_id
            ]

        if isinstance(filter_params, dict):
            conn_filter = filter_params.get("connector_id")
            if conn_filter:
                tenant_items = [s for s in tenant_items if s.connector_id == conn_filter]

        sorted_items = sorted(tenant_items, key=lambda s: s.created_at, reverse=True)
        return sorted_items[offset : offset + limit]

    def save(
        self, entity: ConnectorSchedule, *, tenant_context: TenantContext
    ) -> ConnectorSchedule:
        self._validate_tenant_context(tenant_context)
        entity.tenant_id = tenant_context.tenant_id
        with self._lock:
            self._schedules[(tenant_context.tenant_id, entity.id)] = entity
        return entity

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            key = (tenant_context.tenant_id, entity_id)
            if key in self._schedules:
                del self._schedules[key]
                return True
            return False

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            return (tenant_context.tenant_id, entity_id) in self._schedules

    def get_by_connector_and_capability(
        self,
        connector_id: str,
        capability: ConnectorCapability,
        *,
        tenant_context: TenantContext,
    ) -> ConnectorSchedule | None:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            for (tid, _), sched in self._schedules.items():
                if (
                    tid == tenant_context.tenant_id
                    and sched.connector_id == connector_id
                    and sched.capability == capability
                ):
                    return sched
        return None

    def list_for_connector(
        self, connector_id: str, *, tenant_context: TenantContext
    ) -> builtins.list[ConnectorSchedule]:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            return [
                sched
                for (tid, _), sched in self._schedules.items()
                if tid == tenant_context.tenant_id and sched.connector_id == connector_id
            ]


# Singleton repository accessors
_sync_job_repository = SyncJobRepository()
_quarantine_repository = QuarantineRepository()
_connector_schedule_repository = ConnectorScheduleRepository()


class FirstSyncProgressRepository(TenantAwareRepository[FirstSyncProgressReport]):
    """Tenant-isolated repository for FirstSyncProgressReport state tracking (Prompt 15B Items 21, 22)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # (tenant_id, id) -> FirstSyncProgressReport
        self._reports: dict[tuple[str, str], FirstSyncProgressReport] = {}

    def get(
        self, entity_id: str, *, tenant_context: TenantContext
    ) -> FirstSyncProgressReport | None:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            return self._reports.get((tenant_context.tenant_id, entity_id))

    def get_by_session_id(
        self, session_id: str, *, tenant_context: TenantContext
    ) -> FirstSyncProgressReport | None:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            for (tid, _), report in self._reports.items():
                if tid == tenant_context.tenant_id and report.session_id == session_id:
                    return report
        return None

    def get_by_connector_id(
        self, connector_id: str, *, tenant_context: TenantContext
    ) -> FirstSyncProgressReport | None:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            for (tid, _), report in self._reports.items():
                if tid == tenant_context.tenant_id and report.connector_id == connector_id:
                    return report
        return None

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[FirstSyncProgressReport]:
        self._validate_tenant_context(tenant_context)
        _ = filter_params
        with self._lock:
            items = [r for (tid, _), r in self._reports.items() if tid == tenant_context.tenant_id]
        sorted_items = sorted(items, key=lambda r: r.created_at, reverse=True)
        return sorted_items[offset : offset + limit]

    def save(
        self, entity: FirstSyncProgressReport, *, tenant_context: TenantContext
    ) -> FirstSyncProgressReport:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            key = (tenant_context.tenant_id, entity.id)
            self._reports[key] = entity
            return entity

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            key = (tenant_context.tenant_id, entity_id)
            if key in self._reports:
                del self._reports[key]
                return True
            return False

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            return (tenant_context.tenant_id, entity_id) in self._reports


_first_sync_progress_repository = FirstSyncProgressRepository()


def get_first_sync_progress_repository() -> FirstSyncProgressRepository:
    return _first_sync_progress_repository


def get_sync_job_repository() -> SyncJobRepository:
    return _sync_job_repository


def get_quarantine_repository() -> QuarantineRepository:
    return _quarantine_repository


def get_connector_schedule_repository() -> ConnectorScheduleRepository:
    return _connector_schedule_repository


def reset_sync_repositories() -> None:
    """Resets all synchronization repository singletons in-place."""
    with _first_sync_progress_repository._lock:
        _first_sync_progress_repository._reports.clear()
    with _sync_job_repository._lock:
        _sync_job_repository._jobs.clear()
    with _quarantine_repository._lock:
        _quarantine_repository._records.clear()
    with _connector_schedule_repository._lock:
        _connector_schedule_repository._schedules.clear()


