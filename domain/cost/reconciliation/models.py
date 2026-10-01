"""Domain Models for Cost Reconciliation, Variance Classification, and Executive Trust (Prompt 24).

Enforces:
- Prompt 24 Item 1 & BBP Section 12 (BP-17): Mandatory comparison between platform normalised total and provider billed total.
- Prompt 24 Item 2: Deterministic variance classification taxonomy (restatement, credit, tax, amortisation, missing scope, etc.).
- Prompt 24 Item 3: Explicit framing rule: presents both figures and classification without editorialising.
- Prompt 24 Item 4: Configurable per-provider tolerance with PASS/FAILED and investigation item on failure.
- Prompt 24 Item 5: Executive dashboard trust indicator (single most important number for adoption; never suppressed on failure).
- Prompt 24 Item 6: Separate comparison of estimated cost against actual billed cost (evaluating platform estimation accuracy).
- Prompt 24 Item 7: Retain reconciliation history so the trend in variance is visible over time.
- Prompt 24 Do Not Constraints:
  * Never adjust ingested cost data to force a match.
  * Never suppress a failed reconciliation from the dashboard.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from domain.models.base import CanonicalEntity


class VarianceClassification(StrEnum):
    """Deterministic variance classification taxonomy (Prompt 24 Item 2)."""

    RESTATEMENT = "RESTATEMENT"
    CREDIT = "CREDIT"
    TAX = "TAX"
    AMORTISATION_BASIS_DIFFERENCE = "AMORTISATION_BASIS_DIFFERENCE"
    MISSING_SCOPE = "MISSING_SCOPE"
    UNRECOGNISED_CHARGE = "UNRECOGNISED_CHARGE"
    PRICING_MISMATCH = "PRICING_MISMATCH"
    DATA_FRESHNESS_GAP = "DATA_FRESHNESS_GAP"
    WITHIN_TOLERANCE = "WITHIN_TOLERANCE"
    UNCLASSIFIED = "UNCLASSIFIED"


class ReconciliationStatus(StrEnum):
    """Reconciliation evaluation outcome based on provider tolerance (Prompt 24 Item 4)."""

    PASS = "PASS"
    FAILED = "FAILED"


class InvestigationPriority(StrEnum):
    """Priority level for reconciliation investigation items."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class InvestigationStatus(StrEnum):
    """Lifecycle status of a reconciliation investigation item."""

    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class ExecutiveTrustStatus(StrEnum):
    """Executive adoption trust health classification (Prompt 24 Item 5)."""

    EXCELLENT = "EXCELLENT"  # >= 99.5% match
    HEALTHY = "HEALTHY"  # >= 98.0% match
    NEEDS_ATTENTION = "NEEDS_ATTENTION"  # < 98.0% match


class EstimationBias(StrEnum):
    """Directional bias of pre-deployment estimation vs actual billed cost (Prompt 24 Item 6)."""

    ACCURATE = "ACCURATE"
    OVER_ESTIMATED = "OVER_ESTIMATED"
    UNDER_ESTIMATED = "UNDER_ESTIMATED"


class ProviderToleranceConfig(BaseModel):
    """Configurable tolerance and finalisation lag parameters per provider (Prompt 24 Item 4)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str = Field(
        ..., description="Cloud provider identifier (aws, azure, gcp, oci, default)"
    )
    absolute_tolerance: Decimal = Field(
        default=Decimal("5.00"),
        ge=Decimal("0.0"),
        description="Maximum allowable absolute variance in currency units",
    )
    percentage_tolerance: Decimal = Field(
        default=Decimal("0.50"),
        ge=Decimal("0.0"),
        description="Maximum allowable percentage variance (e.g. 0.50 for 0.5%)",
    )
    currency: str = Field(
        default="USD", min_length=3, max_length=3, description="ISO currency code"
    )
    finalisation_lag_days: int = Field(
        default=3,
        ge=0,
        description="Provider finalisation delay in days before period total is authoritative",
    )


class ReconciliationInvestigationItem(BaseModel):
    """Investigation item automatically generated when reconciliation fails tolerance (Prompt 24 Item 4)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(..., description="Unique investigation tracking ID")
    report_id: str = Field(..., description="Associated reconciliation report ID")
    tenant_id: str = Field(..., description="Organization tenant ID")
    provider: str = Field(..., description="Cloud provider identifier")
    scope_id: str = Field(..., description="Billing scope or account ID")
    billing_period: str = Field(..., description="Billing period format YYYY-MM")
    platform_total: Decimal = Field(..., description="Platform normalised FOCUS total")
    provider_total: Decimal = Field(..., description="Provider authoritative invoice total")
    variance_amount: Decimal = Field(..., description="Absolute variance amount")
    percentage_variance: Decimal = Field(
        ..., description="Variance percentage relative to provider"
    )
    classification: VarianceClassification = Field(
        ..., description="Identified variance classification"
    )
    priority: InvestigationPriority = Field(
        default=InvestigationPriority.MEDIUM, description="Investigation urgency"
    )
    status: InvestigationStatus = Field(
        default=InvestigationStatus.OPEN, description="Workflow investigation status"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when investigation item was raised",
    )
    resolved_at: datetime | None = Field(default=None, description="Resolution timestamp")
    notes: str = Field(default="", description="Auditor investigation notes")


