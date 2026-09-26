"""Allocation Cost Aggregation Service with Strict Unallocated Visibility (Prompt 08 Item 58).

Enforces:
1. "Make Unallocated cost visible at every aggregation level. It is never absorbed into another bucket."
2. "Do not hide unallocated cost in an 'Other' bucket."
3. "Unallocated cost appears explicitly in a test aggregation."
"""

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from domain.attribution.models import AllocatedCostRow, AllocationRuleType
from domain.rules.monetary import round_currency


class CostBucket(BaseModel):
    """Aggregated financial bucket for a specific dimension value."""

    bucket_key: str = Field(..., description="Dimension key (e.g. 'CC-1001', 'UNALLOCATED')")
    bucket_name: str = Field(..., description="Display title for the bucket")
    total_amount: Decimal = Field(..., description="Aggregated spend in this bucket")
    percentage_of_total: Decimal = Field(
        ..., description="Percentage of total estate spend (0.0 to 100.0)"
    )
    fact_count: int = Field(default=0, description="Number of cost allocation facts in bucket")
    is_unallocated: bool = Field(
        default=False,
        description="True if this bucket represents unallocated cost",
    )


class AggregationSummary(BaseModel):
    """Financial aggregation summary across an organizational dimension."""

    dimension: str = Field(..., description="Dimension aggregated on (e.g. 'cost_center', 'scope')")
    total_spend: Decimal = Field(..., description="Total aggregated spend")
    allocated_spend: Decimal = Field(..., description="Total spend successfully allocated")
    unallocated_spend: Decimal = Field(
        ..., description="Total spend unallocated (explicitly exposed)"
    )
    allocated_percentage: Decimal = Field(..., description="Percentage allocated")
    unallocated_percentage: Decimal = Field(..., description="Percentage unallocated")
    buckets: list[CostBucket] = Field(default_factory=list, description="Categorized spend buckets")


class AllocationAggregationService:
    """Aggregates allocated cost facts ensuring unallocated spend is never obscured."""

    def aggregate_by_cost_center(
        self,
        rows: list[AllocatedCostRow],
        other_threshold_percentage: Decimal | None = None,
    ) -> AggregationSummary:
        """Aggregates cost rows by cost center. Unallocated cost is always preserved as its own bucket."""
        return self._aggregate(
            rows=rows,
            dimension_name="cost_center",
            key_extractor=lambda r: r.cost_center_code,
            name_extractor=lambda k: (
                "Unallocated Cost" if k == "UNALLOCATED" else f"Cost Center {k}"
            ),
            other_threshold=other_threshold_percentage,
        )

    def aggregate_by_business_unit(
        self,
        rows: list[AllocatedCostRow],
        other_threshold_percentage: Decimal | None = None,
    ) -> AggregationSummary:
        """Aggregates cost rows by business unit."""
        return self._aggregate(
            rows=rows,
            dimension_name="business_unit",
            key_extractor=lambda r: r.business_unit_code or "UNALLOCATED",
            name_extractor=lambda k: (
                "Unallocated Cost" if k == "UNALLOCATED" else f"Business Unit {k}"
            ),
            other_threshold=other_threshold_percentage,
        )

    def aggregate_by_scope(
        self,
        rows: list[AllocatedCostRow],
        other_threshold_percentage: Decimal | None = None,
    ) -> AggregationSummary:
        """Aggregates cost rows by scope node."""
        return self._aggregate(
            rows=rows,
            dimension_name="scope",
            key_extractor=lambda r: r.scope_id,
            name_extractor=lambda k: f"Scope {k}",
            other_threshold=other_threshold_percentage,
        )

    def aggregate_by_winning_rule_type(
        self,
        rows: list[AllocatedCostRow],
    ) -> AggregationSummary:
        """Aggregates cost rows by the rule tier that allocated them."""
        return self._aggregate(
            rows=rows,
            dimension_name="winning_rule_type",
            key_extractor=lambda r: r.winning_rule_type.value,
            name_extractor=lambda k: f"Rule Tier {k}",
            other_threshold=None,
        )

    def _aggregate(
        self,
        rows: list[AllocatedCostRow],
        dimension_name: str,
        key_extractor: Any,
        name_extractor: Any,
        other_threshold: Decimal | None = None,
    ) -> AggregationSummary:
        total_spend = sum((r.allocated_amount for r in rows), Decimal("0.00"))
        total_spend = round_currency(total_spend)

        if total_spend == Decimal("0.00"):
            return AggregationSummary(
                dimension=dimension_name,
                total_spend=Decimal("0.00"),
                allocated_spend=Decimal("0.00"),
                unallocated_spend=Decimal("0.00"),
                allocated_percentage=Decimal("0.00"),
                unallocated_percentage=Decimal("0.00"),
                buckets=[],
            )

        # Collect buckets
        bucket_data: dict[str, dict[str, Any]] = {}
        unallocated_spend = Decimal("0.00")
        allocated_spend = Decimal("0.00")

        for r in rows:
            key = key_extractor(r)
            is_unalloc = (
                key == "UNALLOCATED"
                or r.winning_rule_type == AllocationRuleType.UNALLOCATED
                or r.cost_center_code == "UNALLOCATED"
            )

            if key not in bucket_data:
                bucket_data[key] = {
                    "key": key,
                    "name": name_extractor(key),
                    "amount": Decimal("0.00"),
                    "count": 0,
                    "is_unallocated": is_unalloc,
                }

            bucket_data[key]["amount"] += r.allocated_amount
            bucket_data[key]["count"] += 1

            if is_unalloc:
                unallocated_spend += r.allocated_amount
            else:
                allocated_spend += r.allocated_amount

        # Compute percentages and build buckets
        buckets: list[CostBucket] = []
        other_amount = Decimal("0.00")
        other_count = 0

        for key, data in bucket_data.items():
            amt = round_currency(data["amount"])
            pct = round_currency((amt / total_spend) * Decimal("100.0"))
            is_unalloc = data["is_unallocated"]

            # If small spend threshold is requested, rollup into "Other", BUT:
            # Rule 58: UNALLOCATED is NEVER absorbed into "Other"
            if other_threshold is not None and pct < other_threshold and not is_unalloc:
                other_amount += amt
                other_count += data["count"]
            else:
                buckets.append(
                    CostBucket(
                        bucket_key=key,
                        bucket_name=data["name"],
                        total_amount=amt,
                        percentage_of_total=pct,
                        fact_count=data["count"],
                        is_unallocated=is_unalloc,
                    )
                )

        if other_amount > Decimal("0.00"):
            other_pct = round_currency((other_amount / total_spend) * Decimal("100.0"))
            buckets.append(
                CostBucket(
                    bucket_key="OTHER",
                    bucket_name="Other (Below Threshold)",
                    total_amount=other_amount,
                    percentage_of_total=other_pct,
                    fact_count=other_count,
                    is_unallocated=False,
                )
            )

        # Sort buckets: Unallocated first or last, rest by amount descending
        buckets.sort(key=lambda b: (b.is_unallocated, b.total_amount), reverse=True)

        alloc_pct = round_currency((allocated_spend / total_spend) * Decimal("100.0"))
        unalloc_pct = round_currency((unallocated_spend / total_spend) * Decimal("100.0"))

        return AggregationSummary(
            dimension=dimension_name,
            total_spend=total_spend,
            allocated_spend=round_currency(allocated_spend),
            unallocated_spend=round_currency(unallocated_spend),
            allocated_percentage=alloc_pct,
            unallocated_percentage=unalloc_pct,
            buckets=buckets,
        )
