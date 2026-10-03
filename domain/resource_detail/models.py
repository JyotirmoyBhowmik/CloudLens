"""Domain Models for Resource Detail, Cost Detail, Usage, Runtime and Investigation (Prompt 39).

Enforces:
- Master brief Section 29 (Resource detail, 15 core questions).
- Master brief Section 51 (Cost detail, drivers, investigation).
- BBP Section 30.3 (Resource detail panels).
- BBP Section 31.3 (Investigation view & cost explorer).
- Six distinct unblended cost values: current, actual, estimated, forecast, budget, variance.
- Cost driver decomposition where drivers sum strictly to total spend.
- Usage gap discipline: explicit gap rendered as NO_DATA, never zero.
- Schedule adherence with excess hours and excess monetary valuation.
- Investigation view with highlighted change point, contributing resources, changed dimensions, inventory diffs, and restatement flags.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CostDriverCategory(StrEnum):
    """Canonical cost driver decomposition categories."""

    COMPUTE = "COMPUTE"
    STORAGE = "STORAGE"
    DATABASE = "DATABASE"
    NETWORK = "NETWORK"
    BACKUP = "BACKUP"
    LICENSING = "LICENSING"
    MANAGEMENT = "MANAGEMENT"
    OTHER = "OTHER"


class CostDriverItem(BaseModel):
    """Decomposed cost driver explaining why a resource costs a stated amount."""

    model_config = ConfigDict(frozen=True)

    category: CostDriverCategory
    name: str = Field(..., description="Driver title (e.g. vCPU Hours, Provisioned IOPS)")
    amount: Decimal = Field(..., description="Monetary spend incurred by this driver")
    percentage: Decimal = Field(..., description="Percentage of total resource cost (0-100)")
    unit: str = Field(..., description="Usage measurement unit (e.g. Core-hours, GB-month)")
    quantity: Decimal = Field(..., description="Consumed quantity")
    rate: Decimal = Field(..., description="Unit rate")
    explanation: str = Field(..., description="Business explanation of driver cause")


class PricingPanelData(BaseModel):
    """Pricing panel specification adhering strictly to master brief."""

    model_config = ConfigDict(frozen=True)

    pricing_status: str = Field(..., description="FREE, PAID, or CONDITIONAL")
    pricing_model: str = Field(..., description="On-Demand, Reserved, Spot, Consumption, Tiered")
    unit: str = Field(..., description="Pricing unit, e.g. hour, GB-mo, invocation")
    unit_price: Decimal = Field(..., description="Published price per unit")
    free_tier_details: str | None = Field(
        default=None, description="Free tier allowance description"
    )
    free_tier_allowance: str | None = Field(default=None, description="Allowance threshold")
    free_tier_consumed_pct: Decimal = Field(
        default=Decimal("0.00"), description="Consumed allowance %"
    )
    additional_cost_conditions: str | None = Field(
        default=None, description="Additional surcharge criteria"
    )
    region: str = Field(..., description="Pricing region")
    currency: str = Field(default="USD")
    pricing_source: str = Field(..., description="Rate card source and API version")
    effective_date: datetime = Field(..., description="Date pricing rates took effect")


class CostPanelData(BaseModel):
    """Six distinct unblended cost values on resource detail."""

    model_config = ConfigDict(frozen=True)

    current_cost: Decimal = Field(..., description="Month-to-date unbilled actual cost")
    actual_cost: Decimal = Field(..., description="Prior billing period closed actual cost")
    estimated_cost: Decimal = Field(..., description="Prompt 23 pre-deployment estimate baseline")
    forecast_cost: Decimal = Field(..., description="Projected period-end spend")
    budget_amount: Decimal = Field(..., description="Target allocated budget")
    variance: Decimal = Field(..., description="Monetary variance (forecast - budget)")
    variance_ratio_pct: Decimal = Field(..., description="Percentage variance against budget")
    variance_status: str = Field(..., description="FAVOURABLE, UNFAVOURABLE, ON_TARGET")
    currency: str = Field(default="USD")


class UsageDataPoint(BaseModel):
    """Usage time series observation with expectation band and explicit gap flag."""

    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    value: float | None = Field(
        default=None, description="Measured quantity, or None for explicit gap"
    )
    expectation_min: float | None = None
    expectation_max: float | None = None
    is_gap: bool = Field(default=False, description="True if telemetry was missed/uncollected")
    gap_reason: str | None = None


class UsageDetailPanel(BaseModel):
    """Usage detail view with metric series against expectation band."""

    model_config = ConfigDict(frozen=True)

    metric_name: str
    unit: str
    monitoring_type_code: str
    monitoring_type_name: str
    threshold_warning: float
    threshold_critical: float
    time_series: list[UsageDataPoint] = Field(default_factory=list)
    has_telemetry_gap: bool = Field(default=False)


class RuntimeExemptionSummary(BaseModel):
    """Active runtime schedule exemption record."""

    model_config = ConfigDict(frozen=True)

    exemption_id: str
    author: str
    reason: str
    approved_at: datetime
    expires_at: datetime
    is_active: bool = True


class RuntimePanelData(BaseModel):
    """Runtime view with schedule adherence, excess hours, and excess cost."""

    model_config = ConfigDict(frozen=True)

    runtime_state: str = Field(..., description="RUNNING, STOPPED, DEALLOCATED, etc.")
    schedule_name: str | None = None
    schedule_expression: str | None = None
    adherence_status: str = Field(..., description="COMPLIANT, OUT_OF_SCHEDULE, EXEMPTED")
    excess_hours: Decimal = Field(
        default=Decimal("0.00"), description="Out-of-schedule execution hours"
    )
    excess_cost: Decimal = Field(
        default=Decimal("0.00"), description="Monetary valuation of out-of-schedule spend"
    )
    active_exemptions: list[RuntimeExemptionSummary] = Field(default_factory=list)


class BreadcrumbItem(BaseModel):
    """Clickable breadcrumb item in resource hierarchy."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    level: str
    deep_link: str