class ReconciliationReport(CanonicalEntity):
    """Authoritative reconciliation audit report per billing period and scope (Prompt 24 Items 1-4)."""

    id: str = Field(..., description="Unique reconciliation report identifier")
    tenant_id: str = Field(..., description="Organization tenant ID")
    provider: str = Field(..., description="Cloud provider identifier")
    billing_period: str = Field(
        ..., min_length=7, max_length=7, description="Audited billing period YYYY-MM"
    )
    scope_id: str = Field(..., description="Audited scope or account identifier")
    reconciled_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Reconciliation execution timestamp"
    )
    platform_total: Decimal = Field(
        ..., description="Platform normalised FOCUS total for period and scope"
    )
    provider_total: Decimal = Field(
        ..., description="Provider authoritative invoice total for period and scope"
    )
    absolute_variance: Decimal = Field(
        ..., ge=Decimal("0.0"), description="abs(platform_total - provider_total)"
    )
    signed_variance: Decimal = Field(
        ..., description="Signed difference (platform_total - provider_total)"
    )
    percentage_variance: Decimal = Field(
        ..., ge=Decimal("0.0"), description="Percentage variance relative to provider"
    )
    status: ReconciliationStatus = Field(
        ..., description="PASS if within tolerance, FAILED otherwise"
    )
    classification: VarianceClassification = Field(
        ..., description="Primary variance classification"
    )
    classification_details: str | None = Field(
        default=None, description="Exploratory breakdown context"
    )
    framing_statement: str = Field(
        ...,
        description="Explicit framing rule: presents both figures and classification without editorialising",
    )
    tolerance_config: ProviderToleranceConfig = Field(
        ..., description="Tolerance parameters evaluated against"
    )
    investigation_item_id: str | None = Field(
        default=None, description="Generated investigation item ID if status is FAILED"
    )
    currency: str = Field(
        default="USD", min_length=3, max_length=3, description="ISO currency code"
    )


class ExecutiveTrustIndicator(BaseModel):
    """Executive dashboard trust metric surfaced as single most important adoption number (Prompt 24 Item 5)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tenant_id: str = Field(..., description="Organization tenant ID")
    trust_score_pct: Decimal = Field(
        ...,
        ge=Decimal("0.0"),
        le=Decimal("100.0"),
        description="Overall platform match rate percentage across audited spend",
    )
    status: ExecutiveTrustStatus = Field(
        ..., description="Health classification (EXCELLENT, HEALTHY, NEEDS_ATTENTION)"
    )
    total_spend_evaluated: Decimal = Field(
        ..., ge=Decimal("0.0"), description="Total provider spend audited"
    )
    total_variance_evaluated: Decimal = Field(
        ..., ge=Decimal("0.0"), description="Total absolute discrepancy detected"
    )
    periods_evaluated_count: int = Field(
        default=0, ge=0, description="Total billing period partitions audited"
    )
    reconciliation_pass_count: int = Field(
        default=0, ge=0, description="Total reconciliations passing tolerance"
    )
    reconciliation_fail_count: int = Field(
        default=0, ge=0, description="Total reconciliations failing tolerance"
    )
    active_investigations_count: int = Field(
        default=0, ge=0, description="Active unresolved investigation items"
    )
    last_reconciliation_timestamp: datetime | None = Field(
        default=None, description="Timestamp of most recent reconciliation run"
    )
    provider_breakdowns: dict[str, dict[str, Any]] = Field(
        default_factory=dict, description="Reconciliation metrics broken down per cloud provider"
    )
    is_suppressed: bool = Field(
        default=False,
        description="Strictly False: failed reconciliations are NEVER suppressed from the dashboard",
    )


class ReconciliationHistorySummary(BaseModel):
    """Historical reconciliation trend across multiple billing periods (Prompt 24 Item 7)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tenant_id: str = Field(..., description="Organization tenant ID")
    provider: str | None = Field(default=None, description="Provider filter if applicable")
    scope_id: str | None = Field(default=None, description="Scope filter if applicable")
    reports: list[ReconciliationReport] = Field(
        default_factory=list, description="Historical reconciliation reports in chronological order"
    )
    trend_direction: str = Field(
        default="STABLE", description="Variance trajectory (IMPROVING, DEGRADING, STABLE)"
    )
    average_absolute_variance: Decimal = Field(
        ..., ge=Decimal("0.0"), description="Mean absolute variance over time"
    )
    average_percentage_variance: Decimal = Field(
        ..., ge=Decimal("0.0"), description="Mean percentage variance over time"
    )
    total_periods_evaluated: int = Field(
        default=0, ge=0, description="Total period snapshots in history"
    )


