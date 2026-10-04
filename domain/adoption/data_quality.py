"""Transparent Data Quality Scoring & Component Inspection Engine (Prompt 61 / BBP Section 43).

Enforces:
- The Headline Quality Score: A single trusted number (0.0 to 100.0%) representing organizational data integrity.
- Seven Inspectable Component Dimensions:
  1. ownership_coverage: % of resources with technical/business owner assigned.
  2. tagging_compliance: % of resources satisfying required corporate tags.
  3. budget_coverage: % of production scopes with active budget threshold sets.
  4. allocation_coverage: % of spend attributed to applications or cost centres.
  5. reconciliation_pass_rate: % of connector periods reconciled without variance.
  6. connector_freshness: % of connectors within sync freshness SLA.
  7. catalogue_gap_rate: % of billing line items successfully mapped to master catalogue.
- Historical Trending: Tracks trajectory over time for steering committee transparency.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from domain.adoption.models import (
    DataQualityComponentScore,
    DataQualityReport,
)
from domain.models.enums import DataQualityRating
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)

DEFAULT_WEIGHTS = {
    "ownership_coverage": 0.15,
    "tagging_compliance": 0.15,
    "budget_coverage": 0.15,
    "allocation_coverage": 0.15,
    "reconciliation_pass_rate": 0.20,
    "connector_freshness": 0.10,
    "catalogue_gap_rate": 0.10,
}


class DataQualityService:
    """Computes, inspects, and tracks longitudinal trends of the enterprise Data Quality Score."""

    def __init__(self) -> None:
        # In-memory history: tenant_id -> list of historical score summaries
        self._history: dict[str, list[dict[str, Any]]] = {}

    def calculate_data_quality(
        self,
        component_metrics: dict[str, dict[str, Any]],
        *,
        tenant_context: TenantContext,
        evaluation_timestamp: dt.datetime | None = None,
    ) -> DataQualityReport:
        """Calculates the weighted composite data quality score and preserves full component inspection."""
        components: list[DataQualityComponentScore] = []
        weighted_sum = 0.0
        now = evaluation_timestamp or dt.datetime.now(dt.UTC)

        for comp_name, weight in DEFAULT_WEIGHTS.items():
            comp_data = component_metrics.get(comp_name, {})
            score_val = float(comp_data.get("score", 100.0))
            # Bound between 0.0 and 100.0
            clamped_score = max(0.0, min(100.0, score_val))

            components.append(
                DataQualityComponentScore(
                    component_name=comp_name,
                    score=clamped_score,
                    weight=weight,
                    inspectable_details=comp_data.get("details", {}),
                )
            )
            weighted_sum += clamped_score * weight

        headline = round(weighted_sum, 1)

        # Determine rating band
        if headline >= 90.0:
            rating = DataQualityRating.EXCELLENT
        elif headline >= 75.0:
            rating = DataQualityRating.GOOD
        elif headline >= 60.0:
            rating = DataQualityRating.NEEDS_ATTENTION
        else:
            rating = DataQualityRating.CRITICAL

        # Append to historical trend
        trend_entry = {
            "timestamp": now.isoformat(),
            "headline_score": headline,
            "rating": rating.value,
        }
        self._history.setdefault(tenant_context.tenant_id, []).append(trend_entry)

        report = DataQualityReport(
            headline_score=headline,
            rating=rating,
            components=components,
            evaluated_at=now,
            historical_trend=list(self._history[tenant_context.tenant_id]),
        )

        logger.info(
            "Computed Data Quality Score for tenant '%s': %0.1f%% [%s] across %d components.",
            tenant_context.tenant_id,
            headline,
            rating.value,
            len(components),
        )
        return report

    def get_score_history(self, tenant_id: str) -> list[dict[str, Any]]:
        """Retrieves historical score trajectory for trending analysis."""
        return list(self._history.get(tenant_id, []))
