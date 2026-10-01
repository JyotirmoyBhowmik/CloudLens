"""Cost Source Classification and Type-Safe Structural Segregation (Prompt 21 Items 160 & 161).

Enforces:
- Six distinct cost source classifications: Actual, Estimated, Forecast, Manual, Cached, Unavailable.
- Structural and visual segregation so the frontend cannot accidentally render an estimate as an actual.
- TYPE SAFETY GUARANTEE: An estimated cost and an actual cost are structurally distinct and
  CANNOT be summed accidentally, strictly enforced by type and operator overload.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from domain.models.exceptions import IncompatibleCostTypeError


class CostSourceClassification(StrEnum):
    """Canonical six cost source classifications per Prompt 21 Item 160."""

    ACTUAL = "Actual"  # Provider billing file or invoice
    ESTIMATED = "Estimated"  # Provider pricing multiplied by usage
    FORECAST = "Forecast"  # Application forecast engine
    MANUAL = "Manual"  # User-entered or curated override
    CACHED = "Cached"  # Last known provider pricing applied during latency
    UNAVAILABLE = "Unavailable"  # Provider data not available (not zero)


class CostValue(BaseModel):
    """Base abstract cost value ensuring strict type bounds and currency validation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    amount: float = Field(..., description="Monetary cost amount in specified currency")
    currency: str = Field(default="USD", description="Currency ISO 4217 code")
    source_classification: CostSourceClassification = Field(
        ..., description="Provenance classification"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Calculation or recording timestamp in UTC",
    )
    is_actual: bool = Field(default=False, description="Whether cost is verified provider billing")
    is_estimate: bool = Field(default=False, description="Whether cost is derived or estimated")


class ActualCost(CostValue):
    """Cost value derived directly from provider billing exports or invoices (Item 160)."""

    source_classification: Literal[CostSourceClassification.ACTUAL] = (
        CostSourceClassification.ACTUAL
    )
    is_actual: Literal[True] = True
    is_estimate: Literal[False] = False
    invoice_id: str | None = Field(default=None, description="Linked provider invoice ID")
    billing_period: str | None = Field(
        default=None, description="Billing cycle window (e.g. 2026-03)"
    )
    line_item_id: str | None = Field(default=None, description="Native billing export line item ID")

    def __add__(self, other: Any) -> ActualCost:
        """Enforces type safety: ActualCost can ONLY be added to another ActualCost."""
        if not isinstance(other, ActualCost):
            raise IncompatibleCostTypeError(
                f"Cannot sum ActualCost with {type(other).__name__} (classification: "
                f"'{getattr(other, 'source_classification', 'Unknown')}'). "
                "Estimates and actuals must remain structurally segregated per Prompt 21 Item 161."
            )
        if self.currency != other.currency:
            raise IncompatibleCostTypeError(
                f"Currency mismatch in ActualCost summation: '{self.currency}' != '{other.currency}'."
            )
        return ActualCost(
            amount=round(self.amount + other.amount, 6),
            currency=self.currency,
            billing_period=self.billing_period or other.billing_period,
            invoice_id=self.invoice_id or other.invoice_id,
        )

    def __radd__(self, other: Any) -> ActualCost:
        """Enforces type safety on reverse addition."""
        if not isinstance(other, ActualCost):
            raise IncompatibleCostTypeError(
                f"Cannot sum ActualCost with {type(other).__name__}. "
                "Estimates and actuals must remain structurally segregated per Prompt 21 Item 161."
            )
        return self.__add__(other)


