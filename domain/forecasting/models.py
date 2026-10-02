"""Domain Models for Forecasting Engine (Prompt 29).

Enforces:
- Prompt 29: Produce forward-looking numbers that never overstate their own confidence.
- Prompt 29: Three MVP methods: simple run-rate (default), historical average, moving average.
- Prompt 29: Four Phase 2 methods behind flags: trend-based regression, seasonality-aware decomposition,
  provider-published forecast comparison, and user-defined adjustment rules for known future events.
- Prompt 29: All seven forecast outputs:
  1. end-of-period cost
  2. expected usage
  3. expected budget consumption
  4. cost trend
  5. forecast variance
  6. predicted threshold breach date
  7. predicted budget breach date
- Prompt 29: Store every forecast with its method, input window, generation timestamp, and confidence label.
- Negative constraint: Do NOT display a forecast without its method.
- Negative constraint: Do NOT use a method whose minimum history is not satisfied (fallback to run-rate with LOW confidence).
- Negative constraint: With fewer than three days of period data, produce a run-rate forecast labelled LOW confidence rather than nothing.
- Prompt 29: Recompute forecasts after any restatement affecting their input window.
- Prompt 29: Forecast accuracy measurement at 25%, 50%, 75%, and period close.
"""

from __future__ import annotations

import datetime as dt
import uuid
from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel, Field

from domain.models.base import CanonicalEntity
from domain.models.enums import (
    BudgetPeriod,
    BudgetScopeType,
    CostTrend,
    ForecastConfidence,
    ForecastMethod,
    ForecastMilestone,
)

# ==============================================================================
# Historical & Input Window Models
# ==============================================================================


class DailySpendPoint(BaseModel):
    """Daily cost and consumption telemetry observation."""

    date: dt.date = Field(..., description="Date of observation")
    amount: float = Field(..., ge=0.0, description="Actual monetary spend incurred on this date")
    usage: float = Field(
        default=0.0, ge=0.0, description="Usage quantity/volume incurred on this date"
    )


class ForecastInputWindow(BaseModel):
    """Temporal window and telemetry parameters supplying the forecast computation."""

    start_date: date = Field(..., description="Start of historical observation window")
    end_date: date = Field(..., description="End of historical observation window")
    window_days: int = Field(..., ge=0, description="Total days spanning the input window")
    data_points_count: int = Field(..., ge=0, description="Count of daily observations available")
    data_freshness_as_of: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Freshness watermark of input telemetry data",
    )


class UserForecastAdjustmentRule(BaseModel):
    """User-defined adjustment rule for planned future events (Prompt 29 Phase 2)."""

    rule_name: str = Field(
        ...,
        min_length=2,
        description="Identifier for future event (e.g. 'Cloud Migration Phase 2')",
    )
    start_date: date = Field(..., description="Start date when adjustment applies")
    end_date: date | None = Field(
        default=None, description="Optional end date of adjustment effect"
    )
    adjustment_type: str = Field(
        default="ADDITIVE_DAILY",
        description="Type of adjustment: 'ADDITIVE_DAILY', 'PERCENTAGE_MULTIPLIER', 'ONE_TIME_CHARGE'",
    )
    adjustment_value: float = Field(
        ...,
        description="Magnitude of adjustment (e.g. +50.0 $/day or +0.25 for +25% multiplier)",
    )
    description: str = Field(..., min_length=5, description="Governance reason for adjustment")


# ==============================================================================
# Derivation & Seven Forecast Outputs
# ==============================================================================


