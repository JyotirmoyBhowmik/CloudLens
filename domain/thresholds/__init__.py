"""Threshold Engine Domain Package (Prompt 27).

Provides:
- Six states (Normal, Warning, High, Critical, Informational, Unknown/No data).
- Ten threshold bases.
- Contiguous non-overlapping band definitions and validation.
- Five-tier precedence resolution with explicit source disclosure.
- Complete anti-flapping (dwell time, asymmetric hysteresis, cool-down, storm grouping, data quality gate).
- Overrides mechanism (temporary with mandatory reason & auto-expiry; administrative).
- Historical series simulation (Phase 2 capability behind feature flag).
"""

from __future__ import annotations

from domain.thresholds.defaults import (
    create_configurable_budget_bands,
    create_tenant_default_budget_rule,
)
from domain.thresholds.evaluator import AntiFlappingEntityState, ThresholdEvaluator
from domain.thresholds.models import (
    AntiFlappingConfig,
    StormGroupEvent,
    ThresholdBandDefinition,
    ThresholdBasis,
    ThresholdEvaluateRequest,
    ThresholdEvaluationResult,
    ThresholdOverride,
    ThresholdOverrideCreateRequest,
    ThresholdRule,
    ThresholdRuleCreateRequest,
    ThresholdSourceType,
    ThresholdState,
    validate_contiguous_non_overlapping_bands,
)
from domain.thresholds.precedence import PrecedenceResolver, ResolvedThreshold
from domain.thresholds.preview import (
    ENABLE_THRESHOLD_PREVIEW,
    HistoricalDataPoint,
    SimulationStepResult,
    ThresholdPreviewSimulationResult,
    simulate_threshold_rule,
)
from domain.thresholds.repository import (
    ThresholdRepository,
    get_threshold_repository,
    reset_threshold_repository,
)
from domain.thresholds.service import (
    ThresholdService,
    get_threshold_service,
    reset_threshold_service,
)

__all__ = [
    "AntiFlappingConfig",
    "AntiFlappingEntityState",
    "ENABLE_THRESHOLD_PREVIEW",
    "HistoricalDataPoint",
    "PrecedenceResolver",
    "ResolvedThreshold",
    "SimulationStepResult",
    "StormGroupEvent",
    "ThresholdBandDefinition",
    "ThresholdBasis",
    "ThresholdEvaluateRequest",
    "ThresholdEvaluationResult",
    "ThresholdEvaluator",
    "ThresholdOverride",
    "ThresholdOverrideCreateRequest",
    "ThresholdPreviewSimulationResult",
    "ThresholdRepository",
    "ThresholdRule",
    "ThresholdRuleCreateRequest",
    "ThresholdService",
    "ThresholdSourceType",
    "ThresholdState",
    "create_configurable_budget_bands",
    "create_tenant_default_budget_rule",
    "get_threshold_repository",
    "get_threshold_service",
    "reset_threshold_repository",
    "reset_threshold_service",
    "simulate_threshold_rule",
    "validate_contiguous_non_overlapping_bands",
]