class OwnershipAttribution(BaseModel):
    """Resource ownership and governance attribution with resolution rules."""

    model_config = ConfigDict(frozen=True)

    business_owner: str
    technical_owner: str
    owner_email: str | None = None
    team: str | None = None
    application: str
    environment: str
    cost_center: str
    business_unit: str
    resolution_rules: dict[str, str] = Field(
        default_factory=dict,
        description="Rule explanation that resolved each attribution dimension",
    )


class DependencyNodeItem(BaseModel):
    """Connected upstream or downstream resource."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    provider: str
    service_name: str
    relationship_type: str
    direction: str  # UPSTREAM or DOWNSTREAM
    status: str


class ConnectivityEndpoint(BaseModel):
    """Network and communication endpoint."""

    model_config = ConfigDict(frozen=True)

    endpoint_type: str
    address: str
    port: int | None = None
    protocol: str = "TCP"


class ResourceAlertItem(BaseModel):
    """Active alert on this resource."""

    model_config = ConfigDict(frozen=True)

    alert_id: str
    severity: str  # HIGH, MEDIUM, LOW, CRITICAL
    title: str
    triggered_at: datetime
    status: str


class AuditLogItem(BaseModel):
    """Resource governance and change audit entry."""

    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    actor: str
    action: str
    details: dict[str, Any] = Field(default_factory=dict)


class FifteenQuestionsSummary(BaseModel):
    """Direct answers to all fifteen core questions from Master Brief Section 29."""

    model_config = ConfigDict(frozen=True)

    q1_what_it_is: str
    q2_where: str
    q3_who_owns_it: str
    q4_what_it_does: str
    q5_how_connected: str
    q6_how_charged: str
    q7_whether_free: str
    q8_what_allowance: str
    q9_what_causes_charges: str
    q10_how_much_it_cost: str
    q11_expected_cost: str
    q12_budget: str
    q13_threshold_crossed: str
    q14_why_cost_changed: str
    q15_provider_info_support: str


class ResourceDetailFull(BaseModel):
    """Full canonical resource detail model with all required panels."""

    model_config = ConfigDict(frozen=True)

    # 1. Overview & Metadata
    id: str
    tenant_id: str
    scope_id: str
    native_id: str
    name: str
    provider: str
    service_id: str
    service_name: str
    service_category: str
    resource_type: str
    region_id: str
    region_name: str
    availability_zone: str | None = None
    lifecycle_status: str
    created_at: datetime
    last_synced_at: datetime
    tags: list[dict[str, Any]] = Field(default_factory=list)

    # 2. Provider-Native Information
    provider_native: dict[str, Any] = Field(default_factory=dict)

    # 3. Hierarchy Breadcrumbs
    breadcrumbs: list[BreadcrumbItem] = Field(default_factory=list)

    # 4. Ownership & Resolution Rules
    ownership: OwnershipAttribution

    # 5. Pricing Panel
    pricing: PricingPanelData

    # 6. Cost Panel (6 Distinct Values)
    cost: CostPanelData

    # 7. Cost Transparency & Driver Decomposition
    cost_drivers: list[CostDriverItem] = Field(default_factory=list)
    total_driver_amount: Decimal = Field(default=Decimal("0.00"))

    # 8. Usage Detail
    usage: UsageDetailPanel

    # 9. Runtime View
    runtime: RuntimePanelData

    # 10. Budget & Thresholds
    threshold_state: str  # NORMAL, WARNING, CRITICAL
    amber_threshold_pct: Decimal = Decimal("80.00")
    red_threshold_pct: Decimal = Decimal("100.00")

    # 11. Dependencies & Connectivity
    dependencies: list[DependencyNodeItem] = Field(default_factory=list)
    connectivity_endpoints: list[ConnectivityEndpoint] = Field(default_factory=list)

    # 12. Alerts
    alerts: list[ResourceAlertItem] = Field(default_factory=list)

    # 13. History & Forecast
    historical_spend_trend: list[dict[str, Any]] = Field(default_factory=list)
    forecast_confidence_interval: dict[str, Decimal] = Field(default_factory=dict)

    # 14. Audit
    audit_trail: list[AuditLogItem] = Field(default_factory=list)

    # 15. The 15 Core Questions Checklist
    fifteen_questions: FifteenQuestionsSummary


# ==============================================================================
# Cost Explorer Models (Prompt 39)
# ==============================================================================


class CostExplorerGranularity(StrEnum):
    HOURLY = "HOURLY"
    DAILY = "DAILY"
    MONTHLY = "MONTHLY"


class CostExplorerDimension(StrEnum):
    PROVIDER = "PROVIDER"
    SERVICE = "SERVICE"
    ACCOUNT = "ACCOUNT"
    REGION = "REGION"
    APPLICATION = "APPLICATION"
    ENVIRONMENT = "ENVIRONMENT"
    COST_CENTRE = "COST_CENTRE"
    OWNER = "OWNER"
    CHARGE_CATEGORY = "CHARGE_CATEGORY"


class CostExplorerSeriesPoint(BaseModel):
    """Time-series cost point within a grouped dimension."""

    timestamp: str
    amount: Decimal


class CostExplorerGroup(BaseModel):
    """Grouped aggregation in Cost Explorer."""

    group_id: str
    group_name: str
    total_cost: Decimal
    percentage: Decimal
    series: list[CostExplorerSeriesPoint] = Field(default_factory=list)
    contributing_resource_count: int = 0


class CostExplorerQuery(BaseModel):
    """Query parameters for Cost Explorer."""

    dimension: CostExplorerDimension = Field(default=CostExplorerDimension.SERVICE)
    granularity: CostExplorerGranularity = Field(default=CostExplorerGranularity.DAILY)
    start_date: str | None = None
    end_date: str | None = None
    comparison_period: str | None = Field(default=None, description="POP, YOY, or None")
    filters: dict[str, list[str]] = Field(default_factory=dict)


class CostExplorerResponse(BaseModel):
    """Response payload for multi-dimensional cost exploration."""

    dimension: CostExplorerDimension
    granularity: CostExplorerGranularity
    total_spend: Decimal
    currency: str = "USD"
    groups: list[CostExplorerGroup] = Field(default_factory=list)
    comparison_total_spend: Decimal | None = None
    variance_pct: Decimal | None = None
    cost_drivers: list[CostDriverItem] = Field(default_factory=list)


# ==============================================================================
# Investigation View Models (Largest Increases) (Prompt 39)
# ==============================================================================


class ContributingResourceDelta(BaseModel):
    """Resource driving the cost change point."""

    resource_id: str
    resource_name: str
    service_name: str
    prior_spend: Decimal
    current_spend: Decimal
    delta_spend: Decimal
    percentage_contribution: Decimal


class ChangedPricingDimension(BaseModel):
    """Pricing dimension change detected during the cost spike."""

    dimension_name: str
    old_value: str
    new_value: str
    effective_date: datetime
    impact_description: str


class InventoryChangeWindowItem(BaseModel):
    """Inventory configuration change occurring in the same window."""

    timestamp: datetime
    resource_id: str
    resource_name: str
    change_type: str  # RESIZED, CREATED, RECONFIGURED
    description: str


class DailySpendInvestigationPoint(BaseModel):
    """Daily cost series point with highlighted change point."""

    date: str
    spend: Decimal
    is_change_point: bool = False
    note: str | None = None


class CostInvestigationReport(BaseModel):
    """Investigation view for Largest Increases explaining cost movements."""

    entity_id: str
    entity_name: str
    service_name: str
    provider: str
    change_point_date: str
    prior_daily_spend: Decimal
    post_daily_spend: Decimal
    increase_amount: Decimal
    increase_percentage: Decimal
    is_restatement: bool = False
    restatement_note: str | None = None
    daily_series: list[DailySpendInvestigationPoint] = Field(default_factory=list)
    contributing_resources: list[ContributingResourceDelta] = Field(default_factory=list)
    changed_pricing_dimensions: list[ChangedPricingDimension] = Field(default_factory=list)
    inventory_changes: list[InventoryChangeWindowItem] = Field(default_factory=list)
    root_cause_summary: str


class ChargeLineItem(BaseModel):
    """Detailed contributing charge line subject to financial-detail permissions."""

    model_config = ConfigDict(frozen=True)

    charge_id: str
    resource_id: str
    resource_name: str
    provider: str
    service_name: str
    usage_date: str
    charge_category: CostDriverCategory
    description: str
    quantity: Decimal
    unit: str
    rate: Decimal
    amount: Decimal
    currency: str = "USD"


class ChargeLinesResponse(BaseModel):
    """Paginated contributing charge lines response."""

    total_count: int
    limit: int
    offset: int
    total_amount: Decimal
    currency: str = "USD"
    items: list[ChargeLineItem] = Field(default_factory=list)


class RuntimeEstateOverview(BaseModel):
    """Estate-wide runtime schedule adherence summary."""

    total_managed_resources: int
    compliant_count: int
    out_of_schedule_count: int
    exempted_count: int
    compliance_rate_pct: Decimal
    total_excess_hours: Decimal
    total_excess_cost: Decimal
    currency: str = "USD"
    active_exemptions: list[RuntimeExemptionSummary] = Field(default_factory=list)
