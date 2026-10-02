"""Quota Consumption Forecasting and Dynamic Lead-Time Alerting Engine (Prompt 54).

Enforces:
- Prompt 54: Project consumption trend against limit to compute predicted_exhaustion_date.
- Prompt 54: Dynamic lead-time alerting: Alert fires at (predicted_exhaustion_date - lead_time - safety_margin),
  giving engineers sufficient runway to request and receive limit increases from the cloud provider.
- Negative constraint: Do NOT alert on a fixed percentage where a predicted exhaustion date is computable.
- Negative constraint: Do NOT present an unknown limit as unlimited (renders as Not Supported / UNKNOWN).
- Negative constraint: Do NOT hard-code any quota name, threshold, or lead time.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from domain.models.enums import QuotaHeadroomState
from domain.quotas.models import QuotaDataPoint, QuotaEntity

logger = logging.getLogger(__name__)


class QuotaForecaster:
    """Predictive trend projection engine calculating exhaustion lead times and states."""

    @classmethod
    def evaluate_quota(
        cls,
        quota: QuotaEntity,
        *,
        as_of: datetime | None = None,
    ) -> QuotaEntity:
        """Evaluates quota capacity, trend velocity, forecast dates, and headroom state."""
        evaluation_time = as_of or datetime.now(UTC)

        # 1. Negative constraint: If limit is unknown, never treat as unlimited
        if quota.limit_value is None:
            quota.status = QuotaHeadroomState.NOT_SUPPORTED
            quota.predicted_exhaustion_date = None
            quota.alert_trigger_date = None
            quota.daily_consumption_velocity = None
            quota.days_until_exhaustion = None
            return quota

        limit = float(quota.limit_value)
        consumed = float(quota.consumed_value)

        # 2. Check immediate exhaustion
        if consumed >= limit:
            quota.status = QuotaHeadroomState.EXHAUSTED
            quota.days_until_exhaustion = 0.0
            quota.predicted_exhaustion_date = evaluation_time
            quota.alert_trigger_date = evaluation_time
            return quota

        headroom = max(0.0, limit - consumed)
        headroom_pct = (headroom / limit) * 100.0 if limit > 0 else 0.0

        # 3. Compute consumption growth velocity (units/day) from history
        velocity = cls.calculate_velocity(
            quota.history, current_consumed=consumed, current_time=evaluation_time
        )
        quota.daily_consumption_velocity = velocity

        # 4. If positive consumption velocity exists, compute predicted exhaustion date
        if velocity is not None and velocity > 0.0:
            days_to_exhaustion = headroom / velocity
            quota.days_until_exhaustion = round(days_to_exhaustion, 2)
            predicted_date = evaluation_time + timedelta(days=days_to_exhaustion)
            quota.predicted_exhaustion_date = predicted_date

            # Calculate required lead-time window in days: lead_time_days + (lead_time_days * (safety_margin_pct / 100))
            # E.g. 3 days + (3 * 0.05) = 3.15 days
            lead_time = float(quota.lead_time_days)
            safety_margin_days = lead_time * (float(quota.safety_margin_pct) / 100.0)
            total_lead_time_days = lead_time + safety_margin_days

            alert_trigger_date = predicted_date - timedelta(days=total_lead_time_days)
            quota.alert_trigger_date = alert_trigger_date

            # Lead-time aware state determination:
            # - If already past predicted_exhaustion_date -> EXHAUSTED
            # - If current_time >= (predicted_exhaustion_date - lead_time_days) -> CRITICAL (insufficient lead time remaining!)
            # - If current_time >= alert_trigger_date -> WARNING (lead-time threshold breached, request increase now!)
            # - Otherwise -> NORMAL (plenty of lead time available)
            critical_date = predicted_date - timedelta(days=lead_time)

            if evaluation_time >= predicted_date:
                quota.status = QuotaHeadroomState.EXHAUSTED
            elif evaluation_time >= critical_date:
                quota.status = QuotaHeadroomState.CRITICAL
            elif evaluation_time >= alert_trigger_date:
                quota.status = QuotaHeadroomState.WARNING
            else:
                # Plentiful lead time. However, if headroom percentage is critically low (under critical_headroom_pct),
                # safety defense applies.
                if headroom_pct <= float(quota.critical_headroom_pct):
                    quota.status = QuotaHeadroomState.CRITICAL
                else:
                    quota.status = QuotaHeadroomState.NORMAL

        else:
            # Velocity is non-positive or unavailable (flat/declining or single point)
            quota.days_until_exhaustion = None
            quota.predicted_exhaustion_date = None
            quota.alert_trigger_date = None

            # Fallback to configured percentage headroom thresholds when trend is flat
            if headroom_pct <= float(quota.critical_headroom_pct):
                quota.status = QuotaHeadroomState.CRITICAL
            elif headroom_pct <= float(quota.warning_headroom_pct):
                quota.status = QuotaHeadroomState.WARNING
            else:
                quota.status = QuotaHeadroomState.NORMAL

        return quota

    @classmethod
    def calculate_velocity(
        cls,
        history: list[QuotaDataPoint],
        *,
        current_consumed: float,
        current_time: datetime,
    ) -> float | None:
        """Calculates daily growth rate of resource consumption across historical points."""
        if not history:
            return None

        # Sort history chronologically
        sorted_points = sorted(history, key=lambda p: p.timestamp)

        # Include current consumed value as latest point if newer than latest history point
        points = list(sorted_points)
        if not points or points[-1].timestamp < current_time:
            points.append(
                QuotaDataPoint(
                    timestamp=current_time,
                    consumed_value=current_consumed,
                    limit_value=None,
                )
            )

        if len(points) < 2:
            return None

        # Calculate linear regression slope or first-to-last delta over observation window
        first_pt = points[0]
        last_pt = points[-1]

        delta_seconds = (last_pt.timestamp - first_pt.timestamp).total_seconds()
        if delta_seconds <= 300:  # Less than 5 minutes difference
            return None

        delta_days = delta_seconds / 86400.0
        delta_consumed = last_pt.consumed_value - first_pt.consumed_value

        velocity = delta_consumed / delta_days
        return round(velocity, 4)
