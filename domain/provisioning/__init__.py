"""Cost-Aware Provisioning Gate Domain Package (Prompt 55).

Enforces:
- Saved estimate object with 4 computed values, full derivation, pricing source, and validity window.
- Provisioning request as a Prompt 50 workflow request type (never a separate approval mechanism).
- Multi-dimensional budget impact computation (remaining budget, consumption %, projected utilisation, forecast effect).
- Master-data gate triggers per scope, environment, and value band, defaulting to NOTIFY_ONLY (opt-in control).
- Quota headroom pre-checks (Prompt 54) and dependency/shared-service chain cost pre-checks (Prompt 33).
- Approval authority routing via AM-12 master data (never named individuals in code).
- Reconciliation loop comparing actuals to approved estimates over the first 3 billing periods with accuracy reporting.
- Unapproved-deployment detection with governance exception, assigned remediation task, and prominent advisory notice.
- Recorded emergency bypass path with post-hoc justification.
- Scenario comparison view evaluating alternative configurations side by side.
"""

from __future__ import annotations

from domain.provisioning.authority import ApprovalAuthorityMaster
from domain.provisioning.budget_impact import BudgetImpactEngine
from domain.provisioning.models import (
    ADVISORY_GATE_NOTICE,
    AccuracyReport,
    ApprovalAuthorityRule,
    BudgetImpactAssessment,
    BudgetImpactTier,
    BypassRecord,
    DependencyComponentCost,
    DependencyPreCheckResult,
    EstimateAccuracyClassification,
    EstimateVsActualTracking,
    GateTriggerAction,
    GateTriggerRule,
    ProvisioningRequest,
    ProvisioningRequestStatus,
    QuotaPreCheckResult,
    ResourcePeriodActual,
    SavedEstimate,
    ScenarioComparisonView,
    ScenarioOption,
    UnapprovedDeploymentFinding,
)
from domain.provisioning.prechecks import DependencyPreCheckEngine, QuotaPreCheckEngine
from domain.provisioning.reconciliation import ProvisioningReconciliationEngine
from domain.provisioning.repository import (
    ProvisioningRepository,
    get_provisioning_repository,
    reset_provisioning_repository,
)
from domain.provisioning.service import (
    ProvisioningGateService,
    get_provisioning_gate_service,
    reset_provisioning_gate_service,
)
from domain.provisioning.triggers import GateTriggerEngine
from domain.provisioning.unapproved import UnapprovedDeploymentDetector

__all__ = [
    "ADVISORY_GATE_NOTICE",
    "AccuracyReport",
    "ApprovalAuthorityMaster",
    "ApprovalAuthorityRule",
    "BudgetImpactAssessment",
    "BudgetImpactEngine",
    "BudgetImpactTier",
    "BypassRecord",
    "DependencyComponentCost",
    "DependencyPreCheckEngine",
    "DependencyPreCheckResult",
    "EstimateAccuracyClassification",
    "EstimateVsActualTracking",
    "GateTriggerAction",
    "GateTriggerEngine",
    "GateTriggerRule",
    "ProvisioningGateService",
    "ProvisioningReconciliationEngine",
    "ProvisioningRepository",
    "ProvisioningRequest",
    "ProvisioningRequestStatus",
    "QuotaPreCheckEngine",
    "QuotaPreCheckResult",
    "ResourcePeriodActual",
    "SavedEstimate",
    "ScenarioComparisonView",
    "ScenarioOption",
    "UnapprovedDeploymentDetector",
    "UnapprovedDeploymentFinding",
    "get_provisioning_gate_service",
    "get_provisioning_repository",
    "reset_provisioning_gate_service",
    "reset_provisioning_repository",
]
