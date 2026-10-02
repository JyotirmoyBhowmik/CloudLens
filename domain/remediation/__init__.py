"""Remediation and Accountability Package (Prompt 51).

Public exports for remediation domain entities, repositories, assignment resolvers,
automated verification, realised-saving ledgers, accountability reporting, and service.
"""

from __future__ import annotations

from domain.remediation.assignment import AssignmentResolver
from domain.remediation.creator import TaskCreationEngine
from domain.remediation.itsm import (
    ITSMAdapter,
    ITSMIntegrationResult,
    get_itsm_adapter,
    reset_itsm_adapter,
)
from domain.remediation.ledger import (
    RealisedSavingLedger,
    get_realised_saving_ledger,
    reset_realised_saving_ledger,
)
from domain.remediation.models import (
    AgeingBucket,
    AgeingReport,
    BulkAssignRequest,
    BulkDeferRequest,
    BulkDuplicateRequest,
    BulkReprioritiseRequest,
    RealisedSavingEntry,
    RealisedSavingReport,
    RemediationHistoryEntry,
    RemediationTask,
    SubjectEntity,
    TaskAcceptRiskRequest,
    TaskCreateRequest,
    TaskCreationRule,
    TaskDeferRequest,
    TaskResolveRequest,
    TaskTransitionRequest,
    TaskVerificationResult,
    TrendPoint,
    TrendReport,
)
from domain.remediation.repository import (
    RemediationRepository,
    get_remediation_repository,
    reset_remediation_repository,
)
from domain.remediation.service import (
    RemediationService,
    get_remediation_service,
    reset_remediation_service,
)
from domain.remediation.verifier import TaskVerifier
from domain.remediation.views import AccountabilityEngine

__all__ = [
    # Models & DTOs
    "SubjectEntity",
    "RemediationHistoryEntry",
    "RemediationTask",
    "RealisedSavingEntry",
    "RealisedSavingReport",
    "TaskCreationRule",
    "AgeingBucket",
    "AgeingReport",
    "TrendPoint",
    "TrendReport",
    "TaskCreateRequest",
    "TaskTransitionRequest",
    "TaskResolveRequest",
    "TaskDeferRequest",
    "TaskAcceptRiskRequest",
    "BulkAssignRequest",
    "BulkReprioritiseRequest",
    "BulkDeferRequest",
    "BulkDuplicateRequest",
    "TaskVerificationResult",
    # Repository
    "RemediationRepository",
    "get_remediation_repository",
    "reset_remediation_repository",
    # Logic & Engines
    "AssignmentResolver",
    "TaskCreationEngine",
    "TaskVerifier",
    "RealisedSavingLedger",
    "get_realised_saving_ledger",
    "reset_realised_saving_ledger",
    "AccountabilityEngine",
    "ITSMAdapter",
    "ITSMIntegrationResult",
    "get_itsm_adapter",
    "reset_itsm_adapter",
    # Service
    "RemediationService",
    "get_remediation_service",
    "reset_remediation_service",
]
