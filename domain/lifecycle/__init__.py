"""Resource Lifecycle and Decommissioning Domain (Prompt 59)."""

from domain.lifecycle.exceptions import (
    CostStopVerificationFailureException,
    DecommissioningRequestNotFoundException,
    InvalidLifecycleTransitionException,
    LifecycleException,
    ProgrammeNotFoundException,
    RetentionObligationUnsatisfiedException,
    UnacknowledgedDependencyException,
)
from domain.lifecycle.models import (
    DecommissioningProgramme,
    DecommissioningProgrammeView,
    DecommissioningRequest,
    DependencyAcknowledgement,
    LifecycleResource,
    LifecycleState,
    OrphanResidueItem,
    OrphanResourceType,
    RetentionObligation,
    StoppedResourceSurfaced,
)
from domain.lifecycle.service import LifecycleService, PERMITTED_TRANSITIONS

__all__ = [
    "CostStopVerificationFailureException",
    "DecommissioningProgramme",
    "DecommissioningProgrammeView",
    "DecommissioningRequest",
    "DecommissioningRequestNotFoundException",
    "DependencyAcknowledgement",
    "InvalidLifecycleTransitionException",
    "LifecycleException",
    "LifecycleResource",
    "LifecycleService",
    "LifecycleState",
    "OrphanResidueItem",
    "OrphanResourceType",
    "PERMITTED_TRANSITIONS",
    "ProgrammeNotFoundException",
    "RetentionObligation",
    "RetentionObligationUnsatisfiedException",
    "StoppedResourceSurfaced",
    "UnacknowledgedDependencyException",
]