class EstimatedCost(CostValue):
    """Cost value calculated by multiplying metered usage by catalogue pricing rate (Item 160)."""

    source_classification: Literal[CostSourceClassification.ESTIMATED] = (
        CostSourceClassification.ESTIMATED
    )
    is_actual: Literal[False] = False
    is_estimate: Literal[True] = True
    pricing_record_id: str = Field(..., description="ID of PricingRecord applied")
    pricing_source: str = Field(..., description="Source of rate (e.g. aws_price_list_bulk)")
    usage_quantity: float = Field(..., description="Metered usage quantity consumed")
    usage_unit: str = Field(..., description="Unit of measured usage")
    estimation_formula: str = Field(
        ..., description="Human-readable formula string (e.g. '744 hrs * 0.1664 USD/hr')"
    )

    def __add__(self, other: Any) -> EstimatedCost:
        """Enforces type safety: EstimatedCost can ONLY be added to another EstimatedCost."""
        if not isinstance(other, EstimatedCost):
            raise IncompatibleCostTypeError(
                f"Cannot sum EstimatedCost with {type(other).__name__}. "
                "Actual and estimated figures must never be conflated per Prompt 21 Item 161."
            )
        if self.currency != other.currency:
            raise IncompatibleCostTypeError(
                f"Currency mismatch in EstimatedCost summation: '{self.currency}' != '{other.currency}'."
            )
        return EstimatedCost(
            amount=round(self.amount + other.amount, 6),
            currency=self.currency,
            pricing_record_id=f"{self.pricing_record_id}+{other.pricing_record_id}",
            pricing_source=self.pricing_source,
            usage_quantity=round(self.usage_quantity + other.usage_quantity, 4),
            usage_unit=self.usage_unit,
            estimation_formula=f"({self.estimation_formula}) + ({other.estimation_formula})",
        )

    def __radd__(self, other: Any) -> EstimatedCost:
        """Enforces type safety on reverse addition."""
        if not isinstance(other, EstimatedCost):
            raise IncompatibleCostTypeError(
                f"Cannot sum EstimatedCost with {type(other).__name__}. "
                "Actual and estimated figures must never be conflated per Prompt 21 Item 161."
            )
        return self.__add__(other)


class ForecastCost(CostValue):
    """Cost value projected by the platform forecasting engine (Item 160)."""

    source_classification: Literal[CostSourceClassification.FORECAST] = (
        CostSourceClassification.FORECAST
    )
    is_actual: Literal[False] = False
    is_estimate: Literal[True] = True
    forecast_model: str = Field(default="ARIMA_EXPONENTIAL_SMOOTHING", description="Forecast model")
    confidence_interval_low: float | None = Field(default=None, description="Lower bound")
    confidence_interval_high: float | None = Field(default=None, description="Upper bound")
    forecast_horizon_days: int = Field(default=30, ge=1)

    def __add__(self, other: Any) -> ForecastCost:
        """Enforces type safety: ForecastCost can ONLY be added to another ForecastCost."""
        if not isinstance(other, ForecastCost):
            raise IncompatibleCostTypeError(
                f"Cannot sum ForecastCost with {type(other).__name__}. "
                "The four core cost types must remain strictly separated per Prompt 23."
            )
        if self.currency != other.currency:
            raise IncompatibleCostTypeError(
                f"Currency mismatch in ForecastCost summation: '{self.currency}' != '{other.currency}'."
            )
        return ForecastCost(
            amount=round(self.amount + other.amount, 6),
            currency=self.currency,
            forecast_model=self.forecast_model,
            forecast_horizon_days=max(self.forecast_horizon_days, other.forecast_horizon_days),
        )

    def __radd__(self, other: Any) -> ForecastCost:
        """Enforces type safety on reverse addition."""
        if not isinstance(other, ForecastCost):
            raise IncompatibleCostTypeError(
                f"Cannot sum ForecastCost with {type(other).__name__}. "
                "The four core cost types must remain strictly separated per Prompt 23."
            )
        return self.__add__(other)


class ProviderListPrice(CostValue):
    """Provider public list/retail price per Prompt 23 (Four-Value Separation)."""

    source_classification: Literal[CostSourceClassification.MANUAL] = (
        CostSourceClassification.MANUAL
    )
    is_actual: Literal[False] = False
    is_estimate: Literal[False] = False
    is_list_price: Literal[True] = True
    provider: str = Field(default="unknown", description="Cloud provider")
    service: str = Field(default="unknown", description="Service name")
    sku: str | None = Field(default=None, description="Service SKU")
    rate_unit: str = Field(default="unit", description="Rate unit of measure")

    def __add__(self, other: Any) -> ProviderListPrice:
        """Enforces type safety: ProviderListPrice can ONLY be added to another ProviderListPrice."""
        if not isinstance(other, ProviderListPrice):
            raise IncompatibleCostTypeError(
                f"Cannot sum ProviderListPrice with {type(other).__name__}. "
                "The four core cost types (List Price, Estimated Cost, Actual Cost, Forecast Cost) "
                "must remain strictly separated per Prompt 23."
            )
        if self.currency != other.currency:
            raise IncompatibleCostTypeError(
                f"Currency mismatch in ProviderListPrice summation: '{self.currency}' != '{other.currency}'."
            )
        return ProviderListPrice(
            amount=round(self.amount + other.amount, 6),
            currency=self.currency,
            provider=self.provider,
            service=self.service,
            sku=f"{self.sku}+{other.sku}" if self.sku and other.sku else (self.sku or other.sku),
            rate_unit=self.rate_unit,
        )

    def __radd__(self, other: Any) -> ProviderListPrice:
        """Enforces type safety on reverse addition."""
        if not isinstance(other, ProviderListPrice):
            raise IncompatibleCostTypeError(
                f"Cannot sum ProviderListPrice with {type(other).__name__}. "
                "The four core cost types must remain strictly separated per Prompt 23."
            )
        return self.__add__(other)


