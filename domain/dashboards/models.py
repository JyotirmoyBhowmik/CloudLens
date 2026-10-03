"""Domain Models for Multi-Level Dashboards (Prompt 37).

Enforces:
- FR-500: Pre-aggregated rollups for interactive performance.
- FR-501: Explicit data freshness timestamp on every widget.
- FR-502: RBAC scope filtering with clear disclosure of omitted/restricted data.
- FR-503: Default landing dashboard per role.
- FR-504: Dynamic period selection (Month, Quarter, Fiscal, Custom) and PoP/YoY comparison.
- FR-505: Widget-level data export in CSV and JSON formats.
- Native vocabulary enforcement for multi-cloud provider dashboards (AWS, Azure, GCP, OCI).
- Service dashboard with all 16 canonical panels.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from domain.cost.models import CostPresentationBasis


class DashboardPeriodType(StrEnum):
    """Dynamic period selection types (FR-504)."""

    MONTH = "MONTH"
    QUARTER = "QUARTER"
    FISCAL_PERIOD = "FISCAL_PERIOD"
    CUSTOM = "CUSTOM"


class ComparisonBasis(StrEnum):
    """Comparison basis switching (FR-504)."""

    POP = "POP"  # Period-over-Period (e.g. prior month)
    YOY = "YOY"  # Year-over-Year (same period last year)


class TimeWindowContext(BaseModel):
    """Active time window and comparison parameters."""

    model_config = ConfigDict(frozen=True)

    period_id: str = Field(..., description="Canonical period identifier, e.g. '2026-09'")
    period_type: DashboardPeriodType = Field(default=DashboardPeriodType.MONTH)
    comparison_basis: ComparisonBasis = Field(default=ComparisonBasis.POP)
    start_date: date = Field(..., description="Start date of active period")
    end_date: date = Field(..., description="End date of active period")
    comparison_start_date: date = Field(..., description="Start date of comparison period")
    comparison_end_date: date = Field(..., description="End date of comparison period")


class WidgetFreshness(BaseModel):
    """Per-widget data freshness attribution (FR-501)."""

    model_config = ConfigDict(frozen=True)

    refreshed_at: datetime = Field(..., description="Timestamp when underlying data was aggregated")
    status: str = Field(default="FRESH", description="FRESH (<4h), DELAYED (4-24h), STALE (>24h)")
    age_seconds: int = Field(default=0, ge=0)
    sla_target_hours: int = Field(default=4)
    is_stale: bool = Field(default=False)


class WidgetScopeDisclosure(BaseModel):
    """Disclosure when user RBAC scope grants restrict data (FR-502)."""

    model_config = ConfigDict(frozen=True)

    is_filtered: bool = Field(default=False, description="Whether access filtering is active")
    authorized_scopes: list[str] = Field(default_factory=list)
    restricted_count: int = Field(default=0, ge=0)
    disclosure_text: str | None = Field(
        default=None,
        description="User-facing disclosure message when access filtering has removed data from total",
    )


class WidgetMetadata(BaseModel):
    """Common envelope for all dashboard widgets."""

    model_config = ConfigDict(frozen=True)

    widget_id: str
    title: str
    freshness: WidgetFreshness
    scope_disclosure: WidgetScopeDisclosure
    is_precomputed: bool = Field(
        default=True, description="Enforces FR-500 pre-aggregated requirement"
    )


# ==============================================================================
# Executive Dashboard Widgets Models (All 22 Widgets)
# ==============================================================================


class CostMetricWidget(BaseModel):
    """Standard cost KPI widget with comparison delta."""

    metadata: WidgetMetadata
    amount: Decimal = Field(..., description="Aggregated cost amount")
    currency: str = Field(default="USD")
    presentation_basis: CostPresentationBasis = Field(default=CostPresentationBasis.BILLED)
    prior_amount: Decimal | None = None
    delta_amount: Decimal | None = None
    delta_percentage: Decimal | None = None
    cost_source: str = Field(default="ACTUAL")  # ACTUAL, ESTIMATED, FORECAST


class BudgetUtilisationWidget(BaseModel):
    """Budget & Utilisation widget."""

    metadata: WidgetMetadata
    budget_amount: Decimal
    actual_spend: Decimal
    forecast_spend: Decimal
    currency: str = Field(default="USD")
    utilisation_percentage: Decimal
    projected_utilisation_percentage: Decimal
    threshold_state: str = Field(default="NORMAL")  # NORMAL, WARNING, CRITICAL
    remaining_budget: Decimal


class BreakdownItem(BaseModel):
    """Categorical slice for breakdown widgets."""

    id: str
    label: str
    cost: Decimal
    percentage: Decimal
    prior_cost: Decimal | None = None
    delta_cost: Decimal | None = None
    delta_percentage: Decimal | None = None


class CostBreakdownWidget(BaseModel):
    """Multi-category cost breakdown (Provider, BU, App, Service)."""

    metadata: WidgetMetadata
    dimension: str
    total_cost: Decimal
    currency: str = Field(default="USD")
    items: list[BreakdownItem]


class TimeSeriesPoint(BaseModel):
    """Timeseries data point."""

    date: str
    actual_cost: Decimal
    comparison_cost: Decimal | None = None
    forecast_cost: Decimal | None = None


class CostTrendWidget(BaseModel):
    """Timeseries spend trend."""

    metadata: WidgetMetadata
    points: list[TimeSeriesPoint]
    comparison_basis: ComparisonBasis


class MovementItem(BaseModel):
    """Significant cost movement or driver."""

    item_id: str
    name: str
    category: str
    provider: str
    current_cost: Decimal
    prior_cost: Decimal
    delta_cost: Decimal
    delta_percentage: Decimal
    explanation: str


class LargestIncreasesWidget(BaseModel):
    """Largest cost increases and movements."""

    metadata: WidgetMetadata
    movements: list[MovementItem]


class BreachItem(BaseModel):
    """Threshold breach summary."""

    alert_id: str
    scope_name: str
    threshold_type: str
    severity: str  # WARNING, CRITICAL
    utilization_pct: Decimal
    triggered_at: datetime


class ThresholdBreachesWidget(BaseModel):
    """Active threshold breaches."""

    metadata: WidgetMetadata
    total_breaches: int
    critical_count: int
    warning_count: int
    breaches: list[BreachItem]


class ServiceCountsWidget(BaseModel):
    """Inventory service tier counts."""

    metadata: WidgetMetadata
    free_services_count: int
    paid_services_count: int
    conditional_services_count: int
    total_services_count: int


class AnomalyItem(BaseModel):
    """Operational exception or anomaly."""

    id: str
    resource_id: str
    resource_name: str
    provider: str
    type: str
    description: str
    impact_amount: Decimal
    detected_at: datetime


class OperationalExceptionsWidget(BaseModel):
    """Runtime exceptions, idle waste, or usage anomalies."""

    metadata: WidgetMetadata
    exception_type: str  # RUNTIME_EXCEPTIONS or USAGE_ANOMALIES
    total_count: int
    items: list[AnomalyItem]


class PricingChangeItem(BaseModel):
    """Rate card / pricing catalog update."""

    id: str
    provider: str
    service_name: str
    change_type: str  # RATE_DECREASE, RATE_INCREASE, NEW_TIER
    old_rate: Decimal
    new_rate: Decimal
    effective_date: str
    impact_description: str


class PricingChangesWidget(BaseModel):
    """Recent provider pricing updates."""

    metadata: WidgetMetadata
    recent_changes: list[PricingChangeItem]


class ProviderFreshnessDetail(BaseModel):
    """Freshness status per cloud provider."""

    provider: str
    last_sync_timestamp: datetime
    age_hours: Decimal
    status: str  # FRESH, DELAYED, STALE
    alert_banner: str | None = None


class DataFreshnessWidget(BaseModel):
    """Multi-cloud data freshness & staleness tracking."""

    metadata: WidgetMetadata
    providers: list[ProviderFreshnessDetail]
    has_stale_provider: bool
    stale_provider_banner: str | None = None


class ReconciliationStatusWidget(BaseModel):
    """Invoice vs FOCUS telemetry reconciliation."""

    metadata: WidgetMetadata
    status: str  # RECONCILED, UNRECONCILED, UNDER_INVESTIGATION
    trust_indicator: str  # VERIFIED, UNVERIFIED, DISPUTED
    invoice_total: Decimal
    telemetry_total: Decimal
    variance_amount: Decimal
    variance_ratio_pct: Decimal
    tolerance_threshold_pct: Decimal = Field(default=Decimal("1.00"))


class GovernanceExceptionsWidget(BaseModel):
    """Governance breaches (unapproved deployments, tag debt, quota limits)."""

    metadata: WidgetMetadata
    unapproved_deployments_count: int
    tagging_gaps_count: int
    quotas_near_limit_count: int
    total_exceptions: int


class ExecutiveDashboardResponse(BaseModel):
    """Complete Executive Dashboard (Prompt 37)."""

    time_window: TimeWindowContext
    data_freshness_banner: str | None = None

    # Top KPI Metrics (1-7)
    total_cloud_cost: CostMetricWidget
    current_month_cost: CostMetricWidget
    actual_cost: CostMetricWidget
    estimated_cost: CostMetricWidget
    forecast_cost: CostMetricWidget
    budget: CostMetricWidget
    budget_utilisation: BudgetUtilisationWidget

    # Breakdowns (8-11)
    cost_by_provider: CostBreakdownWidget
    cost_by_business_unit: CostBreakdownWidget
    cost_by_application: CostBreakdownWidget
    cost_by_service: CostBreakdownWidget

    # Trends & Movers (12-14)
    cost_trend: CostTrendWidget
    top_cost_services: CostBreakdownWidget
    largest_increases: LargestIncreasesWidget

    # Operational & Health (15-22)
    threshold_breaches: ThresholdBreachesWidget
    service_counts: ServiceCountsWidget
    runtime_exceptions: OperationalExceptionsWidget
    usage_anomalies: OperationalExceptionsWidget
    pricing_changes: PricingChangesWidget
    data_freshness: DataFreshnessWidget
    reconciliation_status: ReconciliationStatusWidget
    governance_exceptions: GovernanceExceptionsWidget


# ==============================================================================
# Provider Dashboard Models (Native Vocabulary Enforced)
# ==============================================================================


class NativeHierarchyNode(BaseModel):
    """Node in provider's native structural tree."""

    id: str
    native_id: str
    native_name: str
    native_type: str  # e.g. ManagementGroup, OU, Folder, Compartment
    level: int
    child_count: int
    cost: Decimal
    currency: str = Field(default="USD")
    resource_count: int
    children: list[NativeHierarchyNode] = Field(default_factory=list)


