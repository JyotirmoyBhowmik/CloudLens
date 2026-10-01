"""Cost Calculation Engine and Pre-Deployment Estimation Package (Prompt 23).

Exports:
- Calculation models, four-value separation types, and derivations.
- The 12 canonical calculation rules tested in isolation.
- CostCalculationEngine for extensible calculation.
- PreDeploymentEstimator for 'What will this cost?' estimation across AWS, Azure, GCP, and OCI.
"""

from __future__ import annotations

from domain.cost.calculation.engine import (
    CostCalculationEngine,
    get_calculation_engine,
    reset_calculation_engine,
)
from domain.cost.calculation.estimator import (
    PreDeploymentEstimator,
    ServiceEstimatorRegistry,
    get_pre_deployment_estimator,
    reset_pre_deployment_estimator,
)
from domain.cost.calculation.models import (
    ActualBilledCost,
    ActualCost,
    CostCategoryType,
    CostDerivation,
    CostDriverComponent,
    CostSourceClassification,
    CostValue,
    EstimatedCost,
    EstimatedEffectiveCost,
    ForecastCost,
    ForecastCostValue,
    ListPrice,
    PreDeploymentEstimateRequest,
    PreDeploymentEstimateResult,
    ProviderListPrice,
    RuntimeScheduleType,
    TierStepDerivation,
)
from domain.cost.calculation.rules import (
    rule_1_unit_conversion,
    rule_2_currency_conversion,
    rule_3_rounding,
    rule_4_tier_calculation,
    rule_5_free_allowance,
    rule_6_minimum_charge,
    rule_7_commitment_application,
    rule_8_discount_application,
    rule_9_missing_data,
    rule_10_data_freshness,
    rule_11_runtime_schedule,
    rule_12_cost_driver_decomposition,
)

__all__ = [
    "ActualBilledCost",
    "ActualCost",
    "CostCalculationEngine",
    "CostCategoryType",
    "CostDerivation",
    "CostDriverComponent",
    "CostSourceClassification",
    "CostValue",
    "EstimatedCost",
    "EstimatedEffectiveCost",
    "ForecastCost",
    "ForecastCostValue",
    "ListPrice",
    "PreDeploymentEstimateRequest",
    "PreDeploymentEstimateResult",
    "PreDeploymentEstimator",
    "ProviderListPrice",
    "RuntimeScheduleType",
    "ServiceEstimatorRegistry",
    "TierStepDerivation",
    "get_calculation_engine",
    "get_pre_deployment_estimator",
    "reset_calculation_engine",
    "reset_pre_deployment_estimator",
    "rule_1_unit_conversion",
    "rule_2_currency_conversion",
    "rule_3_rounding",
    "rule_4_tier_calculation",
    "rule_5_free_allowance",
    "rule_6_minimum_charge",
    "rule_7_commitment_application",
    "rule_8_discount_application",
    "rule_9_missing_data",
    "rule_10_data_freshness",
    "rule_11_runtime_schedule",
    "rule_12_cost_driver_decomposition",
]