class EstimateVsActualItem(BaseModel):
    """Comparison line between pre-deployment estimate and actual billed FOCUS cost (Prompt 24 Item 6)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(..., description="Unique comparison line ID")
    tenant_id: str = Field(..., description="Organization tenant ID")
    service_id: str = Field(..., description="Cloud service evaluated (e.g. AmazonEC2)")
    resource_id: str | None = Field(default=None, description="Resource identifier if granular")
    billing_period: str = Field(
        ..., min_length=7, max_length=7, description="Billing period format YYYY-MM"
    )
    estimated_cost: Decimal = Field(
        ..., ge=Decimal("0.0"), description="Pre-deployment estimated monthly cost"
    )
    actual_billed_cost: Decimal = Field(
        ..., ge=Decimal("0.0"), description="Authoritative actual FOCUS billed cost"
    )
    absolute_error: Decimal = Field(
        ..., ge=Decimal("0.0"), description="abs(estimated_cost - actual_billed_cost)"
    )
    percentage_error: Decimal = Field(
        ..., ge=Decimal("0.0"), description="Percentage error relative to actual"
    )
    bias: EstimationBias = Field(
        ..., description="Directional estimation bias (ACCURATE, OVER, UNDER)"
    )
    assumptions_summary: str | None = Field(
        default=None, description="Key assumptions underpinning estimate"
    )


class EstimateVsActualReport(BaseModel):
    """Comprehensive estimation accuracy report evaluating platform pre-deployment estimates (Prompt 24 Item 6)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(..., description="Unique estimation accuracy report identifier")
    tenant_id: str = Field(..., description="Organization tenant ID")
    billing_period: str = Field(
        ..., min_length=7, max_length=7, description="Evaluated billing period YYYY-MM"
    )
    items: list[EstimateVsActualItem] = Field(
        default_factory=list, description="Evaluated line items"
    )
    total_estimated: Decimal = Field(..., ge=Decimal("0.0"), description="Total estimated cost sum")
    total_actual: Decimal = Field(
        ..., ge=Decimal("0.0"), description="Total actual billed cost sum"
    )
    absolute_error_total: Decimal = Field(
        ..., ge=Decimal("0.0"), description="Sum of absolute errors"
    )
    mape_pct: Decimal = Field(
        ..., ge=Decimal("0.0"), description="Mean Absolute Percentage Error (MAPE) across items"
    )
    overall_bias: EstimationBias = Field(..., description="Overall platform estimation bias")
    items_count: int = Field(default=0, ge=0, description="Number of items evaluated")
    evaluated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Evaluation timestamp"
    )


class RunReconciliationRequest(BaseModel):
    """Payload to trigger an authoritative reconciliation job."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    billing_period: str = Field(
        ..., min_length=7, max_length=7, description="Billing period format YYYY-MM"
    )
    provider: str = Field(
        ..., min_length=1, description="Cloud provider identifier (aws, azure, gcp, oci)"
    )
    scope_id: str = Field(..., min_length=1, description="Target billing scope or account ID")
    provider_authoritative_total: Decimal = Field(
        ..., ge=Decimal("0.0"), description="Provider authoritative invoice total"
    )
    currency: str = Field(default="USD", min_length=3, max_length=3, description="Currency code")
    bypass_lag_check: bool = Field(
        default=False,
        description="Whether to bypass provider finalisation lag check (for testing or backfill)",
    )
    unallocated_credits: Decimal = Field(
        default=Decimal("0.0"),
        ge=Decimal("0.0"),
        description="Unallocated promotional or support credits",
    )
    assessed_taxes: Decimal = Field(
        default=Decimal("0.0"), ge=Decimal("0.0"), description="Taxes assessed on provider invoice"
    )
    unlinked_scopes: list[str] = Field(
        default_factory=list,
        description="Scopes present on provider invoice but missing in platform",
    )
    unrecognised_charges: Decimal = Field(
        default=Decimal("0.0"),
        ge=Decimal("0.0"),
        description="Uncatalogued charges or SKU mismatches",
    )
    rate_mismatch_amount: Decimal = Field(
        default=Decimal("0.0"), ge=Decimal("0.0"), description="Rate card mismatch variance"
    )
    is_sync_in_flight: bool = Field(
        default=False, description="Whether a data sync is currently in flight"
    )
