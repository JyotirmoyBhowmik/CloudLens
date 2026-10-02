"""Budget Evaluation Engine (Prompt 28).

Enforces:
- Prompt 28: Evaluation producing actual utilisation, forecast utilisation, variance,
  and state on every cycle.
- Prompt 28: Predict budget breach dates based on run rate before breach occurs.
- Negative constraint: Do NOT evaluate a budget before its effective date.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from domain.budgets.calendar import BudgetPeriodCalendar
from domain.budgets.models import BudgetEntity, BudgetEvaluationResult
from domain.thresholds.models import ThresholdState


class BudgetEvaluator:
    """Evaluates actual consumption, burn rate velocity, and forecast against budget ceilings."""

    def __init__(self, calendar: BudgetPeriodCalendar | None = None) -> None:
        self._calendar = calendar or BudgetPeriodCalendar()

    def evaluate(
        self,
        budget: BudgetEntity,
        as_of: date | None = None,
        actual_spend: float | None = None,
        fiscal_calendar_code: str = "FC_STANDARD",
    ) -> BudgetEvaluationResult:
        """Executes full financial evaluation for a budget.

        Negative Constraint: Never evaluates a budget before its effective date.
        """
        eval_date = as_of or date.today()
        period_start, period_end = self._calendar.resolve_period_bounds(
            budget, as_of=eval_date, fiscal_calendar_code=fiscal_calendar_code
        )

        # Enforce Negative Constraint: Do not evaluate before effective date
        if eval_date < budget.effective_date:
            return BudgetEvaluationResult(
                budget_id=budget.id,
                budget_name=budget.name,
                scope_type=budget.scope_type,
                scope_id=budget.scope_id,
                currency=budget.currency,
                amount=budget.amount,
                actual_spend=0.0,
                actual_utilisation=0.0,
                forecast_spend=0.0,
                forecast_utilisation=0.0,
                variance=budget.amount,
                variance_pct=0.0,
                state=ThresholdState.INFORMATIONAL,
                state_color=ThresholdState.INFORMATIONAL.get_color_hex(),
                is_breached=False,
                is_effective=False,
                effective_date=budget.effective_date,
                expiry_date=budget.expiry_date,
                period_start=period_start,
                period_end=period_end,
                evaluated_at=datetime.now(UTC),
                predicted_breach_date=None,
                notes=f"Budget is not yet effective. Operational effective date is {budget.effective_date}.",
            )

        # Determine spend
        spend = actual_spend if actual_spend is not None else 0.0

        # Compute actual utilisation percentage
        actual_util = round((spend / budget.amount * 100.0), 2) if budget.amount > 0 else 0.0

        # Calculate run rate and forecast burn
        elapsed_days = max(1, (eval_date - period_start).days + 1)
        remaining_days = max(0, (period_end - eval_date).days)

        velocity = spend / elapsed_days
        forecast_spend = round(spend + (velocity * remaining_days), 2)
        forecast_util = (
            round((forecast_spend / budget.amount * 100.0), 2) if budget.amount > 0 else 0.0
        )

        variance = round(budget.amount - spend, 2)
        variance_pct = (
            round(((spend - budget.amount) / budget.amount * 100.0), 2)
            if budget.amount > 0
            else 0.0
        )

        # Threshold bands lookup
        warning_pct = 80.0
        high_pct = 90.0
        critical_pct = 100.0

        for t in budget.thresholds:
            if t.band.upper() in ("WARNING", "AMBER"):
                warning_pct = t.percentage
            elif t.band.upper() in ("HIGH", "ORANGE"):
                high_pct = t.percentage
            elif t.band.upper() in ("CRITICAL", "RED"):
                critical_pct = t.percentage

        # Evaluate threshold state
        predicted_breach_date: date | None = None
        notes: str | None = None

        if actual_util >= critical_pct:
            state = ThresholdState.CRITICAL
            is_breached = True
            notes = f"Critical overspend: {actual_util:.1f}% consumed of budget allocation ceiling."
        elif actual_util >= high_pct:
            state = ThresholdState.HIGH
            is_breached = True
            notes = f"High consumption: {actual_util:.1f}% consumed. Allocation nearing exhaustion."
        elif actual_util >= warning_pct:
            state = ThresholdState.WARNING
            is_breached = True
            notes = f"Warning: {actual_util:.1f}% of budget consumed."
        elif budget.forecast_threshold and forecast_util >= budget.forecast_threshold:
            state = ThresholdState.WARNING
            is_breached = False
            notes = f"Forecast breach alert: projected end-of-period spend reaches {forecast_util:.1f}%."
        else:
            state = ThresholdState.NORMAL
            is_breached = False
            notes = "Spend is healthy within nominal allocated boundaries."

        # Compute predicted breach date if velocity indicates impending overspend
        if velocity > 0 and spend < budget.amount:
            days_to_breach = int((budget.amount - spend) / velocity)
            candidate_date = eval_date + timedelta(days=days_to_breach)
            if candidate_date <= period_end:
                predicted_breach_date = candidate_date

        return BudgetEvaluationResult(
            budget_id=budget.id,
            budget_name=budget.name,
            scope_type=budget.scope_type,
            scope_id=budget.scope_id,
            currency=budget.currency,
            amount=budget.amount,
            actual_spend=spend,
            actual_utilisation=actual_util,
            forecast_spend=forecast_spend,
            forecast_utilisation=forecast_util,
            variance=variance,
            variance_pct=variance_pct,
            state=state,
            state_color=state.get_color_hex(),
            is_breached=is_breached,
            is_effective=True,
            effective_date=budget.effective_date,
            expiry_date=budget.expiry_date,
            period_start=period_start,
            period_end=period_end,
            evaluated_at=datetime.now(UTC),
            predicted_breach_date=predicted_breach_date,
            notes=notes,
        )
