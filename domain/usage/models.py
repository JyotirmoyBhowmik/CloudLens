"""Domain Models for Usage Telemetry, Monitoring Types, Expectations, and Collection (Prompt 25).

Enforces:
- Prompt 25: Fourteen canonical monitoring types (MT-01 to MT-14) + Quota Headroom (MT-15).
- Prompt 25: Per-resource assignment and override with audit.
- Prompt 25: Cardinality discipline - collect only metrics required by monitoring type.
- Prompt 25: Coarse granularity (hourly/daily) - sub-hourly collection is strictly forbidden.
- Prompt 25: Pre-aggregated storage per metric, entity, and interval with aggregation method.
- Prompt 25: Explicit gap recording as 'No Data' (never assumed zero).
- Prompt 25: Labeled interpolation only - silent interpolation is forbidden.
- Prompt 25: Expectation definition across 4 levels (RESOURCE, SERVICE, SCOPE, TENANT) with inheritance.
- Prompt 25: Call-volume estimator and cost-materiality filtering.
- BBP Section 19 (Monitoring types, expectations, collection design).
- Requirements: USE-001 to USE-010, FR-240 to FR-246, API-031, AC-051 to AC-053.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from domain.models.base import CanonicalEntity
from domain.models.enums import ProviderType
from domain.models.measures import QuantityMeasure


class MonitoringType(StrEnum):
    """The canonical monitoring types per Prompt 25 / BBP Section 19.

    MT-01 through MT-14 are the core types; MT-15 is Quota Headroom (USE-001 / Prompt 54).
    """

    RUNTIME_BASED = "RUNTIME_BASED"  # MT-01: Time-driven execution (VMs, instances)
    VOLUME_BASED = "VOLUME_BASED"  # MT-02: Physical volume (disks, block stores)
    TRANSACTION_BASED = "TRANSACTION_BASED"  # MT-03: Transaction counts (databases, queues)
    REQUEST_BASED = "REQUEST_BASED"  # MT-04: Request invocations (serverless, functions)
    STORAGE_BASED = "STORAGE_BASED"  # MT-05: Provisioned/used storage capacity (buckets, blobs)
    DATA_TRANSFER_BASED = (
        "DATA_TRANSFER_BASED"  # MT-06: Egress/ingress bytes transferred (CDN, gateways)
    )
    USER_BASED = "USER_BASED"  # MT-07: Seat-based active users (workspaces, SaaS)
    LICENCE_BASED = "LICENCE_BASED"  # MT-08: Licensed cores or units (OS, enterprise software)
    API_CALL_BASED = "API_CALL_BASED"  # MT-09: Endpoint invocations (API gateways)
    SCHEDULE_BASED = "SCHEDULE_BASED"  # MT-10: Scheduled operational windows
    SEASONAL = "SEASONAL"  # MT-11: Seasonal/cyclical demand profiles
    RESERVED_COMMITTED_USAGE = (
        "RESERVED_COMMITTED_USAGE"  # MT-12: Commitment plans (RI, Savings Plans)
    )
    PROVIDER_SPECIFIC_DIMENSION = (
        "PROVIDER_SPECIFIC_DIMENSION"  # MT-13: Provider-proprietary dimension
    )
    NOT_APPLICABLE = "NOT_APPLICABLE"  # MT-14: No usage generated (resource groups, roles)
    QUOTA_HEADROOM = "QUOTA_HEADROOM"  # MT-15: Provider limits and headroom (Prompt 54)


class CollectionGranularity(StrEnum):
    """Allowable usage collection granularities.

    Sub-hourly collection (< 3600s) is strictly out of scope and forbidden.
    """

    HOURLY = "HOURLY"
    DAILY = "DAILY"
    MONTHLY = "MONTHLY"


class AggregationMethod(StrEnum):
    """Mathematical aggregation methods for pre-aggregated usage fact storage."""

    SUM = "sum"
    AVERAGE = "average"
    MAX = "max"
    LAST = "last"


class ExpectationLevel(StrEnum):
    """Four-level hierarchy for usage expectations with deterministic inheritance."""

    RESOURCE = "RESOURCE"  # Highest precedence (explicit resource override)
    SERVICE = "SERVICE"  # Service-level expectation (e.g. all S3 buckets)
    SCOPE = "SCOPE"  # Scope / account / subscription level
    TENANT = "TENANT"  # Baseline enterprise default


class ExpectationStatus(StrEnum):
    """Status of usage consumption evaluated against expectation."""

    NORMAL = "NORMAL"  # Green: < 80% utilisation
    AMBER = "AMBER"  # Amber: >= 80% and < 100% utilisation (AC-051, AC-052)
    RED = "RED"  # Red: >= 100% utilisation (AC-051, AC-052)
    NO_DATA = "NO_DATA"  # Telemetry gap: distinct from zero (AC-053, USE-004)


class CardinalityRisk(StrEnum):
    """Projected API call volume risk classification tier."""

    LOW = "LOW"  # < 10,000 monthly calls
    MEDIUM = "MEDIUM"  # 10,000 - 100,000 monthly calls
    HIGH = "HIGH"  # 100,000 - 1,000,000 monthly calls
    CRITICAL = "CRITICAL"  # > 1,000,000 monthly calls


class SpikeStatus(StrEnum):
    """Statistical consumption spike detection classification (USE-007 / FR-246)."""

    NORMAL = "NORMAL"
    ANOMALOUS_SPIKE = "ANOMALOUS_SPIKE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


# ==============================================================================
# Entities and DTOs
# ==============================================================================


class MonitoringTypeDefinition(BaseModel):
    """Metadata specification for a canonical monitoring type."""

    code: str = Field(..., description="Canonical identifier (e.g. MT-01, MT-05)")
    type_name: MonitoringType = Field(..., description="Monitoring type enum")
    display_name: str = Field(..., description="Human-readable title")
    description: str = Field(..., description="Detailed description of usage profile")
    allowable_metrics: list[str] = Field(
        default_factory=list, description="Strict set of permissible metrics"
    )
    sample_resource_types: list[str] = Field(
        default_factory=list, description="Representative cloud native resource types"
    )


class MonitoringTypeOverride(CanonicalEntity):
    """Per-resource manual override of the default catalogue monitoring type with audit."""

    tenant_id: str = Field(..., description="Tenant boundary")
    resource_id: str = Field(..., description="Target canonical resource ID")
    monitoring_type: MonitoringType = Field(..., description="Overriding monitoring type applied")
    previous_monitoring_type: MonitoringType = Field(
        ..., description="Original monitoring type before override"
    )
    who: str = Field(..., description="Principal who applied the override")
    why: str = Field(..., description="Mandatory business rationale (min 20 chars)")
    applied_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when override took effect in UTC",
    )


class ResolvedMonitoringType(BaseModel):
    """Resolved monitoring type for a resource, indicating provenance."""

    resource_id: str = Field(..., description="Target resource ID")
    monitoring_type: MonitoringType = Field(..., description="Effective monitoring type")
    is_overridden: bool = Field(
        default=False, description="True if overridden by user; False if defaulted from catalogue"
    )
    source: str = Field(
        default="CATALOGUE_DEFAULT",
        description="'CATALOGUE_DEFAULT' or 'RESOURCE_OVERRIDE'",
    )
    allowable_metrics: list[str] = Field(
        default_factory=list, description="Permissible metrics for this resolved type"
    )
    override_details: MonitoringTypeOverride | None = Field(
        default=None, description="Audit details if overridden"
    )


class PreAggregatedUsageRecord(CanonicalEntity):
    """Pre-aggregated usage record enforcing pre-aggregation, explicit gaps, and labeled interpolation."""

    tenant_id: str = Field(..., description="Tenant boundary")
    scope_id: str = Field(..., description="Scope in force")
    resource_id: str = Field(..., description="Associated canonical resource ID")
    metric_name: str = Field(..., description="Canonical metric descriptor")
    interval_start: datetime = Field(..., description="Start of aggregation interval in UTC")
    interval_end: datetime = Field(..., description="End of aggregation interval in UTC")
    granularity: CollectionGranularity = Field(
        default=CollectionGranularity.HOURLY, description="Coarse granularity (HOURLY, DAILY)"
    )
    aggregation_method: AggregationMethod = Field(
        default=AggregationMethod.SUM, description="Recorded aggregation method"
    )
    usage_quantity: QuantityMeasure = Field(
        ..., description="Observed numeric quantity or explicit NO_DATA gap"
    )
    usage_unit: str = Field(..., description="Unit of consumption (e.g. Bytes, Hours, Requests)")
    is_gap: bool = Field(
        default=False, description="True if interval represents a recorded provider telemetry gap"
    )
    is_interpolated: bool = Field(
        default=False, description="True if value was produced by explicit interpolation"
    )
    interpolation_label: str | None = Field(
        default=None, description="Mandatory label if interpolated (e.g. 'INTERPOLATED: LINEAR')"
    )


class UsageExpectation(CanonicalEntity):
    """Usage expectation defined at resource, service, scope, or tenant level with inheritance."""

    tenant_id: str = Field(..., description="Tenant boundary")
    level: ExpectationLevel = Field(
        ..., description="Hierarchy level (RESOURCE, SERVICE, SCOPE, TENANT)"
    )
    target_id: str = Field(
        ..., description="Target ID: resource_id, service_id, scope_id, or tenant_id"
    )
    monitoring_type: MonitoringType = Field(..., description="Applicable monitoring type")
    metric_name: str | None = Field(default=None, description="Optional specific metric descriptor")

    # Specific expectation dimensions depending on monitoring type
    expected_hours_per_day: Decimal | None = Field(
        default=None, description="Expected operational hours/day (runtime/schedule)"
    )
    expected_quantity_per_period: Decimal | None = Field(
        default=None, description="Expected general consumption quantity per period"
    )
    expected_capacity: Decimal | None = Field(
        default=None, description="Expected provisioned capacity (storage/volume)"
    )
    expected_capacity_unit: str | None = Field(
        default=None, description="Capacity unit (e.g. TB, GB, Bytes)"
    )
    expected_requests: Decimal | None = Field(
        default=None, description="Expected request / API call volume per period"
    )
    expected_seats: int | None = Field(default=None, description="Expected active seats / users")
    named_schedule: str | None = Field(
        default=None, description="Configured operational schedule profile name"
    )
    seasonal_profile: str | None = Field(
        default=None, description="Named seasonal / cyclical profile"
    )
    committed_units: Decimal | None = Field(
        default=None, description="Committed units under reservation plan"
    )
    coverage_target: Decimal | None = Field(
        default=None, description="Coverage percentage target (0-100)"
    )

    # Multi-band threshold percentages
    warning_threshold_pct: Decimal = Field(
        default=Decimal("80.0"), description="Amber threshold percentage (default 80.0%)"
    )
    critical_threshold_pct: Decimal = Field(
        default=Decimal("100.0"), description="Red threshold percentage (default 100.0%)"
    )

    created_by: str = Field(..., description="User principal who configured expectation")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Creation timestamp in UTC"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Update timestamp in UTC"
    )


class ResolvedExpectation(BaseModel):
    """Effective resolved expectation for a resource after traversing the 4-level hierarchy."""

    resource_id: str = Field(..., description="Evaluated resource ID")
    effective_expectation: UsageExpectation = Field(
        ..., description="Active expectation winning inheritance resolution"
    )
    source_level: ExpectationLevel = Field(
        ..., description="Level from which the expectation was sourced"
    )
    is_inherited: bool = Field(
        default=False, description="True if resolved from TENANT, SCOPE, or SERVICE level"
    )
    is_overridden: bool = Field(
        default=False, description="True if defined explicitly at RESOURCE level"
    )
    lineage: list[ExpectationLevel] = Field(
        default_factory=list, description="Evaluation sequence checked during resolution"
    )


class ExpectationEvaluationResult(BaseModel):
    """Result of evaluating observed usage against resolved expectation."""

    resource_id: str = Field(..., description="Resource ID")
    metric_name: str = Field(..., description="Metric descriptor evaluated")
    actual_value_display: str = Field(
        ..., description="Rendered display value or 'No Data' (AC-053)"
    )
    actual_quantity: QuantityMeasure = Field(
        ..., description="Raw observed quantity measure (4-state null compliant)"
    )
    expected_value: Decimal | None = Field(
        default=None, description="Numeric expectation benchmark"
    )
    expected_unit: str | None = Field(default=None, description="Unit of expectation benchmark")
    utilisation_percentage: Decimal | None = Field(
        default=None, description="Calculated utilisation percentage (actual / expected * 100)"
    )
    status: ExpectationStatus = Field(
        ..., description="Evaluated status band: NORMAL, AMBER, RED, or NO_DATA"
    )
    is_gap: bool = Field(
        default=False, description="True if observed telemetry had a gap (renders No Data)"
    )
    explanation: str = Field(..., description="Defensible explanation of evaluation result")
    resolved_expectation: ResolvedExpectation | None = Field(
        default=None, description="Winning expectation lineage details"
    )


# ==============================================================================
# Sizing, Estimation & Materiality DTOs
# ==============================================================================


class CallVolumeEstimateRequest(BaseModel):
    """Request payload for predicting provider API call volumes and costs before configuration."""

    resource_count: int = Field(ge=0, description="Count of resources to monitor")
    granularity: CollectionGranularity = Field(
        default=CollectionGranularity.HOURLY, description="Proposed collection granularity"
    )
    monitoring_types: list[MonitoringType] = Field(
        default_factory=list, description="Target monitoring types"
    )
    provider: ProviderType = Field(default=ProviderType.AWS, description="Target cloud provider")
    batch_efficiency_factor: float = Field(
        default=1.0, ge=0.1, le=10.0, description="Multiplier for provider batch query support"
    )


class CallVolumeEstimate(BaseModel):
    """Projected provider API call volume and cost impact."""

    resource_count: int = Field(..., description="Total resources included")
    granularity: CollectionGranularity = Field(..., description="Collection granularity")
    metrics_per_resource_avg: int = Field(
        ..., description="Average metrics collected per resource based on monitoring types"
    )
    total_active_metrics: int = Field(..., description="Total active metric streams")
    daily_api_calls: int = Field(..., description="Projected daily API calls")
    monthly_api_calls: int = Field(..., description="Projected monthly API calls (30 days)")
    estimated_monthly_cost_usd: Decimal = Field(
        ..., description="Projected provider API telemetry charges in USD"
    )
    cardinality_risk: CardinalityRisk = Field(
        ..., description="Risk tier: LOW, MEDIUM, HIGH, CRITICAL"
    )
    warnings: list[str] = Field(default_factory=list, description="Cardinality and cost warnings")
    recommendations: list[str] = Field(
        default_factory=list, description="Actionable configuration recommendations"
    )


class MaterialityFilterConfig(BaseModel):
    """Configuration for cost-materiality collection filter."""

    min_monthly_cost_threshold: Decimal = Field(
        default=Decimal("5.00"), ge=Decimal("0.00"), description="Cost threshold floor in USD"
    )
    enabled: bool = Field(default=True, description="Whether cost-materiality filtering is active")


class MaterialityFilterResult(BaseModel):
    """Outcome of filtering resources through cost-materiality threshold."""

    candidate_count: int = Field(..., description="Total candidate resources evaluated")
    included_count: int = Field(..., description="Count of resources meeting cost materiality")
    excluded_count: int = Field(
        ..., description="Count of low-spend resources excluded from collection"
    )
    included_resource_ids: list[str] = Field(
        default_factory=list, description="Resource IDs eligible for collection"
    )
    excluded_resource_ids: list[str] = Field(
        default_factory=list, description="Resource IDs excluded below materiality threshold"
    )
    threshold_usd: Decimal = Field(..., description="Applied materiality threshold in USD")
    estimated_monthly_api_calls_saved: int = Field(
        ..., description="Estimated provider API calls saved per month"
    )
    estimated_monthly_cost_savings_usd: Decimal = Field(
        ..., description="Estimated telemetry API cost savings in USD"
    )


class UsageSpikeEvaluationResult(BaseModel):
    """Statistical consumption spike detection report (USE-007 / FR-246)."""

    resource_id: str = Field(..., description="Target resource ID")
    metric_name: str = Field(..., description="Target metric name")
    baseline_mean: Decimal = Field(..., description="Statistical mean across baseline window")
    baseline_std_dev: Decimal = Field(..., description="Standard deviation across baseline window")
    observed_value: Decimal = Field(..., description="Observed consumption value")
    z_score: Decimal = Field(..., description="Standard deviation distance from mean (Z-score)")
    threshold_sigma: Decimal = Field(..., description="Configured sigma threshold (e.g. 3.0)")
    status: SpikeStatus = Field(
        ..., description="Classification: NORMAL, ANOMALOUS_SPIKE, INSUFFICIENT_DATA"
    )
    message: str = Field(..., description="Descriptive explanation of spike evaluation")


# ==============================================================================
# Ingestion & Query DTOs
# ==============================================================================


class UsageIngestRequest(BaseModel):
    """Ingestion payload for usage telemetry batch."""

    resource_id: str = Field(..., description="Target canonical resource ID")
    scope_id: str = Field(..., description="Scope in force")
    metric_name: str = Field(..., description="Metric descriptor")
    interval_start: datetime = Field(..., description="Interval start in UTC")
    interval_end: datetime = Field(..., description="Interval end in UTC")
    granularity: str = Field(default="HOURLY", description="Collection granularity")
    aggregation_method: AggregationMethod = Field(
        default=AggregationMethod.SUM, description="Recorded aggregation method"
    )
    quantity: Decimal | None = Field(
        default=None, description="Numeric consumption quantity, or None if telemetry gap"
    )
    unit: str = Field(..., description="Unit of consumption")
    is_gap: bool = Field(
        default=False, description="Set True to record an explicit telemetry gap (No Data)"
    )
    interpolate: bool = Field(default=False, description="Whether to interpolate a missing gap")
    interpolation_label: str | None = Field(
        default=None, description="Mandatory label when interpolate is True"
    )
    strict_cardinality: bool = Field(
        default=True,
        description="If True, rejects metrics not required by resource's monitoring type",
    )
    provider_native: dict[str, Any] = Field(default_factory=dict)


class UsageQueryFilter(BaseModel):
    """Query filter parameters for retrieving pre-aggregated usage records (API-031)."""

    resource_id: str | None = Field(default=None, description="Filter by resource ID")
    scope_id: str | None = Field(default=None, description="Filter by scope ID")
    metric_name: str | None = Field(default=None, description="Filter by metric name")
    interval_start_gte: datetime | None = Field(
        default=None, description="Interval start on or after UTC"
    )
    interval_end_lte: datetime | None = Field(
        default=None, description="Interval end on or before UTC"
    )
    granularity: CollectionGranularity | None = Field(
        default=None, description="Filter by granularity"
    )
    include_gaps: bool = Field(
        default=True, description="Whether to include recorded telemetry gaps in query output"
    )
    limit: int = Field(default=50, ge=1, le=500, description="Pagination limit")
    offset: int = Field(default=0, ge=0, description="Pagination offset")
