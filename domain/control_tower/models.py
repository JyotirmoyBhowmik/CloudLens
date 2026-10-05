"""Domain Models for Platform Control Tower (Prompt R-CT).

Provides models for:
- 14 Operational Panel Statuses (Green / Amber / Red / Grey)
- Cross-tenant Aggregated Diagnostics and Telemetry
- Blast Radius Assessment for Operational Actions
- Audited Action Requests and Confirmations
"""

from __future__ import annotations

from datetime import datetime, UTC
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, Field


class PanelStatus(StrEnum):
    """Panel status indicators for Control Tower monitoring."""

    GREEN = "green"
    AMBER = "amber"
    RED = "red"
    GREY = "grey"


class StatusText(StrEnum):
    """Accessible text equivalents ensuring status is never communicated by color alone."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


def get_status_label(status: PanelStatus | str) -> str:
    """Returns accessible text label for status."""
    val = status.value if isinstance(status, PanelStatus) else str(status)
    if val == "green":
        return StatusText.HEALTHY.value
    if val == "amber":
        return StatusText.DEGRADED.value
    if val == "red":
        return StatusText.CRITICAL.value
    return StatusText.UNKNOWN.value


class ControlTowerPanel(BaseModel):
    """Overview summary for a single Control Tower monitoring panel."""

    id: str = Field(description="Unique panel identifier")
    name: str = Field(description="Human-readable panel title")
    status: PanelStatus = Field(description="Traffic light status indicator (green/amber/red/grey)")
    status_label: str = Field(description="Accessible status string (never color alone)")
    reason: str = Field(description="Empirical explanation of the current status")
    metrics: dict[str, Any] = Field(default_factory=dict, description="Key operational metric values")
    last_updated: str = Field(description="ISO 8601 UTC timestamp of last probe/update")
    grafana_url: str = Field(description="SSO deep link to corresponding Grafana dashboard")


class ControlTowerOverview(BaseModel):
    """Complete Control Tower status overview containing all 14 panels."""

    overall_status: PanelStatus = Field(description="Worst-case aggregated platform health status")
    overall_label: str = Field(description="Accessible overall health label")
    maintenance_mode: bool = Field(default=False, description="Whether platform maintenance mode is engaged")
    panels: list[ControlTowerPanel] = Field(description="Collection of all 14 monitoring panels")
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class BlastRadius(BaseModel):
    """Predicted operational impact and affected entities before action execution."""

    action: str = Field(description="Target action identifier")
    affected_tenants: list[str] = Field(description="Tenants impacted by this action")
    affected_connectors: list[str] = Field(default_factory=list, description="Connectors impacted")
    affected_queues: list[str] = Field(default_factory=list, description="Background task queues impacted")
    impact_summary: str = Field(description="Detailed description of operational side-effects")
    requires_confirmation: bool = Field(default=True, description="Enforces explicit user confirmation")


class ControlTowerActionRequest(BaseModel):
    """Payload for executing sensitive operational actions in Control Tower."""

    action: str = Field(description="Action name to execute")
    params: dict[str, Any] = Field(default_factory=dict, description="Action parameters")
    reason: str = Field(min_length=20, description="Mandatory operational justification (>= 20 chars)")
    step_up_token: str | None = Field(default=None, description="Step-up MFA authentication proof token")
    confirm: bool = Field(default=False, description="Set True to execute; False returns blast radius only")


class ControlTowerActionResult(BaseModel):
    """Execution receipt for an audited Control Tower administrative action."""

    status: str = Field(description="Execution outcome ('executed' or 'staged')")
    action: str = Field(description="Executed action name")
    reason: str = Field(description="Operational justification recorded in audit log")
    actor: str = Field(description="Authenticated operator user ID or email")
    blast_radius: BlastRadius = Field(description="Affected scope evaluated prior to execution")
    result: dict[str, Any] = Field(description="Technical result of the execution")
    audit_event_id: str = Field(description="Cryptographically linked AuditEvent ID")
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
