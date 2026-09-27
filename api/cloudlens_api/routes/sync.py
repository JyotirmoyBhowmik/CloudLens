"""CloudLens Sync Orchestration, Quarantine, and Schedule Management API Routes (Prompt 15).

Enforces:
- Prompt 15 Item 97: Execution of all 7 sync types via API.
- Prompt 15 Item 98: Schedule listing and updating with cadence warnings.
- Prompt 15 Item 99: Dead-letter quarantine inspection, per-scope partial failures, lag monitoring.
- Prompt 13 Item 83: Tenant context derived strictly from authenticated identity.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from connectors.simulator.connector import ProviderSimulatorConnector
from connectors.sync.orchestrator import get_sync_orchestrator
from connectors.sync.scheduler import get_sync_scheduler
from domain.models.enums import (
    ConnectorCapability,
    QuarantineStatus,
    SyncJobStatus,
    SyncType,
)
from domain.sync.models import (
    CadenceWarning,
    ConnectorSchedule,
    QuarantineRecord,
    SyncJob,
    SyncLagReport,
)
from domain.sync.repository import (
    get_connector_schedule_repository,
    get_quarantine_repository,
    get_sync_job_repository,
)
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sync", tags=["Sync Orchestration"])


class TriggerSyncRequest(BaseModel):
    """Payload to dispatch a synchronization job."""

    connector_id: str = Field(..., description="Target registered connector ID")
    sync_type: SyncType = Field(default=SyncType.SCHEDULED_SYNC, description="Sync execution mode")
    capability: ConnectorCapability | None = Field(
        default=None, description="Optional specific capability to execute"
    )
    target_scopes: list[str] | None = Field(
        default=None, description="Optional specific scopes to target"
    )
    period_start: datetime | None = Field(default=None, description="Window start time")
    period_end: datetime | None = Field(default=None, description="Window end time")
    dataset_version: str | None = Field(default=None, description="Dataset version for idempotency")
    allow_idempotent_skip: bool = Field(
        default=True, description="Whether to return cached result if already completed"
    )


class UpdateScheduleRequest(BaseModel):
    """Payload to configure a connector schedule."""

    connector_id: str = Field(..., description="Target connector ID")
    capability: ConnectorCapability = Field(..., description="Target capability")
    interval_minutes: int = Field(..., ge=1, description="Interval in minutes")
    lookback_days: int | None = Field(default=None, ge=0, description="Restatement lookback days")
    is_enabled: bool = Field(default=True, description="Whether schedule is active")


class ScheduleUpdateResponse(BaseModel):
    schedule: ConnectorSchedule
    warning: CadenceWarning | None = None


@router.post("/jobs", response_model=SyncJob, status_code=status.HTTP_202_ACCEPTED)
async def trigger_sync_job(
    payload: TriggerSyncRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> SyncJob:
    """Dispatches a synchronization run supporting all seven sync types."""
    cid_low = payload.connector_id.lower()
    if "azure" in cid_low:
        provider_str = "azure"
    elif "gcp" in cid_low:
        provider_str = "gcp"
    elif "oci" in cid_low:
        provider_str = "oci"
    else:
        provider_str = "aws"

    connector = ProviderSimulatorConnector(
        connector_id=payload.connector_id,
        tenant_id=tenant_context.tenant_id,
        profile=provider_str,
    )

    orchestrator = get_sync_orchestrator()
    job = await orchestrator.execute_sync(
        connector=connector,
        sync_type=payload.sync_type,
        tenant_context=tenant_context,
        capability=payload.capability,
        target_scopes=payload.target_scopes,
        period_start=payload.period_start,
        period_end=payload.period_end,
        dataset_version=payload.dataset_version,
        allow_idempotent_skip=payload.allow_idempotent_skip,
    )
    return job


@router.get("/jobs", response_model=list[SyncJob])
async def list_sync_jobs(
    connector_id: str | None = Query(default=None, description="Filter by connector"),
    status_filter: SyncJobStatus | None = Query(
        default=None, alias="status", description="Filter by status"
    ),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> list[SyncJob]:
    """Lists sync jobs for the authenticated tenant with pagination and filters."""
    filter_params: dict[str, Any] = {}
    if connector_id:
        filter_params["connector_id"] = connector_id
    if status_filter:
        filter_params["status"] = status_filter

    repo = get_sync_job_repository()
    return repo.list(
        tenant_context=tenant_context,
        filter_params=filter_params,
        limit=limit,
        offset=offset,
    )


@router.get("/jobs/{job_id}", response_model=SyncJob)
async def get_sync_job(
    job_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> SyncJob:
    """Retrieves detailed status and per-scope outcomes of a sync job."""
    repo = get_sync_job_repository()
    job = repo.get(job_id, tenant_context=tenant_context)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sync job '{job_id}' not found.",
        )
    return job


@router.get("/lag", response_model=SyncLagReport)
async def get_sync_lag(
    connector_id: str = Query(..., description="Target connector ID"),
    capability: ConnectorCapability = Query(..., description="Target capability"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> SyncLagReport:
    """Computes sync lag and freshness metrics for a connector capability (Item 99)."""
    orchestrator = get_sync_orchestrator()
    return orchestrator.get_sync_lag(
        connector_id=connector_id,
        capability=capability,
        tenant_context=tenant_context,
    )


@router.get("/quarantine", response_model=list[QuarantineRecord])
async def list_quarantine_records(
    connector_id: str | None = Query(default=None),
    quarantine_status: QuarantineStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> list[QuarantineRecord]:
    """Lists dead-letter quarantine records with diagnostic reasons visible to operators (Item 99)."""
    filter_params: dict[str, Any] = {}
    if connector_id:
        filter_params["connector_id"] = connector_id
    if quarantine_status:
        filter_params["status"] = quarantine_status

    repo = get_quarantine_repository()
    return repo.list(
        tenant_context=tenant_context,
        filter_params=filter_params,
        limit=limit,
        offset=offset,
    )


@router.post("/quarantine/{record_id}/reprocess", response_model=QuarantineRecord)
async def reprocess_quarantined_record(
    record_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> QuarantineRecord:
    """Reprocesses a quarantined dead-letter record after operator review."""
    repo = get_quarantine_repository()
    record = repo.get(record_id, tenant_context=tenant_context)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quarantine record '{record_id}' not found.",
        )
    record.status = QuarantineStatus.REPROCESSED
    record.resolved_at = datetime.now(UTC)
    record.resolved_by = tenant_context.user_id
    saved = repo.save(record, tenant_context=tenant_context)
    return saved


@router.get("/schedules", response_model=list[ConnectorSchedule])
async def list_connector_schedules(
    connector_id: str = Query(..., description="Target connector ID"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> list[ConnectorSchedule]:
    """Lists configured schedules for a connector (Item 98)."""
    repo = get_connector_schedule_repository()
    return repo.list_for_connector(connector_id=connector_id, tenant_context=tenant_context)


@router.put("/schedules", response_model=ScheduleUpdateResponse)
async def update_connector_schedule(
    payload: UpdateScheduleRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> ScheduleUpdateResponse:
    """Updates a connector schedule and returns cadence warning if interval is unlikely to yield new data (Item 98)."""
    scheduler = get_sync_scheduler()
    sched, warning = scheduler.update_schedule(
        connector_id=payload.connector_id,
        capability=payload.capability,
        interval_minutes=payload.interval_minutes,
        lookback_days=payload.lookback_days,
        is_enabled=payload.is_enabled,
        tenant_context=tenant_context,
    )
    return ScheduleUpdateResponse(schedule=sched, warning=warning)
