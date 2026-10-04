"""Domain Exceptions for Budget Planning & Scenario Modelling (Prompt 57)."""

from __future__ import annotations

from domain.models.exceptions import DomainModelException


class PlanningException(DomainModelException):
    """Base exception for planning domain errors."""

    def __init__(self, message: str, error_code: str = "PLANNING_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class PlanningCycleNotFoundException(PlanningException):
    def __init__(self, cycle_id: str) -> None:
        super().__init__(
            f"Planning cycle '{cycle_id}' was not found.",
            error_code="PLANNING_CYCLE_NOT_FOUND",
        )


class PlanningWindowClosedException(PlanningException):
    def __init__(self, cycle_id: str, window_name: str) -> None:
        super().__init__(
            f"Planning window '{window_name}' for cycle '{cycle_id}' is closed.",
            error_code="PLANNING_WINDOW_CLOSED",
        )


class ApprovedPlanImmutableException(PlanningException):
    def __init__(self, submission_id: str) -> None:
        super().__init__(
            f"Submission '{submission_id}' is approved and strictly immutable.",
            error_code="APPROVED_PLAN_IMMUTABLE",
        )


class SubmissionNotFoundException(PlanningException):
    def __init__(self, submission_id: str) -> None:
        super().__init__(
            f"Bottom-up submission '{submission_id}' was not found.",
            error_code="SUBMISSION_NOT_FOUND",
        )


class ScenarioNotFoundException(PlanningException):
    def __init__(self, scenario_id: str) -> None:
        super().__init__(
            f"What-if scenario '{scenario_id}' was not found.",
            error_code="SCENARIO_NOT_FOUND",
        )


class TargetNotFoundException(PlanningException):
    def __init__(self, cycle_id: str, scope_id: str) -> None:
        super().__init__(
            f"Top-down target for scope '{scope_id}' in cycle '{cycle_id}' was not found.",
            error_code="TARGET_NOT_FOUND",
        )
