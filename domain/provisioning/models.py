"""Domain Models for Cost-Aware Provisioning Gate (Prompt 55).

Enforces:
- Master brief Section 6 (pre-deployment estimation); Control Principle Section 2; Addendum A Prompt 50.
- Saved estimate object with 4 computed values, full derivation, pricing source, and validity window.
- Provisioning request as a Prompt 50 workflow request type (never a separate approval mechanism).
- Multi-dimensional budget impact computation (remaining budget, consumption %, projected utilisation, forecast effect).
- Master-data gate triggers per scope, environment, and value band, defaulting to NOTIFY_ONLY (opt-in control).
- Quota headroom pre-checks (Prompt 54) and dependency/shared-service chain cost pre-checks (Prompt 33).
- Approval authority routing via AM-12 master data (never named individuals in code).
- Reconciliation loop comparing actuals to approved estimates over the first 3 billing periods with accuracy reporting.
- Unapproved-deployment detection with governance exception, assigned remediation task, and prominent advisory notice.
- Recorded emergency bypass path with post-hoc justification.
- Scenario comparison view evaluating alternative configurations side by side.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from domain.models.enums import ApprovalChainMode, ApproverResolutionType

ADVISORY_GATE_NOTICE = (
    "ADVISORY GATE NOTICE: CloudLens operates with read-only cloud provider credentials "
    "and provides governance visibility, cost accountability, and automated workflow tracking. "
    "CloudLens does not technically block infrastructure provisioning at the cloud provider API level."
)


# ==============================================================================
# 1. Lifecycle and Classification Enums
# ==============================================================================


class GateTriggerAction(StrEnum):
    """Configurable gate action evaluated from master data."""

    NO_GATE = "NO_GATE"
    NOTIFY_ONLY = "NOTIFY_ONLY"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVAL_REQUIRED_SPECIFIC_CHAIN = "APPROVAL_REQUIRED_SPECIFIC_CHAIN"


class ProvisioningRequestStatus(StrEnum):
    """Lifecycle status of a provisioning gate request."""

    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    BYPASSED = "BYPASSED"
    LINKED_TO_RESOURCE = "LINKED_TO_RESOURCE"


class EstimateAccuracyClassification(StrEnum):
    """Classification of estimate vs actual accuracy over 3 periods."""

    WITHIN_ACCURACY_BAND = "WITHIN_ACCURACY_BAND"  # Within +/- 10%
    UNDER_ESTIMATED = "UNDER_ESTIMATED"  # Actual > Approved by > 10%
    OVER_ESTIMATED = "OVER_ESTIMATED"  # Actual < Approved by > 10%


class BudgetImpactTier(StrEnum):
    """Visual materiality tier of budget consumption."""

    NEGLIGIBLE = "NEGLIGIBLE"  # < 5% of remaining budget
    MODERATE = "MODERATE"  # 5% - 25% of remaining budget
    SUBSTANTIAL = "SUBSTANTIAL"  # 25% - 50% of remaining budget
    CRITICAL = "CRITICAL"  # > 50% of remaining budget or over budget


# ==============================================================================
# 2. Saved Estimate Object
# ==============================================================================


class SavedEstimate(BaseModel):
    """Priced configuration with 4 computed values, full derivation, and validity window."""

    model_config = ConfigDict(populate_by_name=True)

    estimate_id: str = Field(..., description="Unique estimate identifier")
    tenant_id: str = Field(..., description="Tenant boundary")
    requester_id: str = Field(..., description="User ID of requester")
    requester_email: str = Field(..., description="Email of requester")

    provider: str = Field(..., description="Cloud provider (aws, azure, gcp, oci)")
    service: str = Field(..., description="Cloud service code (e.g. AmazonEC2, Virtual Machines)")
    region: str = Field(..., description="Datacenter region")
    size: str = Field(..., description="Compute instance type / SKU size")
    options: dict[str, Any] = Field(
        default_factory=dict, description="Configuration options (storage_gb, os, public_ip, etc.)"
    )

    hourly_cost: Decimal = Field(..., description="Estimated cost per hour")
    daily_cost: Decimal = Field(..., description="Estimated cost per day (24 hours)")
    monthly_cost: Decimal = Field(..., description="Estimated cost per standard month (730 hours)")
    annualised_cost: Decimal = Field(..., description="Annualised estimated cost (monthly * 12)")
    currency: str = Field(default="USD", description="Currency ISO 4217 code")

    derivation: dict[str, Any] = Field(
        default_factory=dict, description="Full mathematical derivation from Prompt 23"
    )
    pricing_source: str = Field(default="cloudlens_catalog", description="Pricing catalog source")
    pricing_effective_date: str = Field(
        default_factory=lambda: dt.date.today().isoformat(),
        description="Date of effective rate card",
    )
    valid_until: str = Field(
        ...,
        description="Validity expiration timestamp UTC after which estimate must be re-priced",
    )
    created_at: str = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC).isoformat(),
        description="Timestamp when estimate was generated",
    )

    def is_expired(self, as_of: dt.datetime | None = None) -> bool:
        """Returns True if the validity window has elapsed."""
        now = as_of or dt.datetime.now(dt.UTC)
        expiry_dt = dt.datetime.fromisoformat(self.valid_until.replace("Z", "+00:00"))
        return now > expiry_dt


# ==============================================================================
# 3. Master Data Gate Triggers & Approval Authority (AM-12)
# ==============================================================================


class GateTriggerRule(BaseModel):
    """Configurable master-data gate trigger rule per scope, environment, and value band."""

    rule_id: str = Field(..., description="Unique trigger rule identifier")
    scope_code: str = Field(default="*", description="Target scope code or '*' for global")
    environment: str = Field(
        default="*", description="Deployment environment (PROD, STAGING, DEV, or '*')"
    )
    min_monthly_amount: Decimal = Field(
        default=Decimal("0.00"), description="Lower boundary of monthly cost value band"
    )
    max_monthly_amount: Decimal | None = Field(
        default=None, description="Upper boundary of monthly cost value band (None if unbounded)"
    )
    action: GateTriggerAction = Field(
        default=GateTriggerAction.NOTIFY_ONLY,
        description="Trigger action (HARD RULE: defaults to NOTIFY_ONLY)",
    )
    approver_chain_id: str | None = Field(
        default=None, description="Specific workflow chain ID if APPROVAL_REQUIRED_SPECIFIC_CHAIN"
    )
    notes: str = Field(default="", description="Governance rationale")


class ApprovalAuthorityRule(BaseModel):
    """Approval-authority master (AM-12) mapping scope, threshold, and approver role."""

    rule_id: str = Field(..., description="Unique authority rule ID")
    scope_type: str = Field(
        default="BUSINESS_UNIT", description="Scope level (BU, COST_CENTRE, ORG)"
    )
    scope_code: str = Field(default="*", description="Specific scope code or '*'")
    min_monthly_amount: Decimal = Field(
        default=Decimal("0.00"), description="Minimum monthly threshold"
    )
    max_monthly_amount: Decimal | None = Field(
        default=None, description="Maximum monthly threshold"
    )
    approver_role: str = Field(
        default="FINOPS_ADMIN",
        description="Authorized approver role (NEVER resolved to named individual in code)",
    )
    approver_resolution: ApproverResolutionType = Field(
        default=ApproverResolutionType.ROLE,
        description="Resolution strategy (ROLE, SCOPE_OWNER, COST_CENTRE_OWNER, BU_OWNER)",
    )
    chain_mode: ApprovalChainMode = Field(default=ApprovalChainMode.SERIAL)
    sla_working_hours: int = Field(default=24, description="SLA in business working hours")


# ==============================================================================
# 4. Pre-Checks: Quota Headroom & Dependency Chain Cost
# ==============================================================================


class QuotaPreCheckResult(BaseModel):
    """Pre-check evaluating whether proposed deployment will exhaust or breach quota headroom."""

    is_blocked: bool = Field(
        default=False, description="True if proposed deployment exceeds quota absolute limit"
    )
    headroom_warning: bool = Field(
        default=False, description="True if remaining headroom drops below warning threshold"
    )
    current_headroom_pct: Decimal = Field(..., description="Current available headroom percentage")
    projected_headroom_pct: Decimal = Field(
        ..., description="Projected available headroom percentage post-deployment"
    )
    quota_name: str = Field(..., description="Name of the affected service limit")
    quota_code: str = Field(..., description="Machine identifier of quota")
    consumed_units: Decimal = Field(..., description="Current consumed units")
    limit_units: Decimal = Field(..., description="Maximum allowed limit units")
    projected_units: Decimal = Field(
        ..., description="Total projected units including proposed deployment"
    )
    message: str = Field(..., description="Human-readable assessment finding")


class DependencyComponentCost(BaseModel):
    """Discrete dependent service implied by the proposed deployment."""

    service_name: str = Field(
        ..., description="Inferred dependent service (e.g. ALB, NAT Gateway, Backup)"
    )
    category: str = Field(..., description="Service category (Compute, Storage, Network, Database)")
    estimated_monthly_cost: Decimal = Field(
        ..., description="Estimated monthly cost for this component"
    )
    basis: str = Field(..., description="Derivation rationale or topology rule")


class DependencyPreCheckResult(BaseModel):
    """Dependency and shared-service pre-check (Prompt 33) assessing complete application chain cost."""

    primary_monthly_cost: Decimal = Field(
        ..., description="Monthly cost of the primary requested resource"
    )
    inferred_dependencies: list[DependencyComponentCost] = Field(
        default_factory=list, description="Downstream dependent services"
    )
    total_chain_monthly_cost: Decimal = Field(
        ..., description="Total monthly cost of primary resource + all dependent services"
    )
    shared_service_apportionment: Decimal = Field(
        default=Decimal("0.00"), description="Apportioned share of central platform shared services"
    )
    chain_multiplier: Decimal = Field(
        default=Decimal("1.0"),
        description="Ratio of total chain cost to primary resource cost (chain / primary)",
    )


# ==============================================================================
# 5. Budget Impact Assessment
# ==============================================================================


class BudgetImpactAssessment(BaseModel):
    """Comprehensive budget impact analysis presenting all 4 key dimensions."""

    period: str = Field(..., description="Billing period partition, e.g. '2026-10'")
    period_budget: Decimal = Field(..., description="Assigned budget ceiling for the period")
    actual_spend: Decimal = Field(..., description="Current actual spend to date")
    remaining_budget: Decimal = Field(..., description="Remaining unspent budget before request")

    request_monthly_cost: Decimal = Field(
        ..., description="Estimated monthly consumption of this request"
    )
    projected_spend: Decimal = Field(..., description="Projected spend (actual + request)")
    projected_utilisation_pct: Decimal = Field(
        ..., description="Projected budget utilisation percentage (projected / budget * 100)"
    )
    consumption_of_remaining_pct: Decimal = Field(
        ..., description="Percentage of remaining budget this request consumes"
    )

    current_forecast: Decimal = Field(..., description="Existing month-end forecast before request")
    revised_forecast: Decimal = Field(..., description="Revised forecast including this request")
    forecast_variance_change: Decimal = Field(
        ..., description="Shift in forecasted month-end budget variance"
    )

    impact_tier: BudgetImpactTier = Field(
        ..., description="Visual materiality tier (NEGLIGIBLE, MODERATE, SUBSTANTIAL, CRITICAL)"
    )
    commentary: str = Field(..., description="Narrative executive summary of budget impact")


# ==============================================================================
# 6. Bypass & Reconciliation Tracking
# ==============================================================================


class BypassRecord(BaseModel):
    """Recorded emergency bypass path with post-hoc justification."""

    bypass_id: str = Field(..., description="Unique bypass transaction ID")
    request_id: str = Field(..., description="Associated provisioning request ID")
    bypassed_by: str = Field(..., description="User ID who executed bypass")
    bypassed_at: str = Field(default_factory=lambda: dt.datetime.now(dt.UTC).isoformat())
    justification: str = Field(
        ..., min_length=10, description="Mandatory post-hoc business rationale"
    )
    governance_exception_id: str = Field(..., description="Recorded governance exception ID")


class ResourcePeriodActual(BaseModel):
    """Actual billed cost recorded for a post-provisioning billing period."""

    period: str = Field(..., description="Billing period (e.g. '2026-10')")
    billed_amount: Decimal = Field(..., description="Actual billed spend in period")
    recorded_at: str = Field(default_factory=lambda: dt.datetime.now(dt.UTC).isoformat())


class EstimateVsActualTracking(BaseModel):
    """Three-period reconciliation tracking linking approved estimate to provisioned resource."""

    tracking_id: str = Field(..., description="Unique tracking identifier")
    request_id: str = Field(..., description="Source approved provisioning request ID")
    resource_id: str = Field(..., description="Linked cloud resource identifier")
    requester_id: str = Field(..., description="Requester user ID")
    approver_role: str = Field(..., description="Role that authorized the request")
    service: str = Field(..., description="Cloud service name")
    approved_monthly_estimate: Decimal = Field(..., description="Approved monthly cost figure")

    periods_tracked: list[ResourcePeriodActual] = Field(
        default_factory=list, description="Observed billing periods (up to 3)"
    )
    latest_variance_amount: Decimal | None = None
    latest_variance_pct: Decimal | None = None
    classification: EstimateAccuracyClassification | None = None
    is_three_periods_complete: bool = Field(
        default=False, description="True once 3 full periods have been observed and reconciled"
    )


class AccuracyReport(BaseModel):
    """Executive accuracy report across requesters, services, and approvers."""

    tenant_id: str
    generated_at: str = Field(default_factory=lambda: dt.datetime.now(dt.UTC).isoformat())
    total_tracked: int
    three_period_completed_count: int
    within_band_pct: Decimal
    under_estimated_pct: Decimal
    over_estimated_pct: Decimal
    mean_absolute_percentage_error: Decimal

    by_requester: list[dict[str, Any]] = Field(default_factory=list)
    by_service: list[dict[str, Any]] = Field(default_factory=list)
    by_approver: list[dict[str, Any]] = Field(default_factory=list)


class UnapprovedDeploymentFinding(BaseModel):
    """Detection of resource deployed in a gated scope without an approved request."""

    finding_id: str = Field(..., description="Unique finding ID")
    resource_id: str = Field(..., description="Cloud resource identifier")
    resource_name: str = Field(..., description="Resource name or tag")
    provider: str = Field(..., description="Cloud provider")
    service: str = Field(..., description="Cloud service")
    scope_code: str = Field(..., description="Gated scope code")
    detected_at: str = Field(default_factory=lambda: dt.datetime.now(dt.UTC).isoformat())
    estimated_monthly_cost: Decimal = Field(
        ..., description="Estimated monthly spend of unapproved resource"
    )
    governance_exception_id: str = Field(..., description="Logged governance exception ID")
    remediation_task_id: str = Field(..., description="Assigned remediation task ID")
    advisory_disclaimer: str = Field(
        default=ADVISORY_GATE_NOTICE,
        description="Plain statement of advisory nature (read-only credentials)",
    )


# ==============================================================================
# 7. Scenario Comparison View (Decision Aid)
# ==============================================================================


class ScenarioOption(BaseModel):
    """Single architecture configuration scenario evaluated side by side."""

    scenario_id: str = Field(..., description="Option key (e.g. OPTION_A, BASELINE, SERVERLESS)")
    name: str = Field(..., description="Friendly title")
    description: str = Field(default="", description="Technical summary")
    estimate: SavedEstimate = Field(..., description="Priced configuration")
    budget_impact: BudgetImpactAssessment = Field(..., description="Calculated budget impact")
    quota_pre_check: QuotaPreCheckResult = Field(..., description="Quota headroom evaluation")
    dependency_pre_check: DependencyPreCheckResult = Field(
        ..., description="Application chain cost"
    )

    monthly_cost: Decimal = Field(..., description="Monthly cost")
    annualised_cost: Decimal = Field(..., description="Annualised cost")
    delta_from_baseline_monthly: Decimal = Field(
        default=Decimal("0.00"), description="Delta against baseline option ($)"
    )
    delta_from_baseline_pct: Decimal = Field(
        default=Decimal("0.00"), description="Percentage delta against baseline option (%)"
    )


class ScenarioComparisonView(BaseModel):
    """Side-by-side comparison of 2 or 3 architecture configurations as a decision aid."""

    comparison_id: str = Field(..., description="Unique comparison identifier")
    baseline_scenario_id: str = Field(..., description="ID of baseline reference scenario")
    target_scope: str = Field(..., description="Evaluation scope code")
    period: str = Field(..., description="Target billing period")
    scenarios: list[ScenarioOption] = Field(
        ..., min_length=2, max_length=4, description="2 to 4 scenarios compared side by side"
    )
    recommendation_notes: str = Field(default="", description="FinOps optimization commentary")


# ==============================================================================
# 8. Provisioning Request Entity
# ==============================================================================


class ProvisioningRequest(BaseModel):
    """Formal cost-aware provisioning gate request wired into Prompt 50 workflow engine."""

    model_config = ConfigDict(populate_by_name=True)

    request_id: str = Field(..., description="Unique provisioning request identifier")
    tenant_id: str = Field(..., description="Tenant boundary")
    estimate_id: str = Field(..., description="Source saved estimate ID")
    estimate: SavedEstimate = Field(..., description="Underlying priced estimate")

    target_scope: str = Field(..., description="Target scope code (e.g. BU-RETAIL, CC-ENG)")
    scope_type: str = Field(default="BUSINESS_UNIT", description="Target scope type")
    intended_application: str = Field(..., description="Workload application identifier")
    intended_environment: str = Field(
        ..., description="Target environment (PROD, STAGING, DEV, etc.)"
    )
    owner_id: str = Field(..., description="Accountable owner user ID")
    owner_email: str = Field(..., description="Accountable owner email")
    cost_centre: str = Field(..., description="Responsible cost centre code")
    business_justification: str = Field(..., min_length=10, description="Business justification")
    intended_start_date: str = Field(..., description="Proposed deployment start date (ISO)")

    budget_impact: BudgetImpactAssessment = Field(
        ..., description="Comprehensive budget impact evaluation"
    )
    quota_pre_check: QuotaPreCheckResult = Field(..., description="Quota headroom evaluation")
    dependency_pre_check: DependencyPreCheckResult = Field(
        ..., description="Application chain cost evaluation"
    )
    gate_action: GateTriggerAction = Field(..., description="Resolved gate action from master data")

    status: ProvisioningRequestStatus = Field(default=ProvisioningRequestStatus.DRAFT)
    workflow_request_id: str | None = Field(
        default=None, description="ID of linked WorkflowRequest in Prompt 50 engine"
    )
    bypass_details: BypassRecord | None = Field(
        default=None, description="Bypass record if bypassed"
    )

    linked_resource_id: str | None = Field(
        default=None, description="Linked cloud inventory resource ID upon discovery"
    )
    linked_at: str | None = None
    created_at: str = Field(default_factory=lambda: dt.datetime.now(dt.UTC).isoformat())
    advisory_notice: str = Field(
        default=ADVISORY_GATE_NOTICE,
        description="Mandatory advisory disclosure stating platform holds read-only credentials",
    )