class ProviderDashboardResponse(BaseModel):
    """Per-provider dashboard strictly enforcing native cloud vocabulary."""

    provider: str  # aws, azure, gcp, oci
    display_name: str
    time_window: TimeWindowContext
    freshness: WidgetFreshness

    # Provider Native Structural Counts (Strictly typed native terms)
    hierarchy_root_name: str
    native_group_term: str  # 'Management Groups' (Azure), 'Organizational Units' (AWS), 'Folders' (GCP), 'Compartments' (OCI)
    native_account_term: str  # 'Subscriptions' (Azure), 'Member Accounts' (AWS), 'Projects' (GCP), 'Tenancies/Compartments' (OCI)
    native_group_count: int
    native_account_count: int

    resource_count: int
    service_count: int

    # Financial & Operational Metrics
    actual_cost: CostMetricWidget
    estimated_cost: CostMetricWidget
    forecast_cost: CostMetricWidget
    budget_amount: Decimal
    budget_utilisation_pct: Decimal
    threshold_state: str

    usage_volume_headline: str
    runtime_active_hours: Decimal
    active_alerts_count: int
    pricing_model_summary: str

    hierarchy_tree: NativeHierarchyNode


# ==============================================================================
# Service Dashboard Models (All 16 Panels)
# ==============================================================================