class ForecastDerivation(BaseModel):
    """Mathematical derivation and proof showing how forecast numbers were produced."""

    daily_burn_rate: float = Field(..., description="Calculated daily spend velocity")
    elapsed_days: int = Field(..., ge=0, description="Elapsed days evaluated in current period")
    remaining_days: int = Field(..., ge=0, description="Remaining days until period close")
    actual_spend_to_date: float = Field(
        ..., description="Cumulative actual spend incurred to evaluation date"
    )
    projected_remaining_spend: float = Field(..., description="Projected spend for remaining days")
    method_details: dict[str, Any] = Field(
        default_factory=dict,
        description="Algorithm-specific parameters (e.g. regression slope, seasonality factors, moving window size)",
    )
    fallback_applied: bool = Field(
        default=False,
        description="True if fallback to run-rate occurred due to insufficient history or disabled feature flag",
    )
    fallback_reason: str | None = Field(
        default=None,
        description="Explanation why fallback occurred",
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Statistical confidence score between 0.0 and 1.0",
    )
    confidence_rationale: str = Field(
        ...,
        description="Honest explanation of the confidence rating",
    )


class ForecastOutputs(BaseModel):
    """The seven mandatory forecast outputs specified by BBP Section 23."""

    # 1. End-of-period cost
    end_of_period_cost: float = Field(
        ...,
        ge=0.0,
        description="Projected total cost for the current period close",
    )

    # 2. Expected usage
    expected_usage: float = Field(
        ...,
        ge=0.0,
        description="Projected total consumption usage quantity/volume for the period close",
    )

    # 3. Expected budget consumption
    expected_budget_consumption: float = Field(
        ...,
        ge=0.0,
        description="Projected budget utilisation percentage (e.g. 105.4% or 0.0 if unbudgeted)",
    )

    # 4. Cost trend
    cost_trend: CostTrend = Field(
        ...,
        description="Cost momentum and trajectory direction (STABLE, INCREASING, DECREASING, SPIKING, VOLATILE)",
    )

    # 5. Forecast variance
    forecast_variance: float = Field(
        ...,
        description="Monetary variance relative to target ceiling or baseline (forecast - budget)",
    )

    # 6. Predicted threshold breach date
    predicted_threshold_breach_date: date | None = Field(
        default=None,
        description="Earliest predicted date when warning/critical threshold band will be breached",
    )

    # 7. Predicted budget breach date
    predicted_budget_breach_date: date | None = Field(
        default=None,
        description="Earliest predicted date when 100% budget ceiling will be breached",
    )


# ==============================================================================
# Canonical Forecast Entity
# ==============================================================================


