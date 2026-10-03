"""Reconciliation Loop & Accuracy Reporting Engine (Prompt 55).

Enforces:
- Linkage of newly inventoried resource to approved provisioning request.
- Tracking actual cost against approved estimate over the first 3 billing periods.
- Classification of accuracy: WITHIN_ACCURACY_BAND (+/-10%), UNDER_ESTIMATED, OVER_ESTIMATED.
- Multi-dimensional accuracy reporting across requesters, services, and approvers.
- Mean Absolute Percentage Error (MAPE) calculation.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any

from domain.provisioning.models import (
    AccuracyReport,
    EstimateAccuracyClassification,
    EstimateVsActualTracking,
    ProvisioningRequest,
    ResourcePeriodActual,
)
from domain.rules.monetary import round_currency

logger = logging.getLogger(__name__)


class ProvisioningReconciliationEngine:
    """Orchestrates 3-period actual vs estimate reconciliation and accuracy reporting."""

    def initialize_tracking(
        self,
        request: ProvisioningRequest,
        resource_id: str,
        approver_role: str | None = None,
    ) -> EstimateVsActualTracking:
        """Initializes a 3-period tracking record when a newly inventoried resource is linked."""
        resolved_approver = approver_role or "FINOPS_ADMIN"
        return EstimateVsActualTracking(
            tracking_id=f"track-{uuid.uuid4().hex[:8]}",
            request_id=request.request_id,
            resource_id=resource_id,
            requester_id=request.estimate.requester_id,
            approver_role=resolved_approver,
            service=request.estimate.service,
            approved_monthly_estimate=request.estimate.monthly_cost,
            periods_tracked=[],
            latest_variance_amount=None,
            latest_variance_pct=None,
            classification=None,
            is_three_periods_complete=False,
        )

    def record_period_actual(
        self,
        tracking: EstimateVsActualTracking,
        period: str,
        billed_amount: Decimal,
    ) -> EstimateVsActualTracking:
        """Records an actual billed spend observation for a billing period.

        Supports tracking up to 3 billing periods. Computes variance and classification.
        """
        billed = round_currency(billed_amount)
        # Update or append period
        existing = [p for p in tracking.periods_tracked if p.period == period]
        if existing:
            existing[0].billed_amount = billed
        else:
            tracking.periods_tracked.append(
                ResourcePeriodActual(period=period, billed_amount=billed)
            )

        # 3-period completion
        if len(tracking.periods_tracked) >= 3:
            tracking.is_three_periods_complete = True

        # Variance calculations against approved monthly estimate
        approved = tracking.approved_monthly_estimate
        variance_amount = round_currency(billed - approved)

        if approved > Decimal("0.00"):
            variance_pct = round_currency((variance_amount / approved) * Decimal("100.00"))
        else:
            variance_pct = Decimal("0.00")

        tracking.latest_variance_amount = variance_amount
        tracking.latest_variance_pct = variance_pct

        # Classification (+/- 10% tolerance)
        if abs(variance_pct) <= Decimal("10.00"):
            tracking.classification = EstimateAccuracyClassification.WITHIN_ACCURACY_BAND
        elif variance_pct > Decimal("10.00"):
            # Actual spend exceeded approved estimate by more than 10%
            tracking.classification = EstimateAccuracyClassification.UNDER_ESTIMATED
        else:
            # Actual spend was more than 10% below approved estimate
            tracking.classification = EstimateAccuracyClassification.OVER_ESTIMATED

        return tracking

    def generate_accuracy_report(
        self,
        tenant_id: str,
        trackings: list[EstimateVsActualTracking],
    ) -> AccuracyReport:
        """Generates cross-sectional accuracy metrics across requesters, services, and approvers."""
        if not trackings:
            return AccuracyReport(
                tenant_id=tenant_id,
                total_tracked=0,
                three_period_completed_count=0,
                within_band_pct=Decimal("0.00"),
                under_estimated_pct=Decimal("0.00"),
                over_estimated_pct=Decimal("0.00"),
                mean_absolute_percentage_error=Decimal("0.00"),
                by_requester=[],
                by_service=[],
                by_approver=[],
            )

        total_tracked = len(trackings)
        completed_count = sum(1 for t in trackings if t.is_three_periods_complete)

        # Filter trackings with at least 1 period observed
        active_with_data = [t for t in trackings if t.latest_variance_pct is not None]
        active_count = len(active_with_data)

        if active_count == 0:
            return AccuracyReport(
                tenant_id=tenant_id,
                total_tracked=total_tracked,
                three_period_completed_count=completed_count,
                within_band_pct=Decimal("0.00"),
                under_estimated_pct=Decimal("0.00"),
                over_estimated_pct=Decimal("0.00"),
                mean_absolute_percentage_error=Decimal("0.00"),
                by_requester=[],
                by_service=[],
                by_approver=[],
            )

        within_count = sum(
            1
            for t in active_with_data
            if t.classification == EstimateAccuracyClassification.WITHIN_ACCURACY_BAND
        )
        under_count = sum(
            1
            for t in active_with_data
            if t.classification == EstimateAccuracyClassification.UNDER_ESTIMATED
        )
        over_count = sum(
            1
            for t in active_with_data
            if t.classification == EstimateAccuracyClassification.OVER_ESTIMATED
        )

        within_pct = round_currency(
            (Decimal(within_count) / Decimal(active_count)) * Decimal("100.00")
        )
        under_pct = round_currency(
            (Decimal(under_count) / Decimal(active_count)) * Decimal("100.00")
        )
        over_pct = round_currency((Decimal(over_count) / Decimal(active_count)) * Decimal("100.00"))

        mape_sum = sum(abs(t.latest_variance_pct or Decimal("0.00")) for t in active_with_data)
        mape = round_currency(mape_sum / Decimal(active_count))

        # Group by helper
        def group_breakdown(key_attr: str) -> list[dict[str, Any]]:
            groups: dict[str, list[EstimateVsActualTracking]] = {}
            for t in active_with_data:
                k = getattr(t, key_attr)
                groups.setdefault(k, []).append(t)

            res = []
            for k, group in groups.items():
                g_count = len(group)
                g_within = sum(
                    1
                    for item in group
                    if item.classification == EstimateAccuracyClassification.WITHIN_ACCURACY_BAND
                )
                g_under = sum(
                    1
                    for item in group
                    if item.classification == EstimateAccuracyClassification.UNDER_ESTIMATED
                )
                g_over = sum(
                    1
                    for item in group
                    if item.classification == EstimateAccuracyClassification.OVER_ESTIMATED
                )
                g_mape = round_currency(
                    sum(abs(item.latest_variance_pct or Decimal("0.00")) for item in group)
                    / Decimal(g_count)
                )
                res.append(
                    {
                        "key": k,
                        "count": g_count,
                        "within_band_pct": float(
                            round_currency(
                                (Decimal(g_within) / Decimal(g_count)) * Decimal("100.00")
                            )
                        ),
                        "under_estimated_pct": float(
                            round_currency(
                                (Decimal(g_under) / Decimal(g_count)) * Decimal("100.00")
                            )
                        ),
                        "over_estimated_pct": float(
                            round_currency((Decimal(g_over) / Decimal(g_count)) * Decimal("100.00"))
                        ),
                        "mape": float(g_mape),
                    }
                )
            return sorted(res, key=lambda x: str(x["key"]))

        by_requester = group_breakdown("requester_id")
        by_service = group_breakdown("service")
        by_approver = group_breakdown("approver_role")

        return AccuracyReport(
            tenant_id=tenant_id,
            total_tracked=total_tracked,
            three_period_completed_count=completed_count,
            within_band_pct=within_pct,
            under_estimated_pct=under_pct,
            over_estimated_pct=over_pct,
            mean_absolute_percentage_error=mape,
            by_requester=by_requester,
            by_service=by_service,
            by_approver=by_approver,
        )
