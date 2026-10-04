"""Domain Exceptions for Commitment Renewal and Coverage Management (Prompt 58)."""

from __future__ import annotations

from domain.models.exceptions import DomainModelException


class CommitmentException(DomainModelException):
    """Base exception for commitment renewal domain errors."""

    def __init__(self, message: str, error_code: str = "COMMITMENT_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class CommitmentNotFoundException(CommitmentException):
    def __init__(self, commitment_id: str) -> None:
        super().__init__(
            f"Commitment '{commitment_id}' was not found.",
            error_code="COMMITMENT_NOT_FOUND",
        )


class DecisionWindowExpiredException(CommitmentException):
    def __init__(self, commitment_id: str) -> None:
        super().__init__(
            f"Renewal decision window for commitment '{commitment_id}' has already expired.",
            error_code="DECISION_WINDOW_EXPIRED",
        )


class MissingSupportingEvidenceException(CommitmentException):
    def __init__(self, commitment_id: str) -> None:
        super().__init__(
            f"Cannot issue bare recommendation for commitment '{commitment_id}' without supporting evidence.",
            error_code="MISSING_SUPPORTING_EVIDENCE",
        )
