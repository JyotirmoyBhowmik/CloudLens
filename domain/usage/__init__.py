"""Usage Telemetry & Monitoring Domain Module (Prompt 25).

Enforces:
- Prompt 25: Fourteen canonical monitoring types (MT-01 to MT-14) + Quota Headroom (MT-15).
- Prompt 25: Cardinality discipline, coarse granularity (hourly/daily), and explicit gaps.
- Prompt 25: Labeled interpolation only.
- Prompt 25: 4-level usage expectation hierarchy with inheritance and multi-band status.
- Prompt 25: Call-volume estimator and cost-materiality filter.
- BBP Section 19 (Monitoring types, expectations, collection design).
- Requirements: USE-001 to USE-010, FR-240 to FR-246, API-031, AC-051 to AC-053.
"""

from domain.usage.collector import UsageCollector
from domain.usage.estimator import CallVolumeEstimator
from domain.usage.expectations import ExpectationEngine
from domain.usage.materiality import CostMaterialityFilter
from domain.usage.models import (
    AggregationMethod,
    CallVolumeEstimate,
    CallVolumeEstimateRequest,
    CardinalityRisk,
    CollectionGranularity,
    ExpectationEvaluationResult,
    ExpectationLevel,
    ExpectationStatus,
    MaterialityFilterConfig,
    MaterialityFilterResult,
    MonitoringType,
    MonitoringTypeDefinition,
    MonitoringTypeOverride,
    PreAggregatedUsageRecord,
    ResolvedExpectation,
    ResolvedMonitoringType,
    SpikeStatus,
    UsageExpectation,
    UsageIngestRequest,
    UsageQueryFilter,
    UsageSpikeEvaluationResult,
)
from domain.usage.registry import (
    filter_allowed_metrics,
    get_allowable_metrics,
    get_default_monitoring_type_for_resource,
    get_monitoring_type_definition,
    is_metric_allowed,
    list_monitoring_types,
)
from domain.usage.repository import UsageRepository
from domain.usage.service import (
    UsageService,
    get_usage_service,
    reset_usage_service,
)

__all__ = [
    "AggregationMethod",
    "CallVolumeEstimate",
    "CallVolumeEstimateRequest",
    "CallVolumeEstimator",
    "CardinalityRisk",
    "CollectionGranularity",
    "CostMaterialityFilter",
    "ExpectationEngine",
    "ExpectationEvaluationResult",
    "ExpectationLevel",
    "ExpectationStatus",
    "MaterialityFilterConfig",
    "MaterialityFilterResult",
    "MonitoringType",
    "MonitoringTypeDefinition",
    "MonitoringTypeOverride",
    "PreAggregatedUsageRecord",
    "ResolvedExpectation",
    "ResolvedMonitoringType",
    "SpikeStatus",
    "UsageCollector",
    "UsageExpectation",
    "UsageIngestRequest",
    "UsageQueryFilter",
    "UsageRepository",
    "UsageService",
    "UsageSpikeEvaluationResult",
    "filter_allowed_metrics",
    "get_allowable_metrics",
    "get_default_monitoring_type_for_resource",
    "get_monitoring_type_definition",
    "get_usage_service",
    "is_metric_allowed",
    "list_monitoring_types",
    "reset_usage_service",
]
