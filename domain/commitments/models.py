"""Domain Models for Commitment Renewal and Coverage Management (Prompt 58).

Enforces:
- Fixed-point Decimal arithmetic on financial figures with ROUND_HALF_EVEN.
- Clear distinction between OVER_COMMITMENT (excess coverage, low utilization)
  and UNDER_COMMITMENT (high utilization, deficient coverage).
- Inspectable evidence-based renewal recommendations (never bare instructions).
- What-if comparison against forecast workload including the do-nothing option.
- Post-expiry check quantifying on-demand rate increases after lapse.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, ROUND_HALF_EVEN
from enum import Enum
from typing import Any
import uuid

from pydantic import BaseModel, Field, field_validator

from domain.models.enums import ProviderType


class CommitmentType(str, Enum):
    """Types of cloud commitment instruments."""
    SAVINGS_PLAN = "SAVINGS_PLAN"
    RESERVED_INSTANCE = "RESERVED_INSTANCE"
    COMMITTED_USE_DISCOUNT = "COMMITTED_USE_DISCOUNT"  # GCP CUD
    RESERVED_CAPACITY = "RESERVED_CAPACITY"          # OCI / Azure


class CommitmentAssessment(str, Enum):
    """Diagnostic assessment of commitment performance."""
    OVER_COMMITMENT = "OVER_COMMITMENT"    # High coverage, poor utilization -> waste
    UNDER_COMMITMENT = "UNDER_COMMITMENT"  # Low coverage, high utilization -> missed savings
    OPTIMAL = "OPTIMAL"                    # Balanced utilization and coverage


class RenewalAction(str, Enum):
    """Formal renewal recommendation actions."""
    RENEW_SAME = "RENEW_SAME"
    RENEW_HIGHER = "RENEW_HIGHER"
    RENEW_LOWER = "RENEW_LOWER"
    CHANGE_TERM = "CHANGE_TERM"
    CHANGE_SCOPE = "CHANGE_SCOPE"
    ALLOW_TO_LAPSE = "ALLOW_TO_LAPSE"
    DO_NOTHING = "DO_NOTHING"


class HistoricalTrend(BaseModel):
    """Historical coverage and utilization data point."""
    period: str
    coverage_ratio: Decimal
    utilization_ratio: Decimal
    realized_saving: Decimal

    @field_validator("coverage_ratio", "utilization_ratio", "realized_saving", mode="before")
    @classmethod
    def _coerce_decimal(cls, v: Any) -> Decimal:
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN)


class CommitmentEntity(BaseModel):
    """Registered cloud commitment contract."""
    commitment_id: str
    tenant_id: str
    provider: ProviderType
    account_id: str
    commitment_type: CommitmentType
    service_category: str
    term_months: int = 12
    start_date: dt.datetime
    expiry_date: dt.datetime
    hourly_committed_rate: Decimal
    annual_committed_cost: Decimal
    owner_id: str
    scope_id: str
    is_active: bool = True

    @field_validator("hourly_committed_rate", "annual_committed_cost", mode="before")
    @classmethod
    def _coerce_amount(cls, v: Any) -> Decimal:
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


class CommitmentCoverageAnalysis(BaseModel):
    """Detailed coverage, utilization, and financial saving metrics."""
    commitment_id: str
    provider: ProviderType
    commitment_type: CommitmentType
    term_months: int
    expiry_date: dt.datetime
    eligible_usage_cost: Decimal
    covered_usage_cost: Decimal
    commitment_cost: Decimal
    actual_consumed_cost: Decimal
    list_price_cost: Decimal
    coverage_ratio: Decimal
    utilization_ratio: Decimal
    realized_saving: Decimal
    assessment: CommitmentAssessment
    trend_history: list[HistoricalTrend] = Field(default_factory=list)

    @field_validator(
        "eligible_usage_cost",
        "covered_usage_cost",
        "commitment_cost",
        "actual_consumed_cost",
        "list_price_cost",
        "realized_saving",
        mode="before",
    )
    @classmethod
    def _coerce_money(cls, v: Any) -> Decimal:
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)

    @field_validator("coverage_ratio", "utilization_ratio", mode="before")
    @classmethod
    def _coerce_ratio(cls, v: Any) -> Decimal:
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN)


class RenewalPipelineItem(BaseModel):
    """Commitment in renewal decision window ranked by financial exposure."""
    commitment_id: str
    provider: ProviderType
    commitment_type: CommitmentType
    expiry_date: dt.datetime
    days_until_expiry: int
    is_in_decision_window: bool
    value_at_risk: Decimal
    analysis: CommitmentCoverageAnalysis
    rank: int = 1

    @field_validator("value_at_risk", mode="before")
    @classmethod
    def _coerce_var(cls, v: Any) -> Decimal:
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


class WhatIfOption(BaseModel):
    """What-if renewal option priced against workload."""
    action: RenewalAction
    description: str
    projected_annual_cost: Decimal
    projected_annual_saving: Decimal
    delta_vs_do_nothing: Decimal

    @field_validator(
        "projected_annual_cost",
        "projected_annual_saving",
        "delta_vs_do_nothing",
        mode="before",
    )
    @classmethod
    def _coerce_option(cls, v: Any) -> Decimal:
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


class RenewalRecommendation(BaseModel):
    """Explainable, evidence-backed recommendation."""
    commitment_id: str
    recommended_action: RenewalAction
    recommended_commitment_amount: Decimal
    projected_annual_saving: Decimal
    reasoning: list[str]
    what_if_options: list[WhatIfOption] = Field(default_factory=list)
    generated_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))

    @field_validator("recommended_commitment_amount", "projected_annual_saving", mode="before")
    @classmethod
    def _coerce_rec(cls, v: Any) -> Decimal:
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


class CommitmentDecisionRecord(BaseModel):
    """Immutable audit record of renewal decision."""
    decision_id: str = Field(default_factory=lambda: f"cdec-{uuid.uuid4().hex[:8]}")
    commitment_id: str
    tenant_id: str
    chosen_action: RenewalAction
    approver_id: str
    justification: str
    decided_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    workflow_request_id: str | None = None


class PostExpiryImpact(BaseModel):
    """Verification of financial impact after a commitment has lapsed."""
    commitment_id: str
    lapsed_at: dt.datetime
    evaluation_period: str
    on_demand_rate_cost: Decimal
    previous_committed_cost: Decimal
    on_demand_increase: Decimal

    @field_validator("on_demand_rate_cost", "previous_committed_cost", "on_demand_increase", mode="before")
    @classmethod
    def _coerce_impact(cls, v: Any) -> Decimal:
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


class PortfolioSummary(BaseModel):
    """Enterprise-wide portfolio view across all cloud providers."""
    total_commitments: int
    total_annual_committed_value: Decimal
    overall_coverage_ratio: Decimal
    overall_utilization_ratio: Decimal
    total_realized_savings: Decimal
    total_value_at_risk: Decimal
    provider_breakdowns: dict[str, Any] = Field(default_factory=dict)
