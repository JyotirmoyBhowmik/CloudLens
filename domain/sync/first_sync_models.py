"""Domain Models for First-Sync Progress View (Prompt 15B Items 21, 22, 23).

Enforces:
- Prompt 15B Item 21: Exposes five visible stages with live status:
  1. Discover services
  2. Retrieve pricing data
  3. Retrieve cost data
  4. Retrieve usage data
  5. Discover dependencies
  Each stage shows not started, running, complete, partial or failed, with counts and any error.
- Prompt 15B Item 22: First-sync progress view is the landing destination on wizard completion.
- Prompt 15B Item 23: Per-stage expected duration, elapsed time, and explanation where a stage
  will legitimately take hours (provider billing latency).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from domain.models.base import CanonicalEntity
from domain.models.enums import ConnectorCapability, SyncStageStatus


class FirstSyncStage(BaseModel):
    """Individual stage in the first-sync progress view (Prompt 15B Item 21)."""

    stage_id: str = Field(..., description="Unique machine stage identifier")
    name: str = Field(..., description="Human-readable stage title")
    capability: ConnectorCapability = Field(..., description="Associated connector capability")
    status: SyncStageStatus = Field(
        default=SyncStageStatus.NOT_STARTED,
        description="Current stage status (not_started, running, complete, partial, failed)",
    )
    items_count: int = Field(default=0, description="Normalized items processed in this stage")
    expected_duration_seconds: int = Field(
        ..., description="Standard expected stage runtime in seconds"
    )
    elapsed_time_seconds: int = Field(
        default=0, description="Observed elapsed execution time in seconds"
    )
    latency_explanation: str = Field(
        ..., description="Explanation of stage latency and asynchronous provider delivery mechanics"
    )
    error_message: str | None = Field(
        default=None, description="Detailed diagnostic error if stage partially or fully failed"
    )
    started_at: datetime | None = Field(default=None, description="Stage start timestamp in UTC")
    completed_at: datetime | None = Field(default=None, description="Stage finish timestamp in UTC")


class FirstSyncProgressReport(CanonicalEntity):
    """Aggregated first-sync progress report across the five restored stages (Items 21, 22)."""

    tenant_id: str = Field(..., description="Organization tenant ID")
    session_id: str = Field(..., description="Onboarding wizard session identifier")
    connector_id: str = Field(..., description="Registered cloud connector ID")
    initial_sync_job_id: str = Field(..., description="Associated background sync job identifier")
    overall_status: str = Field(
        default="RUNNING",
        description="Overall progress status (RUNNING, COMPLETED, PARTIAL, FAILED)",
    )
    stages: list[FirstSyncStage] = Field(
        default_factory=list, description="Ordered list of the 5 canonical sync stages"
    )
    total_stages: int = Field(default=5, description="Total stage count (5 canonical stages)")
    completed_stages: int = Field(default=0, description="Count of successfully finalized stages")
    estimated_time_to_first_cost_seconds: int = Field(
        default=14400,
        description="Anticipated latency until first provider billing dataset is landed",
    )
    landing_destination: str = Field(
        ..., description="Post-wizard navigation route (/onboarding/first-sync-progress?...)"
    )


__all__ = [
    "FirstSyncStage",
    "FirstSyncProgressReport",
]
