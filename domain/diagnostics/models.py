"""Domain Models for Connector Diagnostics and Failure Recovery (Prompt 15 Items 104, 105).

Enforces:
- Prompt 15 Item 104: Per-capability attempt, success, verbatim error + explanation, lag, headroom.
- Prompt 15 Item 105: Outage gap reports, recovery checkpoints, and degradation tracking.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from domain.models.enums import ConnectorCapability, SyncType


class CapabilityDiagnostic(BaseModel):
    """Detailed health, freshness, and error diagnostics for a single capability (Prompt 15 Item 104)."""

    capability: ConnectorCapability = Field(..., description="Target capability")
    last_attempt_at: datetime | None = Field(
        default=None, description="Timestamp of most recent attempt"
    )
    last_success_at: datetime | None = Field(
        default=None, description="Timestamp of most recent success"
    )
    last_error_verbatim: str | None = Field(
        default=None, description="Exact verbatim provider error string"
    )
    last_error_explanation: str | None = Field(
        default=None, description="Human-readable plain language explanation of the error"
    )
    freshness_lag_seconds: float | None = Field(
        default=None, description="Seconds elapsed since last successful sync"
    )
    quota_headroom_percent: float = Field(
        default=100.0, description="Remaining hourly API request headroom percentage"
    )
    status_display: str = Field(
        default="Operational",
        description="Presentation status: 'Operational', 'Degraded', 'Failed', 'Not Supported'",
    )


class ConnectorDiagnosticReport(BaseModel):
    """Aggregated diagnostics across all declared capabilities for a connector (Prompt 15 Item 104)."""

    connector_id: str = Field(..., description="Connector identifier")
    tenant_id: str = Field(..., description="Tenant owning the connector")
    overall_state: str = Field(..., description="Overall lifecycle state")
    capabilities: list[CapabilityDiagnostic] = Field(
        default_factory=list, description="Per-capability diagnostic breakdown"
    )
    quota_headroom_total: float = Field(
        default=100.0, description="Lowest headroom percent across capabilities"
    )
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OutageGapReport(BaseModel):
    """Outage time window analysis and gap identification for backfill (Prompt 15 Item 105)."""

    connector_id: str = Field(..., description="Connector that experienced the outage")
    tenant_id: str = Field(..., description="Tenant identifier")
    outage_start: datetime = Field(..., description="Estimated beginning of outage / degradation")
    outage_end: datetime = Field(..., description="Timestamp when connectivity was restored")
    duration_hours: float = Field(..., description="Total duration of the gap in hours")
    missed_periods: list[dict[str, Any]] = Field(
        default_factory=list, description="List of uncollected time intervals"
    )
    missed_scopes: list[str] = Field(
        default_factory=list, description="Scopes affected by the outage"
    )
    recommended_backfill_types: list[SyncType] = Field(
        default_factory=list, description="Recommended sync types to recover missed data"
    )


__all__ = [
    "CapabilityDiagnostic",
    "ConnectorDiagnosticReport",
    "OutageGapReport",
]