class ForecastEntity(CanonicalEntity):
    """First-class canonical domain entity tracking a calculated financial projection."""

    tenant_id: str = Field(..., description="Tenant boundary isolating governance")
    scope_type: BudgetScopeType = Field(..., description="Scope type of forecast target")
    scope_id: str = Field(..., description="Scope identifier (account ID, app name, etc.)")
    budget_id: str | None = Field(default=None, description="Optional associated budget ceiling ID")
    currency: str = Field(default="USD", description="Currency ISO code")
    period: BudgetPeriod = Field(default=BudgetPeriod.MONTHLY, description="Target period cadence")
    period_start: date = Field(..., description="Period cycle start date")
    period_end: date = Field(..., description="Period cycle end date")

    # Algorithm provenance
    requested_method: ForecastMethod = Field(
        ...,
        description="Originally requested forecasting algorithm",
    )
    effective_method: ForecastMethod = Field(
        ...,
        description="Effective algorithm actually executed (matches requested, or RUN_RATE on fallback)",
    )
    fallback_applied: bool = Field(
        default=False,
        description="True if method fell back to RUN_RATE due to insufficient history or disabled flag",
    )
    fallback_reason: str | None = Field(
        default=None,
        description="Documented rationale for algorithm fallback",
    )

    # Confidence rating
    confidence: ForecastConfidence = Field(
        ...,
        description="Confidence label: HIGH, MEDIUM, LOW",
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Statistical confidence score (0.0 to 1.0)",
    )

    # Input window & provenance
    input_window: ForecastInputWindow = Field(
        ...,
        description="Input temporal window and telemetry statistics",
    )
    generation_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Exact UTC timestamp when forecast was produced",
    )

    # Outputs & Derivation
    outputs: ForecastOutputs = Field(
        ...,
        description="The seven mandatory forecast outputs",
    )
    derivation: ForecastDerivation = Field(
        ...,
        description="Mathematical derivation details",
    )

    # State & Restatement linkage
    is_active: bool = Field(
        default=True,
        description="True if this is the active authoritative forecast for this scope and period",
    )
    superseded_by_id: str | None = Field(
        default=None,
        description="Forecast ID that superseded this record following restatement or update",
    )
    superseded_at: datetime | None = Field(
        default=None,
        description="Timestamp when this forecast was superseded",
    )
    recomputed_from_restatement_id: str | None = Field(
        default=None,
        description="CostRestatementRecord ID that triggered recomputation, if applicable",
    )

    # Prominent Display Label Enforcing Negative Constraint:
    # "A forecast displayed without its method is a defect, not a cosmetic issue."
    # "Every forecast displays its method, window and confidence wherever it appears."
    display_summary: str = Field(
        ...,
        description="Mandatory display string embedding method, window, and confidence",
    )

    @classmethod
    def create(
        cls,
        *,
        id: str | None = None,
        tenant_id: str,
        scope_type: BudgetScopeType,
        scope_id: str,
        budget_id: str | None = None,
        currency: str = "USD",
        period: BudgetPeriod = BudgetPeriod.MONTHLY,
        period_start: date,
        period_end: date,
        requested_method: ForecastMethod,
        effective_method: ForecastMethod,
        fallback_applied: bool = False,
        fallback_reason: str | None = None,
        confidence: ForecastConfidence,
        confidence_score: float,
        input_window: ForecastInputWindow,
        outputs: ForecastOutputs,
        derivation: ForecastDerivation,
        recomputed_from_restatement_id: str | None = None,
    ) -> ForecastEntity:
        """Instantiates a valid ForecastEntity with mandatory prominent display summary."""
        fid = id or f"fc-{uuid.uuid4().hex[:12]}"
        window_str = (
            f"{input_window.window_days}d ({input_window.start_date} to {input_window.end_date})"
        )
        fallback_str = f" [FALLBACK from {requested_method.value}]" if fallback_applied else ""
        display_sum = (
            f"[METHOD: {effective_method.value}{fallback_str} | "
            f"WINDOW: {window_str} | "
            f"CONFIDENCE: {confidence.value}]"
        )

        return cls(
            id=fid,
            tenant_id=tenant_id,
            scope_type=scope_type,
            scope_id=scope_id,
            budget_id=budget_id,
            currency=currency,
            period=period,
            period_start=period_start,
            period_end=period_end,
            requested_method=requested_method,
            effective_method=effective_method,
            fallback_applied=fallback_applied,
            fallback_reason=fallback_reason,
            confidence=confidence,
            confidence_score=confidence_score,
            input_window=input_window,
            outputs=outputs,
            derivation=derivation,
            is_active=True,
            recomputed_from_restatement_id=recomputed_from_restatement_id,
            display_summary=display_sum,
        )


# ==============================================================================
# Accuracy Measurement & Milestone Models
# ==============================================================================


class ForecastMilestoneSnapshot(BaseModel):
    """Snapshot of a forecast taken at a specific milestone (25%, 50%, 75%, or period close)."""

    id: str = Field(default_factory=lambda: f"ms-{uuid.uuid4().hex[:12]}")
    tenant_id: str = Field(..., description="Tenant boundary")
    scope_id: str = Field(..., description="Target scope ID")
    budget_id: str | None = Field(default=None, description="Target budget ID if linked")
    period_identifier: str = Field(..., description="Period identifier (e.g. '2026-06')")
    period_start: date = Field(..., description="Period start date")
    period_end: date = Field(..., description="Period end date")
    milestone: ForecastMilestone = Field(
        ..., description="Milestone checkpoint: M25, M50, M75, PERIOD_CLOSE"
    )
    checkpoint_date: date = Field(..., description="Date on which milestone was recorded")
    forecast_id: str = Field(..., description="Forecast record ID evaluated")
    forecast_amount: float = Field(..., description="Projected spend amount recorded at milestone")
    method: ForecastMethod = Field(..., description="Forecasting method used")
    confidence: ForecastConfidence = Field(..., description="Confidence label at checkpoint")

    # Evaluation fields populated at period close
    actual_billed_amount: float | None = Field(
        default=None, description="Actual billed spend at period close"
    )
    absolute_error: float | None = Field(default=None, description="abs(forecast - actual)")
    percentage_error: float | None = Field(
        default=None, description="(forecast - actual) / actual * 100"
    )
    accuracy_percentage: float | None = Field(
        default=None, description="max(0.0, 100 - abs(percentage_error))"
    )
    evaluated_at: datetime | None = Field(
        default=None, description="UTC timestamp of close evaluation"
    )
    recorded_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="UTC timestamp recorded"
    )


