"""Standard API Exceptions for Nine Platform Error Codes (Prompt 34 / BBP Section 38)."""

from __future__ import annotations

from typing import Any

from api.cloudlens_api.conventions.models import StandardErrorCode


class PublicAPIException(Exception):
    """Base exception for all contract-first Public API errors."""

    def __init__(
        self,
        status_code: int,
        error_code: StandardErrorCode,
        message: str,
        title: str | None = None,
        last_successful_ingestion_at: str | None = None,
        invalid_params: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.title = title
        self.last_successful_ingestion_at = last_successful_ingestion_at
        self.invalid_params = invalid_params


class InvalidRequestException(PublicAPIException):
    """HTTP 400 Bad Request / Schema or Parameter syntax validation failed."""

    def __init__(self, message: str, invalid_params: list[dict[str, Any]] | None = None) -> None:
        super().__init__(
            status_code=400,
            error_code=StandardErrorCode.INVALID_REQUEST,
            message=message,
            title="Invalid Request",
            invalid_params=invalid_params,
        )


class UnauthenticatedException(PublicAPIException):
    """HTTP 401 Unauthorized / Missing, malformed, or expired authentication token."""

    def __init__(
        self, message: str = "Authentication token is missing, invalid, or expired."
    ) -> None:
        super().__init__(
            status_code=401,
            error_code=StandardErrorCode.UNAUTHENTICATED,
            message=message,
            title="Unauthenticated",
        )


class ForbiddenException(PublicAPIException):
    """HTTP 403 Forbidden / Authenticated caller lacks permissions."""

    def __init__(self, message: str = "Access forbidden for caller permissions.") -> None:
        super().__init__(
            status_code=403,
            error_code=StandardErrorCode.FORBIDDEN,
            message=message,
            title="Forbidden",
        )


class NotFoundException(PublicAPIException):
    """HTTP 404 Not Found.

    NOTE (Prompt 34): Also used when resource exists outside caller's permitted scope
    to avoid leaking existence of entities.
    """

    def __init__(self, message: str = "Resource not found.") -> None:
        super().__init__(
            status_code=404,
            error_code=StandardErrorCode.NOT_FOUND,
            message=message,
            title="Not Found",
        )


class ConflictException(PublicAPIException):
    """HTTP 409 Conflict / Duplicate key or entity state conflict."""

    def __init__(self, message: str) -> None:
        super().__init__(
            status_code=409,
            error_code=StandardErrorCode.CONFLICT,
            message=message,
            title="Conflict",
        )


class PreconditionFailedException(PublicAPIException):
    """HTTP 412 Precondition Failed / If-Match ETag mismatch."""

    def __init__(self, message: str = "If-Match ETag condition evaluated to false.") -> None:
        super().__init__(
            status_code=412,
            error_code=StandardErrorCode.PRECONDITION_FAILED,
            message=message,
            title="Precondition Failed",
        )


class DataUnavailableException(PublicAPIException):
    """HTTP 503 Service Unavailable / Ingestion lag or data not yet ready."""

    def __init__(
        self,
        message: str = "Data temporarily unavailable or ingestion not completed.",
        last_successful_ingestion_at: str | None = None,
    ) -> None:
        super().__init__(
            status_code=503,
            error_code=StandardErrorCode.DATA_UNAVAILABLE,
            message=message,
            title="Data Unavailable",
            last_successful_ingestion_at=last_successful_ingestion_at,
        )


class RateLimitedException(PublicAPIException):
    """HTTP 429 Too Many Requests / Quota limit exceeded."""

    def __init__(self, message: str = "Rate limit exceeded. Please retry later.") -> None:
        super().__init__(
            status_code=429,
            error_code=StandardErrorCode.RATE_LIMITED,
            message=message,
            title="Rate Limited",
        )


class InternalErrorException(PublicAPIException):
    """HTTP 500 Internal Server Error."""

    def __init__(self, message: str = "An unexpected internal server error occurred.") -> None:
        super().__init__(
            status_code=500,
            error_code=StandardErrorCode.INTERNAL_ERROR,
            message=message,
            title="Internal Server Error",
        )