class ServiceDashboardResponse(BaseModel):
    """Service dashboard with all sixteen canonical panels."""

    service_id: str
    service_code: str
    service_name: str
    provider: str
    category: str
    time_window: TimeWindowContext
    freshness: WidgetFreshness

    # 1. Service Description
    description: str

    # 2. Pricing Model
    pricing_model: str  # Consumption, Tiered, Reserved, Spot, Committed

    # 3. Free-Tier Details
    free_tier_details: dict[str, Any]

    # 4. Actual Cost
    actual_cost: CostMetricWidget

    # 5. Estimated Cost
    estimated_cost: CostMetricWidget

    # 6. Forecast
    forecast_cost: CostMetricWidget

    # 7. Budget
    budget_allocated: Decimal
    budget_utilisation_pct: Decimal

    # 8. Runtime
    active_instances_count: int
    total_runtime_hours: Decimal
    runtime_status: str

    # 9. Usage
    metered_usage_quantity: Decimal
    usage_metric_name: str

    # 10. Pricing Units
    pricing_units: list[str]

    # 11. Cost Drivers
    primary_cost_driver: str
    secondary_cost_drivers: list[str]

    # 12. Dependencies
    upstream_dependencies: list[str]
    downstream_dependencies: list[str]

    # 13. Connectivity
    network_endpoints_count: int
    cross_region_egress_gb: Decimal

    # 14. Historical Trend
    historical_points: list[TimeSeriesPoint]

    # 15. Documentation Link
    documentation_url: str
    finops_guidelines_url: str

    # 16. Pricing Source
    pricing_source_name: str
    pricing_source_effective_date: str
    pricing_source_badge: str


# ==============================================================================
# Landing & Export Models (FR-503, FR-505)
# ==============================================================================


class RoleDefaultLanding(BaseModel):
    """Role-based default landing dashboard configuration (FR-503)."""

    role: str
    default_dashboard: str  # EXECUTIVE, PROVIDER, SERVICE, BUDGET, GOVERNANCE
    default_provider: str | None = None
    default_service_id: str | None = None


class UserLandingPreference(BaseModel):
    """Stored user preference for landing dashboard."""

    user_id: str
    role: str
    landing_dashboard: str
    provider: str | None = None
    service_id: str | None = None
    updated_at: datetime
