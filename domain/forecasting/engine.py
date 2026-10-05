"""Forecasting Computation Engine (Prompt 29).

Enforces:
- Prompt 29: Produce forward-looking numbers that never overstate their own confidence.
- Prompt 29: Three MVP methods:
  * Simple run-rate (default)
  * Historical average
  * Moving average
- Prompt 29: Four Phase 2 methods behind flags:
  * Trend-based regression
  * Seasonality-aware decomposition
  * Provider-published forecast comparison
  * User-defined adjustment rules
- Prompt 29: All seven forecast outputs:
  1. end-of-period cost
  2. expected usage
  3. expected budget consumption
  4. cost trend
  5. forecast variance
  6. predicted threshold breach date
  7. predicted budget breach date
- Prompt 29: Fallback rule:
  * Where history is insufficient for configured method, fall back to run-rate and label confidence LOW.
  * With fewer than three days of period data, produce run-rate forecast labelled LOW confidence rather than nothing.
  * Do NOT use a method whose minimum history is not satisfied.
- Prompt 29: Store method, window, confidence, and timestamp on every forecast.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta
from typing import Any

from domain.config.feature_flags import feature_flag_service
from domain.forecasting.models import (
    DailySpendPoint,
    ForecastDerivation,
    ForecastInputWindow,
    ForecastOutputs,
    UserForecastAdjustmentRule,
)
from domain.models.enums import (
    CostTrend,
    ForecastConfidence,
    ForecastMethod,
)


class ForecastingEngine:
    """Core computational engine calculating financial projections across MVP and Phase 2 algorithms."""

    def __init__(self, tenant_id: str = "SYSTEM_TENANT") -> None:
        self.tenant_id = tenant_id

    def compute_forecast(
        self,
        *,
        period_start: date,
        period_end: date,
        as_of: date,
        requested_method: ForecastMethod,
        daily_spends: list[DailySpendPoint],
        historical_spends: list[DailySpendPoint] | None = None,
        budget_amount: float | None = None,
        warning_threshold_pct: float = 80.0,
        moving_average_window_days: int = 7,
        provider_published_amount: float | None = None,
        adjustment_rules: list[UserForecastAdjustmentRule] | None = None,
    ) -> tuple[
        ForecastMethod,
        bool,
        str | None,
        ForecastConfidence,
        float,
        ForecastInputWindow,
        ForecastOutputs,
        ForecastDerivation,
    ]:
        """Calculates forecast projection with strict fallback and confidence discipline.

        Returns:
            (effective_method, fallback_applied, fallback_reason, confidence, confidence_score,
             input_window, outputs, derivation)
        """
        historical_spends = historical_spends or []
        adjustment_rules = adjustment_rules or []

        # 1. Filter telemetry to active period up to as_of
        period_spends = [p for p in daily_spends if period_start <= p.date <= as_of]
        period_spends.sort(key=lambda p: p.date)

        # 2. Compute cumulative actuals
        actual_spend = round(sum(p.amount for p in period_spends), 2)
        actual_usage = round(sum(p.usage for p in period_spends), 2)

        elapsed_days = max(1, (as_of - period_start).days + 1)
        remaining_days = max(0, (period_end - as_of).days)

        # 3. Determine telemetry window
        all_available_spends = historical_spends + period_spends
        all_available_spends.sort(key=lambda p: p.date)

        window_start = all_available_spends[0].date if all_available_spends else period_start
        window_end = as_of
        window_days = max(1, (window_end - window_start).days + 1)

        input_window = ForecastInputWindow(
            start_date=window_start,
            end_date=window_end,
            window_days=window_days,
            data_points_count=len(all_available_spends),
            data_freshness_as_of=datetime.now(UTC),
        )

        # 4. Method Dispatch & Fallback Verification
        effective_method = requested_method
        fallback_applied = False
        fallback_reason: str | None = None

        # Check Phase 2 feature flags
        if requested_method.is_phase2():
            flag_key = requested_method.feature_flag_key()
            if flag_key and not feature_flag_service.evaluate(flag_key, self.tenant_id):
                effective_method = ForecastMethod.RUN_RATE
                fallback_applied = True
                fallback_reason = (
                    f"Phase 2 feature flag '{flag_key}' is disabled; fell back to run-rate."
                )

        # Check minimum history requirements
        min_history_required = requested_method.minimum_history_days()
        available_history_days = len(all_available_spends)

        if not fallback_applied and requested_method != ForecastMethod.RUN_RATE:
            if available_history_days < min_history_required:
                effective_method = ForecastMethod.RUN_RATE
                fallback_applied = True
                fallback_reason = (
                    f"Insufficient history for {requested_method.value}: requires at least "
                    f"{min_history_required} days, but only {available_history_days} days were available."
                )

        # 5. Execute Effective Algorithm
        daily_velocity: float = 0.0
        daily_usage_velocity: float = 0.0
        projected_remaining_spend: float = 0.0
        projected_remaining_usage: float = 0.0
        method_details: dict[str, Any] = {}
        confidence: ForecastConfidence = ForecastConfidence.HIGH
        confidence_score: float = 0.85
        confidence_rationale: str = "Standard algorithm confidence."

        if effective_method == ForecastMethod.RUN_RATE:
            # Simple Run-Rate
            daily_velocity = actual_spend / elapsed_days
            daily_usage_velocity = actual_usage / elapsed_days
            projected_remaining_spend = round(daily_velocity * remaining_days, 2)
            projected_remaining_usage = round(daily_usage_velocity * remaining_days, 2)

            method_details = {
                "algorithm": "Simple Run-Rate (Daily Velocity Linear Extrapolation)",
                "daily_burn_rate": round(daily_velocity, 4),
                "elapsed_days": elapsed_days,
                "remaining_days": remaining_days,
            }

            # Negative Constraint: With fewer than 3 days of period data, produce run-rate with LOW confidence
            if elapsed_days < 3:
                confidence = ForecastConfidence.LOW
                confidence_score = 0.35
                confidence_rationale = (
                    f"Fewer than 3 days of period data available ({elapsed_days}d elapsed). "
                    "Run-rate forecast produced with Low confidence per policy."
                )
            elif fallback_applied:
                confidence = ForecastConfidence.LOW
                confidence_score = 0.40
                confidence_rationale = (
                    f"Fallback applied from {requested_method.value}. Reason: {fallback_reason}"
                )
            elif elapsed_days < 7:
                confidence = ForecastConfidence.MEDIUM
                confidence_score = 0.65
                confidence_rationale = (
                    f"Moderate data depth ({elapsed_days} days of current period elapsed)."
                )
            else:
                confidence = ForecastConfidence.HIGH
                confidence_score = 0.85
                confidence_rationale = (
                    f"Robust baseline run-rate ({elapsed_days} days of current period elapsed)."
                )

        elif effective_method == ForecastMethod.HISTORICAL_AVERAGE:
            # Historical Average
            hist_points = historical_spends if historical_spends else period_spends
            total_hist_spend = sum(p.amount for p in hist_points)
            total_hist_usage = sum(p.usage for p in hist_points)
            daily_velocity = total_hist_spend / len(hist_points)
            daily_usage_velocity = total_hist_usage / len(hist_points)
            projected_remaining_spend = round(daily_velocity * remaining_days, 2)
            projected_remaining_usage = round(daily_usage_velocity * remaining_days, 2)

            method_details = {
                "algorithm": "Historical Average",
                "historical_data_points": len(hist_points),
                "historical_daily_mean_spend": round(daily_velocity, 4),
            }
            confidence = ForecastConfidence.HIGH
            confidence_score = 0.90  # no-hardcode-allow: reason="Empirical statistical confidence score for historical baseline", reviewer="Prompt-48-Audit"
            confidence_rationale = f"Historical baseline established over {len(hist_points)} days of prior observations."

        elif effective_method == ForecastMethod.MOVING_AVERAGE:
            # Moving Average
            window_size = min(moving_average_window_days, len(all_available_spends))
            recent_points = all_available_spends[-window_size:]
            daily_velocity = sum(p.amount for p in recent_points) / window_size
            daily_usage_velocity = sum(p.usage for p in recent_points) / window_size
            projected_remaining_spend = round(daily_velocity * remaining_days, 2)
            projected_remaining_usage = round(daily_usage_velocity * remaining_days, 2)

            method_details = {
                "algorithm": f"Moving Average ({window_size}-day window)",
                "moving_window_size": window_size,
                "moving_average_daily_spend": round(daily_velocity, 4),
            }
            if window_size >= 14:
                confidence = ForecastConfidence.HIGH
                confidence_score = 0.85
                confidence_rationale = (
                    f"Moving average over stable {window_size}-day trailing window."
                )
            else:
                confidence = ForecastConfidence.MEDIUM
                confidence_score = 0.70
                confidence_rationale = f"Short moving average trailing window ({window_size} days)."

        elif effective_method == ForecastMethod.TREND_REGRESSION:
            # Phase 2: Trend-Based Regression
            n = len(all_available_spends)
            x_vals = list(range(1, n + 1))
            y_vals = [p.amount for p in all_available_spends]

            sum_x = sum(x_vals)
            sum_y = sum(y_vals)
            sum_xy = sum(x * y for x, y in zip(x_vals, y_vals, strict=False))
            sum_x2 = sum(x * x for x in x_vals)

            denom = (n * sum_x2) - (sum_x * sum_x)
            if denom != 0:
                slope = ((n * sum_xy) - (sum_x * sum_y)) / denom
                intercept = (sum_y - (slope * sum_x)) / n
            else:
                slope = 0.0
                intercept = sum_y / max(1, n)

            # Extrapolate for remaining days
            projected_future_daily = []
            for d in range(1, remaining_days + 1):
                proj_d = max(0.0, slope * (n + d) + intercept)
                projected_future_daily.append(proj_d)

            projected_remaining_spend = round(sum(projected_future_daily), 2)
            daily_velocity = (
                projected_remaining_spend / remaining_days
                if remaining_days > 0
                else (sum_y / max(1, n))
            )
            daily_usage_velocity = (actual_usage / elapsed_days) if elapsed_days > 0 else 0.0
            projected_remaining_usage = round(daily_usage_velocity * remaining_days, 2)

            method_details = {
                "algorithm": "Trend-Based Linear Regression",
                "regression_slope": round(slope, 6),
                "regression_intercept": round(intercept, 4),
                "data_points_fitted": n,
            }
            confidence = ForecastConfidence.HIGH
            confidence_score = 0.85
            confidence_rationale = (
                f"Fitted linear trajectory across {n} observations with slope {slope:.4f}."
            )

        elif effective_method == ForecastMethod.SEASONALITY_DECOMPOSITION:
            # Phase 2: Seasonality-Aware Decomposition (Day of week)
            dow_spends: dict[int, list[float]] = {i: [] for i in range(7)}
            for p in all_available_spends:
                dow_spends[p.date.weekday()].append(p.amount)

            dow_means = {
                dow: (sum(vals) / len(vals) if vals else 0.0) for dow, vals in dow_spends.items()
            }
            overall_mean = sum(dow_means.values()) / 7.0 if sum(dow_means.values()) > 0 else 1.0

            dow_factors = {
                dow: (mean_val / overall_mean if overall_mean > 0 else 1.0)
                for dow, mean_val in dow_means.items()
            }

            # Extrapolate daily by weekday factor
            base_daily = actual_spend / elapsed_days
            projected_future_daily = []
            for d in range(1, remaining_days + 1):
                day_date = as_of + timedelta(days=d)
                day_factor = dow_factors.get(day_date.weekday(), 1.0)
                projected_future_daily.append(base_daily * day_factor)

            projected_remaining_spend = round(sum(projected_future_daily), 2)
            daily_velocity = (
                projected_remaining_spend / remaining_days if remaining_days > 0 else base_daily
            )
            daily_usage_velocity = (actual_usage / elapsed_days) if elapsed_days > 0 else 0.0
            projected_remaining_usage = round(daily_usage_velocity * remaining_days, 2)

            method_details = {
                "algorithm": "Seasonality-Aware Day-of-Week Decomposition",
                "day_of_week_factors": {k: round(v, 4) for k, v in dow_factors.items()},
                "seasonal_cycles_fitted": len(all_available_spends) // 7,
            }
            confidence = ForecastConfidence.HIGH
            confidence_score = 0.90  # no-hardcode-allow: reason="Empirical statistical confidence score for seasonal pattern", reviewer="Prompt-48-Audit"
            confidence_rationale = f"Cyclical weekly seasonal pattern fitted over {len(all_available_spends)} daily points."

        elif effective_method == ForecastMethod.PROVIDER_PUBLISHED:
            # Phase 2: Provider-Published Forecast
            if provider_published_amount is not None and provider_published_amount > 0:
                total_proj = provider_published_amount
                projected_remaining_spend = max(0.0, round(total_proj - actual_spend, 2))
                daily_velocity = (
                    projected_remaining_spend / remaining_days if remaining_days > 0 else 0.0
                )
                daily_usage_velocity = (actual_usage / elapsed_days) if elapsed_days > 0 else 0.0
                projected_remaining_usage = round(daily_usage_velocity * remaining_days, 2)

                method_details = {
                    "algorithm": "Provider-Published Forecast Direct Integration",
                    "provider_published_total": round(provider_published_amount, 2),
                    "cloudlens_run_rate_comparison": round(
                        actual_spend + ((actual_spend / elapsed_days) * remaining_days), 2
                    ),
                }
                confidence = ForecastConfidence.HIGH
                confidence_score = 0.85
                confidence_rationale = (
                    "Ingested authoritative cloud provider native projected billing ceiling."
                )
            else:
                # Fallback to run rate
                effective_method = ForecastMethod.RUN_RATE
                fallback_applied = True
                fallback_reason = (
                    "Provider-published amount missing or non-positive; fell back to run-rate."
                )
                daily_velocity = actual_spend / elapsed_days
                daily_usage_velocity = actual_usage / elapsed_days
                projected_remaining_spend = round(daily_velocity * remaining_days, 2)
                projected_remaining_usage = round(daily_usage_velocity * remaining_days, 2)
                confidence = ForecastConfidence.LOW
                confidence_score = 0.40
                confidence_rationale = fallback_reason

        elif effective_method == ForecastMethod.USER_ADJUSTMENT:
            # Phase 2: User-Defined Adjustment Rules
            base_daily = actual_spend / elapsed_days
            projected_days_spend: list[float] = []

            for d in range(1, remaining_days + 1):
                day_date = as_of + timedelta(days=d)
                day_amount = base_daily

                for rule in adjustment_rules:
                    rule_applies = False
                    if rule.end_date:
                        rule_applies = rule.start_date <= day_date <= rule.end_date
                    else:
                        rule_applies = day_date >= rule.start_date

                    if rule_applies:
                        if rule.adjustment_type == "ADDITIVE_DAILY":
                            day_amount += rule.adjustment_value
                        elif rule.adjustment_type == "PERCENTAGE_MULTIPLIER":
                            day_amount *= 1.0 + rule.adjustment_value
                        elif (
                            rule.adjustment_type == "ONE_TIME_CHARGE"
                            and day_date == rule.start_date
                        ):
                            day_amount += rule.adjustment_value

                projected_days_spend.append(max(0.0, day_amount))

            projected_remaining_spend = round(sum(projected_days_spend), 2)
            daily_velocity = (
                projected_remaining_spend / remaining_days if remaining_days > 0 else base_daily
            )
            daily_usage_velocity = (actual_usage / elapsed_days) if elapsed_days > 0 else 0.0
            projected_remaining_usage = round(daily_usage_velocity * remaining_days, 2)

            method_details = {
                "algorithm": "User-Defined Adjustment Rules Extrapolation",
                "rules_applied_count": len(adjustment_rules),
                "rule_names": [r.rule_name for r in adjustment_rules],
            }
            confidence = ForecastConfidence.MEDIUM
            confidence_score = 0.75
            confidence_rationale = f"Base run-rate adjusted with {len(adjustment_rules)} user-defined future planned events."

        # 6. Finalise End-of-Period Totals
        end_of_period_cost = round(actual_spend + projected_remaining_spend, 2)
        expected_usage = round(actual_usage + projected_remaining_usage, 2)

        # 7. Budget Utilisation & Variance
        expected_budget_consumption: float = 0.0
        forecast_variance: float = 0.0

        if budget_amount and budget_amount > 0:
            expected_budget_consumption = round((end_of_period_cost / budget_amount * 100.0), 2)
            forecast_variance = round(end_of_period_cost - budget_amount, 2)
        else:
            # Baseline variance
            baseline_spend = (
                sum(p.amount for p in historical_spends) if historical_spends else actual_spend
            )
            forecast_variance = round(end_of_period_cost - baseline_spend, 2)

        # 8. Cost Trend Determination
        cost_trend = self._determine_cost_trend(period_spends=period_spends)

        # 9. Predicted Breach Dates
        predicted_threshold_breach_date: date | None = None
        predicted_budget_breach_date: date | None = None

        if budget_amount and budget_amount > 0 and daily_velocity > 0:
            warning_ceiling = budget_amount * (warning_threshold_pct / 100.0)

            # Warning threshold breach
            if actual_spend >= warning_ceiling:
                predicted_threshold_breach_date = as_of
            else:
                days_to_warn = (warning_ceiling - actual_spend) / daily_velocity
                warn_date = as_of + timedelta(days=math.ceil(days_to_warn))
                if warn_date <= period_end:
                    predicted_threshold_breach_date = warn_date

            # 100% budget breach
            if actual_spend >= budget_amount:
                predicted_budget_breach_date = as_of
            else:
                days_to_breach = (budget_amount - actual_spend) / daily_velocity
                breach_date = as_of + timedelta(days=math.ceil(days_to_breach))
                if breach_date <= period_end:
                    predicted_budget_breach_date = breach_date

        outputs = ForecastOutputs(
            end_of_period_cost=end_of_period_cost,
            expected_usage=expected_usage,
            expected_budget_consumption=expected_budget_consumption,
            cost_trend=cost_trend,
            forecast_variance=forecast_variance,
            predicted_threshold_breach_date=predicted_threshold_breach_date,
            predicted_budget_breach_date=predicted_budget_breach_date,
        )

        derivation = ForecastDerivation(
            daily_burn_rate=round(daily_velocity, 4),
            elapsed_days=elapsed_days,
            remaining_days=remaining_days,
            actual_spend_to_date=actual_spend,
            projected_remaining_spend=projected_remaining_spend,
            method_details=method_details,
            fallback_applied=fallback_applied,
            fallback_reason=fallback_reason,
            confidence_score=round(confidence_score, 2),
            confidence_rationale=confidence_rationale,
        )

        return (
            effective_method,
            fallback_applied,
            fallback_reason,
            confidence,
            round(confidence_score, 2),
            input_window,
            outputs,
            derivation,
        )

    def _determine_cost_trend(
        self,
        period_spends: list[DailySpendPoint],
    ) -> CostTrend:
        """Determines cost momentum and trajectory direction."""
        if len(period_spends) < 3:
            return CostTrend.STABLE

        amounts = [p.amount for p in period_spends]
        mean_amt = sum(amounts) / len(amounts)

        if mean_amt <= 0:
            return CostTrend.STABLE

        # 1. Check for Spiking (Last 2 days > 30% higher than prior period average)
        if len(amounts) >= 4:
            recent_avg = sum(amounts[-2:]) / 2.0
            prior_avg = sum(amounts[:-2]) / len(amounts[:-2])
            if prior_avg > 0 and (recent_avg - prior_avg) / prior_avg > 0.30:  # no-hardcode-allow: reason="Cost trend spiking threshold ratio (30%)", reviewer="Prompt-48-Audit"
                return CostTrend.SPIKING

        # 2. Check for Volatility (Coefficient of Variation > 0.40)
        variance = sum((x - mean_amt) ** 2 for x in amounts) / len(amounts)
        std_dev = math.sqrt(variance)
        cv = std_dev / mean_amt

        if cv > 0.40:  # no-hardcode-allow: reason="Cost trend volatility coefficient of variation threshold (0.40)", reviewer="Prompt-48-Audit"
            return CostTrend.VOLATILE

        # 3. Check for Trend Slope
        n = len(amounts)
        x_vals = list(range(1, n + 1))
        sum_x = sum(x_vals)
        sum_y = sum(amounts)
        sum_xy = sum(x * y for x, y in zip(x_vals, amounts, strict=False))
        sum_x2 = sum(x * x for x in x_vals)
        denom = (n * sum_x2) - (sum_x * sum_x)

        if denom != 0:
            slope = ((n * sum_xy) - (sum_x * sum_y)) / denom
            normalized_slope = slope / mean_amt

            if normalized_slope > 0.05:  # no-hardcode-allow: reason="Cost trend normalized slope drift threshold (5%)", reviewer="Prompt-48-Audit"
                return CostTrend.INCREASING
            elif normalized_slope < -0.05:  # no-hardcode-allow: reason="Cost trend normalized slope drift threshold (5%)", reviewer="Prompt-48-Audit"
                return CostTrend.DECREASING

        return CostTrend.STABLE
