"""Domain Exceptions for Resource Lifecycle and Decommissioning (Prompt 59)."""

from __future__ import annotations

from domain.models.exceptions import DomainModelException


class LifecycleException(DomainModelException):
    """Base exception for resource lifecycle domain errors."""

    def __init__(self, message: str, error_code: str = "LIFECYCLE_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class InvalidLifecycleTransitionException(LifecycleException):
    def __init__(self, from_state: str, to_state: str, reason: str = "") -> None:
        super().__init__(
            f"Invalid lifecycle transition from '{from_state}' to '{to_state}'. {reason}".strip(),
            error_code="INVALID_LIFECYCLE_TRANSITION",
        )


class UnacknowledgedDependencyException(LifecycleException):
    def __init__(self, resource_id: str, dependent_team: str, dependency_id: str) -> None:
        super().__init__(
            f"Cannot approve decommissioning for resource '{resource_id}': cross-team dependency "
            f"'{dependency_id}' owned by team '{dependent_team}' has not been acknowledged.",
            error_code="UNACKNOWLEDGED_CROSS_TEAM_DEPENDENCY",
        )


class RetentionObligationUnsatisfiedException(LifecycleException):
    def __init__(self, resource_id: str, retention_basis: str) -> None:
        super().__init__(
            f"Resource '{resource_id}' cannot proceed to deletion: active data retention obligation "
            f"'{retention_basis}' has not been confirmed satisfied by a named compliance officer.",
            error_code="RETENTION_OBLIGATION_UNSATISFIED",
        )


class CostStopVerificationFailureException(LifecycleException):
    def __init__(self, resource_id: str, ongoing_cost: str) -> None:
        super().__init__(
            f"Cost-stop verification failure for resource '{resource_id}': resource is marked deleted "
            f"but continues to accrue billing cost of ${ongoing_cost}.",
            error_code="COST_STOP_VERIFICATION_FAILURE",
        )


class DecommissioningRequestNotFoundException(LifecycleException):
    def __init__(self, request_id: str) -> None:
        super().__init__(
            f"Decommissioning request '{request_id}' was not found.",
            error_code="DECOMMISSIONING_REQUEST_NOT_FOUND",
        )


class ProgrammeNotFoundException(LifecycleException):
    def __init__(self, programme_id: str) -> None:
        super().__init__(
            f"Decommissioning programme '{programme_id}' was not found.",
            error_code="PROGRAMME_NOT_FOUND",
        )
