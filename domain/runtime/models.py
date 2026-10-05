"""Runtime Model, Schedule Adherence, and Exemption Data Models (Prompt 26).

Enforces:
- Prompt 26: Six runtime states with distinct meanings:
  RUNNING, STOPPED, PARTIALLY_RUNNING, NOT_APPLICABLE, UNKNOWN, NO_DATA.
- Prompt 26: Unknown and No Data are NEVER rendered as compliant and NEVER coloured green.
- Prompt 26: Do not conflate Stopped with Not applicable.
- Prompt 26: Named schedule model with timezone, working days, exclusion dates, and maintenance windows.
- Prompt 26: Adherence evaluation with warning and critical tolerances.
- Prompt 26: Mandatory monetary valuation on every schedule breach.
- Prompt 26: Temporary exemption mechanism with mandatory reason (>= 20 chars) and auto-expiry.
- Prompt 26: Phase 2 idle and underutilisation signals behind a feature flag (ready but disabled).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

from domain.models.base import CanonicalEntity
from domain.models.exceptions import (
    ExemptionReasonTooShortException,
    RuntimeStateNonComplianceException,
)

# ==============================================================================
# 1. Six-State Runtime Model & Discipline
# ==============================================================================


class RuntimeState(StrEnum):
    """The six canonical runtime states per Prompt 26 Item 158.

    Distinct meanings:
    - RUNNING: Resource is active, healthy, and consuming compute/runtime units.
    - STOPPED: Resource compute is halted; attached persistent storage remains billable.
    - PARTIALLY_RUNNING: Clustered/composite resource where some nodes are executing while others are halted.
    - NOT_APPLICABLE: Resource does not possess a start/stop runtime lifecycle (e.g. S3, Route53, KMS).
    - UNKNOWN: Operational state could not be verified by provider telemetry.
    - NO_DATA: Telemetry window contains an unobserved data gap.
    """

    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    PARTIALLY_RUNNING = "PARTIALLY_RUNNING"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"
    NO_DATA = "NO_DATA"

    def is_active_execution(self) -> bool:
        """Returns True if the resource is actively consuming runtime execution units."""
        return self in (RuntimeState.RUNNING, RuntimeState.PARTIALLY_RUNNING)

    def is_compliant_permitted(self) -> bool:
        """Enforces that UNKNOWN and NO_DATA can never be evaluated or rendered as compliant."""
        return self not in (RuntimeState.UNKNOWN, RuntimeState.NO_DATA)

    def is_green_permitted(self) -> bool:
        """Enforces that UNKNOWN and NO_DATA must NEVER be coloured green."""
        return self not in (RuntimeState.UNKNOWN, RuntimeState.NO_DATA)

    def get_default_color_hex(self) -> str:
        """Returns the canonical UI color hex enforcing the non-green discipline for Unknown & No Data."""
        if self == RuntimeState.RUNNING:
            return "#10b981"  # no-hardcode-allow: reason="Canonical UI runtime state hex colour code", reviewer="Prompt-48-Audit"
        if self == RuntimeState.STOPPED:
            return "#64748b"  # no-hardcode-allow: reason="Canonical UI runtime state hex colour code", reviewer="Prompt-48-Audit"
        if self == RuntimeState.PARTIALLY_RUNNING:
            return "#f59e0b"  # no-hardcode-allow: reason="Canonical UI runtime state hex colour code", reviewer="Prompt-48-Audit"
        if self == RuntimeState.NOT_APPLICABLE:
            return "#94a3b8"  # no-hardcode-allow: reason="Canonical UI runtime state hex colour code", reviewer="Prompt-48-Audit"
        if self == RuntimeState.UNKNOWN:
            # STRICT: Prompt 26: Unknown must NEVER be green
            return "#94a3b8"  # no-hardcode-allow: reason="Canonical UI runtime state hex colour code", reviewer="Prompt-48-Audit"
        if self == RuntimeState.NO_DATA:
            # STRICT: Prompt 26: No Data must NEVER be green
            return "#94a3b8"  # no-hardcode-allow: reason="Canonical UI runtime state hex colour code", reviewer="Prompt-48-Audit"
        return "#94a3b8"  # no-hardcode-allow: reason="Canonical UI runtime state hex colour code", reviewer="Prompt-48-Audit"

    @staticmethod
    def assert_not_conflated(state_a: RuntimeState, state_b: RuntimeState) -> None:
        """Enforces Prompt 26 negative constraint: 'Do not conflate Stopped with Not applicable'."""
        if (state_a == RuntimeState.STOPPED and state_b == RuntimeState.NOT_APPLICABLE) or (
            state_a == RuntimeState.NOT_APPLICABLE and state_b == RuntimeState.STOPPED
        ):
            raise RuntimeStateNonComplianceException(
                state=state_a.value,
                detail="STOPPED and NOT_APPLICABLE are strictly non-conflatable distinct states.",
            )


# ==============================================================================
# 2. Schedule & Workload Types
# ==============================================================================


class WorkloadType(StrEnum):
    """Categorisation of workload execution profile (RUN-009)."""

    CONTINUOUS_24X7 = "CONTINUOUS_24X7"
    SCHEDULE_BASED = "SCHEDULE_BASED"
    BURST_WORKLOAD = "BURST_WORKLOAD"


class ScheduleLevel(StrEnum):
    """Hierarchy level for attaching operational runtime schedules."""

    RESOURCE = "RESOURCE"
    SERVICE = "SERVICE"
    SCOPE = "SCOPE"
    ENVIRONMENT = "ENVIRONMENT"
    TENANT = "TENANT"


class AdherenceStatus(StrEnum):
    """Adherence evaluation status classification."""

    COMPLIANT = "COMPLIANT"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    EXEMPT = "EXEMPT"
    UNKNOWN = "UNKNOWN"
    NO_DATA = "NO_DATA"
    NOT_APPLICABLE = "NOT_APPLICABLE"

    def is_compliant(self) -> bool:
        """Returns True if the adherence state satisfies organizational approval."""
        return self in (
            AdherenceStatus.COMPLIANT,
            AdherenceStatus.EXEMPT,
            AdherenceStatus.NOT_APPLICABLE,
        )

    def is_green_permitted(self) -> bool:
        """Enforces that UNKNOWN, NO_DATA, WARNING, and CRITICAL are never rendered green."""
        return self == AdherenceStatus.COMPLIANT

    def get_badge_color(self) -> str:
        """Returns the canonical badge color enforcing the strict non-green rule."""
        if self == AdherenceStatus.COMPLIANT:
            return "#10b981"  # no-hardcode-allow: reason="Canonical UI adherence badge hex colour code", reviewer="Prompt-48-Audit"
        if self == AdherenceStatus.EXEMPT:
            return "#3b82f6"  # no-hardcode-allow: reason="Canonical UI adherence badge hex colour code", reviewer="Prompt-48-Audit"
        if self == AdherenceStatus.WARNING:
            return "#f59e0b"  # no-hardcode-allow: reason="Canonical UI adherence badge hex colour code", reviewer="Prompt-48-Audit"
        if self == AdherenceStatus.CRITICAL:
            return "#ef4444"  # no-hardcode-allow: reason="Canonical UI adherence badge hex colour code", reviewer="Prompt-48-Audit"
        if self == AdherenceStatus.UNKNOWN:
            # STRICT: never green
            return "#94a3b8"  # no-hardcode-allow: reason="Canonical UI adherence badge hex colour code", reviewer="Prompt-48-Audit"
        if self == AdherenceStatus.NO_DATA:
            # STRICT: never green
            return "#94a3b8"  # no-hardcode-allow: reason="Canonical UI adherence badge hex colour code", reviewer="Prompt-48-Audit"
        if self == AdherenceStatus.NOT_APPLICABLE:
            return "#94a3b8"  # no-hardcode-allow: reason="Canonical UI adherence badge hex colour code", reviewer="Prompt-48-Audit"
        return "#94a3b8"  # no-hardcode-allow: reason="Canonical UI adherence badge hex colour code", reviewer="Prompt-48-Audit"


# ==============================================================================
# 3. Schedule Definitions & Attachments
# ==============================================================================


class MaintenanceWindow(BaseModel):
    """Window of allowed execution outside standard schedule (e.g. patching, backups)."""

    id: str = Field(default_factory=lambda: f"mw-{uuid.uuid4().hex[:8]}")
    name: str = Field(..., description="Descriptive name of maintenance window")
    day_of_week: int | None = Field(
        default=None, description="ISO day of week (1=Mon ... 7=Sun) for recurring windows"
    )
    start_time: str = Field(default="02:00", description="Start time in HH:MM (24-hour format)")
    end_time: str = Field(default="04:00", description="End time in HH:MM (24-hour format)")
    is_recurring: bool = Field(default=True, description="Whether window recurs weekly")
    specific_date: str | None = Field(
        default=None, description="Optional specific date YYYY-MM-DD for one-off windows"
    )


class NamedSchedule(BaseModel):
    """Named operational runtime schedule with timezone, working days, and tolerances."""

    id: str = Field(..., description="Unique schedule code (e.g. WW_STANDARD_MON_FRI)")
    name: str = Field(..., description="Human-readable schedule name")
    description: str = Field(..., description="Operational schedule purpose and scope")
    timezone: str = Field(
        default="UTC", description="IANA timezone identifier (e.g. UTC, Europe/London)"
    )
    workload_type: WorkloadType = Field(
        default=WorkloadType.SCHEDULE_BASED,
        description="Workload profile (SCHEDULE_BASED, CONTINUOUS_24X7, BURST)",
    )
    working_days: list[int] = Field(
        default_factory=lambda: [1, 2, 3, 4, 5],
        description="ISO working days where running is approved (1=Mon, 7=Sun)",
    )
    daily_start_time: str = Field(
        default="08:00", description="Approved daily start time in HH:MM (24-hour format)"
    )
    daily_end_time: str = Field(
        default="18:00", description="Approved daily shutdown time in HH:MM (24-hour format)"
    )
    exclusion_dates: list[str] = Field(
        default_factory=list,
        description="Public holidays / exclusion dates in YYYY-MM-DD where running is not approved",
    )
    maintenance_windows: list[MaintenanceWindow] = Field(
        default_factory=list,
        description="Approved maintenance windows permitting execution outside standard hours",
    )
    warning_tolerance_hours: Decimal = Field(
        default=Decimal("1.0"),
        description="Out-of-schedule hours permitted before raising WARNING status",
    )
    critical_tolerance_hours: Decimal = Field(
        default=Decimal("4.0"),
        description="Out-of-schedule hours permitted before escalating to CRITICAL status",
    )
    warning_tolerance_pct: Decimal = Field(
        default=Decimal("5.0"),
        description="Percentage of schedule hours permitted before raising WARNING status",
    )
    critical_tolerance_pct: Decimal = Field(
        default=Decimal("10.0"),
        description="Percentage of schedule hours permitted before escalating to CRITICAL status",
    )


class ScheduleAttachment(BaseModel):
    """Attachment of a named schedule at resource, service, scope, environment, or tenant level."""

    id: str = Field(default_factory=lambda: f"sched-att-{uuid.uuid4().hex[:8]}")
    schedule_id: str = Field(..., description="Target NamedSchedule ID")
    level: ScheduleLevel = Field(..., description="Attachment hierarchy level")
    target_id: str = Field(
        ..., description="Identifier of the target resource, service, scope, env, or tenant"
    )
    environment: str | None = Field(
        default=None,
        description="Associated environment tier (production, staging, development, sandbox)",
    )
    business_justification: str | None = Field(
        default=None,
        description="Mandatory business rationale for running 24x7 in non-production (BR-007)",
    )
    attached_by: str = Field(default="system", description="Actor who assigned the schedule")
    attached_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when schedule was attached",
    )


# ==============================================================================
# 4. Runtime Observations & Telemetry
# ==============================================================================


class RuntimeObservation(BaseModel):
    """Discrete runtime state observation record."""

    id: str = Field(default_factory=lambda: f"obs-{uuid.uuid4().hex[:8]}")
    resource_id: str = Field(..., description="Target canonical resource ID")
    interval_start: datetime = Field(..., description="Observation interval start in UTC")
    interval_end: datetime = Field(..., description="Observation interval end in UTC")
    state: RuntimeState = Field(..., description="Observed operational runtime state")
    observed_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Observation capture timestamp in UTC",
    )
    raw_provider_status: str | None = Field(
        default=None, description="Verbatim provider native status string"
    )


# ==============================================================================
# 5. Temporary Runtime Exemptions
# ==============================================================================


class RuntimeExemption(BaseModel):
    """Time-boxed runtime schedule exemption with mandatory recorded reason and auto-expiry.

    Enforces:
    - RUN-005 / FR-254: Time-boxed, requires recorded justification, fully audited, expires automatically.
    - AC-062: Suppresses alert, appears in active reports, and expires.
    - Minimum justification length >= 20 characters per enterprise audit standard.
    """

    id: str = Field(default_factory=lambda: f"exemp-{uuid.uuid4().hex[:8]}")
    tenant_id: str = Field(..., description="Organization tenant ID")
    resource_id: str = Field(..., description="Target canonical resource ID")
    schedule_id: str | None = Field(
        default=None, description="Specific schedule exempted from, or None for all"
    )
    reason: str = Field(
        ...,
        description="Mandatory business justification (minimum 20 characters)",
    )
    created_by: str = Field(..., description="Identity of actor who requested exemption")
    approved_by: str | None = Field(
        default=None, description="Identity of approver (or supervisor for step-up)"
    )
    valid_from: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp from which exemption is active",
    )
    expires_at: datetime = Field(
        ..., description="Mandatory expiration timestamp in UTC after which exemption reverts"
    )
    is_active: bool = Field(default=True, description="Whether exemption is actively in effect")

    @field_validator("reason")
    @classmethod
    def validate_reason_length(cls, val: str) -> str:
        trimmed = val.strip()
        min_chars = 20
        if len(trimmed) < min_chars:
            raise ExemptionReasonTooShortException(length=len(trimmed), min_length=min_chars)
        return trimmed

    def is_expired(self, as_of: datetime | None = None) -> bool:
        """Determines whether the exemption has expired at the specified timestamp."""
        check_time = as_of or datetime.now(UTC)
        return check_time >= self.expires_at


# ==============================================================================
# 6. Schedule Adherence Evaluation Result (FOCUS / Canonical Entity)
# ==============================================================================


class ScheduleAdherenceResult(CanonicalEntity):
    """Comprehensive adherence evaluation result for a resource over an evaluation window.

    Enforces:
    - Mandatory monetary valuation: breach_cost carries a calculated financial amount.
    - Non-compliance discipline: UNKNOWN and NO_DATA are never compliant and never green.
    """

    tenant_id: str = Field(..., description="Organization tenant ID")
    resource_id: str = Field(..., description="Canonical resource ID")
    resource_name: str | None = Field(default=None, description="Human-readable resource name")
    environment: str = Field(
        default="production",
        description="Environment tier (production, staging, development, sandbox)",
    )
    evaluation_window_start: datetime = Field(
        ..., description="Evaluation window start timestamp in UTC"
    )
    evaluation_window_end: datetime = Field(
        ..., description="Evaluation window end timestamp in UTC"
    )
    schedule_id: str = Field(..., description="Resolved NamedSchedule ID")
    schedule_name: str = Field(..., description="Resolved NamedSchedule human name")
    runtime_state: RuntimeState = Field(
        ..., description="Observed predominant runtime state across window"
    )
    adherence_status: AdherenceStatus = Field(..., description="Evaluated adherence status")
    is_compliant: bool = Field(
        ...,
        description="Whether runtime complied with organizational approved schedule",
    )
    color_hex: str = Field(
        ..., description="Rendered status color hex enforcing non-green for Unknown/No Data"
    )
    expected_running_hours: Decimal = Field(
        ..., description="Hours approved by schedule to run in window"
    )
    actual_running_hours: Decimal = Field(
        ..., description="Hours actually observed running in window"
    )
    excess_running_hours: Decimal = Field(
        ..., description="Hours run outside approved schedule (unapproved running)"
    )
    shortfall_running_hours: Decimal = Field(
        default=Decimal("0.0"),
        description="Hours resource was stopped when approved to run",
    )
    hourly_rate: Decimal = Field(
        ..., description="Effective hourly cost rate applied to compute breach valuation"
    )
    currency: str = Field(default="USD", description="Billing currency")
    breach_cost: Decimal = Field(
        ...,
        description="Monetary value of unapproved excess running (excess_running_hours * hourly_rate)",
    )
    projected_monthly_excess_cost: Decimal = Field(
        default=Decimal("0.0"),
        description="Projected monthly financial waste if out-of-schedule pattern continues",
    )
    exemption_id: str | None = Field(
        default=None, description="Associated active exemption ID suppressing alert"
    )
    exemption_reason: str | None = Field(
        default=None, description="Recorded justification of active exemption"
    )
    evaluated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when evaluation was executed",
    )
    notes: str | None = Field(
        default=None, description="Evaluation rationale, derivation, and breakdown notes"
    )

    @model_validator(mode="after")
    def validate_non_compliance_and_color_rules(self) -> ScheduleAdherenceResult:
        """Enforces that Unknown and No Data are NEVER rendered as compliant and NEVER green."""
        green_hexes = {"#10b981", "#22c55e", "#16a34a", "#15803d", "green"}  # no-hardcode-allow: reason="Disallowed green shade hex values for runtime compliance validation", reviewer="Prompt-48-Audit"
        is_unknown_or_nodata = self.runtime_state in (
            RuntimeState.UNKNOWN,
            RuntimeState.NO_DATA,
        ) or self.adherence_status in (AdherenceStatus.UNKNOWN, AdherenceStatus.NO_DATA)
        if is_unknown_or_nodata:
            if self.is_compliant is True:
                raise RuntimeStateNonComplianceException(
                    state=str(self.runtime_state or self.adherence_status),
                    detail="Unknown and No Data must NEVER be rendered as compliant.",
                )
            if self.color_hex.lower() in green_hexes:
                raise RuntimeStateNonComplianceException(
                    state=str(self.runtime_state or self.adherence_status),
                    detail="Unknown and No Data must NEVER be coloured green.",
                )
        return self


# ==============================================================================
# 7. Phase 2 Idle & Underutilisation Signals (Flag-Gated)
# ==============================================================================


class IdleDetectionSensitivity(StrEnum):
    """Sensitivity configuration for Phase 2 idle detection."""

    CONSERVATIVE = "CONSERVATIVE"
    BALANCED = "BALANCED"
    AGGRESSIVE = "AGGRESSIVE"


class IdleSignalType(StrEnum):
    """Five Phase 2 idle and underutilisation signal categories."""

    IDLE_COMPUTE = "IDLE_COMPUTE"
    IDLE_STORAGE = "IDLE_STORAGE"
    ORPHANED_RESOURCE = "ORPHANED_RESOURCE"
    ZERO_USAGE_INCURRING_COST = "ZERO_USAGE_INCURRING_COST"
    OVERSIZED_RESOURCE = "OVERSIZED_RESOURCE"


class IdleResourceFinding(BaseModel):
    """Finding descriptor for an idle or underutilised cloud resource."""

    resource_id: str = Field(..., description="Target canonical resource ID")
    signal_type: IdleSignalType = Field(..., description="Signal classification")
    description: str = Field(..., description="Technical detail and evidence")
    observed_metric_value: Decimal = Field(
        ..., description="Observed metric value (e.g. 1.2% CPU or 0 IOPS)"
    )
    threshold_value: Decimal = Field(..., description="Configured sensitivity floor threshold")
    waste_estimate_monthly: Decimal = Field(
        ..., description="Estimated monthly financial waste if not decommissioned"
    )
    currency: str = Field(default="USD", description="Currency code")
    recommended_action: str = Field(
        ..., description="Recommended remediation (e.g. Stop, Snapshot and Delete, Resize)"
    )


# ==============================================================================
# 8. API Request & Filter DTOs
# ==============================================================================


class AdherenceEvaluateRequest(BaseModel):
    """Request payload to trigger schedule adherence evaluation."""

    resource_id: str = Field(..., description="Canonical resource ID to evaluate")
    start_time: datetime = Field(..., description="Evaluation window start in UTC")
    end_time: datetime = Field(..., description="Evaluation window end in UTC")
    hourly_rate: Decimal | None = Field(
        default=None,
        description="Optional explicit hourly rate; if omitted, resolved from pricing engine",
    )
    currency: str = Field(default="USD", description="Billing currency")
    environment: str | None = Field(default=None, description="Resource environment tier")


class RuntimeExemptionCreateRequest(BaseModel):
    """Request payload to create a temporary runtime exemption."""

    resource_id: str = Field(..., description="Canonical resource ID to exempt")
    reason: str = Field(..., description="Mandatory recorded justification (minimum 20 characters)")
    expires_at: datetime = Field(
        ..., description="Expiration timestamp in UTC when exemption automatically reverts"
    )
    schedule_id: str | None = Field(
        default=None, description="Optional specific schedule exempted from"
    )
    valid_from: datetime | None = Field(
        default=None, description="Optional start timestamp (defaults to now)"
    )


class ScheduleCreateRequest(BaseModel):
    """Request payload to create a named operational runtime schedule."""

    id: str = Field(..., description="Unique schedule identifier")
    name: str = Field(..., description="Human-readable schedule name")
    description: str = Field(..., description="Schedule description")
    timezone: str = Field(default="UTC", description="IANA timezone")
    workload_type: WorkloadType = Field(default=WorkloadType.SCHEDULE_BASED)
    working_days: list[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5])
    daily_start_time: str = Field(default="08:00")
    daily_end_time: str = Field(default="18:00")
    exclusion_dates: list[str] = Field(default_factory=list)
    warning_tolerance_hours: Decimal = Field(default=Decimal("1.0"))
    critical_tolerance_hours: Decimal = Field(default=Decimal("4.0"))


class ScheduleAttachRequest(BaseModel):
    """Request payload to attach a schedule to a resource, service, scope, env, or tenant."""

    schedule_id: str = Field(..., description="Target schedule ID")
    level: ScheduleLevel = Field(..., description="Hierarchy level")
    target_id: str = Field(..., description="Target resource, service, scope, env, or tenant ID")
    environment: str | None = Field(default=None)
    business_justification: str | None = Field(default=None)
