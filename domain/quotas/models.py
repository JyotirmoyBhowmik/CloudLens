"""Quota, Service Limits, and Headroom Domain Models (Prompt 54).

Enforces:
- Prompt 54: First-class Quota entity with its own history (headroom trend over time for >= 3 months).
- Prompt 54: Consumed-versus-limit tracking per provider, scope, and service.
- Prompt 54: Dynamic lead-time forecasting (alert fires at predicted_exhaustion_date - lead_time - safety_margin).
- Prompt 54: Manual quota limits marked as manual with mandatory source note.
- Prompt 54: Increase request tracking and lead-time calculation.
- Negative constraint: Do NOT present an unknown limit as unlimited (renders as Not Supported / UNKNOWN).
- Negative constraint: Do NOT alert on a fixed percentage where a predicted exhaustion date is computable.
- Negative constraint: Do NOT hard-code any quota name, threshold, or lead time.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from domain.models.base import CanonicalEntity
from domain.models.enums import (
    CloudProvider,
    QuotaCoverage,
    QuotaHeadroomState,
    QuotaIncreaseRequestStatus,
    QuotaScopeType,
    QuotaServiceAffectingType,
)
from domain.models.exceptions import (
    InvalidQuotaLimitException,
    ManualQuotaSourceNoteRequiredException,
)


class QuotaDataPoint(BaseModel):
    """Historical telemetry observation point for quota headroom trend."""

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp of the observation",
    )
    consumed_value: float = Field(
        ...,
        ge=0.0,
        description="Quantity of resource consumed at observation time",
    )
    limit_value: float | None = Field(
        default=None,
        description="Authoritative quota limit at observation time (None if unknown/not supported)",
    )
    headroom_value: float | None = Field(
        default=None,
        description="Absolute headroom (limit - consumed)",
    )
    headroom_pct: float | None = Field(
        default=None,
        description="Percentage headroom remaining relative to limit",
    )


class QuotaEntity(CanonicalEntity):
    """First-class domain entity tracking service limit, consumption, and headroom."""

    tenant_id: str = Field(
        ...,
        description="Tenant boundary isolating quota state",
    )
    provider: CloudProvider = Field(
        ...,
        description="Hyperscaler provider (AWS, Azure, GCP, OCI)",
    )
    scope_type: QuotaScopeType = Field(
        ...,
        description="Scope level where limit applies (ACCOUNT, SUBSCRIPTION, PROJECT, etc.)",
    )
    scope_id: str = Field(
        ...,
        description="Identifier of scope instance (account ID, subscription ID, region, etc.)",
    )
    service_code: str = Field(
        ...,
        description="Cloud service code (e.g. ec2, compute, vpc, storage)",
    )
    quota_code: str = Field(
        ...,
        description="Machine-readable quota identifier from provider or master",
    )
    quota_name: str = Field(
        ...,
        description="Human-readable quota display title",
    )
    description: str | None = Field(
        default=None,
        description="Detailed description of limit purpose and boundary",
    )
    limit_value: float | None = Field(
        default=None,
        description="Maximum allowed capacity. None indicates Not Supported / Unknown limit; NEVER treated as unlimited.",
    )
    consumed_value: float = Field(
        default=0.0,
        ge=0.0,
        description="Current consumed capacity",
    )
    unit: str = Field(
        ...,
        description="Unit of measurement (vCPU, Cores, count, GiB, etc.)",
    )
    is_adjustable: bool = Field(
        default=True,
        description="Whether this quota can be increased via provider support ticket or API",
    )
    is_manual: bool = Field(
        default=False,
        description="True if manually recorded by tenant administrator",
    )
    manual_source_note: str | None = Field(
        default=None,
        description="Mandatory documentation note explaining origin of manual quota setting",
    )
    category: str = Field(
        default="GENERAL",
        description="Resource category (COMPUTE, NETWORK, STORAGE, DATABASE, etc.)",
    )
    exhaustion_impact: QuotaServiceAffectingType = Field(
        default=QuotaServiceAffectingType.SERVICE_AFFECTING,
        description="Whether exhaustion halts service operations or causes API throttling",
    )
    lead_time_days: int = Field(
        default=3,
        ge=0,
        description="Declared provider lead time in business days for increase approval",
    )
    safety_margin_pct: float = Field(
        default=5.0,
        ge=0.0,
        description="Safety buffer margin percentage subtracted from lead-time alerting window",
    )
    warning_headroom_pct: float = Field(
        default=20.0,
        ge=0.0,
        description="Headroom percentage threshold below which warning is raised",
    )
    critical_headroom_pct: float = Field(
        default=10.0,
        ge=0.0,
        description="Headroom percentage threshold below which critical alert is raised",
    )
    status: QuotaHeadroomState = Field(
        default=QuotaHeadroomState.NORMAL,
        description="Computed operational headroom state",
    )
    predicted_exhaustion_date: datetime | None = Field(
        default=None,
        description="Extrapolated date when consumption is forecast to reach or exceed limit",
    )
    alert_trigger_date: datetime | None = Field(
        default=None,
        description="Lead-time adjusted date when alert must trigger (predicted - lead_time - safety_margin)",
    )
    daily_consumption_velocity: float | None = Field(
        default=None,
        description="Average rate of consumption growth per day",
    )
    days_until_exhaustion: float | None = Field(
        default=None,
        description="Forecast number of days remaining until capacity limit reached",
    )
    last_probed_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp of last synchronization or probe from connector/admin",
    )
    history: list[QuotaDataPoint] = Field(
        default_factory=list,
        description="Rolling history of quota observations over at least three months",
    )

    @model_validator(mode="after")
    def validate_manual_quota_integrity(self) -> QuotaEntity:
        """Enforces that manual quotas mandate a source note and valid limit."""
        if self.is_manual:
            if not self.manual_source_note or len(self.manual_source_note.strip()) < 10:
                raise ManualQuotaSourceNoteRequiredException(
                    "Manual quota limit requires a descriptive manual_source_note of at least 10 characters."
                )
            if self.limit_value is None or self.limit_value <= 0.0:
                raise InvalidQuotaLimitException(
                    f"Manual quota limit must be a positive number; got {self.limit_value}."
                )
        return self

    @computed_field
    def headroom_value(self) -> float | None:
        """Returns absolute capacity remaining, or None if limit is unknown."""
        if self.limit_value is None:
            return None
        return max(0.0, self.limit_value - self.consumed_value)

    @computed_field
    def headroom_percentage(self) -> float | None:
        """Returns percentage capacity remaining relative to limit, or None if unknown."""
        if self.limit_value is None or self.limit_value <= 0.0:
            return None
        return max(0.0, (self.limit_value - self.consumed_value) / self.limit_value * 100.0)

    @computed_field
    def is_supported(self) -> bool:
        """Whether this quota has a verified authoritative limit."""
        return self.limit_value is not None


class QuotaIncreaseRequest(BaseModel):
    """Tracks a formal quota increase request with the cloud provider."""

    id: str = Field(
        default_factory=lambda: f"qir-{uuid.uuid4().hex[:10]}",
        description="Unique increase request tracking ID",
    )
    tenant_id: str = Field(
        ...,
        description="Tenant boundary",
    )
    quota_id: str = Field(
        ...,
        description="Associated QuotaEntity ID",
    )
    quota_code: str = Field(
        ...,
        description="Machine-readable quota code",
    )
    provider: CloudProvider = Field(
        ...,
        description="Target cloud provider",
    )
    requested_date: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when request was filed",
    )
    requested_value: float = Field(
        ...,
        gt=0.0,
        description="New requested quota limit",
    )
    current_value: float = Field(
        ...,
        ge=0.0,
        description="Quota limit at time of request",
    )
    justification: str = Field(
        ...,
        min_length=10,
        description="Business justification required by cloud provider",
    )
    status: QuotaIncreaseRequestStatus = Field(
        default=QuotaIncreaseRequestStatus.REQUESTED,
        description="Current workflow status of the request",
    )
    granted_date: datetime | None = Field(
        default=None,
        description="Timestamp when provider granted or fulfilled request",
    )
    actual_lead_time_days: float | None = Field(
        default=None,
        description="Calculated duration in days between request and grant",
    )
    external_ticket_id: str | None = Field(
        default=None,
        description="Provider support ticket or case number (e.g. AWS Case 123456789)",
    )
    notes: str | None = Field(
        default=None,
        description="Internal administrative notes or communication history",
    )

    def mark_granted(self, granted_date: datetime | None = None) -> None:
        """Marks request granted and calculates actual lead time."""
        effective_date = granted_date or datetime.now(UTC)
        self.status = QuotaIncreaseRequestStatus.GRANTED
        self.granted_date = effective_date
        delta = effective_date - self.requested_date
        self.actual_lead_time_days = max(0.0, round(delta.total_seconds() / 86400.0, 2))


class QuotaRemediationTask(BaseModel):
    """Assigned remediation task generated when quota capacity exhaustion is forecast."""

    id: str = Field(
        default_factory=lambda: f"qrt-{uuid.uuid4().hex[:10]}",
        description="Remediation task identifier",
    )
    tenant_id: str = Field(
        ...,
        description="Tenant boundary",
    )
    quota_id: str = Field(
        ...,
        description="Target quota identifier",
    )
    quota_code: str = Field(
        ...,
        description="Quota code",
    )
    title: str = Field(
        ...,
        description="Task summary title",
    )
    description: str = Field(
        ...,
        description="Actionable remediation steps and quota forecast details",
    )
    due_date: datetime = Field(
        ...,
        description="Task due date matching predicted exhaustion date",
    )
    assigned_owner_id: str = Field(
        ...,
        description="Assigned owner ID from ownership chain or FinOps lead",
    )
    status: str = Field(
        default="OPEN",
        description="Task workflow status (OPEN, IN_PROGRESS, RESOLVED)",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Creation timestamp",
    )


# ==============================================================================
# API Request / Response DTOs
# ==============================================================================


class QuotaManualCreateRequest(BaseModel):
    """Payload for registering a manual quota limit (Prompt 54)."""

    provider: CloudProvider
    scope_type: QuotaScopeType
    scope_id: str
    service_code: str
    quota_code: str
    quota_name: str
    description: str | None = None
    limit_value: float = Field(..., gt=0.0)
    consumed_value: float = Field(default=0.0, ge=0.0)
    unit: str
    manual_source_note: str = Field(..., min_length=10)
    is_adjustable: bool = True
    category: str = "GENERAL"
    exhaustion_impact: QuotaServiceAffectingType = QuotaServiceAffectingType.SERVICE_AFFECTING
    lead_time_days: int = 3
    safety_margin_pct: float = 5.0
    warning_headroom_pct: float = 20.0
    critical_headroom_pct: float = 10.0

    @field_validator("provider", mode="before")
    @classmethod
    def parse_provider(cls, v: Any) -> Any:
        if isinstance(v, str):
            return CloudProvider(v.lower())
        return v

    @field_validator("scope_type", mode="before")
    @classmethod
    def parse_scope_type(cls, v: Any) -> Any:
        if isinstance(v, str):
            return QuotaScopeType(v.upper())
        return v


class QuotaIncreaseCreateRequest(BaseModel):
    """Payload to request a quota increase (Prompt 54)."""

    requested_value: float = Field(..., gt=0.0)
    justification: str = Field(..., min_length=10)
    external_ticket_id: str | None = None


class QuotaIncreaseUpdateRequest(BaseModel):
    """Payload to update an increase request status."""

    status: QuotaIncreaseRequestStatus
    granted_date: datetime | None = None
    notes: str | None = None


class QuotaOverrideRequest(BaseModel):
    """Payload to customize headroom threshold and lead-time settings."""

    warning_headroom_pct: float | None = Field(default=None, gt=0.0, le=100.0)
    critical_headroom_pct: float | None = Field(default=None, gt=0.0, le=100.0)
    lead_time_days: int | None = Field(default=None, ge=0)
    safety_margin_pct: float | None = Field(default=None, ge=0.0)
    reason: str = Field(..., min_length=10)


class QuotaSummaryResponse(BaseModel):
    """Aggregated headroom health summary per provider or scope (Prompt 54)."""

    provider: CloudProvider
    total_quotas: int
    normal_count: int
    warning_count: int
    critical_count: int
    exhausted_count: int
    not_supported_count: int
    coverage: QuotaCoverage
    quotas_at_risk: list[QuotaEntity] = Field(default_factory=list)
