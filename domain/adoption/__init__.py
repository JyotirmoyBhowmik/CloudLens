"""CloudLens Adoption Analytics and Platform Value Package (Prompt 61 / BBP Section 43).

Public Exports:
- AdoptionAnalyticsService, UsageTelemetryService, GovernanceMetricsService,
  PlatformValueService, DataQualityService, FeatureAdoptionService,
  OnboardingFunnelService, QuarterlyReviewPackGenerator.
- Exceptions: IndividualSurveillanceForbiddenException, MissingBillingEvidenceException,
  InvalidFunnelProgressionException, ReviewPackGenerationException.
- Models & Reports: UsageTelemetryReport, GovernanceOperationsReport, PlatformValueLedgerReport,
  DataQualityReport, FeatureAdoptionReport, OnboardingFunnelReport, QuarterlyReviewPack.
"""

from __future__ import annotations

from domain.adoption.data_quality import DataQualityService
from domain.adoption.exceptions import (
    AdoptionAnalyticsException,
    IndividualSurveillanceForbiddenException,
    InvalidFunnelProgressionException,
    MissingBillingEvidenceException,
    ReviewPackGenerationException,
)
from domain.adoption.features import FeatureAdoptionService
from domain.adoption.funnel import OnboardingFunnelService
from domain.adoption.governance_metrics import GovernanceMetricsService
from domain.adoption.models import (
    AlertGovernanceMetrics,
    DataQualityComponentScore,
    DataQualityReport,
    ExemptionBypassMetrics,
    FeatureAdoptionItem,
    FeatureAdoptionReport,
    FunnelProgressStep,
    GovernanceOperationsReport,
    GovernanceTrendPoint,
    OnboardingFunnelReport,
    OverdueAgingBreakdown,
    PlatformRunningCost,
    PlatformValueLedgerReport,
    QuarterlyReviewPack,
    RealisedSavingSourceBreakdown,
    ScopeOnboardingFunnel,
    TaskGovernanceMetrics,
    UsageAggregationRecord,
    UsageTelemetryEvent,
    UsageTelemetryReport,
)
from domain.adoption.review_pack import QuarterlyReviewPackGenerator
from domain.adoption.service import AdoptionAnalyticsService
from domain.adoption.telemetry import UsageTelemetryService
from domain.adoption.value_ledger import PlatformValueService

__all__ = [
    "AdoptionAnalyticsException",
    "AdoptionAnalyticsService",
    "AlertGovernanceMetrics",
    "DataQualityComponentScore",
    "DataQualityReport",
    "DataQualityService",
    "ExemptionBypassMetrics",
    "FeatureAdoptionItem",
    "FeatureAdoptionReport",
    "FeatureAdoptionService",
    "FunnelProgressStep",
    "GovernanceMetricsService",
    "GovernanceOperationsReport",
    "GovernanceTrendPoint",
    "IndividualSurveillanceForbiddenException",
    "InvalidFunnelProgressionException",
    "MissingBillingEvidenceException",
    "OnboardingFunnelReport",
    "OnboardingFunnelService",
    "OverdueAgingBreakdown",
    "PlatformRunningCost",
    "PlatformValueLedgerReport",
    "PlatformValueService",
    "QuarterlyReviewPack",
    "QuarterlyReviewPackGenerator",
    "RealisedSavingSourceBreakdown",
    "ReviewPackGenerationException",
    "ScopeOnboardingFunnel",
    "TaskGovernanceMetrics",
    "UsageAggregationRecord",
    "UsageTelemetryEvent",
    "UsageTelemetryReport",
    "UsageTelemetryService",
]