# Four-Value Separation First-Class Aliases (Prompt 23)
ListPrice = ProviderListPrice
EstimatedEffectiveCost = EstimatedCost
ActualBilledCost = ActualCost
ForecastCostValue = ForecastCost


class ManualCost(CostValue):
    """Cost value manually entered or overridden by an administrator (Item 160)."""

    source_classification: Literal[CostSourceClassification.MANUAL] = (
        CostSourceClassification.MANUAL
    )
    is_actual: Literal[False] = False
    is_estimate: Literal[False] = False
    entered_by: str = Field(..., min_length=1, description="Username or service principal")
    justification: str = Field(..., min_length=5, description="Business rationale")
    override_id: str | None = Field(default=None, description="Linked Governance Override ID")


class CachedCost(CostValue):
    """Cost value calculated using last known provider pricing during provider latency (Item 160)."""

    source_classification: Literal[CostSourceClassification.CACHED] = (
        CostSourceClassification.CACHED
    )
    is_actual: Literal[False] = False
    is_estimate: Literal[True] = True
    original_retrieved_at: datetime = Field(..., description="Timestamp of cached rate")
    cache_age_hours: float = Field(..., ge=0.0, description="Age of cached data in hours")


class UnavailableCost(CostValue):
    """Explicit indicator that provider cost data is unavailable (Item 160).

    STRICT PROHIBITION: Never defaults to 0.0 or free silently.
    """

    source_classification: Literal[CostSourceClassification.UNAVAILABLE] = (
        CostSourceClassification.UNAVAILABLE
    )
    amount: float = Field(default=0.0, description="Nominal amount")
    is_actual: Literal[False] = False
    is_estimate: Literal[False] = False
    is_unavailable: bool = True
    reason: str = Field(
        default="Provider billing data unavailable for period",
        description="Reason for unavailability",
    )


class BlendedCostSummary(BaseModel):
    """Explicit multi-source cost container preventing accidental arithmetic mixing."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    currency: str = "USD"
    actual_subtotal: float = 0.0
    estimated_subtotal: float = 0.0
    forecast_subtotal: float = 0.0
    manual_subtotal: float = 0.0
    cached_subtotal: float = 0.0
    has_unavailable_items: bool = False
    unavailable_count: int = 0
    line_items: list[CostValue] = Field(default_factory=list)

    @classmethod
    def from_items(cls, items: list[CostValue], currency: str = "USD") -> BlendedCostSummary:
        """Aggregates items into distinct subtotals without combining actuals and estimates."""
        actual = 0.0
        estimated = 0.0
        forecast = 0.0
        manual = 0.0
        cached = 0.0
        unavailable = 0

        for item in items:
            if item.currency != currency:
                raise IncompatibleCostTypeError(
                    f"BlendedCostSummary currency mismatch: '{item.currency}' != '{currency}'."
                )
            if isinstance(item, ActualCost):
                actual += item.amount
            elif isinstance(item, EstimatedCost):
                estimated += item.amount
            elif isinstance(item, ForecastCost):
                forecast += item.amount
            elif isinstance(item, ManualCost):
                manual += item.amount
            elif isinstance(item, CachedCost):
                cached += item.amount
            elif isinstance(item, UnavailableCost):
                unavailable += 1

        return cls(
            currency=currency,
            actual_subtotal=round(actual, 4),
            estimated_subtotal=round(estimated, 4),
            forecast_subtotal=round(forecast, 4),
            manual_subtotal=round(manual, 4),
            cached_subtotal=round(cached, 4),
            has_unavailable_items=unavailable > 0,
            unavailable_count=unavailable,
            line_items=items,
        )
