"""Domain Models for FOCUS Cost Ingestion, Normalisation, Restatement, and Currency (Prompt 22).

Enforces:
- Full alignment with FinOps Open Cost & Usage Specification (FOCUS) v1.0 (BBP Section 15.5 & 17).
- Retains all four cost measures: billed_cost, effective_cost, list_cost, contracted_cost (CST-001, CST-002).
- Presentation basis distinction: BILLED vs AMORTISED.
- Restatement tracking models with prior values retention and audit trail (CST-004).
- Currency conversion at query time with mandatory disclosure (CST-003).
- Drill-through hierarchy nodes from aggregate to contributing charge lines (CST-008).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from domain.models.facts import CostFact

# Canonical FOCUS Cost Fact alias
FocusCostFact = CostFact


class CostPresentationBasis(StrEnum):
    """Presentation basis for cost display (Prompt 22 Item 5).

    - BILLED: Invoice cash-flow view showing upfront purchases at purchase date and ongoing runtime.
    - AMORTISED: Accrual view distributing upfront commitment fees evenly across the coverage duration.
    """

    BILLED = "BILLED"
    AMORTISED = "AMORTISED"


class CostRestatementRecord(BaseModel):
    """Audit record capturing a detected cost restatement for a billing period (Prompt 22 Item 3 / CST-004)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(..., description="Unique restatement record ID")
    tenant_id: str = Field(..., description="Organization tenant ID")
    provider: str = Field(..., description="Cloud provider identifier (aws, azure, gcp, oci)")
    billing_period: str = Field(..., description="Target billing cycle (e.g. '2026-03')")
    detected_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when restatement variance was detected",
    )
    original_billed_total: Decimal = Field(
        ..., description="Billed total from previous ingestion before restatement"
    )
    restated_billed_total: Decimal = Field(
        ..., description="New billed total resulting from restated dataset"
    )
    billed_delta: Decimal = Field(
        ..., description="Variance amount (restated_billed_total - original_billed_total)"
    )
    original_effective_total: Decimal = Field(
        ..., description="Effective total from previous ingestion before restatement"
    )
    restated_effective_total: Decimal = Field(
        ..., description="New effective total resulting from restated dataset"
    )
    effective_delta: Decimal = Field(
        ..., description="Variance amount (restated_effective_total - original_effective_total)"
    )
    affected_row_count: int = Field(
        ..., ge=0, description="Number of charge line items modified or restated"
    )
    is_acknowledged: bool = Field(
        default=False, description="Whether enterprise administrator has acknowledged restatement"
    )
    notes: str | None = Field(
        default=None, description="Audit or provider explanation for variance"
    )


class CurrencyExchangeRate(BaseModel):
    """Effective-dated exchange rate for query-time currency conversion (Prompt 22 Item 6 / CST-003)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    from_currency: str = Field(..., min_length=3, max_length=3, description="Source ISO 4217 code")
    to_currency: str = Field(..., min_length=3, max_length=3, description="Target ISO 4217 code")
    effective_date: date = Field(..., description="Date from which this rate is valid")
    rate: Decimal = Field(
        ..., gt=Decimal("0.0"), description="Multiplier from source to target currency"
    )
    source: str = Field(default="ECB_DAILY_REFERENCE", description="Authoritative rate feed source")


class ConvertedCostFigure(BaseModel):
    """Result of query-time currency conversion with full disclosure (Prompt 22 Item 6)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    original_amount: Decimal = Field(..., description="Cost figure in native billing currency")
    original_currency: str = Field(..., min_length=3, max_length=3, description="Billing currency")
    target_amount: Decimal = Field(..., description="Cost figure in target reporting currency")
    target_currency: str = Field(
        ..., min_length=3, max_length=3, description="Target reporting currency"
    )
    exchange_rate: Decimal = Field(..., description="Applied exchange rate multiplier")
    rate_effective_date: date = Field(..., description="Effective date of applied exchange rate")
    presentation_basis: CostPresentationBasis = Field(
        default=CostPresentationBasis.BILLED, description="Labelled presentation basis"
    )
    disclosure: str = Field(
        ..., description="Mandatory disclosure sentence detailing rate and date"
    )


class CostAggregateNode(BaseModel):
    """Hierarchical node supporting drill-through from high-level aggregate to charge lines (Prompt 22 Item 8 / CST-008)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dimension_name: str = Field(
        ..., description="Dimension key (e.g. 'Scope', 'Service', 'ChargeCategory', 'ChargeLine')"
    )
    dimension_value: str = Field(
        ..., description="Value of dimension (e.g. 'ProductionCore', 'AmazonEC2')"
    )
    level: int = Field(
        ...,
        ge=1,
        le=4,
        description="Drill-down level (1: Scope, 2: Service, 3: Category, 4: Lines)",
    )
    billed_cost: Decimal = Field(..., description="Total billed cost for this node")
    effective_cost: Decimal = Field(..., description="Total effective cost for this node")
    currency: str = Field(default="USD", description="Currency of amounts")
    presentation_basis: CostPresentationBasis = Field(default=CostPresentationBasis.BILLED)
    child_count: int = Field(default=0, ge=0, description="Number of children at next level")
    children: list[CostAggregateNode] = Field(default_factory=list, description="Sub-aggregates")
    charge_lines: list[FocusCostFact] = Field(
        default_factory=list,
        description="Contributing line items (accessible only at Level 4 with financial permission)",
    )


class IngestionJobResult(BaseModel):
    """Result payload emitted after executing bulk cost ingestion (Prompt 22 Item 1)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    job_id: str = Field(..., description="Unique ingestion run identifier")
    tenant_id: str = Field(..., description="Target tenant ID")
    provider: str = Field(..., description="Cloud provider identifier")
    schema_version: str = Field(..., description="Validated dataset schema version")
    billing_periods: list[str] = Field(..., description="List of periods processed in this run")
    rows_ingested: int = Field(..., ge=0, description="Count of FOCUS cost facts persisted")
    is_restatement_detected: bool = Field(
        default=False, description="True if any period had restated values"
    )
    restatement_records: list[CostRestatementRecord] = Field(
        default_factory=list, description="Audit records for all detected restatements"
    )
    freshness_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Freshness marker updated upon successful ingestion",
    )
    duration_seconds: float = Field(
        ..., ge=0.0, description="Pipeline execution runtime in seconds"
    )
