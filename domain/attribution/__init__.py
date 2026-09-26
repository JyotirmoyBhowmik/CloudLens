"""Domain Attribution Module: Tags, Ownership Resolution, Allocation & Curated Field Protection."""

from domain.attribution.aggregation import (
    AggregationSummary,
    AllocationAggregationService,
    CostBucket,
)
from domain.attribution.allocation import AllocationRuleEngine
from domain.attribution.curated import CuratedFieldProtectionService
from domain.attribution.models import (
    AllocatedCostRow,
    AllocationRule,
    AllocationRuleType,
    AllocationSplitTarget,
    AllocationSplitType,
    CuratedField,
    CuratedFieldRecord,
    OwnershipResolutionResult,
    OwnershipResolutionRule,
)
from domain.attribution.ownership import OwnershipResolutionService

__all__ = [
    "AllocationAggregationService",
    "AggregationSummary",
    "CostBucket",
    "AllocationRuleEngine",
    "CuratedFieldProtectionService",
    "AllocatedCostRow",
    "AllocationRule",
    "AllocationRuleType",
    "AllocationSplitTarget",
    "AllocationSplitType",
    "CuratedField",
    "CuratedFieldRecord",
    "OwnershipResolutionResult",
    "OwnershipResolutionRule",
    "OwnershipResolutionService",
]
