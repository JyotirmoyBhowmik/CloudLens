"""Forecast Accuracy Measurement and Trend Engine (Prompt 29).

Enforces:
- Prompt 29: At 25%, 50% and 75% of each period, record the forecast made.
- Prompt 29: At period close, compare to actual and report the error (MAPE, absolute error, percentage error).
- Prompt 29: Publish accuracy as a trend, because 'a forecast whose accuracy is unknown is an opinion'.
- Prompt 29: Convergence verification: forecast error decreases as period progresses (M75 < M50 < M25).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from domain.forecasting.models import (
    ForecastAccuracyTrend,
    ForecastMilestone,
    ForecastMilestoneSnapshot,
    PeriodAccuracyReport,
)


class AccuracyEngine:
    """Engine measuring forecast variance across lifecycle milestones and computing historical trends."""

    @staticmethod
    def resolve_milestone(
        period_start: date,
        period_end: date,
        as_of: date,
    ) -> ForecastMilestone:
        """Determines the appropriate milestone checkpoint for a given evaluation date."""
        if as_of >= period_end:
            return ForecastMilestone.PERIOD_CLOSE

        total_days = max(1, (period_end - period_start).days + 1)
        elapsed_days = max(1, (as_of - period_start).days + 1)
        ratio = elapsed_days / total_days

        if ratio >= 0.75:
            return ForecastMilestone.M75
        elif ratio >= 0.50:
            return ForecastMilestone.M50
        elif ratio >= 0.25:
            return ForecastMilestone.M25
        return ForecastMilestone.M25  # Earliest checkpoint

    @staticmethod
    def evaluate_milestone_accuracy(
        snapshot: ForecastMilestoneSnapshot,
        actual_billed_amount: float,
    ) -> ForecastMilestoneSnapshot:
        """Calculates error metrics for a recorded milestone against final actual billed spend."""
        actual = max(0.0, actual_billed_amount)
        abs_error = round(abs(snapshot.forecast_amount - actual), 2)

        if actual > 0.0:
            pct_error = round(((snapshot.forecast_amount - actual) / actual * 100.0), 2)
            accuracy_pct = round(max(0.0, 100.0 - abs(pct_error)), 2)
        else:
            pct_error = 0.0 if snapshot.forecast_amount == 0.0 else 100.0
            accuracy_pct = 100.0 if snapshot.forecast_amount == 0.0 else 0.0

        return ForecastMilestoneSnapshot(
            id=snapshot.id,
            tenant_id=snapshot.tenant_id,
            scope_id=snapshot.scope_id,
            budget_id=snapshot.budget_id,
            period_identifier=snapshot.period_identifier,
            period_start=snapshot.period_start,
            period_end=snapshot.period_end,
            milestone=snapshot.milestone,
            checkpoint_date=snapshot.checkpoint_date,
            forecast_id=snapshot.forecast_id,
            forecast_amount=snapshot.forecast_amount,
            method=snapshot.method,
            confidence=snapshot.confidence,
            actual_billed_amount=actual,
            absolute_error=abs_error,
            percentage_error=pct_error,
            accuracy_percentage=accuracy_pct,
            evaluated_at=datetime.now(UTC),
            recorded_at=snapshot.recorded_at,
        )

    @classmethod
    def evaluate_period_close(
        cls,
        *,
        period_identifier: str,
        period_start: date,
        period_end: date,
        actual_billed_amount: float,
        milestone_snapshots: list[ForecastMilestoneSnapshot],
    ) -> PeriodAccuracyReport:
        """Evaluates all milestone snapshots recorded for a closed period against actual billed spend."""
        evaluated_milestones: dict[str, dict[str, Any]] = {}
        accuracies: list[float] = []

        for ms in milestone_snapshots:
            evaluated = cls.evaluate_milestone_accuracy(ms, actual_billed_amount)
            accuracies.append(evaluated.accuracy_percentage or 0.0)

            evaluated_milestones[ms.milestone.value] = {
                "checkpoint_date": ms.checkpoint_date.isoformat(),
                "forecast_amount": ms.forecast_amount,
                "method": ms.method.value,
                "confidence": ms.confidence.value,
                "absolute_error": evaluated.absolute_error,
                "percentage_error": evaluated.percentage_error,
                "accuracy_percentage": evaluated.accuracy_percentage,
                "bias": "OVER_ESTIMATED"
                if ms.forecast_amount > actual_billed_amount
                else "UNDER_ESTIMATED",
            }

        avg_acc = round(sum(accuracies) / len(accuracies), 2) if accuracies else 0.0

        return PeriodAccuracyReport(
            period_identifier=period_identifier,
            period_start=period_start,
            period_end=period_end,
            actual_billed_amount=actual_billed_amount,
            milestones=evaluated_milestones,
            average_accuracy_percentage=avg_acc,
        )

    @staticmethod
    def build_accuracy_trend(
        *,
        tenant_id: str,
        period_reports: list[PeriodAccuracyReport],
    ) -> ForecastAccuracyTrend:
        """Computes multi-period accuracy trend and convergence metrics (Prompt 29)."""
        if not period_reports:
            return ForecastAccuracyTrend(
                tenant_id=tenant_id,
                total_closed_periods_evaluated=0,
                average_mape_m25=0.0,
                average_mape_m50=0.0,
                average_mape_m75=0.0,
                overall_accuracy_percentage=0.0,
                trend_direction="STABLE",
                is_convergent=True,
                periods=[],
            )

        mape_m25_vals: list[float] = []
        mape_m50_vals: list[float] = []
        mape_m75_vals: list[float] = []
        all_accuracies: list[float] = []

        for rep in period_reports:
            all_accuracies.append(rep.average_accuracy_percentage)
            for m_key, m_val in rep.milestones.items():
                pct_err = abs(m_val.get("percentage_error", 0.0))
                if m_key == ForecastMilestone.M25.value:
                    mape_m25_vals.append(pct_err)
                elif m_key == ForecastMilestone.M50.value:
                    mape_m50_vals.append(pct_err)
                elif m_key == ForecastMilestone.M75.value:
                    mape_m75_vals.append(pct_err)

        avg_mape_25 = round(sum(mape_m25_vals) / len(mape_m25_vals), 2) if mape_m25_vals else 0.0
        avg_mape_50 = round(sum(mape_m50_vals) / len(mape_m50_vals), 2) if mape_m50_vals else 0.0
        avg_mape_75 = round(sum(mape_m75_vals) / len(mape_m75_vals), 2) if mape_m75_vals else 0.0
        overall_acc = round(sum(all_accuracies) / len(all_accuracies), 2) if all_accuracies else 0.0

        # Convergence: Error decreases as period progresses (M75 <= M50 <= M25)
        is_convergent = avg_mape_75 <= avg_mape_50 and avg_mape_50 <= avg_mape_25

        # Trend direction across periods: Compare first half of periods to second half
        trend_direction = "STABLE"
        if len(period_reports) >= 2:
            mid = len(period_reports) // 2
            first_half_avg = sum(r.average_accuracy_percentage for r in period_reports[:mid]) / mid
            second_half_avg = sum(r.average_accuracy_percentage for r in period_reports[mid:]) / (
                len(period_reports) - mid
            )
            if second_half_avg - first_half_avg > 3.0:
                trend_direction = "IMPROVING"
            elif first_half_avg - second_half_avg > 3.0:
                trend_direction = "DEGRADING"

        return ForecastAccuracyTrend(
            tenant_id=tenant_id,
            total_closed_periods_evaluated=len(period_reports),
            average_mape_m25=avg_mape_25,
            average_mape_m50=avg_mape_50,
            average_mape_m75=avg_mape_75,
            overall_accuracy_percentage=overall_acc,
            trend_direction=trend_direction,
            is_convergent=is_convergent,
            periods=period_reports,
        )
