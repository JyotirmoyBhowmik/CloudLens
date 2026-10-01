"""Cost-Materiality Collection Filter (Prompt 25).

Enforces:
- Prompt 25: Cost-threshold filter allowing metric collection to be limited to resources above
  a configurable cost materiality, so the platform does not spend more collecting than the
  insight is worth.
- Cardinality control & provider API cost suppression.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from domain.usage.models import MaterialityFilterConfig, MaterialityFilterResult

logger = logging.getLogger(__name__)


class CostMaterialityFilter:
    """Evaluates candidate resources against spend thresholds to eliminate low-value metric collection."""

    @staticmethod
    def filter_resources(
        candidates: list[dict[str, Any]],
        config: MaterialityFilterConfig | None = None,
    ) -> MaterialityFilterResult:
        """Filters resources by 30-day spend against configured materiality threshold.

        Each candidate dict must contain:
        - 'resource_id': str
        - 'monthly_cost': Decimal | float | int (30-day billed or estimated run-rate)
        """
        cfg = config or MaterialityFilterConfig()
        threshold = cfg.min_monthly_cost_threshold

        if not cfg.enabled:
            # Filtering disabled: include all candidates
            all_ids = [str(c.get("resource_id", "")) for c in candidates if c.get("resource_id")]
            return MaterialityFilterResult(
                candidate_count=len(candidates),
                included_count=len(all_ids),
                excluded_count=0,
                included_resource_ids=all_ids,
                excluded_resource_ids=[],
                threshold_usd=threshold,
                estimated_monthly_api_calls_saved=0,
                estimated_monthly_cost_savings_usd=Decimal("0.00"),
            )

        included_ids: list[str] = []
        excluded_ids: list[str] = []

        for item in candidates:
            res_id = str(item.get("resource_id", ""))
            if not res_id:
                continue

            raw_cost = item.get("monthly_cost", Decimal("0.00"))
            monthly_cost = Decimal(str(raw_cost)) if not isinstance(raw_cost, Decimal) else raw_cost

            if monthly_cost >= threshold:
                included_ids.append(res_id)
            else:
                excluded_ids.append(res_id)

        # Estimate savings from excluded low-spend resources:
        # Assuming hourly polling of ~3 metrics per resource in 50-metric batches: ~1.5 calls/hour -> ~1,080 calls/month/res
        calls_saved = len(excluded_ids) * 1080
        cost_saved = (Decimal(str(calls_saved)) / Decimal("1000")) * Decimal("0.010")
        cost_saved = cost_saved.quantize(Decimal("0.01"))

        return MaterialityFilterResult(
            candidate_count=len(candidates),
            included_count=len(included_ids),
            excluded_count=len(excluded_ids),
            included_resource_ids=included_ids,
            excluded_resource_ids=excluded_ids,
            threshold_usd=threshold,
            estimated_monthly_api_calls_saved=calls_saved,
            estimated_monthly_cost_savings_usd=cost_saved,
        )
