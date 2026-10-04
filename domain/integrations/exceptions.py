"""Integration Hub Domain Exceptions (Prompt 60 / BBP Section 13.5).

Enforces:
- Rule 2.1 & 2.2: Specific, custom domain exceptions for all integration failure modes.
- Failure isolation and honest error reporting without masking root causes.
"""

from __future__ import annotations


class IntegrationException(Exception):
    """Base domain exception for all integration hub operations."""


class UndeclaredIntegrationCapabilityException(IntegrationException):
    """Raised when an operation attempts to invoke an undeclared adapter capability."""


class AuthoritativeFieldOverwriteBlockedException(IntegrationException):
    """Raised when CloudLens attempts to overwrite a field where an external system has declared authority."""


class IntegrationDeliveryException(IntegrationException):
    """Raised when event delivery fails after exhausting all configured retry attempts."""


class UnrecognizedEventException(IntegrationException):
    """Raised when an unrecognized or unsupported outbound event is passed for dispatch."""


class LeaverDetectionException(IntegrationException):
    """Raised when directory scanning or leaver gap resolution fails."""


class IntegrationCircuitOpenException(IntegrationException):
    """Raised when an adapter's circuit breaker is in OPEN state, rejecting calls to prevent cascading failure."""


class IntegrationRateLimitExceededException(IntegrationException):
    """Raised when outbound requests exceed the adapter's configured rate limit."""


class ConflictResolutionException(IntegrationException):
    """Raised when resolving a CMDB/Finance authority conflict encounters invalid state."""


class InvalidChatSignatureException(IntegrationException):
    """Raised when an interactive chat action contains an invalid signature or verification token."""
