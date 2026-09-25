"""CloudLens FinOps Threshold Band & Alert Evaluation Engine.

STRICT RULE (Prompt 04 Item 28):
Must achieve 100% test coverage with zero tolerance for floating-point drift.
Evaluates:
- Budget consumption bands: NORMAL, AMBER, RED, CRITICAL
- Day-over-day anomalous spend spikes
- Idle resource thresholds
All thresholds resolve from configuration defaults or tenant settings.
"""

from decimal import Decimal
from enum import Enum
from typing import NamedTuple

from domain.rules.monetary import to_decimal


class ThresholdBand(str, Enum):
    """FinOps governance alert severity levels."""

    NORMAL = "NORMAL"  # Healthy / Under amber threshold
    AMBER = "AMBER"  # Warning: approaching allocation limit
    RED = "RED"  # Exhaustion: 100% or more of budget consumed
    CRITICAL = "CRITICAL"  # Severe overspend: exceeded critical threshold limit


class BudgetEvaluation(NamedTuple):
    """Result of budget threshold evaluation."""

    consumption_percentage: Decimal
    band: ThresholdBand
    is_alert_triggered: bool
    message: str


class CostSpikeEvaluation(NamedTuple):
    """Result of day-over-day spend spike evaluation."""

    delta_amount: Decimal
    percentage_increase: Decimal
    is_spike_detected: bool
    severity: ThresholdBand


def evaluate_budget_threshold(
    current_spend: Decimal | float | str,
    allocated_budget: Decimal | float | str,
    amber_threshold_pct: Decimal | float | str,
    critical_threshold_pct: Decimal | float | str | None = None,
) -> BudgetEvaluation:
    """Evaluates budget consumption percentage and determines appropriate alert band."""
    spend = to_decimal(current_spend)
    budget = to_decimal(allocated_budget)
    amber_limit = to_decimal(amber_threshold_pct)
    crit_limit = (
        to_decimal(critical_threshold_pct)
        if critical_threshold_pct is not None
        else Decimal("120.0")
    )

    if budget <= Decimal("0.00"):
        if spend > Decimal("0.00"):
            return BudgetEvaluation(
                consumption_percentage=Decimal("100.0"),
                band=ThresholdBand.CRITICAL,
                is_alert_triggered=True,
                message="Spend incurred against zero allocated budget.",
            )
        return BudgetEvaluation(
            consumption_percentage=Decimal("0.0"),
            band=ThresholdBand.NORMAL,
            is_alert_triggered=False,
            message="Zero spend against zero budget.",
        )

    consumption_pct = ((spend / budget) * Decimal("100.0")).quantize(Decimal("0.01"))

    if consumption_pct >= crit_limit:
        return BudgetEvaluation(
            consumption_percentage=consumption_pct,
            band=ThresholdBand.CRITICAL,
            is_alert_triggered=True,
            message=f"Critical overspend: {consumption_pct}% of budget consumed (threshold: {crit_limit}%).",
        )
    if consumption_pct >= Decimal("100.0"):
        return BudgetEvaluation(
            consumption_percentage=consumption_pct,
            band=ThresholdBand.RED,
            is_alert_triggered=True,
            message=f"Budget exhausted: {consumption_pct}% of budget consumed.",
        )
    if consumption_pct >= amber_limit:
        return BudgetEvaluation(
            consumption_percentage=consumption_pct,
            band=ThresholdBand.AMBER,
            is_alert_triggered=True,
            message=f"Budget warning: {consumption_pct}% consumed (approaching warning limit {amber_limit}%).",
        )

    return BudgetEvaluation(
        consumption_percentage=consumption_pct,
        band=ThresholdBand.NORMAL,
        is_alert_triggered=False,
        message=f"Spend is healthy at {consumption_pct}% of allocation.",
    )


def evaluate_cost_spike(
    baseline_spend: Decimal | float | str,
    current_spend: Decimal | float | str,
    spike_threshold_pct: Decimal | float | str,
) -> CostSpikeEvaluation:
    """Determines if current spend exhibits an anomalous spike over baseline spend."""
    base = to_decimal(baseline_spend)
    curr = to_decimal(current_spend)
    threshold = to_decimal(spike_threshold_pct)

    delta = curr - base
    if base <= Decimal("0.00"):
        if curr > Decimal("0.00"):
            return CostSpikeEvaluation(
                delta_amount=curr,
                percentage_increase=Decimal("100.0"),
                is_spike_detected=True,
                severity=ThresholdBand.RED,
            )
        return CostSpikeEvaluation(
            delta_amount=Decimal("0.00"),
            percentage_increase=Decimal("0.0"),
            is_spike_detected=False,
            severity=ThresholdBand.NORMAL,
        )

    pct_increase = ((delta / base) * Decimal("100.0")).quantize(Decimal("0.01"))

    if pct_increase >= threshold:
        severity = (
            ThresholdBand.CRITICAL
            if pct_increase >= (threshold * Decimal("2.0"))
            else ThresholdBand.AMBER
        )
        return CostSpikeEvaluation(
            delta_amount=delta,
            percentage_increase=pct_increase,
            is_spike_detected=True,
            severity=severity,
        )

    return CostSpikeEvaluation(
        delta_amount=delta,
        percentage_increase=pct_increase,
        is_spike_detected=False,
        severity=ThresholdBand.NORMAL,
    )


def evaluate_idle_resource(
    metric_value: Decimal | float | str,
    idle_threshold: Decimal | float | str,
) -> bool:
    """Returns True if the resource metric is strictly below the configured idle threshold."""
    metric = to_decimal(metric_value)
    thresh = to_decimal(idle_threshold)
    return metric < thresh
