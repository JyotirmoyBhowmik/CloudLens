"""Budget Impact Computation Engine (Prompt 55).

Enforces:
- Comprehensive 4-dimensional budget impact analysis:
  1. Remaining budget for the billing period.
  2. Estimated consumption of remaining budget (%).
  3. Resulting projected period utilisation (%).
  4. Effect on existing month-end forecast and variance.
- Visual materiality tiers (NEGLIGIBLE, MODERATE, SUBSTANTIAL, CRITICAL)
  distinguishing e.g. 3% consumption vs 80% consumption.
- Defensible narrative commentary.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from domain.provisioning.models import BudgetImpactAssessment, BudgetImpactTier
from domain.rules.monetary import round_currency

logger = logging.getLogger(__name__)


class BudgetImpactEngine:
    """Computes multidimensional budget and forecast impact for pre-deployment gate."""

    def evaluate_impact(
        self,
        period: str,
        period_budget: Decimal,
        actual_spend: Decimal,
        request_monthly_cost: Decimal,
        current_forecast: Decimal | None = None,
    ) -> BudgetImpactAssessment:
        """Evaluates budget impact against the target scope.

        Handles zero and negative remaining budget cleanly without division by zero.
        """
        budget = round_currency(period_budget)
        actual = round_currency(actual_spend)
        req_cost = round_currency(request_monthly_cost)

        remaining_budget = round_currency(budget - actual)
        projected_spend = round_currency(actual + req_cost)

        # 1. Projected Utilisation %
        if budget > Decimal("0.00"):
            projected_utilisation_pct = round_currency(
                (projected_spend / budget) * Decimal("100.00")
            )
        else:
            projected_utilisation_pct = (
                Decimal("100.00") if projected_spend > 0 else Decimal("0.00")
            )

        # 2. Consumption of Remaining Budget %
        if remaining_budget > Decimal("0.00"):
            consumption_of_remaining_pct = round_currency(
                (req_cost / remaining_budget) * Decimal("100.00")
            )
        else:
            # Over-budget condition: any non-zero request consumes 100%+ of remaining headroom
            consumption_of_remaining_pct = Decimal("100.00") if req_cost > 0 else Decimal("0.00")

        # 3. Forecast shift
        forecast_val = round_currency(current_forecast if current_forecast is not None else actual)
        revised_forecast = round_currency(forecast_val + req_cost)
        forecast_variance_change = round_currency(revised_forecast - budget)

        # 4. Materiality Tier
        # Distinguish 3% (NEGLIGIBLE) from 80% (CRITICAL)
        if remaining_budget <= Decimal("0.00") or consumption_of_remaining_pct >= Decimal("50.00"):
            tier = BudgetImpactTier.CRITICAL
        elif consumption_of_remaining_pct >= Decimal("25.00"):
            tier = BudgetImpactTier.SUBSTANTIAL
        elif consumption_of_remaining_pct >= Decimal("5.00"):
            tier = BudgetImpactTier.MODERATE
        else:
            tier = BudgetImpactTier.NEGLIGIBLE

        # 5. Narrative Commentary
        if tier == BudgetImpactTier.CRITICAL:
            commentary = (
                f"CRITICAL BUDGET IMPACT: Proposed spend of ${req_cost:,.2f}/mo consumes "
                f"{consumption_of_remaining_pct:.1f}% of remaining budget (${remaining_budget:,.2f}). "
                f"Projected period spend is ${projected_spend:,.2f} ({projected_utilisation_pct:.1f}% of ${budget:,.2f} budget). "
                f"Month-end forecast revised to ${revised_forecast:,.2f}."
            )
        elif tier == BudgetImpactTier.SUBSTANTIAL:
            commentary = (
                f"SUBSTANTIAL BUDGET IMPACT: Proposed spend of ${req_cost:,.2f}/mo consumes "
                f"{consumption_of_remaining_pct:.1f}% of remaining budget (${remaining_budget:,.2f}). "
                f"Projected utilisation increases to {projected_utilisation_pct:.1f}%. "
                f"Revised forecast: ${revised_forecast:,.2f}."
            )
        elif tier == BudgetImpactTier.MODERATE:
            commentary = (
                f"MODERATE BUDGET IMPACT: Proposed spend of ${req_cost:,.2f}/mo consumes "
                f"{consumption_of_remaining_pct:.1f}% of remaining budget (${remaining_budget:,.2f}). "
                f"Projected utilisation is {projected_utilisation_pct:.1f}%. "
                f"Revised forecast: ${revised_forecast:,.2f}."
            )
        else:
            commentary = (
                f"NEGLIGIBLE BUDGET IMPACT: Proposed spend of ${req_cost:,.2f}/mo consumes only "
                f"{consumption_of_remaining_pct:.1f}% of remaining budget (${remaining_budget:,.2f}). "
                f"Period utilisation remains healthy at {projected_utilisation_pct:.1f}%. "
                f"Revised forecast: ${revised_forecast:,.2f}."
            )

        return BudgetImpactAssessment(
            period=period,
            period_budget=budget,
            actual_spend=actual,
            remaining_budget=remaining_budget,
            request_monthly_cost=req_cost,
            projected_spend=projected_spend,
            projected_utilisation_pct=projected_utilisation_pct,
            consumption_of_remaining_pct=consumption_of_remaining_pct,
            current_forecast=forecast_val,
            revised_forecast=revised_forecast,
            forecast_variance_change=forecast_variance_change,
            impact_tier=tier,
            commentary=commentary,
        )
