"""Threshold Engine Models, States, Bases, and Anti-Flapping Configurations (Prompt 27).

Enforces:
- Prompt 27: Six states: Normal (green), Warning (amber), High (orange), Critical (red),
  Informational (blue), Unknown/No data (grey).
- Prompt 27: All ten threshold bases: absolute value, percentage, budget utilisation, forecast,
  runtime, volume, growth percentage, variance from baseline, historical average, seasonal baseline.
- Prompt 27: Band validation that bands are contiguous and non-overlapping, rejected at save time if not.
- Prompt 27: Resolution precedence (temporary override -> local -> nearest ancestor -> tenant default)
  with source display disclosure.
- Prompt 27: Anti-flapping configuration (dwell time, asymmetric hysteresis, cool-down, storm grouping,
  data quality gate).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

from domain.models.base import CanonicalEntity
from domain.models.exceptions import (
    BandDiscontinuityException,
    BandOverlapException,
    ThresholdOverrideReasonTooShortException,
)

# ==============================================================================
# 1. Six Threshold States & Ten Bases
# ==============================================================================


class ThresholdState(StrEnum):
    """The six canonical threshold states per Prompt 27."""

    NORMAL = "NORMAL"  # Green (#10b981)
    WARNING = "WARNING"  # Amber (#f59e0b)
    HIGH = "HIGH"  # Orange (#f97316)
    CRITICAL = "CRITICAL"  # Red (#ef4444)
    INFORMATIONAL = "INFORMATIONAL"  # Blue (#3b82f6)
    UNKNOWN = "UNKNOWN"  # Grey (#94a3b8) - Missing / No Data

    def get_color_hex(self) -> str:
        """Returns the canonical color hex per Prompt 27 specification."""
        if self == ThresholdState.NORMAL:
            return "#10b981"  # no-hardcode-allow: reason="Canonical UI threshold state hex colour code", reviewer="Prompt-48-Audit"
        if self == ThresholdState.WARNING:
            return "#f59e0b"  # no-hardcode-allow: reason="Canonical UI threshold state hex colour code", reviewer="Prompt-48-Audit"
        if self == ThresholdState.HIGH:
            return "#f97316"  # no-hardcode-allow: reason="Canonical UI threshold state hex colour code", reviewer="Prompt-48-Audit"
        if self == ThresholdState.CRITICAL:
            return "#ef4444"  # no-hardcode-allow: reason="Canonical UI threshold state hex colour code", reviewer="Prompt-48-Audit"
        if self == ThresholdState.INFORMATIONAL:
            return "#3b82f6"  # no-hardcode-allow: reason="Canonical UI threshold state hex colour code", reviewer="Prompt-48-Audit"
        if self == ThresholdState.UNKNOWN:
            return "#94a3b8"  # no-hardcode-allow: reason="Canonical UI threshold state hex colour code", reviewer="Prompt-48-Audit"
        return "#94a3b8"  # no-hardcode-allow: reason="Canonical UI threshold state hex colour code", reviewer="Prompt-48-Audit"

    def is_breach(self) -> bool:
        """Returns True if the state represents an anomalous or threshold breach."""
        return self in (ThresholdState.WARNING, ThresholdState.HIGH, ThresholdState.CRITICAL)

    def is_compliant(self) -> bool:
        """Returns True if the state represents nominal approved operation."""
        return self in (ThresholdState.NORMAL, ThresholdState.INFORMATIONAL)


class ThresholdBasis(StrEnum):
    """The ten canonical threshold bases per Prompt 27."""

    ABSOLUTE_VALUE = "ABSOLUTE_VALUE"
    PERCENTAGE = "PERCENTAGE"
    BUDGET_UTILISATION = "BUDGET_UTILISATION"
    FORECAST = "FORECAST"
    RUNTIME = "RUNTIME"
    VOLUME = "VOLUME"
    GROWTH_PERCENTAGE = "GROWTH_PERCENTAGE"
    VARIANCE_FROM_BASELINE = "VARIANCE_FROM_BASELINE"
    HISTORICAL_AVERAGE = "HISTORICAL_AVERAGE"
    SEASONAL_BASELINE = "SEASONAL_BASELINE"
    QUOTA_HEADROOM = "QUOTA_HEADROOM"


class ThresholdSourceType(StrEnum):
    """Resolution precedence hierarchy levels (Prompt 27 Item 165)."""

    TEMPORARY_OVERRIDE = "TEMPORARY_OVERRIDE"  # 1st precedence
    ADMIN_OVERRIDE = "ADMIN_OVERRIDE"  # 2nd precedence
    LOCAL = "LOCAL"  # 3rd precedence (direct attachment)
    INHERITED_ANCESTOR = "INHERITED_ANCESTOR"  # 4th precedence (nearest ancestor)
    TENANT_DEFAULT = "TENANT_DEFAULT"  # 5th precedence (tenant fallback)


# ==============================================================================
# 2. Band Definitions & Validation
# ==============================================================================


class ThresholdBandDefinition(BaseModel):
    """Definition of a single severity band bracket."""

    id: str = Field(default_factory=lambda: f"band-{uuid.uuid4().hex[:8]}")
    state: ThresholdState = Field(..., description="Target threshold state")
    name: str = Field(..., description="Band name (e.g. Normal, Warning, High, Critical)")
    lower_bound: Decimal | None = Field(
        default=None, description="Lower bound value (inclusive, None = negative infinity)"
    )
    upper_bound: Decimal | None = Field(
        default=None, description="Upper bound value (exclusive, None = positive infinity)"
    )
    lower_inclusive: bool = Field(default=True, description="Whether lower bound is inclusive")
    upper_inclusive: bool = Field(default=False, description="Whether upper bound is inclusive")
    exit_threshold_lower: Decimal | None = Field(
        default=None,
        description="Optional asymmetric hysteresis lower threshold to exit this band",
    )
    exit_threshold_upper: Decimal | None = Field(
        default=None,
        description="Optional asymmetric hysteresis upper threshold to exit this band",
    )
    description: str = Field(default="", description="Band explanation")


def validate_contiguous_non_overlapping_bands(bands: list[ThresholdBandDefinition]) -> None:
    """Validates that threshold bands are contiguous and non-overlapping.

    Enforces Prompt 27 constraint: 'bands are contiguous and non-overlapping, rejected at save time if not.'
    """
    if not bands:
        raise BandDiscontinuityException(
            band1_name="empty", band2_name="empty", gap_detail="At least one band must be defined."
        )

    # Sort bands by lower bound (None counts as -infinity)
    def sort_key(b: ThresholdBandDefinition) -> Decimal:
        return b.lower_bound if b.lower_bound is not None else Decimal("-Infinity")

    sorted_bands = sorted(bands, key=sort_key)

    for i in range(len(sorted_bands) - 1):
        curr = sorted_bands[i]
        nxt = sorted_bands[i + 1]

        # Check for unbounded upper in a non-terminal band
        if curr.upper_bound is None:
            raise BandOverlapException(
                band1_name=curr.name,
                band2_name=nxt.name,
                detail=f"Band '{curr.name}' has no upper bound but is followed by '{nxt.name}'.",
            )

        # Check for missing lower bound in subsequent band
        if nxt.lower_bound is None:
            raise BandOverlapException(
                band1_name=curr.name,
                band2_name=nxt.name,
                detail=f"Band '{nxt.name}' has unbounded lower bound but is preceded by '{curr.name}'.",
            )

        # Check for overlap
        if curr.upper_bound > nxt.lower_bound:
            raise BandOverlapException(
                band1_name=curr.name,
                band2_name=nxt.name,
                detail=f"Band '{curr.name}' upper bound ({curr.upper_bound}) exceeds '{nxt.name}' lower bound ({nxt.lower_bound}).",
            )

        # Check for gap / discontinuity
        if curr.upper_bound < nxt.lower_bound:
            raise BandDiscontinuityException(
                band1_name=curr.name,
                band2_name=nxt.name,
                gap_detail=f"Gap detected between '{curr.name}' upper bound ({curr.upper_bound}) and '{nxt.name}' lower bound ({nxt.lower_bound}).",
            )


# ==============================================================================
# 3. Anti-Flapping Configuration
# ==============================================================================


class AntiFlappingConfig(BaseModel):
    """Anti-flapping parameters to suppress noise and oscillating alerts (Prompt 27)."""

    dwell_evaluations: int = Field(
        default=1,
        ge=1,
        description="Consecutive evaluation cycles required in new state before state is published (dwell time)",
    )
    hysteresis_margin_pct: Decimal = Field(
        default=Decimal("2.0"),
        ge=Decimal("0.0"),
        description="Percentage margin for asymmetric exit thresholds to prevent boundary oscillation",
    )
    cooldown_seconds: int = Field(
        default=3600,
        ge=0,
        description="Cool-down duration in seconds after transition before repeat alert is permitted",
    )
    grouping_storm_threshold: int = Field(
        default=5,
        ge=2,
        description="Number of scope child transitions in single cycle triggering storm grouping",
    )
    enable_data_quality_gate: bool = Field(
        default=True,
        description="Whether missing data produces a data-quality signal rather than threshold breach",
    )


# ==============================================================================
# 4. Threshold Rule Definition
# ==============================================================================


class ThresholdRule(BaseModel):
    """Canonical threshold rule with basis, contiguous bands, and anti-flapping controls."""

    id: str = Field(default_factory=lambda: f"thr-rule-{uuid.uuid4().hex[:8]}")
    tenant_id: str = Field(..., description="Organization tenant ID")
    name: str = Field(..., description="Rule descriptor")
    description: str = Field(default="", description="Rule governance purpose")
    basis: ThresholdBasis = Field(..., description="Threshold evaluation basis")
    bands: list[ThresholdBandDefinition] = Field(
        ..., description="Contiguous, non-overlapping severity bands"
    )
    anti_flapping: AntiFlappingConfig = Field(
        default_factory=AntiFlappingConfig, description="Anti-flapping controls"
    )
    scope_id: str | None = Field(default=None, description="Scope attachment target")
    service_id: str | None = Field(default=None, description="Service attachment target")
    resource_id: str | None = Field(default=None, description="Resource attachment target")
    environment: str | None = Field(default=None, description="Environment tier")
    is_tenant_default: bool = Field(
        default=False, description="Whether this is the tenant fallback"
    )
    unit: str = Field(default="%", description="Measurement unit (%, USD, Hours, Requests)")

    @model_validator(mode="after")
    def validate_bands(self) -> ThresholdRule:
        """Enforces contiguous non-overlapping bands on creation/save."""
        validate_contiguous_non_overlapping_bands(self.bands)
        return self


# ==============================================================================
# 5. Overrides Mechanism
# ==============================================================================


class ThresholdOverride(BaseModel):
    """Operational or administrative override on a threshold rule (Prompt 27)."""

    id: str = Field(default_factory=lambda: f"thr-ovr-{uuid.uuid4().hex[:8]}")
    tenant_id: str = Field(..., description="Organization tenant ID")
    target_id: str = Field(..., description="Resource, scope, or rule ID being overridden")
    source_type: ThresholdSourceType = Field(
        ..., description="TEMPORARY_OVERRIDE or ADMIN_OVERRIDE"
    )
    custom_bands: list[ThresholdBandDefinition] | None = Field(
        default=None, description="Alternative contiguous bands in force during override"
    )
    reason: str = Field(..., description="Mandatory recorded justification (minimum 20 characters)")
    created_by: str = Field(..., description="Actor who created the override")
    approved_by: str | None = Field(default=None, description="Supervisor or approver ID")
    valid_from: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Effective start timestamp"
    )
    expires_at: datetime | None = Field(
        default=None,
        description="Mandatory expiration timestamp for TEMPORARY_OVERRIDE (auto-reverts)",
    )
    is_active: bool = Field(default=True, description="Whether override is active")

    @field_validator("reason")
    @classmethod
    def validate_reason_length(cls, val: str) -> str:
        trimmed = val.strip()
        min_chars = 20
        if len(trimmed) < min_chars:
            raise ThresholdOverrideReasonTooShortException(
                length=len(trimmed), min_length=min_chars
            )
        return trimmed

    @model_validator(mode="after")
    def validate_temporary_expiry_and_bands(self) -> ThresholdOverride:
        if self.source_type == ThresholdSourceType.TEMPORARY_OVERRIDE and self.expires_at is None:
            raise ValueError("Temporary overrides must specify a mandatory 'expires_at' timestamp.")
        if self.custom_bands:
            validate_contiguous_non_overlapping_bands(self.custom_bands)
        return self

    def is_expired(self, as_of: datetime | None = None) -> bool:
        """Determines whether the override has expired."""
        if self.expires_at is None:
            return False
        check_time = as_of or datetime.now(UTC)
        return check_time >= self.expires_at


# ==============================================================================
# 6. Evaluation Result & State Transitions
# ==============================================================================


class ThresholdEvaluationResult(CanonicalEntity):
    """Result of threshold evaluation with anti-flapping and source traceability (Prompt 27)."""

    tenant_id: str = Field(..., description="Organization tenant ID")
    entity_id: str = Field(..., description="Target entity ID (resource, scope, service)")
    entity_type: str = Field(default="RESOURCE", description="Entity category")
    rule_id: str = Field(..., description="Resolved threshold rule ID")
    rule_name: str = Field(..., description="Resolved threshold rule name")
    basis: ThresholdBasis = Field(..., description="Evaluation basis applied")
    measured_value: Decimal | None = Field(
        default=None, description="Observed numeric value, or None if data quality gap"
    )
    evaluated_state: ThresholdState = Field(
        ..., description="Raw state derived from measured value vs bands"
    )
    committed_state: ThresholdState = Field(
        ..., description="Published state after anti-flapping (dwell/cool-down) filters"
    )
    color_hex: str = Field(..., description="Rendered state color hex")
    resolved_source_type: ThresholdSourceType = Field(
        ..., description="Origin in precedence chain (temporary, local, inherited, tenant default)"
    )
    resolved_source_id: str = Field(..., description="ID of source defining the rule/override")
    resolved_source_display: str = Field(
        ..., description="Human-readable disclosure of where threshold was resolved from"
    )
    is_alert_dispatched: bool = Field(
        default=False, description="Whether alert notification was dispatched"
    )
    is_flapping_suppressed: bool = Field(
        default=False, description="Whether transition was held or alert suppressed"
    )
    suppression_reason: str | None = Field(
        default=None, description="Explanation if suppressed by dwell, cooldown, or storm grouping"
    )
    is_data_quality_issue: bool = Field(
        default=False,
        description="Whether missing data triggered data quality signal rather than breach",
    )
    evaluated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp of evaluation",
    )
    transition_occurred: bool = Field(
        default=False, description="Whether committed state changed from previous evaluation"
    )
    previous_committed_state: ThresholdState | None = Field(
        default=None, description="Previous published state before this evaluation"
    )


class StormGroupEvent(BaseModel):
    """Aggregated event emitted when multiple children transition simultaneously (storm suppression)."""

    id: str = Field(default_factory=lambda: f"storm-{uuid.uuid4().hex[:8]}")
    scope_id: str = Field(..., description="Common parent scope ID")
    cycle_timestamp: datetime = Field(..., description="Evaluation cycle timestamp")
    transition_count: int = Field(..., description="Number of child entities transitioning")
    child_entity_ids: list[str] = Field(..., description="List of transitioning child entity IDs")
    summary: str = Field(..., description="Aggregated event explanation")


# ==============================================================================
# 7. Request DTOs
# ==============================================================================


class ThresholdEvaluateRequest(BaseModel):
    """Payload to evaluate a metric value against thresholds."""

    entity_id: str
    entity_type: str = "RESOURCE"
    value: Decimal | None = None
    basis: ThresholdBasis = ThresholdBasis.BUDGET_UTILISATION
    scope_id: str | None = None
    service_id: str | None = None
    environment: str | None = None
    rule_id: str | None = None


class ThresholdRuleCreateRequest(BaseModel):
    """Payload to create or update a threshold rule."""

    id: str | None = None
    name: str
    description: str = ""
    basis: ThresholdBasis
    bands: list[ThresholdBandDefinition]
    anti_flapping: AntiFlappingConfig = Field(default_factory=AntiFlappingConfig)
    scope_id: str | None = None
    service_id: str | None = None
    resource_id: str | None = None
    environment: str | None = None
    is_tenant_default: bool = False
    unit: str = "%"


class ThresholdOverrideCreateRequest(BaseModel):
    """Payload to create a threshold override."""

    target_id: str
    source_type: ThresholdSourceType = ThresholdSourceType.TEMPORARY_OVERRIDE
    reason: str = Field(..., min_length=20)
    expires_at: datetime | None = None
    custom_bands: list[ThresholdBandDefinition] | None = None
    valid_from: datetime | None = None
