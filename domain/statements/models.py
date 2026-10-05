"""Domain Models for Showback, Chargeback Statements, and Cost Allocation Packs (Prompt 52).

Enforces:
- Prompt 52 / BBP Sections 17.5, 22, 36; Master brief Section 51.
- Recipient scope statements (Business Unit, Cost Centre, Application, Project, Team).
- Showback vs Chargeback distinction: MVP is SHOWBACK with explicit management information banner.
  Chargeback fields (journal reference, posting period, GL account) prepared behind Phase 2 flag.
- Shared-service apportionment with mandatory visible basis.
- Period close cycle (Draft -> In Review -> Finalised -> Adjusted via restatement).
- Dispute items routed through workflow engine with tracked SLA, owner, and documented reallocation.
- Formal acceptance with outstanding-acceptance reporting.
- Multi-currency presentation with exchange rate and rate date disclosure.
- Allocation transparency view with drill-through to rules, contributing resources, and permissioned charge lines.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from domain.models.exceptions import MissingApportionmentBasisException

# ==============================================================================
# 1. Statement Lifecycle & Classification Enums
# ==============================================================================


class RecipientScopeType(StrEnum):
    """Supported recipient scope types for cost statements (Prompt 52)."""

    BUSINESS_UNIT = "BUSINESS_UNIT"
    COST_CENTRE = "COST_CENTRE"
    APPLICATION = "APPLICATION"
    PROJECT = "PROJECT"
    TEAM = "TEAM"


class StatementLifecycleStatus(StrEnum):
    """Lifecycle states of a showback statement through the period close cycle."""

    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    FINALISED = "FINALISED"
    ADJUSTED = "ADJUSTED"
    SUPERSEDED = "SUPERSEDED"
    DISPUTED = "DISPUTED"
    ACCEPTED = "ACCEPTED"


class StatementMode(StrEnum):
    """Statement accounting presentation mode."""

    SHOWBACK = "SHOWBACK"
    CHARGEBACK = "CHARGEBACK"


class BudgetVarianceStatus(StrEnum):
    """Budget alignment health status."""

    ON_TRACK = "ON_TRACK"
    AT_RISK = "AT_RISK"
    EXCEEDED = "EXCEEDED"
    UNBUDGETED = "UNBUDGETED"


class MovementDirection(StrEnum):
    """Direction of cost delta compared to prior period."""

    UP = "UP"
    DOWN = "DOWN"
    FLAT = "FLAT"


class DisputeStatus(StrEnum):
    """Lifecycle status of a queried/disputed statement line."""

    SUBMITTED = "SUBMITTED"
    IN_REVIEW = "IN_REVIEW"
    RESOLVED_ACCEPTED = "RESOLVED_ACCEPTED"
    RESOLVED_REJECTED = "RESOLVED_REJECTED"


class ExportFormat(StrEnum):
    """Supported presentation export formats."""

    JSON = "JSON"
    MARKDOWN = "MARKDOWN"
    HTML = "HTML"
    CSV = "CSV"


# ==============================================================================
# 2. Multi-Dimensional Breakdown Items
# ==============================================================================


class ProviderBreakdownItem(BaseModel):
    """Cost breakdown by cloud infrastructure provider."""

    provider: str = Field(..., description="Cloud provider code (e.g. AWS, AZURE, GCP, OCI)")
    allocated_amount: Decimal = Field(..., description="Total allocated cost from this provider")
    share_percentage: Decimal = Field(
        ..., description="Percentage of total statement allocated cost"
    )
    prior_period_amount: Decimal = Field(default=Decimal("0.00"), description="Prior period spend")
    movement_amount: Decimal = Field(default=Decimal("0.00"), description="Delta from prior period")
    movement_pct: Decimal = Field(default=Decimal("0.00"), description="Percentage movement")


class CategoryBreakdownItem(BaseModel):
    """Cost breakdown by canonical FOCUS service category."""

    service_category: str = Field(
        ..., description="Service category (e.g. Compute, Storage, Database, Network)"
    )
    allocated_amount: Decimal = Field(..., description="Total allocated cost in category")
    share_percentage: Decimal = Field(..., description="Share percentage of total statement cost")
    prior_period_amount: Decimal = Field(
        default=Decimal("0.00"), description="Prior period category spend"
    )


class ApplicationBreakdownItem(BaseModel):
    """Cost breakdown attributed to business application workloads."""

    application_code: str = Field(..., description="Application identifier (e.g. app-checkout)")
    application_name: str = Field(..., description="Human-readable application name")
    allocated_amount: Decimal = Field(..., description="Total allocated cost for application")
    share_percentage: Decimal = Field(..., description="Share percentage of total statement cost")


class EnvironmentBreakdownItem(BaseModel):
    """Cost breakdown by deployment lifecycle environment."""

    environment: str = Field(
        ..., description="Environment classification (e.g. PROD, STAGING, DEV, DR)"
    )
    allocated_amount: Decimal = Field(..., description="Total allocated cost in environment")
    share_percentage: Decimal = Field(..., description="Share percentage of total statement cost")


# ==============================================================================
# 3. Variance, Movements & Shared Cost Apportionment
# ==============================================================================


class CostMovementItem(BaseModel):
    """Largest cost movement item with business narrative explanation (Prompt 52)."""

    item_name: str = Field(
        ..., description="Resource, service or category exhibiting material change"
    )
    prior_amount: Decimal = Field(..., description="Previous billing period amount")
    current_amount: Decimal = Field(..., description="Current billing period amount")
    delta_amount: Decimal = Field(..., description="Net absolute dollar variance")
    delta_pct: Decimal = Field(..., description="Percentage shift")
    movement_direction: MovementDirection = Field(..., description="UP, DOWN, or FLAT")
    narrative_explanation: str = Field(
        ..., description="Business explanation of why this cost shifted"
    )


class SharedServiceApportionmentItem(BaseModel):
    """Shared-service cost apportionment line with mandatory visible basis (Prompt 52 / BBP 17.5)."""

    shared_service_id: str = Field(..., description="ID or key of the shared platform service/pool")
    shared_service_name: str = Field(
        ..., description="Human-readable title (e.g. Shared K8s Cluster)"
    )
    provider: str = Field(default="AWS", description="Underlying provider")
    source_total_cost: Decimal = Field(..., description="Total gross shared cost prior to split")
    apportioned_amount: Decimal = Field(..., description="Cost allocated to this recipient scope")
    apportionment_percentage: Decimal = Field(
        ..., description="Percentage share received (e.g. 25.0)"
    )
    allocation_rule_id: str = Field(
        ..., description="ID of the allocation rule producing this split"
    )
    allocation_rule_name: str = Field(..., description="Name of the allocation rule")
    apportionment_basis: str = Field(
        ...,
        min_length=3,
        description="MANDATORY EXPLICIT BASIS: formula, metric, or ratio explaining the apportionment.",
    )

    @field_validator("apportionment_basis")
    @classmethod
    def validate_basis_not_empty(cls, v: str) -> str:
        """Enforces: 'Do not apportion shared cost without showing the basis.'"""
        if not v or not v.strip():
            raise MissingApportionmentBasisException(
                shared_service_id="unknown",
                reason="Apportionment basis must be explicitly documented on statement",
            )
        return v.strip()


class UnallocatedCostItem(BaseModel):
    """Explicit disclosure of unallocated cost associated with recipient context (Prompt 08 / 52)."""

    unallocated_amount: Decimal = Field(
        ..., description="Dollar amount that could not be attributed"
    )
    unallocated_percentage: Decimal = Field(
        ..., description="Percentage of total estate unallocated spend"
    )
    reasons: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Root causes for non-allocation (e.g. missing Owner tag, orphan scope)",
    )


class DiscountBenefitItem(BaseModel):
    """Commitment, Savings Plan, and Enterprise Discount benefit received by this scope."""

    list_cost: Decimal = Field(..., description="Public list rate cost equivalent")
    contracted_cost: Decimal = Field(..., description="Negotiated enterprise rate equivalent")
    effective_cost: Decimal = Field(..., description="Actual billed/effective cost paid")
    realised_discount_amount: Decimal = Field(
        ..., description="Total realised discount savings ($)"
    )
    realised_discount_percentage: Decimal = Field(
        ..., description="Realised savings percentage against list rates"
    )


class CurrencyDisclosure(BaseModel):
    """Full foreign exchange rate disclosure for multi-currency presentation (Prompt 46 / 52)."""

    base_currency: str = Field(default="USD", description="Billing baseline currency")
    presentation_currency: str = Field(default="USD", description="Statement presentation currency")
    exchange_rate: Decimal = Field(
        default=Decimal("1.0"), description="Effective exchange rate applied"
    )
    rate_type: str = Field(
        default="CORPORATE_CLOSING", description="FX rate provider/type classification"
    )
    rate_effective_date: str = Field(
        default_factory=lambda: dt.date.today().isoformat(),
        description="Date the exchange rate was fixed",
    )


class Phase2ChargebackFields(BaseModel):
    """Phase 2 Chargeback fields prepared but disabled by default (Prompt 52)."""

    is_enabled: bool = Field(
        default=False,
        description="Phase 2 toggle. Statements state they are showback when False.",
    )
    journal_reference: str | None = Field(default=None, description="GL journal transaction ID")
    posting_period: str | None = Field(default=None, description="ERP financial posting period")
    gl_account: str | None = Field(default=None, description="General Ledger account code")
    chargeback_status: str | None = Field(
        default=None, description="ERP integration posting status"
    )


# ==============================================================================
# 4. Master-Data Statement Template
# ==============================================================================


class StatementTemplate(BaseModel):
    """Master-data-driven statement layout, section configuration, and phrasing (Prompt 52)."""

    template_id: str = Field(..., description="Unique template identifier")
    name: str = Field(..., description="Template friendly title")
    description: str = Field(default="", description="Business purpose of template")
    sections_enabled: list[str] = Field(
        default_factory=lambda: [
            "opening_summary",
            "kpi_summary",
            "budget_variance",
            "prior_period_comparison",
            "provider_breakdown",
            "service_category_breakdown",
            "application_breakdown",
            "environment_breakdown",
            "largest_movements",
            "shared_service_apportionment",
            "unallocated_cost",
            "discount_benefit",
            "governance_freshness",
        ]
    )
    section_order: list[str] = Field(
        default_factory=lambda: [
            "opening_summary",
            "kpi_summary",
            "budget_variance",
            "prior_period_comparison",
            "provider_breakdown",
            "service_category_breakdown",
            "application_breakdown",
            "environment_breakdown",
            "largest_movements",
            "shared_service_apportionment",
            "unallocated_cost",
            "discount_benefit",
            "governance_freshness",
        ]
    )
    narrative_phrasing: dict[str, str] = Field(
        default_factory=lambda: {
            "showback_banner": (
                "SHOWBACK STATEMENT — FOR INTERNAL MANAGEMENT INFORMATION ONLY. "
                "THIS STATEMENT DOES NOT CONSTITUTE A GENERAL LEDGER JOURNAL CHARGE."
            ),
            "budget_on_track": (
                "Spend of ${cost} is within allocated budget of ${budget} "
                "by ${variance} ({variance_pct}% headroom)."
            ),
            "budget_exceeded": (
                "Spend of ${cost} exceeded allocated budget of ${budget} "
                "by ${variance} ({variance_pct}% overage)."
            ),
            "movement_increase": (
                "Spend increased by ${delta} ({pct}%) compared to prior period {prior_period} "
                "primarily driven by {top_driver}."
            ),
            "movement_decrease": (
                "Spend decreased by ${delta} ({pct}%) compared to prior period {prior_period}."
            ),
        }
    )


# ==============================================================================
# 5. Showback Statement Entity
# ==============================================================================


class ShowbackStatement(BaseModel):
    """Authoritative monthly showback statement and cost allocation pack (Prompt 52)."""

    model_config = ConfigDict(populate_by_name=True)

    # Identifiers & Scope
    statement_id: str = Field(..., description="Unique statement identifier")
    tenant_id: str = Field(..., description="Tenant identifier")
    period: str = Field(..., description="Billing period partition, e.g. '2026-09'")
    version: int = Field(default=1, description="Statement version (incremented on adjustment)")
    supersedes_statement_id: str | None = Field(
        default=None, description="ID of previous statement version if adjusted"
    )

    scope_type: RecipientScopeType = Field(..., description="Recipient scope classification")
    scope_code: str = Field(
        ..., description="Recipient accounting or organizational code (e.g. BU-RETAIL)"
    )
    scope_name: str = Field(..., description="Human-readable recipient title")
    recipient_owner_id: str = Field(..., description="Accountable owner user ID")
    recipient_owner_email: str = Field(..., description="Accountable owner email address")

    # Lifecycle & Mode
    status: StatementLifecycleStatus = Field(
        default=StatementLifecycleStatus.DRAFT,
        description="Lifecycle status in period close cycle",
    )
    mode: StatementMode = Field(
        default=StatementMode.SHOWBACK,
        description="MVP is strictly SHOWBACK (management information only)",
    )
    showback_banner: str = Field(
        default=(
            "SHOWBACK STATEMENT — FOR INTERNAL MANAGEMENT INFORMATION ONLY. "
            "THIS STATEMENT DOES NOT CONSTITUTE A GENERAL LEDGER JOURNAL CHARGE."
        ),
        description="Prominent showback disclaimer banner",
    )

    # Financial Totals
    total_allocated_cost: Decimal = Field(
        ..., description="Total net allocated spend for recipient scope"
    )
    direct_allocated_cost: Decimal = Field(
        ..., description="Spend directly attributable to resources/scopes"
    )
    shared_service_apportioned_cost: Decimal = Field(
        ..., description="Spend apportioned from central shared services"
    )
    unallocated_cost: Decimal = Field(
        default=Decimal("0.00"), description="Unallocated spend associated with scope context"
    )

    # Currency & Cost Basis
    cost_basis: str = Field(default="BILLED", description="Cost basis: BILLED or EFFECTIVE")
    currency: str = Field(default="USD", description="Statement presentation currency")
    currency_disclosure: CurrencyDisclosure = Field(default_factory=CurrencyDisclosure)

    # Budget Comparison
    budget_amount: Decimal = Field(default=Decimal("0.00"), description="Allocated budget ceiling")
    budget_variance_amount: Decimal = Field(default=Decimal("0.00"), description="Actual - Budget")
    budget_variance_pct: Decimal = Field(default=Decimal("0.00"), description="Variance %")
    budget_status: BudgetVarianceStatus = Field(default=BudgetVarianceStatus.ON_TRACK)
    budget_commentary: str = Field(default="", description="Narrative commentary on budget status")

    # Prior Period Comparison
    prior_period: str = Field(default="", description="Preceding billing period (e.g. '2026-08')")
    prior_period_cost: Decimal = Field(default=Decimal("0.00"), description="Prior period spend")
    period_movement_amount: Decimal = Field(
        default=Decimal("0.00"), description="Delta from prior period"
    )
    period_movement_pct: Decimal = Field(default=Decimal("0.00"), description="Percentage movement")
    movement_direction: MovementDirection = Field(default=MovementDirection.FLAT)
    movement_commentary: str = Field(default="", description="Narrative commentary on cost shifts")

    # Multi-Dimensional Breakdowns
    provider_breakdown: list[ProviderBreakdownItem] = Field(default_factory=list)
    category_breakdown: list[CategoryBreakdownItem] = Field(default_factory=list)
    application_breakdown: list[ApplicationBreakdownItem] = Field(default_factory=list)
    environment_breakdown: list[EnvironmentBreakdownItem] = Field(default_factory=list)

    # Detailed Movements, Apportionment, Unallocated & Discounts
    largest_movements: list[CostMovementItem] = Field(default_factory=list)
    shared_service_apportionments: list[SharedServiceApportionmentItem] = Field(
        default_factory=list
    )
    unallocated_cost_details: UnallocatedCostItem | None = None
    discount_benefit: DiscountBenefitItem | None = None

    # Governance & Timestamps
    provider_freshness: dict[str, str] = Field(
        default_factory=lambda: {
            "AWS": dt.datetime.now(dt.UTC).isoformat(),
            "AZURE": dt.datetime.now(dt.UTC).isoformat(),
            "GCP": dt.datetime.now(dt.UTC).isoformat(),
            "OCI": dt.datetime.now(dt.UTC).isoformat(),
        }
    )
    template_id: str = Field(default="tpl-standard-showback")
    generated_at: str = Field(default_factory=lambda: dt.datetime.now(dt.UTC).isoformat())
    circulated_at: str | None = None
    review_deadline: str | None = None
    finalised_at: str | None = None
    accepted_at: str | None = None
    accepted_by: str | None = None
    acceptance_notes: str | None = None

    # Phase 2 Chargeback (gated)
    chargeback_fields: Phase2ChargebackFields = Field(default_factory=Phase2ChargebackFields)


# ==============================================================================
# 6. Restatement Adjustment Pack
# ==============================================================================


class AdjustmentLine(BaseModel):
    """Line-level delta produced by post-finalisation restatement."""

    line_id: str = Field(..., description="Target line or category identifier")
    description: str = Field(..., description="Line description")
    original_amount: Decimal = Field(..., description="Amount on original finalised statement")
    adjustment_delta: Decimal = Field(..., description="Adjustment delta (+ or -)")
    adjusted_amount: Decimal = Field(..., description="Final adjusted amount")
    reason: str = Field(..., description="Specific business reason for adjustment")


class StatementAdjustment(BaseModel):
    """Authoritative restatement adjustment record linking to finalised statement (Prompt 52)."""

    adjustment_id: str = Field(..., description="Unique adjustment transaction ID")
    tenant_id: str = Field(..., description="Tenant ID")
    original_statement_id: str = Field(..., description="ID of original finalised statement")
    adjusted_statement_id: str = Field(..., description="ID of newly emitted adjusted statement")
    version: int = Field(..., description="Adjustment version sequence")
    original_total: Decimal = Field(..., description="Original total cost")
    adjustment_total: Decimal = Field(..., description="Net dollar adjustment delta")
    adjusted_total: Decimal = Field(..., description="New adjusted total cost")
    restatement_reason: str = Field(..., description="Root business justification for restatement")
    adjustment_timestamp: str = Field(default_factory=lambda: dt.datetime.now(dt.UTC).isoformat())
    adjusted_by: str = Field(..., description="User or system actor initiating adjustment")
    lines: list[AdjustmentLine] = Field(default_factory=list)


# ==============================================================================
# 7. Disputes & Reallocations (Workflow Integration)
# ==============================================================================


class StatementDispute(BaseModel):
    """Tracked line or statement dispute routed through the workflow engine (Prompt 50 / 52)."""

    dispute_id: str = Field(..., description="Unique dispute identifier")
    tenant_id: str = Field(..., description="Tenant ID")
    statement_id: str = Field(..., description="Statement ID under query")
    line_id: str = Field(..., description="Specific statement line or 'WHOLE_STATEMENT'")
    line_description: str = Field(default="", description="Friendly title of queried line")
    recipient_id: str = Field(..., description="User ID raising the query")
    recipient_email: str = Field(..., description="User contact email")
    disputed_amount: Decimal = Field(..., description="Dollar amount queried")
    proposed_amount: Decimal = Field(..., description="Recipient's expected correct amount")
    reason: str = Field(..., description="Detailed business justification for dispute")
    status: DisputeStatus = Field(default=DisputeStatus.SUBMITTED)
    assigned_owner: str = Field(..., description="Assigned investigator")
    sla_deadline: str = Field(..., description="SLA deadline timestamp")
    workflow_request_id: str | None = Field(
        default=None, description="Linked WorkflowRequest ID from workflow engine"
    )
    resolution_notes: str | None = Field(default=None, description="Resolution rationale")
    resolved_at: str | None = None
    resolved_by: str | None = None
    created_at: str = Field(default_factory=lambda: dt.datetime.now(dt.UTC).isoformat())


class ReallocationRecord(BaseModel):
    """Documented reallocation record resulting from an accepted dispute (Prompt 52)."""

    reallocation_id: str = Field(..., description="Unique reallocation audit ID")
    tenant_id: str = Field(..., description="Tenant ID")
    dispute_id: str = Field(..., description="Source dispute ID")
    statement_id: str = Field(..., description="Source statement ID")
    source_scope_code: str = Field(..., description="Scope being credited")
    target_scope_code: str = Field(..., description="Scope receiving the reallocated debit")
    reallocated_amount: Decimal = Field(..., description="Reallocation dollar amount")
    reason: str = Field(..., description="Audit rationale")
    approved_by: str = Field(..., description="Approving authority")
    reallocated_at: str = Field(default_factory=lambda: dt.datetime.now(dt.UTC).isoformat())


# ==============================================================================
# 8. Allocation Transparency & Drill-Through
# ==============================================================================


class ContributingResourceItem(BaseModel):
    """Contributing resource backing a statement line."""

    resource_id: str = Field(..., description="Resource identifier")
    resource_name: str = Field(..., description="Resource name or tag")
    provider: str = Field(..., description="Cloud provider")
    service: str = Field(..., description="Service code")
    cost_contribution: Decimal = Field(..., description="Amount contributed to line total")
    tags: dict[str, str] = Field(default_factory=dict, description="Resource tags")


class ContributingChargeLineItem(BaseModel):
    """Granular underlying charge line item (subject to financial-detail permission)."""

    charge_line_id: str = Field(..., description="Charge line ID")
    charge_type: str = Field(..., description="Usage, Tax, Fee, Credit, etc.")
    unit_price: Decimal = Field(..., description="Unit rate")
    quantity: Decimal = Field(..., description="Consumed metric quantity")
    period_start: str = Field(..., description="Charge period start")
    period_end: str = Field(..., description="Charge period end")
    amount: Decimal = Field(..., description="Raw cost amount")


class AllocationTransparencyView(BaseModel):
    """Transparency view proving which rule, resources, and charge lines produced an allocation."""

    line_id: str = Field(..., description="Queried statement line ID")
    line_description: str = Field(..., description="Line description")
    allocated_amount: Decimal = Field(..., description="Total line cost")
    winning_rule_id: str = Field(..., description="Rule ID that allocated this line")
    winning_rule_name: str = Field(..., description="Rule name")
    winning_rule_type: str = Field(
        ..., description="Rule precedence tier (e.g. SPLIT_RULE, DIRECT_RESOURCE)"
    )
    split_basis: str = Field(..., description="Apportionment or split formula and rationale")
    contributing_resources: list[ContributingResourceItem] = Field(default_factory=list)
    financial_detail_permitted: bool = Field(
        ..., description="Whether user possesses financial-detail permission"
    )
    charge_lines: list[ContributingChargeLineItem] = Field(
        default_factory=list,
        description="Granular charge lines (redacted if user lacks financial-detail permission)",
    )
    disclosure_message: str | None = Field(
        default=None, description="Notice if drill-through was redacted or filtered"
    )


# ==============================================================================
# 9. Outstanding Non-Acceptance Reporting
# ==============================================================================


class OutstandingAcceptanceItem(BaseModel):
    """Single unaccepted statement item in the outstanding acceptance report."""

    statement_id: str
    scope_type: RecipientScopeType
    scope_code: str
    scope_name: str
    recipient_owner: str
    recipient_email: str
    total_allocated_cost: Decimal
    period: str
    review_opened_at: str
    days_outstanding: int
    status: StatementLifecycleStatus
    escalation_status: str = Field(
        default="NORMAL", description="NORMAL, REMINDER_SENT, ESCALATED_TO_CFO"
    )


class OutstandingAcceptanceReport(BaseModel):
    """Executive report of unaccepted showback statements (Prompt 52)."""

    period: str
    tenant_id: str
    generated_at: str = Field(default_factory=lambda: dt.datetime.now(dt.UTC).isoformat())
    total_statements_issued: int
    total_accepted: int
    total_outstanding: int
    acceptance_rate_percentage: Decimal
    overdue_count: int
    items: list[OutstandingAcceptanceItem] = Field(default_factory=list)
