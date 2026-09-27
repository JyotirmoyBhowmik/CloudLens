"""Domain Models for Synchronization Orchestration, Schedules, and Quarantine (Prompt 15).

Enforces:
- Prompt 15 Item 97: Seven sync types with comprehensive tracking.
- Prompt 15 Item 98: Per-connector, per-capability schedules.
- Prompt 15 Item 99: Partial failure isolation, quarantine records, lag reports.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from domain.models.base import CanonicalEntity
from domain.models.enums import (
    ConnectorCapability,
    QuarantineReason,
    QuarantineStatus,
    SyncJobStatus,
    SyncType,
)
from domain.models.governance import SyncJob


class SyncScopeResult(BaseModel):
    """Isolated per-scope execution outcome for partial failure tracking (Prompt 15 Item 99)."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str = Field(..., description="Parent sync job identifier")
    scope_id: str = Field(..., description="Target cloud account/subscription/project scope")
    status: str = Field(default="SUCCESS", description="Outcome status (SUCCESS, FAILED, SKIPPED)")
    records_ingested: int = Field(
        default=0, description="Normalized records ingested from this scope"
    )
    error_message: str | None = Field(
        default=None, description="Scope-level error message if failed"
    )
    error_code: str | None = Field(default=None, description="Scope-level error code if failed")
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = Field(default=None)


class QuarantineRecord(CanonicalEntity):
    """Dead-letter quarantine record preserving defective payloads with operator visibility (Prompt 15 Item 99)."""

    tenant_id: str = Field(..., description="Tenant identifier owning the payload")
    connector_id: str = Field(..., description="Connector from which payload originated")
    job_id: str | None = Field(default=None, description="Associated sync job ID if known")
    capability: ConnectorCapability = Field(
        ..., description="Capability that collected the payload"
    )
    quarantine_reason: QuarantineReason = Field(..., description="Failure classification")
    error_details: str = Field(..., description="Detailed diagnostic error message")
    payload_summary: dict[str, Any] = Field(
        default_factory=dict, description="Metadata and sample fields of quarantined payload"
    )
    raw_payload_path: str | None = Field(
        default=None, description="Object storage path to preserved raw payload"
    )
    status: QuarantineStatus = Field(
        default=QuarantineStatus.QUARANTINED, description="Lifecycle status"
    )
    quarantined_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = Field(default=None)
    resolved_by: str | None = Field(default=None)


class ConnectorSchedule(CanonicalEntity):
    """Configured synchronization schedule for a specific connector capability (Prompt 15 Item 98)."""

    tenant_id: str = Field(..., description="Tenant owning the schedule")
    connector_id: str = Field(..., description="Target connector identifier")
    capability: ConnectorCapability = Field(..., description="Capability governed by this schedule")
    interval_minutes: int = Field(..., description="Recurrence interval in minutes")
    cron_expression: str | None = Field(
        default=None, description="Optional cron schedule expression"
    )
    lookback_days: int = Field(default=0, description="Restatement lookback window in days")
    is_enabled: bool = Field(
        default=True, description="Whether this schedule is actively dispatched"
    )
    last_run_at: datetime | None = Field(default=None)
    last_successful_run_at: datetime | None = Field(default=None)
    next_run_at: datetime | None = Field(default=None)


class SyncLagReport(BaseModel):
    """Freshness and sync lag metrics for a connector capability (Prompt 15 Item 99)."""

    connector_id: str = Field(..., description="Connector identifier")
    capability: ConnectorCapability = Field(..., description="Target capability")
    last_successful_sync: datetime | None = Field(
        default=None, description="Timestamp of last success"
    )
    lag_seconds: float = Field(..., description="Current lag in seconds (now - last_success)")
    is_stale: bool = Field(
        default=False, description="Whether lag exceeds configured freshness limit"
    )
    warning: str | None = Field(default=None, description="Operator-facing lag warning message")


class CadenceWarning(BaseModel):
    """Warning generated when a schedule interval is unlikely to yield new data (Prompt 15 Item 98)."""

    capability: ConnectorCapability
    interval_hours: float
    recommended_min_hours: float
    warning_message: str


__all__ = [
    "SyncJob",
    "SyncScopeResult",
    "QuarantineRecord",
    "ConnectorSchedule",
    "SyncLagReport",
    "CadenceWarning",
    "SyncJobStatus",
    "SyncType",
    "QuarantineReason",
    "QuarantineStatus",
]
