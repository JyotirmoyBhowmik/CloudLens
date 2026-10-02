"""Configurable Default Threshold Templates and Band Factories (Prompt 27).

Enforces:
- Prompt 27 Acceptance Criteria:
  'The default budget bands (0–70 green, 70–90 amber, 90–100 orange, 100+ red) behave as specified
   and every boundary is configurable.'
- Prompt 27 Negative Constraint:
  'Do not hard-code any band boundary.'
"""

from __future__ import annotations

from decimal import Decimal

from domain.thresholds.models import (
    AntiFlappingConfig,
    ThresholdBandDefinition,
    ThresholdBasis,
    ThresholdRule,
    ThresholdState,
)


def create_configurable_budget_bands(
    *,
    normal_upper: Decimal = Decimal("70.0"),
    warning_upper: Decimal = Decimal("90.0"),
    high_upper: Decimal = Decimal("100.0"),
    hysteresis_pct: Decimal = Decimal("2.0"),
) -> list[ThresholdBandDefinition]:
    """Generates the four canonical budget bands with fully configurable boundaries.

    Default boundaries per Prompt 27:
    - 0 to 70: Normal (Green)
    - 70 to 90: Warning (Amber)
    - 90 to 100: High (Orange)
    - 100+: Critical (Red)
    """
    return [
        ThresholdBandDefinition(
            state=ThresholdState.NORMAL,
            name="Normal Consumption",
            lower_bound=Decimal("0.0"),
            upper_bound=normal_upper,
            description="Actual consumption is healthy and within nominal budget boundaries.",
        ),
        ThresholdBandDefinition(
            state=ThresholdState.WARNING,
            name="Warning Threshold",
            lower_bound=normal_upper,
            upper_bound=warning_upper,
            exit_threshold_lower=normal_upper - hysteresis_pct,
            description="Consumption is approaching budget allocation limits.",
        ),
        ThresholdBandDefinition(
            state=ThresholdState.HIGH,
            name="High Burn Rate",
            lower_bound=warning_upper,
            upper_bound=high_upper,
            exit_threshold_lower=warning_upper - hysteresis_pct,
            description="High budget burn rate; exhaustion imminent without intervention.",
        ),
        ThresholdBandDefinition(
            state=ThresholdState.CRITICAL,
            name="Critical Overspend",
            lower_bound=high_upper,
            upper_bound=None,  # Unbounded above
            exit_threshold_lower=high_upper - hysteresis_pct,
            description="Budget limit fully exhausted (>= 100%). Overspend alert in effect.",
        ),
    ]


def create_tenant_default_budget_rule(
    tenant_id: str,
    *,
    normal_upper: Decimal = Decimal("70.0"),
    warning_upper: Decimal = Decimal("90.0"),
    high_upper: Decimal = Decimal("100.0"),
    cooldown_seconds: int = 3600,
    dwell_evaluations: int = 1,
) -> ThresholdRule:
    """Creates the default fallback budget rule for a tenant with configurable boundaries."""
    bands = create_configurable_budget_bands(
        normal_upper=normal_upper,
        warning_upper=warning_upper,
        high_upper=high_upper,
    )
    return ThresholdRule(
        id=f"thr-default-budget-{tenant_id}",
        tenant_id=tenant_id,
        name="Tenant Default Budget Threshold Rule",
        description="Standard 4-tier budget consumption threshold bands with anti-flapping.",
        basis=ThresholdBasis.BUDGET_UTILISATION,
        bands=bands,
        anti_flapping=AntiFlappingConfig(
            dwell_evaluations=dwell_evaluations,
            cooldown_seconds=cooldown_seconds,
            hysteresis_margin_pct=Decimal("2.0"),
            grouping_storm_threshold=5,
            enable_data_quality_gate=True,
        ),
        is_tenant_default=True,
        unit="%",
    )
