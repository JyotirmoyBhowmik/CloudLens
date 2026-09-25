"""Comprehensive Unit Tests for FinOps Threshold Bands (100% Coverage Target)."""

from decimal import Decimal

from domain.rules.thresholds import (
    ThresholdBand,
    evaluate_budget_threshold,
    evaluate_cost_spike,
    evaluate_idle_resource,
)


def test_budget_threshold_bands():
    """Verify evaluation across all 4 budget bands: NORMAL, AMBER, RED, CRITICAL."""
    budget = Decimal("1000.00")
    amber_threshold = Decimal("80.0")

    # 1. NORMAL band (< 80%)
    res_normal = evaluate_budget_threshold(Decimal("500.00"), budget, amber_threshold)
    assert res_normal.band == ThresholdBand.NORMAL
    assert res_normal.is_alert_triggered is False
    assert res_normal.consumption_percentage == Decimal("50.00")

    # 2. AMBER band (>= 80% and < 100%)
    res_amber = evaluate_budget_threshold(Decimal("850.00"), budget, amber_threshold)
    assert res_amber.band == ThresholdBand.AMBER
    assert res_amber.is_alert_triggered is True

    # 3. RED band (>= 100% and < 120%)
    res_red = evaluate_budget_threshold(Decimal("1050.00"), budget, amber_threshold)
    assert res_red.band == ThresholdBand.RED
    assert res_red.is_alert_triggered is True

    # 4. CRITICAL band (>= 120%)
    res_crit = evaluate_budget_threshold(Decimal("1250.00"), budget, amber_threshold)
    assert res_crit.band == ThresholdBand.CRITICAL
    assert res_crit.is_alert_triggered is True


def test_budget_threshold_zero_budget_cases():
    """Verify edge cases when allocated budget is zero."""
    amber_threshold = Decimal("80.0")

    # Spend > 0 on zero budget -> CRITICAL
    res_over = evaluate_budget_threshold(Decimal("100.00"), Decimal("0.00"), amber_threshold)
    assert res_over.band == ThresholdBand.CRITICAL
    assert res_over.is_alert_triggered is True

    # Spend 0 on zero budget -> NORMAL
    res_zero = evaluate_budget_threshold(Decimal("0.00"), Decimal("0.00"), amber_threshold)
    assert res_zero.band == ThresholdBand.NORMAL
    assert res_zero.is_alert_triggered is False


def test_cost_spike_evaluation():
    """Verify day-over-day anomalous spend spike detection."""
    spike_threshold = Decimal("20.0")  # 20% increase threshold

    # Normal delta (< 20%)
    res_norm = evaluate_cost_spike(Decimal("100.00"), Decimal("110.00"), spike_threshold)
    assert res_norm.is_spike_detected is False
    assert res_norm.severity == ThresholdBand.NORMAL

    # Moderate spike (>= 20%, < 40%) -> AMBER
    res_amber = evaluate_cost_spike(Decimal("100.00"), Decimal("125.00"), spike_threshold)
    assert res_amber.is_spike_detected is True
    assert res_amber.severity == ThresholdBand.AMBER

    # Severe spike (>= 40%) -> CRITICAL
    res_crit = evaluate_cost_spike(Decimal("100.00"), Decimal("150.00"), spike_threshold)
    assert res_crit.is_spike_detected is True
    assert res_crit.severity == ThresholdBand.CRITICAL

    # Zero baseline with spend -> RED
    res_zero_base = evaluate_cost_spike(Decimal("0.00"), Decimal("50.00"), spike_threshold)
    assert res_zero_base.is_spike_detected is True
    assert res_zero_base.severity == ThresholdBand.RED

    # Zero baseline with zero spend -> NORMAL
    res_zero_zero = evaluate_cost_spike(Decimal("0.00"), Decimal("0.00"), spike_threshold)
    assert res_zero_zero.is_spike_detected is False
    assert res_zero_zero.severity == ThresholdBand.NORMAL


def test_evaluate_idle_resource():
    """Verify idle resource comparison logic."""
    idle_threshold = Decimal("5.0")  # 5% CPU threshold

    # CPU 2.5% < 5.0% -> Idle
    assert evaluate_idle_resource(Decimal("2.5"), idle_threshold) is True

    # CPU 5.0% >= 5.0% -> Not idle
    assert evaluate_idle_resource(Decimal("5.0"), idle_threshold) is False

    # CPU 25.0% >= 5.0% -> Not idle
    assert evaluate_idle_resource(Decimal("25.0"), idle_threshold) is False
