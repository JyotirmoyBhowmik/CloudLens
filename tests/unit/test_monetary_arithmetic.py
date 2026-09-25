"""Comprehensive Unit Tests for Monetary Arithmetic (100% Coverage Target)."""

from decimal import Decimal

import pytest

from domain.rules.monetary import (
    calculate_amortisation,
    calculate_blended_rate,
    calculate_variance_ratio,
    round_currency,
    to_decimal,
)


def test_to_decimal_conversions():
    """Verify to_decimal handles Decimal, float, int, str cleanly."""
    d1 = to_decimal(Decimal("12.34"))
    assert d1 == Decimal("12.34")

    d2 = to_decimal(12.34)
    assert d2 == Decimal("12.34")

    d3 = to_decimal(100)
    assert d3 == Decimal("100")

    d4 = to_decimal("99.99")
    assert d4 == Decimal("99.99")


def test_round_currency_bankers_rounding():
    """Verify ISO banker's rounding (ROUND_HALF_EVEN)."""
    # 2.5 rounds to 2 (even)
    assert round_currency(Decimal("2.5"), decimal_places=0) == Decimal("2")
    # 3.5 rounds to 4 (even)
    assert round_currency(Decimal("3.5"), decimal_places=0) == Decimal("4")

    assert round_currency(Decimal("10.555"), decimal_places=2) == Decimal("10.56")
    assert round_currency(Decimal("10.554"), decimal_places=2) == Decimal("10.55")
    assert round_currency("100.125", decimal_places=2) == Decimal("100.12")


def test_calculate_amortisation_success():
    """Verify upfront commitment cost amortization schedule."""
    upfront = Decimal("3650.00")
    duration = 365
    sched = calculate_amortisation(upfront, duration)

    assert sched.daily_amortised_amount == Decimal("10.00")
    assert sched.total_spread_amount == upfront
    assert sched.rounding_adjustment == Decimal("0.00")
    assert sched.hourly_amortised_amount > Decimal("0")


def test_calculate_amortisation_with_rounding_adjustment():
    """Verify exact reconciliation with remainder penny adjustment."""
    upfront = Decimal("100.00")
    duration = 3  # 100 / 3 = 33.33 daily * 3 = 99.99 + 0.01 adjustment
    sched = calculate_amortisation(upfront, duration)

    assert sched.daily_amortised_amount == Decimal("33.33")
    assert sched.rounding_adjustment == Decimal("0.01")
    assert sched.total_spread_amount == upfront


def test_calculate_amortisation_invalid_inputs():
    """Verify validation errors on negative fees or non-positive durations."""
    with pytest.raises(ValueError, match="duration must be greater than zero"):
        calculate_amortisation(Decimal("100"), 0)

    with pytest.raises(ValueError, match="duration must be greater than zero"):
        calculate_amortisation(Decimal("100"), -5)

    with pytest.raises(ValueError, match="fee cannot be negative"):
        calculate_amortisation(Decimal("-10.00"), 30)


def test_calculate_blended_rate():
    """Verify blended rate calculation and division by zero protection."""
    # $1000 for 500 hours = $2.000000/hour
    rate = calculate_blended_rate(Decimal("1000.00"), Decimal("500.00"))
    assert rate == Decimal("2.000000")

    # Zero usage returns 0
    zero_rate = calculate_blended_rate(Decimal("100.00"), Decimal("0.00"))
    assert zero_rate == Decimal("0.000000")

    # Negative usage returns 0
    neg_rate = calculate_blended_rate(Decimal("100.00"), Decimal("-10.00"))
    assert neg_rate == Decimal("0.000000")


def test_calculate_variance_ratio():
    """Verify invoice reconciliation discrepancy variance ratio."""
    # Exact match -> 0% variance
    assert calculate_variance_ratio(Decimal("100.00"), Decimal("100.00")) == Decimal("0.0000")

    # 100 invoice vs 105 calculated -> 5% variance
    assert calculate_variance_ratio(Decimal("100.00"), Decimal("105.00")) == Decimal("0.0500")

    # 100 invoice vs 95 calculated -> 5% variance
    assert calculate_variance_ratio(Decimal("100.00"), Decimal("95.00")) == Decimal("0.0500")

    # 0 invoice and 0 calculated -> 0% variance
    assert calculate_variance_ratio(Decimal("0.00"), Decimal("0.00")) == Decimal("0.0000")

    # 0 invoice and >0 calculated -> 100% variance
    assert calculate_variance_ratio(Decimal("0.00"), Decimal("50.00")) == Decimal("1.0000")
