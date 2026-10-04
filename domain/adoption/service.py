"""Master Adoption Analytics & Platform Value Service Facade (Prompt 61 / BBP Section 43).

Unifies:
1. Usage telemetry by role and team with strict anti-surveillance privacy guards.
2. Governance operations metrics: MTTA, MTTC, aging, open/closed trends.
3. Platform value ledger: empirical realised savings alongside platform self-costs & net ROI.
4. Data quality scoring: composite headline number with 7 inspectable components and trending.
5. Feature adoption view: identifying active vs dormant capabilities.
6. Onboarding maturity funnel per tenant or business unit.
7. Single-action quarterly platform review pack generator for the steering committee.
"""

from __future__ import annotations

import datetime as dt
import logging
from decimal import Decimal
from typing import Any

from domain.adoption.data_quality import DataQualityService
from domain.adoption.features import FeatureAdoptionService
from domain.adoption.funnel import OnboardingFunnelService
from domain.adoption.governance_metrics import GovernanceMetricsService
from domain.adoption.models import (
    DataQualityReport,
    FeatureAdoptionReport,
    GovernanceOperationsReport,
    OnboardingFunnelReport,
    PlatformRunningCost,
    PlatformValueLedgerReport,
    QuarterlyReviewPack,
    RealisedSavingSourceBreakdown,
    UsageTelemetryEvent,
    UsageTelemetryReport,
)
from domain.adoption.review_pack import QuarterlyReviewPackGenerator
from domain.adoption.telemetry import UsageTelemetryService
from domain.adoption.value_ledger import PlatformValueService
from domain.alerting.models import AlertEntity
from domain.models.enums import TelemetryActionType, ValueSourceType
from domain.remediation.models import RemediationTask
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)


