"""Domain exceptions for Resource Detail and Cost Exploration (Prompt 39)."""

from domain.models.exceptions import DomainModelException


class ResourceDetailNotFoundException(DomainModelException):
    """Raised when a requested resource is not found or is outside tenant scope."""

    def __init__(self, resource_id: str) -> None:
        super().__init__(
            f"Resource '{resource_id}' was not found or is inaccessible.",
            error_code="RESOURCE_DETAIL_NOT_FOUND",
        )
        self.resource_id = resource_id


class FinancialDetailAccessDeniedException(DomainModelException):
    """Raised when user lacks permission to view low-level financial charge lines."""

    def __init__(
        self, message: str = "Access to itemized financial charge lines is restricted."
    ) -> None:
        super().__init__(message, error_code="FINANCIAL_DETAIL_ACCESS_DENIED")