class PeriodAccuracyReport(BaseModel):
    """Summary of accuracy for a single closed period across its recorded milestones."""

    period_identifier: str
    period_start: date
    period_end: date
    actual_billed_amount: float
    milestones: dict[str, dict[str, Any]] = Field(default_factory=dict)
    average_accuracy_percentage: float = 0.0


class ForecastAccuracyTrend(BaseModel):
    """Historical accuracy trend across closed periods and milestones (Prompt 29)."""

    tenant_id: str
    total_closed_periods_evaluated: int
    average_mape_m25: float = Field(
        ..., description="Mean Absolute Percentage Error at 25% milestone"
    )
    average_mape_m50: float = Field(
        ..., description="Mean Absolute Percentage Error at 50% milestone"
    )
    average_mape_m75: float = Field(
        ..., description="Mean Absolute Percentage Error at 75% milestone"
    )
    overall_accuracy_percentage: float = Field(
        ..., description="Average accuracy across all milestones"
    )
    trend_direction: str = Field(..., description="'IMPROVING', 'STABLE', 'DEGRADING'")
    is_convergent: bool = Field(
        ...,
        description="True if error consistently decreases as period advances (M75 < M50 < M25)",
    )
    periods: list[PeriodAccuracyReport] = Field(default_factory=list)


# ==============================================================================
# API Request / Response DTOs
# ==============================================================================


class ForecastGenerateRequest(BaseModel):
    """Request payload to generate a new forecast for a scope or budget."""

    scope_type: BudgetScopeType = BudgetScopeType.ORGANISATION
    scope_id: str = Field(..., min_length=1, description="Target scope identifier")
    budget_id: str | None = Field(
        default=None, description="Optional budget ceiling to evaluate against"
    )
    budget_amount: float | None = Field(
        default=None, ge=0.0, description="Optional target budget limit amount"
    )
    period: BudgetPeriod = BudgetPeriod.MONTHLY
    as_of: date | None = Field(default=None, description="Evaluation date (defaults to today)")
    method: ForecastMethod = Field(
        default=ForecastMethod.RUN_RATE, description="Desired forecast algorithm"
    )
    moving_average_window_days: int = Field(
        default=7, ge=3, le=90, description="Window size for MOVING_AVERAGE"
    )
    daily_spends: list[DailySpendPoint] = Field(
        default_factory=list,
        description="Daily telemetry series within period and historical window",
    )
    historical_spends: list[DailySpendPoint] = Field(
        default_factory=list,
        description="Prior historical telemetry series (for historical average, regression, seasonality)",
    )
    provider_published_amount: float | None = Field(
        default=None,
        description="Provider-published forecast amount (for PROVIDER_PUBLISHED method)",
    )
    adjustment_rules: list[UserForecastAdjustmentRule] = Field(
        default_factory=list,
        description="User adjustment rules (for USER_ADJUSTMENT method)",
    )
    warning_threshold_pct: float = Field(default=80.0, ge=0.0, le=100.0)
    currency: str = "USD"


class ForecastMethodInfo(BaseModel):
    """Metadata describing an available forecasting algorithm and its requirements."""

    method: ForecastMethod
    display_name: str
    description: str
    minimum_history_days: int
    is_mvp: bool
    is_enabled: bool
    feature_flag_key: str | None = None