class AdoptionAnalyticsService:
    """Enterprise domain service facade for platform adoption, governance velocity, and value measurement."""

    def __init__(
        self,
        telemetry_service: UsageTelemetryService | None = None,
        governance_service: GovernanceMetricsService | None = None,
        value_service: PlatformValueService | None = None,
        data_quality_service: DataQualityService | None = None,
        feature_service: FeatureAdoptionService | None = None,
        funnel_service: OnboardingFunnelService | None = None,
        review_pack_generator: QuarterlyReviewPackGenerator | None = None,
    ) -> None:
        self.telemetry = telemetry_service or UsageTelemetryService()
        self.governance = governance_service or GovernanceMetricsService()
        self.value_ledger = value_service or PlatformValueService()
        self.data_quality = data_quality_service or DataQualityService()
        self.features = feature_service or FeatureAdoptionService()
        self.funnel = funnel_service or OnboardingFunnelService()
        self.review_pack = review_pack_generator or QuarterlyReviewPackGenerator()

    # =========================================================================
    # 1. Telemetry Facade
    # =========================================================================

    def record_usage(
        self,
        role: str,
        team_id: str,
        screen_or_feature: str,
        action_type: TelemetryActionType,
        result: str = "SUCCESS",
        *,
        tenant_context: TenantContext,
        timestamp: dt.datetime | None = None,
        **forbidden_kwargs: Any,
    ) -> UsageTelemetryEvent:
        """Records aggregate usage telemetry while strictly prohibiting individual user tracking."""
        return self.telemetry.record_usage(
            role=role,
            team_id=team_id,
            screen_or_feature=screen_or_feature,
            action_type=action_type,
            result=result,
            tenant_context=tenant_context,
            timestamp=timestamp,
            **forbidden_kwargs,
        )

    def get_usage_report(
        self,
        period: str,
        *,
        tenant_context: TenantContext,
    ) -> UsageTelemetryReport:
        """Generates an aggregated usage report by role and team with privacy disclosure."""
        return self.telemetry.generate_report(period=period, tenant_context=tenant_context)

    # =========================================================================
    # 2. Value Ledger Facade
    # =========================================================================

    def record_empirical_saving(
        self,
        source: ValueSourceType,
        amount: Decimal | float,
        billing_reference: str,
        *,
        tenant_context: TenantContext,
        currency: str = "USD",
        verified_at: dt.datetime | None = None,
    ) -> RealisedSavingSourceBreakdown:
        """Records an empirical cost saving verified against actual billing telemetry."""
        return self.value_ledger.record_empirical_saving(
            source=source,
            amount=amount,
            billing_reference=billing_reference,
            tenant_context=tenant_context,
            currency=currency,
            verified_at=verified_at,
        )

    def record_platform_cost(
        self,
        period: str,
        bigquery_query_cost: Decimal | float,
        connector_api_cost: Decimal | float,
        infrastructure_hosting_cost: Decimal | float,
        *,
        tenant_context: TenantContext,
        currency: str = "USD",
    ) -> PlatformRunningCost:
        """Records operational self-costs incurred by CloudLens during a period."""
        return self.value_ledger.record_platform_running_cost(
            period=period,
            bigquery_query_cost=bigquery_query_cost,
            connector_api_cost=connector_api_cost,
            infrastructure_hosting_cost=infrastructure_hosting_cost,
            tenant_context=tenant_context,
            currency=currency,
        )

    def get_value_ledger_report(
        self,
        period: str,
        *,
        tenant_context: TenantContext,
        team_attributions: dict[str, Decimal] | None = None,
        default_platform_cost: PlatformRunningCost | None = None,
    ) -> PlatformValueLedgerReport:
        """Produces the net platform value case (empirical savings minus platform costs)."""
        return self.value_ledger.generate_value_ledger_report(
            period=period,
            tenant_context=tenant_context,
            team_attributions=team_attributions,
            default_platform_cost=default_platform_cost,
        )

    # =========================================================================
    # 3. Governance Metrics Facade
    # =========================================================================

    def compute_governance_report(
        self,
        period: str,
        alerts: list[AlertEntity],
        tasks: list[RemediationTask],
        exemptions_count: int = 0,
        bypasses_count: int = 0,
        active_exemptions_count: int = 0,
        *,
        tenant_context: TenantContext,
    ) -> GovernanceOperationsReport:
        """Computes governance velocity, MTTA, MTTC, and aging brackets."""
        return self.governance.compute_governance_report(
            period=period,
            alerts=alerts,
            tasks=tasks,
            exemptions_count=exemptions_count,
            bypasses_count=bypasses_count,
            active_exemptions_count=active_exemptions_count,
            tenant_context=tenant_context,
        )

    # =========================================================================
    # 4. Data Quality Facade
    # =========================================================================

    def calculate_data_quality(
        self,
        component_metrics: dict[str, dict[str, Any]],
        *,
        tenant_context: TenantContext,
        evaluation_timestamp: dt.datetime | None = None,
    ) -> DataQualityReport:
        """Computes headline weighted data quality score with full component inspection."""
        return self.data_quality.calculate_data_quality(
            component_metrics=component_metrics,
            tenant_context=tenant_context,
            evaluation_timestamp=evaluation_timestamp,
        )

    # =========================================================================
    # 5. Feature Adoption Facade
    # =========================================================================

    def evaluate_feature_adoption(
        self,
        enabled_feature_flags: dict[str, bool],
        usage_by_feature: dict[str, int],
        active_teams_by_feature: dict[str, int] | None = None,
        *,
        tenant_context: TenantContext,
    ) -> FeatureAdoptionReport:
        """Identifies active vs dormant capabilities across the platform."""
        return self.features.evaluate_feature_adoption(
            enabled_feature_flags=enabled_feature_flags,
            usage_by_feature=usage_by_feature,
            active_teams_by_feature=active_teams_by_feature,
            tenant_context=tenant_context,
        )

    # =========================================================================
    # 6. Onboarding Funnel Facade
    # =========================================================================

    def generate_onboarding_funnel_report(
        self,
        scope_milestones: list[dict[str, Any]],
        *,
        tenant_context: TenantContext,
    ) -> OnboardingFunnelReport:
        """Evaluates onboarding progression and surfaces stalled scopes."""
        return self.funnel.generate_funnel_report(
            scope_milestones=scope_milestones,
            tenant_context=tenant_context,
        )

    # =========================================================================
    # 7. Quarterly Platform Review Pack Facade
    # =========================================================================

    def generate_quarterly_review_pack(
        self,
        quarter_label: str,
        *,
        tenant_context: TenantContext,
        adoption_summary: UsageTelemetryReport,
        governance_operations: GovernanceOperationsReport,
        value_ledger: PlatformValueLedgerReport,
        data_quality: DataQualityReport,
        feature_adoption: FeatureAdoptionReport,
        onboarding_funnel: OnboardingFunnelReport,
        outstanding_governance_gaps: list[dict[str, Any]] | None = None,
    ) -> QuarterlyReviewPack:
        """Generates the consolidated steering committee review pack in a single programmatic action."""
        return self.review_pack.generate_review_pack(
            quarter_label=quarter_label,
            adoption_summary=adoption_summary,
            governance_operations=governance_operations,
            value_ledger=value_ledger,
            data_quality=data_quality,
            feature_adoption=feature_adoption,
            onboarding_funnel=onboarding_funnel,
            outstanding_governance_gaps=outstanding_governance_gaps,
            tenant_context=tenant_context,
        )
