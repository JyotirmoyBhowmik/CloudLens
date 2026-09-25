"""CloudLens Monetary Arithmetic & Financial Calculation Engine.

STRICT RULE (Prompt 04 Item 28):
Must achieve 100% test coverage with zero tolerance for floating-point inaccuracy.
Uses Python Decimal with explicit banker's rounding (ROUND_HALF_EVEN) and exact precision.
"""

from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal
from typing import NamedTuple


class AmortisationSchedule(NamedTuple):
    """Result of upfront commitment cost spreading."""

    daily_amortised_amount: Decimal
    hourly_amortised_amount: Decimal
    total_spread_amount: Decimal
    rounding_adjustment: Decimal


def to_decimal(val: int | float | str | Decimal) -> Decimal:
    """Safely converts numeric input to Decimal without float representation noise."""
    if isinstance(val, Decimal):
        return val
    if isinstance(val, float):
        # Convert via string representation to avoid binary float artifacts
        return Decimal(str(val))
    return Decimal(val)


def round_currency(amount: Decimal | float | str, decimal_places: int = 2) -> Decimal:
    """Rounds monetary amount using ISO financial banker's rounding (ROUND_HALF_EVEN)."""
    dec_val = to_decimal(amount)
    exponent = Decimal("10") ** -decimal_places
    return dec_val.quantize(exponent, rounding=ROUND_HALF_EVEN)


def calculate_amortisation(
    upfront_fee: Decimal | float | str,
    duration_days: int,
) -> AmortisationSchedule:
    """Spreads an upfront reservation or commitment payment across days and hours.

    Guarantees exact reconciliation: daily_amortised * days + adjustment == upfront_fee.
    """
    if duration_days <= 0:
        raise ValueError("Amortisation duration must be greater than zero days.")

    fee = to_decimal(upfront_fee)
    if fee < Decimal("0.00"):
        raise ValueError("Upfront fee cannot be negative.")

    days = Decimal(duration_days)
    hours = Decimal(duration_days * 24)

    # Calculate unrounded daily and hourly rates
    daily_rate = (fee / days).quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN)
    hourly_rate = (fee / hours).quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)

    daily_two_places = round_currency(daily_rate, decimal_places=2)
    spread_subtotal = daily_two_places * days
    adjustment = fee - spread_subtotal

    return AmortisationSchedule(
        daily_amortised_amount=daily_two_places,
        hourly_amortised_amount=hourly_rate,
        total_spread_amount=spread_subtotal + adjustment,
        rounding_adjustment=adjustment,
    )


def calculate_blended_rate(
    total_cost: Decimal | float | str,
    total_usage_units: Decimal | float | str,
) -> Decimal:
    """Calculates blended unit cost rate (total cost / total usage)."""
    cost = to_decimal(total_cost)
    usage = to_decimal(total_usage_units)

    if usage <= Decimal("0.00"):
        return Decimal("0.000000")

    return (cost / usage).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def calculate_variance_ratio(
    invoice_total: Decimal | float | str,
    calculated_total: Decimal | float | str,
) -> Decimal:
    """Calculates absolute discrepancy ratio between billed invoice and computed resource total."""
    inv = to_decimal(invoice_total)
    calc = to_decimal(calculated_total)

    if inv == Decimal("0.00"):
        return Decimal("0.0000") if calc == Decimal("0.00") else Decimal("1.0000")

    delta = abs(inv - calc)
    return (delta / inv).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
