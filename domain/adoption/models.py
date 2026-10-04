"""Domain Models and DTOs for Adoption Analytics and Platform Value (Prompt 61 / BBP Section 43).

Enforces:
- Strict non-surveillance privacy: usage telemetry is aggregated by role and team only.
  Named individual user identifiers are excluded from the telemetry schema by design.
- Governance operation metrics: MTTA, MTTC, aging, open-versus-closed trends.
- Value ledger: cumulative realised savings attributed to actual billing alongside the
  platform's own running cost (Net Value Delivered & ROI Multiple).
- Transparent Data Quality Score: 7 inspectable components combined into a weighted headline number.
- Feature adoption view: identifying active vs dormant capabilities.
- Onboarding maturity funnel per tenant and business unit.
- Quarterly steering committee review pack.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from domain.models.enums import (
    DataQualityRating,
    FeatureAdoptionStatus,
    FunnelStage,
    TelemetryActionType,
    ValueSourceType,
)

PRIVACY_POLICY_STATEMENT = (
    "CloudLens measures aggregate adoption by role and organizational team only. "
    "Individual user surveillance, monitoring, and performance ranking are strictly prohibited by platform policy."
)


# ==============================================================================
# 1. Privacy-Respecting Usage Telemetry
# ==============================================================================


class UsageTelemetryEvent(BaseModel):
    """Aggregate, role-and-team scoped user behavior event (no individual surveillance)."""

    event_id: str = Field(
        default_factory=lambda: f"ute-{uuid.uuid4().hex[:10]}",
        description="Unique telemetry event ID",
    )
    tenant_id: str = Field(..., description="Tenant boundary")
    role: str = Field(..., description="System role of the actor (e.g. FINOPS_ADMIN, DEVELOPER)")
    team_id: str = Field(..., description="Organizational team identifier (e.g. TEAM_DATA_PLATFORM)")
    screen_or_feature: str = Field(..., description="Screen, report, dashboard, or workflow identifier")
    action_type: TelemetryActionType = Field(..., description="Action category")
    result: str = Field(default="SUCCESS", description="Outcome of the action ('SUCCESS', 'FAILED')")
    timestamp: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC), description="Event UTC timestamp"
    )


class UsageAggregationRecord(BaseModel):
    """Aggregated usage metrics roll-up by role and team."""

    role: str = Field(..., description="Actor role")
    team_id: str = Field(..., description="Actor team")
    screen_or_feature: str = Field(..., description="Screen, report, or feature name")
    view_count: int = Field(default=0, ge=0, description="Total views or accesses")
    action_count: int = Field(default=0, ge=0, description="Total user actions performed")
    success_count: int = Field(default=0, ge=0, description="Successful actions")
    failure_count: int = Field(default=0, ge=0, description="Failed actions")
    success_rate: float = Field(default=100.0, ge=0.0, le=100.0, description="Success percentage")
    last_used_at: dt.datetime | None = Field(default=None, description="Most recent activity timestamp")


class UsageTelemetryReport(BaseModel):
    """Privacy-preserving usage telemetry report."""

    tenant_id: str = Field(..., description="Tenant boundary")
    privacy_policy_notice: str = Field(
        default=PRIVACY_POLICY_STATEMENT, description="Mandatory non-surveillance policy notice"
    )
    period: str = Field(..., description="Reporting period (e.g. '2026-Q3')")
    aggregations_by_role: dict[str, list[UsageAggregationRecord]] = Field(
        default_factory=dict, description="Usage roll-ups grouped by role"
    )
    aggregations_by_team: dict[str, list[UsageAggregationRecord]] = Field(
        default_factory=dict, description="Usage roll-ups grouped by organizational team"
    )
    total_events: int = Field(default=0, ge=0, description="Total telemetry events analyzed")


# ==============================================================================
# 2. Governance Operation Metrics
# ==============================================================================


class AlertGovernanceMetrics(BaseModel):
    """Alert responsiveness metrics."""

    raised_count: int = Field(default=0, ge=0)
    acknowledged_count: int = Field(default=0, ge=0)
    actioned_count: int = Field(default=0, ge=0)
    mean_time_to_acknowledge_hours: float = Field(default=0.0, ge=0.0)
    acknowledgement_rate: float = Field(default=0.0, ge=0.0, le=100.0)


class TaskGovernanceMetrics(BaseModel):
    """Remediation task operational flow metrics."""

    created_count: int = Field(default=0, ge=0)
    closed_count: int = Field(default=0, ge=0)
    verified_count: int = Field(default=0, ge=0)
    mean_time_to_close_hours: float = Field(default=0.0, ge=0.0)
    closure_rate: float = Field(default=0.0, ge=0.0, le=100.0)


class OverdueAgingBreakdown(BaseModel):
    """Overdue task aging brackets."""

    overdue_1_to_7_days: int = Field(default=0, ge=0)
    overdue_8_to_30_days: int = Field(default=0, ge=0)
    overdue_30_plus_days: int = Field(default=0, ge=0)
    total_overdue: int = Field(default=0, ge=0)


class ExemptionBypassMetrics(BaseModel):
    """Governance exemptions and safety bypass counts."""

    exemption_count: int = Field(default=0, ge=0)
    bypass_count: int = Field(default=0, ge=0)
    active_exemptions: int = Field(default=0, ge=0)


class GovernanceTrendPoint(BaseModel):
    """Timeseries data point tracking open-versus-closed governance flow."""

    date_label: str = Field(..., description="Date or week label (e.g. '2026-W36')")
    open_tasks: int = Field(default=0, ge=0)
    closed_tasks: int = Field(default=0, ge=0)
    active_alerts: int = Field(default=0, ge=0)


class GovernanceOperationsReport(BaseModel):
    """Consolidated operational health and governance execution report."""

    period: str = Field(..., description="Evaluation period")
    tenant_id: str = Field(..., description="Tenant boundary")
    alerts: AlertGovernanceMetrics = Field(default_factory=AlertGovernanceMetrics)
    tasks: TaskGovernanceMetrics = Field(default_factory=TaskGovernanceMetrics)
    overdue_aging: OverdueAgingBreakdown = Field(default_factory=OverdueAgingBreakdown)
    exemptions: ExemptionBypassMetrics = Field(default_factory=ExemptionBypassMetrics)
    trends: list[GovernanceTrendPoint] = Field(default_factory=list)


# ==============================================================================
# 3. Platform Value Ledger & Running Cost
# ==============================================================================


class RealisedSavingSourceBreakdown(BaseModel):
    """Verifiable cost saving line item backed by actual billing."""

    source: ValueSourceType = Field(..., description="Originating savings lever")
    amount: Decimal = Field(..., ge=Decimal("0.00"), description="Empirical dollar saving")
    billing_reference: str = Field(
        ..., description="Reference to actual billing telemetry proving the reduction"
    )
    currency: str = Field(default="USD")
    verified_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC), description="Verification timestamp"
    )


class PlatformRunningCost(BaseModel):
    """Itemized operational expenditure incurred by running CloudLens itself."""

    period: str = Field(..., description="Accounting period")
    bigquery_query_cost: Decimal = Field(
        default=Decimal("0.00"), ge=Decimal("0.00"), description="BigQuery query and extract charges"
    )
    connector_api_cost: Decimal = Field(
        default=Decimal("0.00"), ge=Decimal("0.00"), description="Cloud provider API calls invoked by connectors"
    )
    infrastructure_hosting_cost: Decimal = Field(
        default=Decimal("0.00"), ge=Decimal("0.00"), description="CloudLens host, cluster, and DB costs"
    )
    total_platform_cost: Decimal = Field(
        ..., ge=Decimal("0.00"), description="Grand total platform self-cost"
    )
    currency: str = Field(default="USD")


class PlatformValueLedgerReport(BaseModel):
    """True net platform value case: empirical savings minus platform cost."""

    period: str = Field(..., description="Reporting period")
    tenant_id: str = Field(..., description="Tenant boundary")
    cumulative_realised_savings: Decimal = Field(
        ..., ge=Decimal("0.00"), description="Total empirical dollars saved across all levers"
    )
    savings_by_source: dict[str, Decimal] = Field(
        default_factory=dict, description="Savings split by ValueSourceType"
    )
    savings_by_team: dict[str, Decimal] = Field(
        default_factory=dict, description="Savings attributed by organizational team"
    )
    platform_running_cost: PlatformRunningCost = Field(
        ..., description="The platform's own running costs"
    )
    net_value_delivered: Decimal = Field(
        ..., description="Cumulative Realised Savings minus Total Platform Cost"
    )
    roi_multiple: float = Field(
        ..., ge=0.0, description="Realised Savings divided by Platform Cost (e.g. 5.4x ROI)"
    )
    currency: str = Field(default="USD")


# ==============================================================================
# 4. Transparent Data Quality Scoring
# ==============================================================================


class DataQualityComponentScore(BaseModel):
    """Individual inspectable component contributing to the headline data quality score."""

    component_name: str = Field(..., description="Score dimension key")
    score: float = Field(..., ge=0.0, le=100.0, description="Score percentage (0.0 to 100.0)")
    weight: float = Field(..., ge=0.0, le=1.0, description="Contribution weight (sums to 1.0)")
    inspectable_details: dict[str, Any] = Field(
        default_factory=dict, description="Underlying denominator, numerator, and diagnostics"
    )


class DataQualityReport(BaseModel):
    """Composite headline score trending over time with inspectable components."""

    headline_score: float = Field(
        ..., ge=0.0, le=100.0, description="Weighted composite data quality score"
    )
    rating: DataQualityRating = Field(..., description="Headline rating band")
    components: list[DataQualityComponentScore] = Field(
        default_factory=list, description="Seven inspectable component dimensions"
    )
    evaluated_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC), description="Evaluation timestamp"
    )
    historical_trend: list[dict[str, Any]] = Field(
        default_factory=list, description="Historical score trajectory"
    )


# ==============================================================================
# 5. Feature Adoption View
# ==============================================================================


class FeatureAdoptionItem(BaseModel):
    """Maturity and utilization status of an individual platform capability."""

    feature_key: str = Field(..., description="Internal capability key (e.g. 'budget_forecasting')")
    feature_name: str = Field(..., description="Display title")
    category: str = Field(..., description="Capability category")
    enabled: bool = Field(default=True, description="Whether capability is enabled in configuration")
    status: FeatureAdoptionStatus = Field(..., description="Adoption state")
    usage_count_last_30_days: int = Field(default=0, ge=0)
    active_teams_count: int = Field(default=0, ge=0)
    first_used_at: dt.datetime | None = None
    last_used_at: dt.datetime | None = None
    recommendation: str = Field(
        default="HEALTHY", description="Actionable suggestion (e.g. 'PROMOTE_DORMANT_FEATURE')"
    )


class FeatureAdoptionReport(BaseModel):
    """Summary of active vs dormant capabilities."""

    tenant_id: str = Field(..., description="Tenant boundary")
    active_features: list[FeatureAdoptionItem] = Field(default_factory=list)
    dormant_features: list[FeatureAdoptionItem] = Field(default_factory=list)
    disabled_features: list[FeatureAdoptionItem] = Field(default_factory=list)
    dormancy_rate: float = Field(
        default=0.0, ge=0.0, le=100.0, description="Percentage of enabled features that are dormant"
    )


# ==============================================================================
# 6. Onboarding Maturity Funnel
# ==============================================================================


class FunnelProgressStep(BaseModel):
    """Milestone evaluation within the onboarding funnel."""

    stage: FunnelStage = Field(..., description="Funnel step")
    achieved: bool = Field(default=False)
    achieved_at: dt.datetime | None = None
    elapsed_days_from_start: float | None = None


class ScopeOnboardingFunnel(BaseModel):
    """Progress of a tenant or business unit through the onboarding funnel."""

    scope_id: str = Field(..., description="Identifier of the onboarded scope")
    scope_type: str = Field(default="TENANT", description="'TENANT' or 'BUSINESS_UNIT'")
    current_stage: FunnelStage = Field(..., description="Highest reached stage")
    steps: list[FunnelProgressStep] = Field(default_factory=list)
    is_stalled: bool = Field(default=False, description="True if stuck without progress > 14 days")
    stalled_stage: FunnelStage | None = None
    onboarding_started_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC)
    )


class OnboardingFunnelReport(BaseModel):
    """Funnel analytics across all onboarding scopes."""

    tenant_id: str = Field(..., description="Tenant boundary")
    total_scopes: int = Field(default=0, ge=0)
    completed_funnels: int = Field(default=0, ge=0)
    stalled_funnels: int = Field(default=0, ge=0)
    funnels: list[ScopeOnboardingFunnel] = Field(default_factory=list)


# ==============================================================================
# 7. Quarterly Platform Review Pack
# ==============================================================================


class QuarterlyReviewPack(BaseModel):
    """Comprehensive executive review pack for steering committee presentation."""

    pack_id: str = Field(
        default_factory=lambda: f"pack-{uuid.uuid4().hex[:8]}",
        description="Unique pack document ID",
    )
    tenant_id: str = Field(..., description="Tenant boundary")
    quarter_label: str = Field(..., description="Quarter designation (e.g. '2026-Q3')")
    generated_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC), description="Generation timestamp"
    )
    executive_summary: str = Field(..., description="High-level narrative for executives")
    adoption_summary: UsageTelemetryReport
    governance_operations: GovernanceOperationsReport
    value_ledger: PlatformValueLedgerReport
    data_quality: DataQualityReport
    feature_adoption: FeatureAdoptionReport
    onboarding_funnel: OnboardingFunnelReport
    outstanding_governance_gaps: list[dict[str, Any]] = Field(default_factory=list)
    document_markdown: str = Field(..., description="Formatted markdown report for PDF/presentation")
