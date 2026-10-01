"""The Twelve Canonical Calculation Rules for Cloud Cost Estimation (Prompt 23).

Enforces:
- Rule 1: Unit conversion strictly through the unit catalogue.
- Rule 2: Currency conversion at stated rate and date with disclosure.
- Rule 3: Uniform rounding policy defined once (Banker's rounding ROUND_HALF_EVEN).
- Rule 4: Tier calculation walking boundaries correctly (Graduated vs Volume).
- Rule 5: Free-tier consumption deducted before charged consumption.
- Rule 6: Minimum-charge handling floor enforcement.
- Rule 7: Commitment application (Reservations, Savings Plans, UCC).
- Rule 8: Discount application (Contracted percentage or fixed rates).
- Rule 9: Missing-data handling yielding UNKNOWN rather than silent zero.
- Rule 10: Data freshness tracking carrying through to result.
- Rule 11: Runtime scheduling (24x7, 8x5, custom hours, fractional month).
- Rule 12: Cost-driver decomposition with drill-through support.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from domain.cost.calculation.models import (
    CostCategoryType,
    CostDerivation,
    CostDriverComponent,
    EstimatedCost,
    RuntimeScheduleType,
    TierStepDerivation,
)
from domain.cost.currency_service import ConvertedCostFigure, get_currency_service
from domain.models.enums import PricingStatus
from domain.pricing.models import (
    CommitmentInfo,
    DiscountInfo,
    FreeAllowance,
    PricingTierModel,
    TierStructure,
)
from domain.rules.monetary import round_currency, to_decimal
from normalisation.units.converter import convert_unit


# ==============================================================================
# Rule 1: Unit Conversion Through Unit Catalogue Only
# ==============================================================================
def rule_1_unit_conversion(
    quantity: Decimal | float | str | int,
    from_unit: str,
    to_unit: str,
    duration_hours: Decimal | float | str | int | None = None,
) -> Decimal:
    """Converts consumption units strictly using the canonical Unit Catalogue.

    STRICT PROHIBITION: Never perform ad-hoc unit conversions outside the catalogue.
    """
    if from_unit.strip().lower() == to_unit.strip().lower():
        return to_decimal(quantity)

    # Delegate exclusively to the Unit Catalogue converter
    return convert_unit(
        value=quantity,
        from_unit=from_unit,
        to_unit=to_unit,
        duration_hours=duration_hours,
        decimal_places=6,
    )


# ==============================================================================
# Rule 2: Currency Conversion at Stated Rate and Date
# ==============================================================================
def rule_2_currency_conversion(
    amount: Decimal | float | str,
    from_currency: str,
    to_currency: str,
    as_of_date: date | None = None,
) -> ConvertedCostFigure:
    """Converts monetary amounts using effective-dated exchange rates with full disclosure.

    STRICT PROHIBITION: Never convert inside a fact record; query-time conversion only.
    """
    amt = to_decimal(amount)
    from_curr = from_currency.strip().upper()
    to_curr = to_currency.strip().upper()
    eval_date = as_of_date or datetime.now(UTC).date()

    if from_curr == to_curr:
        return ConvertedCostFigure(
            original_amount=amt,
            original_currency=from_curr,
            target_amount=amt,
            target_currency=to_curr,
            exchange_rate=Decimal("1.0"),
            rate_effective_date=eval_date,
            disclosure=f"Amounts reported in native currency {from_curr}.",
        )

    service = get_currency_service()
    return service.convert_at_query_time(
        amount=amt,
        from_currency=from_curr,
        to_currency=to_curr,
        as_of_date=eval_date,
    )


# ==============================================================================
# Rule 3: Uniform Rounding Policy (Banker's Rounding ROUND_HALF_EVEN)
# ==============================================================================
def rule_3_rounding(amount: Decimal | float | str, decimal_places: int = 2) -> Decimal:
    """Applies ISO financial banker's rounding (ROUND_HALF_EVEN) defined once uniformly.

    STRICT: Round only at final reporting steps, never intermediate accumulation steps.
    """
    return round_currency(amount, decimal_places=decimal_places)


# ==============================================================================
# Rule 4: Tier Calculation Walking Boundaries Correctly
# ==============================================================================
def rule_4_tier_calculation(
    quantity: Decimal | float | str,
    tier_structure: TierStructure | None,
    default_unit_rate: Decimal | float | str,
) -> tuple[Decimal, list[TierStepDerivation]]:
    """Calculates tiered cost walking graduated boundaries or volume tier brackets.

    Returns:
        tuple[Decimal, list[TierStepDerivation]]: Total unrounded cost and detailed bracket breakdown.
    """
    qty = to_decimal(quantity)
    def_rate = to_decimal(default_unit_rate)

    if qty <= Decimal("0.0"):
        return Decimal("0.00"), []

    if tier_structure is None or not tier_structure.brackets:
        # Flat rate calculation
        total = qty * def_rate
        return total, [
            TierStepDerivation(
                bracket_index=0,
                tier_start=Decimal("0.0"),
                tier_end=None,
                bracket_rate=def_rate,
                units_in_bracket=qty,
                flat_fee=Decimal("0.0"),
                bracket_subtotal=total,
            )
        ]

    steps: list[TierStepDerivation] = []

    if tier_structure.pricing_model == PricingTierModel.VOLUME:
        # Volume pricing: All units charged at highest volume threshold rate reached
        qualifying_bracket = tier_structure.brackets[0]
        for bracket in tier_structure.brackets:
            if qty >= Decimal(str(bracket.tier_start)):
                qualifying_bracket = bracket

        b_rate = to_decimal(qualifying_bracket.tier_unit_rate)
        flat = to_decimal(qualifying_bracket.flat_fee)
        total = (qty * b_rate) + flat
        step = TierStepDerivation(
            bracket_index=tier_structure.brackets.index(qualifying_bracket),
            tier_start=to_decimal(qualifying_bracket.tier_start),
            tier_end=to_decimal(qualifying_bracket.tier_end)
            if qualifying_bracket.tier_end is not None
            else None,
            bracket_rate=b_rate,
            units_in_bracket=qty,
            flat_fee=flat,
            bracket_subtotal=total,
        )
        return total, [step]

    # Graduated pricing: Incremental bracket by bracket calculation
    remaining = qty
    total_cost = Decimal("0.0")

    for idx, bracket in enumerate(tier_structure.brackets):
        if remaining <= Decimal("0.0"):
            break

        b_start = to_decimal(bracket.tier_start)
        b_end = to_decimal(bracket.tier_end) if bracket.tier_end is not None else None
        b_rate = to_decimal(bracket.tier_unit_rate)
        flat = to_decimal(bracket.flat_fee)

        if b_end is not None:
            capacity = b_end - b_start
            units = min(remaining, capacity)
        else:
            units = remaining

        subtotal = (units * b_rate) + flat
        total_cost += subtotal
        remaining -= units

        steps.append(
            TierStepDerivation(
                bracket_index=idx,
                tier_start=b_start,
                tier_end=b_end,
                bracket_rate=b_rate,
                units_in_bracket=units,
                flat_fee=flat,
                bracket_subtotal=subtotal,
            )
        )

    return total_cost, steps


# ==============================================================================
# Rule 5: Free-Tier Consumption Deducted Before Charged Consumption
# ==============================================================================
def rule_5_free_allowance(
    quantity: Decimal | float | str,
    free_allowance: FreeAllowance | None,
) -> tuple[Decimal, Decimal]:
    """Deducts free-tier consumption before charged consumption.

    Returns:
        tuple[Decimal, Decimal]: (net_billable_quantity, allowance_deducted)
    """
    qty = to_decimal(quantity)
    if free_allowance is None or free_allowance.quantity <= 0.0:
        return qty, Decimal("0.00")

    allowance_qty = to_decimal(free_allowance.quantity)
    if qty <= allowance_qty:
        # Fully covered by free allowance
        return Decimal("0.00"), qty

    # Partially covered
    net_billable = qty - allowance_qty
    return net_billable, allowance_qty


# ==============================================================================
# Rule 6: Minimum-Charge Handling
# ==============================================================================
def rule_6_minimum_charge(
    subtotal: Decimal | float | str,
    minimum_charge: Decimal | float | str,
) -> tuple[Decimal, bool]:
    """Applies billing floor minimum charge if calculated consumption is less than minimum.

    Returns:
        tuple[Decimal, bool]: (effective_subtotal, is_minimum_charge_applied)
    """
    sub = to_decimal(subtotal)
    min_chg = to_decimal(minimum_charge)

    if min_chg > Decimal("0.0") and sub < min_chg:
        return min_chg, True
    return sub, False


# ==============================================================================
# Rule 7: Commitment Application (Reservations & Savings Plans)
# ==============================================================================
def rule_7_commitment_application(
    on_demand_rate: Decimal | float | str,
    commitment_info: CommitmentInfo | None,
    runtime_hours: Decimal | float | str,
) -> tuple[Decimal, Decimal, str | None]:
    """Applies commitment discounts (e.g. 1-year or 3-year RI / Savings Plan).

    Returns:
        tuple[Decimal, Decimal, str | None]: (effective_cost, savings_amount, commitment_reference)
    """
    od_rate = to_decimal(on_demand_rate)
    hours = to_decimal(runtime_hours)
    baseline_cost = od_rate * hours

    if commitment_info is None or commitment_info.commitment_type == "NONE":
        return baseline_cost, Decimal("0.00"), None

    c_type = commitment_info.commitment_type
    term = commitment_info.term_months or 12

    # Standard commitment discount multipliers
    discount_fraction = Decimal("0.30") if term <= 12 else Decimal("0.50")
    if commitment_info.hourly_commitment is not None and commitment_info.hourly_commitment > 0:
        effective_rate = to_decimal(commitment_info.hourly_commitment)
    else:
        effective_rate = od_rate * (Decimal("1.0") - discount_fraction)

    committed_cost = effective_rate * hours
    savings = max(Decimal("0.00"), baseline_cost - committed_cost)
    ref = f"{c_type}_{term}M_{commitment_info.payment_option}"

    return committed_cost, savings, ref


# ==============================================================================
# Rule 8: Discount Application (Contracted & Negotiated Rates)
# ==============================================================================
def rule_8_discount_application(
    subtotal: Decimal | float | str,
    discount_info: DiscountInfo | None,
    contracted_rate: Decimal | float | str | None = None,
    list_rate: Decimal | float | str | None = None,
) -> tuple[Decimal, Decimal, Decimal]:
    """Applies contracted discounts and computes the realised discount monetary value.

    Returns:
        tuple[Decimal, Decimal, Decimal]: (discounted_subtotal, discount_amount, discount_percent)
    """
    sub = to_decimal(subtotal)

    # 1. Direct rate differential if both list and contracted are supplied
    if contracted_rate is not None and list_rate is not None:
        c_rate = to_decimal(contracted_rate)
        l_rate = to_decimal(list_rate)
        if l_rate > Decimal("0.0") and c_rate < l_rate:
            discount_pct = ((l_rate - c_rate) / l_rate) * Decimal("100.0")
            discount_amt = sub * ((l_rate - c_rate) / l_rate)
            return sub - discount_amt, discount_amt, discount_pct

    # 2. Percentage discount in DiscountInfo
    if discount_info is not None and discount_info.discount_percentage > 0.0:
        pct = to_decimal(discount_info.discount_percentage)
        discount_amt = sub * (pct / Decimal("100.0"))
        return sub - discount_amt, discount_amt, pct

    return sub, Decimal("0.00"), Decimal("0.00")


# ==============================================================================
# Rule 9: Missing-Data Handling (Yields UNKNOWN, Never Zero)
# ==============================================================================
def rule_9_missing_data(
    pricing_found: bool,
    provider: str,
    service: str,
    sku: str | None,
    region: str,
) -> tuple[PricingStatus, str | None]:
    """Handles missing or uncatalogued pricing data.

    STRICT: Unavailable pricing produces UNKNOWN with an explicit reason, never a silent zero!
    """
    if pricing_found:
        return PricingStatus.PAID, None

    reason = (
        f"Pricing record not available for provider='{provider}', service='{service}', "
        f"sku='{sku or 'default'}' in region='{region}'. Pre-deployment estimate cannot assume 0.00."
    )
    return PricingStatus.UNKNOWN, reason


# ==============================================================================
# Rule 10: Data Freshness Tracking
# ==============================================================================
def rule_10_data_freshness(
    retrieved_at: datetime,
    stale_threshold_hours: float = 24.0,
) -> tuple[bool, float]:
    """Evaluates whether pricing data is within the acceptable freshness threshold.

    Returns:
        tuple[bool, float]: (is_stale, age_in_hours)
    """
    now = datetime.now(UTC)
    retrieved_utc = retrieved_at if retrieved_at.tzinfo else retrieved_at.replace(tzinfo=UTC)
    delta_seconds = max(0.0, (now - retrieved_utc).total_seconds())
    age_hours = delta_seconds / 3600.0
    is_stale = age_hours > stale_threshold_hours
    return is_stale, age_hours


# ==============================================================================
# Rule 11: Runtime Scheduling
# ==============================================================================
def rule_11_runtime_schedule(
    schedule_type: RuntimeScheduleType,
    custom_hours: float | None = None,
    days_in_month: int = 30,
) -> Decimal:
    """Calculates active billing hours in a monthly cycle based on operational schedule.

    - CONTINUOUS_24_7: Standard 730 hours (or days * 24).
    - BUSINESS_HOURS_8X5: 8 hours/day * 5 days/week = 40 hrs/wk * (52 / 12) = 173.3333 hours.
    - CUSTOM_HOURS: Explicit user value.
    - FRACTIONAL_MONTH: Scaled by active days.
    """
    if schedule_type == RuntimeScheduleType.BUSINESS_HOURS_8X5:
        # 40 hrs/week * (52 weeks / 12 months) = 173.3333 hrs/month
        return Decimal("173.3333")

    if schedule_type == RuntimeScheduleType.CUSTOM_HOURS:
        if custom_hours is not None and custom_hours >= 0.0:
            return to_decimal(custom_hours)
        return Decimal("730.0")

    if schedule_type == RuntimeScheduleType.FRACTIONAL_MONTH:
        active_days = min(30, max(1, days_in_month))
        return Decimal(str(active_days * 24))

    # Default CONTINUOUS_24_7
    return Decimal("730.0")


# ==============================================================================
# Rule 12: Cost-Driver Decomposition
# ==============================================================================
def rule_12_cost_driver_decomposition(
    drivers: list[tuple[CostCategoryType, str, Decimal, CostDerivation, dict[str, Any]]],
    currency: str = "USD",
) -> list[CostDriverComponent]:
    """Decomposes a total cost into contributing components with percentage attribution."""
    if not drivers:
        return []

    total_amount = sum(item[2] for item in drivers)
    components: list[CostDriverComponent] = []

    for category, name, amount, derivation, details in drivers:
        pct = (
            round_currency((amount / total_amount) * Decimal("100.0"), decimal_places=2)
            if total_amount > Decimal("0.0")
            else Decimal("0.00")
        )
        rounded_monthly = round_currency(amount, decimal_places=2)
        est_cost = EstimatedCost(
            amount=float(rounded_monthly),
            currency=currency,
            pricing_record_id=f"driver-{name.lower().replace(' ', '-')}",
            pricing_source=derivation.pricing_source,
            usage_quantity=float(derivation.quantity_consumed),
            usage_unit=derivation.unit,
            estimation_formula=f"{derivation.quantity_consumed} {derivation.unit} * {derivation.rate_applied} {currency}/{derivation.unit}",
        )
        components.append(
            CostDriverComponent(
                category=category,
                name=name,
                monthly_cost=est_cost,
                percentage_of_total=pct,
                derivation=derivation,
                drillable_details=details,
            )
        )

    return components


__all__ = [
    "rule_1_unit_conversion",
    "rule_2_currency_conversion",
    "rule_3_rounding",
    "rule_4_tier_calculation",
    "rule_5_free_allowance",
    "rule_6_minimum_charge",
    "rule_7_commitment_application",
    "rule_8_discount_application",
    "rule_9_missing_data",
    "rule_10_data_freshness",
    "rule_11_runtime_schedule",
    "rule_12_cost_driver_decomposition",
]
