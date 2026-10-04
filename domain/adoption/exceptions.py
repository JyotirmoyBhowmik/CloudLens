"""Adoption Analytics & Platform Value Exceptions (Prompt 61 / BBP Section 43).

Enforces:
- Rule 2.1 & 2.2: Specific, custom domain exceptions for adoption and value tracking.
- Strict privacy guard: Individual surveillance and user profiling are prohibited.
"""

from __future__ import annotations


class AdoptionAnalyticsException(Exception):
    """Base domain exception for adoption analytics and value measurement."""


class IndividualSurveillanceForbiddenException(AdoptionAnalyticsException):
    """Raised when an operation attempts to record or query usage by individual user identity."""


class MissingBillingEvidenceException(AdoptionAnalyticsException):
    """Raised when realised savings are claimed without verifiable backing billing telemetry."""


class InvalidFunnelProgressionException(AdoptionAnalyticsException):
    """Raised when an onboarding funnel transition violates logical prerequisite order."""


class ReviewPackGenerationException(AdoptionAnalyticsException):
    """Raised when quarterly review pack generation encounters fatal rendering failure."""
