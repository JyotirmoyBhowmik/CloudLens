"""Comprehensive Verification Test Suite for Adoption Analytics & Platform Value (Prompt 61 / BBP Section 43).

Covers all prompt requirements and acceptance criteria:
1. Privacy-respecting usage telemetry strictly aggregated by role and team.
   Rejects named individual surveillance attributes with IndividualSurveillanceForbiddenException.
2. Governance operation metrics: MTTA, MTTC, aging brackets (1-7d, 8-30d, 30+d), exemptions/bypasses,
   and open-versus-closed volume trend points.
3. Platform value ledger consolidating cumulative realised savings across 4 canonical levers
   (REMEDIATION_TASK, DECOMMISSIONING, SCHEDULE_ADHERENCE, COMMITMENT_OPTIMISATION) with mandatory
   billing evidence (MissingBillingEvidenceException on missing reference), presented alongside
   the platform's own running cost (BigQuery queries, connector API calls, hosting) to produce
   Net Value Delivered and ROI multiple.
4. Transparent Data Quality Score: 0-100% headline score weighted across 7 inspectable components
   with rating bands and historical trend tracking.
5. Feature adoption view: identifying active vs dormant capabilities, calculating dormancy rate,
   and providing actionable recommendations.
6. Onboarding maturity funnel: tracking 5 sequential milestones per scope and surfacing stalled scopes (>14 days).
7. Single-action quarterly platform review pack generator: producing executive summary, structured DTO,
   and steering committee markdown document.
8. End-to-end integration via the master AdoptionAnalyticsService facade.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from domain.adoption.exceptions import (
    IndividualSurveillanceForbiddenException,
    MissingBillingEvidenceException,
)
from domain.adoption.models import (
    PRIVACY_POLICY_STATEMENT,
)
from domain.adoption.service import AdoptionAnalyticsService
from domain.alerting.models import AlertEntity, AlertEvidence
from domain.models.enums import (
    AlertLifecycleStatus,
    AlertSeverity,
    AlertType,
    DataQualityRating,
    FeatureAdoptionStatus,
    FunnelStage,
    TaskCategory,
    TaskPriority,
    TaskSource,
    TaskState,
    TelemetryActionType,
    ValueSourceType,
)
from domain.remediation.models import RemediationTask, SubjectEntity
from domain.tenant.context import TenantContext

# ==============================================================================
# Test Fixtures
# ==============================================================================


@pytest.fixture
def tenant_context() -> TenantContext:
    return TenantContext(
        tenant_id="tenant-acme-corp",
        user_id="finops-lead-01",
        email="finops@acme.com",
        roles=["FINOPS_ADMIN"],
    )


@pytest.fixture
def adoption_service() -> AdoptionAnalyticsService:
    return AdoptionAnalyticsService()


# ==============================================================================
# 1. Privacy-Respecting Usage Telemetry Tests
# ==============================================================================


class TestUsageTelemetry:
    """Verifies privacy-preserving aggregate telemetry and anti-surveillance enforcement."""

    def test_record_valid_usage_telemetry_by_role_and_team(
        self, adoption_service: AdoptionAnalyticsService, tenant_context: TenantContext
    ) -> None:
        """Usage is recorded by role and team without individual tracking."""
        event = adoption_service.record_usage(
            role="FINOPS_ANALYST",
            team_id="TEAM_CORE_PLATFORM",
            screen_or_feature="budget_scenario_planner",
            action_type=TelemetryActionType.WORKFLOW_ACTION,
            result="SUCCESS",
            tenant_context=tenant_context,
        )

        assert event.event_id.startswith("ute-")
        assert event.tenant_id == "tenant-acme-corp"
        assert event.role == "FINOPS_ANALYST"
        assert event.team_id == "TEAM_CORE_PLATFORM"
        assert event.screen_or_feature == "budget_scenario_planner"
        assert event.action_type == TelemetryActionType.WORKFLOW_ACTION
        assert event.result == "SUCCESS"

    def test_rejects_individual_surveillance_attributes(
        self, adoption_service: AdoptionAnalyticsService, tenant_context: TenantContext
    ) -> None:
        """Any attempt to record individual user surveillance strictly raises IndividualSurveillanceForbiddenException."""
        forbidden_attributes = [
            {"user_id": "usr-john-doe"},
            {"user": "johndoe"},
            {"username": "jdoe42"},
            {"email": "john.doe@enterprise.com"},
            {"user_email": "john.doe@enterprise.com"},
            {"actor_id": "usr-12345"},
            {"actor_name": "John Doe"},
            {"employee_id": "EMP-98765"},
        ]

        for forbidden_kwarg in forbidden_attributes:
            with pytest.raises(IndividualSurveillanceForbiddenException) as exc_info:
                adoption_service.record_usage(
                    role="ENGINEER",
                    team_id="TEAM_CHECKOUT",
                    screen_or_feature="remediation_dashboard",
                    action_type=TelemetryActionType.SCREEN_VIEW,
                    tenant_context=tenant_context,
                    **forbidden_kwarg,
                )
            assert "Privacy Policy Violation" in str(exc_info.value)
            assert "individual surveillance" in str(exc_info.value)

    def test_usage_report_aggregates_by_role_and_team_with_privacy_notice(
        self, adoption_service: AdoptionAnalyticsService, tenant_context: TenantContext
    ) -> None:
        """Usage report aggregates by role and team and prominently displays the privacy statement."""
        # Record events for multiple roles and teams
        adoption_service.record_usage(
            role="FINOPS_ADMIN",
            team_id="TEAM_FINOPS",
            screen_or_feature="commitment_renewal_board",
            action_type=TelemetryActionType.SCREEN_VIEW,
            tenant_context=tenant_context,
        )
        adoption_service.record_usage(
            role="FINOPS_ADMIN",
            team_id="TEAM_FINOPS",
            screen_or_feature="commitment_renewal_board",
            action_type=TelemetryActionType.EXPORT_DOWNLOADED,
            tenant_context=tenant_context,
        )
        adoption_service.record_usage(
            role="DEVELOPER",
            team_id="TEAM_CHECKOUT",
            screen_or_feature="remediation_task_view",
            action_type=TelemetryActionType.SCREEN_VIEW,
            tenant_context=tenant_context,
        )

        report = adoption_service.get_usage_report("2026-Q3", tenant_context=tenant_context)

        assert report.tenant_id == "tenant-acme-corp"
        assert report.period == "2026-Q3"
        assert report.privacy_policy_notice == PRIVACY_POLICY_STATEMENT
        assert report.total_events == 3

        # Role aggregation check
        assert "FINOPS_ADMIN" in report.aggregations_by_role
        finops_records = report.aggregations_by_role["FINOPS_ADMIN"]
        assert len(finops_records) == 1
        assert finops_records[0].screen_or_feature == "commitment_renewal_board"
        assert finops_records[0].action_count == 1
        assert finops_records[0].view_count == 1
        assert finops_records[0].success_count == 2

        # Team aggregation check
        assert "TEAM_CHECKOUT" in report.aggregations_by_team
        checkout_records = report.aggregations_by_team["TEAM_CHECKOUT"]
        assert len(checkout_records) == 1
        assert checkout_records[0].screen_or_feature == "remediation_task_view"
        assert checkout_records[0].view_count == 1


# ==============================================================================
# 2. Governance Operation Metrics Tests
# ==============================================================================


class TestGovernanceMetrics:
    """Verifies operational throughput, velocity (MTTA, MTTC), and aging brackets."""

    def test_computes_governance_velocity_and_aging_brackets(
        self, adoption_service: AdoptionAnalyticsService, tenant_context: TenantContext
    ) -> None:
        """Computes alerts acknowledged/actioned, tasks closed, MTTA, MTTC, and aging."""
        now = dt.datetime.now(dt.UTC)

        # 1. Prepare Alerts
        alert_evidence = AlertEvidence(summary="High CPU anomaly detected", datapoints=[{"util": 95}])
        alert_1 = AlertEntity(
            tenant_id="tenant-acme-corp",
            alert_type=AlertType.UNEXPECTED_COST_INCREASE,
            severity=AlertSeverity.HIGH,
            title="Spike in compute spend",
            description="Investigate immediately",
            source="anomaly_engine",
            evidence=alert_evidence,
            status=AlertLifecycleStatus.RESOLVED,
            created_at=now - dt.timedelta(hours=6),
            acknowledged_at=now - dt.timedelta(hours=4),  # 2 hours MTTA
            resolved_at=now - dt.timedelta(hours=1),
        )
        alert_2 = AlertEntity(
            tenant_id="tenant-acme-corp",
            alert_type=AlertType.FORECAST_BUDGET_BREACH,
            severity=AlertSeverity.CRITICAL,
            title="Forecast breach",
            description="Budget exceeded",
            source="budget_engine",
            evidence=alert_evidence,
            status=AlertLifecycleStatus.ACKNOWLEDGED,
            created_at=now - dt.timedelta(hours=10),
            acknowledged_at=now - dt.timedelta(hours=6),  # 4 hours MTTA
        )
        alert_3 = AlertEntity(
            tenant_id="tenant-acme-corp",
            alert_type=AlertType.RESOURCE_WITHOUT_OWNER,
            severity=AlertSeverity.WARNING,
            title="Unattached disk",
            description="Delete orphaned disk",
            source="waste_engine",
            evidence=alert_evidence,
            status=AlertLifecycleStatus.ACTIVE,  # Unacknowledged
            created_at=now - dt.timedelta(hours=12),
        )

        # 2. Prepare Remediation Tasks
        subject = SubjectEntity(entity_type="disk", entity_id="vol-012345")
        task_closed = RemediationTask(
            tenant_id="tenant-acme-corp",
            source=TaskSource.ALERT,
            assignee_id="team-finops",
            title="Delete unattached volume",
            description="Remove volume to save $50/mo",
            evidence_linkage={"detail": "Attached to terminated instance"},
            subject_entity=subject,
            due_date=now + dt.timedelta(days=2),
            priority=TaskPriority.HIGH,
            category=TaskCategory.IDLE_RESOURCE,
            state=TaskState.CLOSED,
            created_at=now - dt.timedelta(hours=24),
            updated_at=now - dt.timedelta(hours=4),  # 20 hours to close
        )
        task_overdue_5d = RemediationTask(
            tenant_id="tenant-acme-corp",
            source=TaskSource.ALERT,
            assignee_id="team-finops",
            title="Rightsize EC2 instance",
            description="Downsize m5.2xlarge to m5.large",
            evidence_linkage={"detail": "CPU under 5% over 30d"},
            subject_entity=subject,
            due_date=now - dt.timedelta(days=5),  # 5 days overdue (Bracket: 1-7d)
            priority=TaskPriority.MEDIUM,
            category=TaskCategory.UNOWNED_RESOURCE,
            state=TaskState.OPEN,
            created_at=now - dt.timedelta(days=10),
        )
        task_overdue_15d = RemediationTask(
            tenant_id="tenant-acme-corp",
            source=TaskSource.ALERT,
            assignee_id="team-finops",
            title="Decommission unused RDS DB",
            description="Database inactive for 60d",
            evidence_linkage={"detail": "Zero connections"},
            subject_entity=subject,
            due_date=now - dt.timedelta(days=15),  # 15 days overdue (Bracket: 8-30d)
            priority=TaskPriority.HIGH,
            category=TaskCategory.IDLE_RESOURCE,
            state=TaskState.IN_PROGRESS,
            created_at=now - dt.timedelta(days=25),
        )
        task_overdue_45d = RemediationTask(
            tenant_id="tenant-acme-corp",
            source=TaskSource.ALERT,
            assignee_id="team-finops",
            title="Migrate legacy GP2 volumes",
            description="Migrate to GP3",
            evidence_linkage={"detail": "20% cost reduction"},
            subject_entity=subject,
            due_date=now - dt.timedelta(days=45),  # 45 days overdue (Bracket: 30+d)
            priority=TaskPriority.LOW,
            category=TaskCategory.TAG_COMPLIANCE,
            state=TaskState.OPEN,
            created_at=now - dt.timedelta(days=60),
        )

        gov_report = adoption_service.compute_governance_report(
            period="2026-Q3",
            alerts=[alert_1, alert_2, alert_3],
            tasks=[task_closed, task_overdue_5d, task_overdue_15d, task_overdue_45d],
            exemptions_count=4,
            bypasses_count=1,
            active_exemptions_count=3,
            tenant_context=tenant_context,
        )

        # Alert checks: 3 raised, 2 acknowledged, 1 actioned. MTTA = (2 + 4)/2 = 3.0h
        assert gov_report.alerts.raised_count == 3
        assert gov_report.alerts.acknowledged_count == 2
        assert gov_report.alerts.actioned_count == 1
        assert gov_report.alerts.mean_time_to_acknowledge_hours == 3.0
        assert gov_report.alerts.acknowledgement_rate == 66.7

        # Task checks: 4 created, 1 closed. MTTC = 20.0h. Closure rate = 25.0%
        assert gov_report.tasks.created_count == 4
        assert gov_report.tasks.closed_count == 1
        assert gov_report.tasks.mean_time_to_close_hours == 20.0
        assert gov_report.tasks.closure_rate == 25.0

        # Overdue Aging checks: 1 in 1-7d, 1 in 8-30d, 1 in 30+d
        assert gov_report.overdue_aging.overdue_1_to_7_days == 1
        assert gov_report.overdue_aging.overdue_8_to_30_days == 1
        assert gov_report.overdue_aging.overdue_30_plus_days == 1
        assert gov_report.overdue_aging.total_overdue == 3

        # Exemptions and bypass checks
        assert gov_report.exemptions.exemption_count == 4
        assert gov_report.exemptions.bypass_count == 1
        assert gov_report.exemptions.active_exemptions == 3


# ==============================================================================
# 3. Platform Value Ledger & Running Cost Tests
# ==============================================================================


class TestPlatformValueLedger:
    """Verifies empirical savings attribution, running cost transparency, and net ROI."""

    def test_requires_actual_billing_reference_for_realised_saving(
        self, adoption_service: AdoptionAnalyticsService, tenant_context: TenantContext
    ) -> None:
        """Hypothetical or unbacked savings claims are rejected with MissingBillingEvidenceException."""
        # Empty string
        with pytest.raises(MissingBillingEvidenceException) as exc_info:
            adoption_service.record_empirical_saving(
                source=ValueSourceType.REMEDIATION_TASK,
                amount=Decimal("1500.00"),
                billing_reference="",
                tenant_context=tenant_context,
            )
        assert "billing reference" in str(exc_info.value).lower()

        # Whitespace only
        with pytest.raises(MissingBillingEvidenceException):
            adoption_service.record_empirical_saving(
                source=ValueSourceType.DECOMMISSIONING,
                amount=Decimal("800.00"),
                billing_reference="   ",
                tenant_context=tenant_context,
            )

    def test_consolidates_multi_source_savings_and_computes_net_roi(
        self, adoption_service: AdoptionAnalyticsService, tenant_context: TenantContext
    ) -> None:
        """Consolidates savings across 4 levers, records platform running costs, and computes net value."""
        # 1. Record verified savings across all 4 levers
        adoption_service.record_empirical_saving(
            source=ValueSourceType.REMEDIATION_TASK,
            amount=Decimal("12000.00"),
            billing_reference="AWS-CUR-2026-08-LINE-49102",
            tenant_context=tenant_context,
        )
        adoption_service.record_empirical_saving(
            source=ValueSourceType.DECOMMISSIONING,
            amount=Decimal("18000.00"),
            billing_reference="AZURE-INV-2026-08-ITEM-8812",
            tenant_context=tenant_context,
        )
        adoption_service.record_empirical_saving(
            source=ValueSourceType.SCHEDULE_ADHERENCE,
            amount=Decimal("6000.00"),
            billing_reference="GCP-BILL-2026-08-SKU-1029",
            tenant_context=tenant_context,
        )
        adoption_service.record_empirical_saving(
            source=ValueSourceType.COMMITMENT_OPTIMISATION,
            amount=Decimal("24000.00"),
            billing_reference="AWS-SP-2026-08-DISCOUNT-5501",
            tenant_context=tenant_context,
        )

        # 2. Record CloudLens running costs
        # Total cost: $1,200 (BQ) + $400 (Connector APIs) + $3,400 (Hosting) = $5,000
        platform_cost = adoption_service.record_platform_cost(
            period="2026-Q3",
            bigquery_query_cost=Decimal("1200.00"),
            connector_api_cost=Decimal("400.00"),
            infrastructure_hosting_cost=Decimal("3400.00"),
            tenant_context=tenant_context,
        )
        assert platform_cost.total_platform_cost == Decimal("5000.00")

        # 3. Generate Value Ledger Report
        team_attributions = {
            "TEAM_DATA_PLATFORM": Decimal("20000.00"),
            "TEAM_COMMERCE": Decimal("25000.00"),
            "TEAM_INFRASTRUCTURE": Decimal("15000.00"),
        }

        report = adoption_service.get_value_ledger_report(
            period="2026-Q3",
            tenant_context=tenant_context,
            team_attributions=team_attributions,
        )

        # Total Realised Savings: 12k + 18k + 6k + 24k = 60,000.00
        assert report.cumulative_realised_savings == Decimal("60000.00")
        assert report.platform_running_cost.total_platform_cost == Decimal("5000.00")
        # Net Value Delivered = 60,000 - 5,000 = 55,000.00
        assert report.net_value_delivered == Decimal("55000.00")
        # ROI Multiple = 60,000 / 5,000 = 12.0x
        assert report.roi_multiple == 12.0

        # Check source breakdown
        assert report.savings_by_source[ValueSourceType.REMEDIATION_TASK.value] == Decimal("12000.00")
        assert report.savings_by_source[ValueSourceType.DECOMMISSIONING.value] == Decimal("18000.00")
        assert report.savings_by_source[ValueSourceType.SCHEDULE_ADHERENCE.value] == Decimal("6000.00")
        assert report.savings_by_source[ValueSourceType.COMMITMENT_OPTIMISATION.value] == Decimal("24000.00")

        # Check team breakdown
        assert report.savings_by_team["TEAM_COMMERCE"] == Decimal("25000.00")


# ==============================================================================
# 4. Transparent Data Quality Scoring Tests
# ==============================================================================


class TestDataQualityScoring:
    """Verifies composite headline data quality score, 7 inspectable components, and trends."""

    def test_computes_weighted_headline_score_across_seven_components(
        self, adoption_service: AdoptionAnalyticsService, tenant_context: TenantContext
    ) -> None:
        """Evaluates all 7 components and applies weights to yield headline score."""
        metrics = {
            "ownership_coverage": {"score": 92.0, "details": {"total": 1000, "owned": 920}},
            "tagging_compliance": {"score": 85.0, "details": {"total": 1000, "compliant": 850}},
            "budget_coverage": {"score": 100.0, "details": {"scopes": 50, "budgeted": 50}},
            "allocation_coverage": {"score": 88.0, "details": {"spend": 100000, "allocated": 88000}},
            "reconciliation_pass_rate": {"score": 95.0, "details": {"periods": 20, "passed": 19}},
            "connector_freshness": {"score": 90.0, "details": {"connectors": 10, "fresh": 9}},
            "catalogue_gap_rate": {"score": 80.0, "details": {"unmapped": 5, "total_skus": 25}},
        }
        # Expected Weighted Score:
        # 92*0.15 + 85*0.15 + 100*0.15 + 88*0.15 + 95*0.20 + 90*0.10 + 80*0.10
        # = 13.8 + 12.75 + 15.0 + 13.2 + 19.0 + 9.0 + 8.0 = 90.75 -> 90.8% (EXCELLENT)

        report = adoption_service.calculate_data_quality(metrics, tenant_context=tenant_context)

        assert report.headline_score == 90.8
        assert report.rating == DataQualityRating.EXCELLENT
        assert len(report.components) == 7

        comp_dict = {c.component_name: c for c in report.components}
        assert comp_dict["ownership_coverage"].score == 92.0
        assert comp_dict["ownership_coverage"].weight == 0.15
        assert comp_dict["reconciliation_pass_rate"].score == 95.0
        assert comp_dict["reconciliation_pass_rate"].weight == 0.20

        # Check historical trend tracking
        assert len(report.historical_trend) >= 1
        assert report.historical_trend[-1]["headline_score"] == 90.8
        assert report.historical_trend[-1]["rating"] == DataQualityRating.EXCELLENT.value


# ==============================================================================
# 5. Feature Adoption View Tests
# ==============================================================================


class TestFeatureAdoption:
    """Verifies active vs dormant feature detection and dormancy rate."""

    def test_identifies_active_vs_dormant_capabilities_with_recommendations(
        self, adoption_service: AdoptionAnalyticsService, tenant_context: TenantContext
    ) -> None:
        """Surfaces features that are enabled but never used as dormant with actionable suggestions."""
        flags = {
            "budget_planning": True,
            "commitment_renewal": True,
            "decommissioning_workflow": True,
            "itsm_integration": True,
            "analytical_extract": False,  # Disabled
        }
        usage = {
            "budget_planning": 45,  # Active
            "commitment_renewal": 12,  # Active
            "decommissioning_workflow": 0,  # Dormant!
            "itsm_integration": 0,  # Dormant!
        }
        teams = {
            "budget_planning": 4,
            "commitment_renewal": 2,
            "decommissioning_workflow": 0,
            "itsm_integration": 0,
        }

        report = adoption_service.evaluate_feature_adoption(
            enabled_feature_flags=flags,
            usage_by_feature=usage,
            active_teams_by_feature=teams,
            tenant_context=tenant_context,
        )

        assert len(report.active_features) >= 2
        active_keys = [f.feature_key for f in report.active_features]
        assert "budget_planning" in active_keys
        assert "commitment_renewal" in active_keys

        dormant_keys = [f.feature_key for f in report.dormant_features]
        assert "decommissioning_workflow" in dormant_keys
        assert "itsm_integration" in dormant_keys

        # Dormant items must carry actionable recommendations
        decom_item = next(f for f in report.dormant_features if f.feature_key == "decommissioning_workflow")
        assert decom_item.status == FeatureAdoptionStatus.ENABLED_DORMANT
        assert "PROMOTE_DORMANT_FEATURE" in decom_item.recommendation

        disabled_keys = [f.feature_key for f in report.disabled_features]
        assert "analytical_extract" in disabled_keys

        # Dormancy rate must be greater than 0
        assert report.dormancy_rate > 0.0


# ==============================================================================
# 6. Onboarding Maturity Funnel Tests
# ==============================================================================


class TestOnboardingFunnel:
    """Verifies 5-milestone progression and stalled scope detection (>14 days in stage)."""

    def test_tracks_funnel_milestones_and_flags_stalled_scopes(
        self, adoption_service: AdoptionAnalyticsService, tenant_context: TenantContext
    ) -> None:
        """Scopes progressing normally are unflagged, while those stuck >14 days are flagged as stalled."""
        now = dt.datetime.now(dt.UTC)

        scope_milestones = [
            # Scope 1: Completed full funnel
            {
                "scope_id": "sub-prod-commerce",
                "scope_type": "BUSINESS_UNIT",
                "start_time": now - dt.timedelta(days=20),
                "milestones": {
                    FunnelStage.CONNECTOR_ADDED: now - dt.timedelta(days=20),
                    FunnelStage.FIRST_DATA_INGESTED: now - dt.timedelta(days=19),
                    FunnelStage.FIRST_BUDGET_SET: now - dt.timedelta(days=17),
                    FunnelStage.FIRST_ALERT_ACKNOWLEDGED: now - dt.timedelta(days=10),
                    FunnelStage.FIRST_TASK_CLOSED: now - dt.timedelta(days=2),
                },
            },
            # Scope 2: Stalled at FIRST_BUDGET_SET for 25 days (> 14 days threshold)
            {
                "scope_id": "sub-staging-analytics",
                "scope_type": "BUSINESS_UNIT",
                "start_time": now - dt.timedelta(days=35),
                "milestones": {
                    FunnelStage.CONNECTOR_ADDED: now - dt.timedelta(days=35),
                    FunnelStage.FIRST_DATA_INGESTED: now - dt.timedelta(days=33),
                    FunnelStage.FIRST_BUDGET_SET: now - dt.timedelta(days=25),
                    # Missing: FIRST_ALERT_ACKNOWLEDGED, FIRST_TASK_CLOSED
                },
            },
            # Scope 3: Newly enrolled 3 days ago at FIRST_DATA_INGESTED (Not stalled)
            {
                "scope_id": "sub-dev-sandbox",
                "scope_type": "BUSINESS_UNIT",
                "start_time": now - dt.timedelta(days=3),
                "milestones": {
                    FunnelStage.CONNECTOR_ADDED: now - dt.timedelta(days=3),
                    FunnelStage.FIRST_DATA_INGESTED: now - dt.timedelta(days=2),
                },
            },
        ]

        report = adoption_service.generate_onboarding_funnel_report(
            scope_milestones=scope_milestones,
            tenant_context=tenant_context,
        )

        assert report.total_scopes == 3
        assert report.completed_funnels == 1
        assert report.stalled_funnels == 1

        scope_map = {f.scope_id: f for f in report.funnels}

        # Completed scope check
        completed = scope_map["sub-prod-commerce"]
        assert completed.current_stage == FunnelStage.FIRST_TASK_CLOSED
        assert not completed.is_stalled

        # Stalled scope check
        stalled = scope_map["sub-staging-analytics"]
        assert stalled.current_stage == FunnelStage.FIRST_BUDGET_SET
        assert stalled.is_stalled is True
        assert stalled.stalled_stage == FunnelStage.FIRST_BUDGET_SET

        # New scope check
        new_scope = scope_map["sub-dev-sandbox"]
        assert new_scope.current_stage == FunnelStage.FIRST_DATA_INGESTED
        assert not new_scope.is_stalled


# ==============================================================================
# 7. Quarterly Platform Review Pack & End-to-End Facade Tests
# ==============================================================================


class TestQuarterlyReviewPack:
    """Verifies single-action generation of executive review pack and formatted markdown."""

    def test_single_action_generates_complete_c_suite_review_pack(
        self, adoption_service: AdoptionAnalyticsService, tenant_context: TenantContext
    ) -> None:
        """Review pack generates in one cohesive action with executive summary and markdown doc."""
        now = dt.datetime.now(dt.UTC)

        # 1. Prepare Telemetry
        adoption_service.record_usage(
            role="FINOPS_LEAD",
            team_id="TEAM_FINOPS",
            screen_or_feature="executive_dashboard",
            action_type=TelemetryActionType.SCREEN_VIEW,
            tenant_context=tenant_context,
        )
        usage_report = adoption_service.get_usage_report("2026-Q3", tenant_context=tenant_context)

        # 2. Prepare Governance
        alert_evidence = AlertEvidence(summary="High CPU anomaly detected", datapoints=[{"util": 95}])
        alert = AlertEntity(
            tenant_id="tenant-acme-corp",
            alert_type=AlertType.UNEXPECTED_COST_INCREASE,
            severity=AlertSeverity.HIGH,
            title="Spike in compute spend",
            description="Investigate",
            source="anomaly_engine",
            evidence=alert_evidence,
            status=AlertLifecycleStatus.RESOLVED,
            created_at=now - dt.timedelta(hours=4),
            acknowledged_at=now - dt.timedelta(hours=2),
            resolved_at=now - dt.timedelta(hours=1),
        )
        task = RemediationTask(
            tenant_id="tenant-acme-corp",
            source=TaskSource.ALERT,
            assignee_id="team-finops",
            title="Delete unattached disk",
            description="Waste removal",
            evidence_linkage={"detail": "Unused disk"},
            subject_entity=SubjectEntity(entity_type="disk", entity_id="vol-99"),
            due_date=now + dt.timedelta(days=1),
            priority=TaskPriority.HIGH,
            category=TaskCategory.IDLE_RESOURCE,
            state=TaskState.CLOSED,
            created_at=now - dt.timedelta(hours=12),
            updated_at=now - dt.timedelta(hours=2),
        )
        gov_report = adoption_service.compute_governance_report(
            period="2026-Q3",
            alerts=[alert],
            tasks=[task],
            tenant_context=tenant_context,
        )

        # 3. Prepare Value Ledger
        adoption_service.record_empirical_saving(
            source=ValueSourceType.REMEDIATION_TASK,
            amount=Decimal("35000.00"),
            billing_reference="AWS-CUR-2026-09-SAVING-01",
            tenant_context=tenant_context,
        )
        adoption_service.record_empirical_saving(
            source=ValueSourceType.COMMITMENT_OPTIMISATION,
            amount=Decimal("45000.00"),
            billing_reference="AWS-SP-2026-09-SAVING-02",
            tenant_context=tenant_context,
        )
        adoption_service.record_platform_cost(
            period="2026-Q3",
            bigquery_query_cost=Decimal("1500.00"),
            connector_api_cost=Decimal("500.00"),
            infrastructure_hosting_cost=Decimal("4000.00"),
            tenant_context=tenant_context,
        )
        value_report = adoption_service.get_value_ledger_report(
            period="2026-Q3",
            tenant_context=tenant_context,
            team_attributions={"TEAM_FINOPS": Decimal("80000.00")},
        )

        # 4. Prepare Data Quality
        dq_report = adoption_service.calculate_data_quality(
            component_metrics={
                "ownership_coverage": {"score": 95.0, "details": {"pct": 95}},
                "tagging_compliance": {"score": 92.0, "details": {"pct": 92}},
                "budget_coverage": {"score": 98.0, "details": {"pct": 98}},
                "allocation_coverage": {"score": 90.0, "details": {"pct": 90}},
                "reconciliation_pass_rate": {"score": 99.0, "details": {"pct": 99}},
                "connector_freshness": {"score": 95.0, "details": {"pct": 95}},
                "catalogue_gap_rate": {"score": 92.0, "details": {"pct": 92}},
            },
            tenant_context=tenant_context,
        )

        # 5. Prepare Feature Adoption
        feat_report = adoption_service.evaluate_feature_adoption(
            enabled_feature_flags={"budget_planning": True, "commitment_renewal": True},
            usage_by_feature={"budget_planning": 50, "commitment_renewal": 25},
            tenant_context=tenant_context,
        )

        # 6. Prepare Funnel Report
        funnel_report = adoption_service.generate_onboarding_funnel_report(
            scope_milestones=[
                {
                    "scope_id": "scope-bu-finance",
                    "scope_type": "BUSINESS_UNIT",
                    "milestones": {
                        FunnelStage.CONNECTOR_ADDED: now - dt.timedelta(days=10),
                        FunnelStage.FIRST_DATA_INGESTED: now - dt.timedelta(days=9),
                        FunnelStage.FIRST_BUDGET_SET: now - dt.timedelta(days=8),
                        FunnelStage.FIRST_ALERT_ACKNOWLEDGED: now - dt.timedelta(days=5),
                        FunnelStage.FIRST_TASK_CLOSED: now - dt.timedelta(days=1),
                    },
                }
            ],
            tenant_context=tenant_context,
        )

        # 7. Generate Review Pack
        pack = adoption_service.generate_quarterly_review_pack(
            quarter_label="2026-Q3",
            tenant_context=tenant_context,
            adoption_summary=usage_report,
            governance_operations=gov_report,
            value_ledger=value_report,
            data_quality=dq_report,
            feature_adoption=feat_report,
            onboarding_funnel=funnel_report,
            outstanding_governance_gaps=[
                {"finding": "3 dormant features detected", "action": "Schedule enablement webinar"}
            ],
        )

        assert pack.pack_id.startswith("pack-")
        assert pack.tenant_id == "tenant-acme-corp"
        assert pack.quarter_label == "2026-Q3"

        # Check Executive Summary
        assert "CloudLens delivered a verified cumulative net value" in pack.executive_summary
        assert "ROI" in pack.executive_summary
        assert "Data Quality" in pack.executive_summary

        # Check Formatted Markdown Document
        doc = pack.document_markdown
        assert "# CloudLens Platform Quarterly Review Pack — 2026-Q3" in doc
        assert "## 1. Executive Summary" in doc
        assert "## 2. Platform Value Case & ROI Ledger" in doc
        assert "## 3. Data Quality Score & Component Inspection" in doc
        assert "## 4. Governance Operations & Process Velocity" in doc
        assert "## 5. Usage Telemetry & Role Adoption" in doc
        assert "## 6. Feature Adoption & Dormant Capability Analysis" in doc
        assert "## 7. Onboarding Maturity Funnel" in doc
        assert "## 8. Outstanding Governance Gaps & Recommended Interventions" in doc
        assert PRIVACY_POLICY_STATEMENT in doc


# ==============================================================================
# 8. Edge Cases, Boundary Conditions, and Error Paths
# ==============================================================================


class TestAdoptionEdgeCasesAndBoundaries:
    """Verifies edge cases, division-by-zero resilience, and error handling."""

    def test_telemetry_empty_report_and_failure_rates(
        self, adoption_service: AdoptionAnalyticsService, tenant_context: TenantContext
    ) -> None:
        """Empty events list produces empty aggregations, and failure events compute correct success rate."""
        empty_report = adoption_service.get_usage_report("2026-Q4", tenant_context=tenant_context)
        assert empty_report.total_events == 0
        assert empty_report.aggregations_by_role == {}
        assert empty_report.aggregations_by_team == {}

        # Record 1 success and 1 failed action for the same role/team
        adoption_service.record_usage(
            role="DEVELOPER",
            team_id="TEAM_CORE",
            screen_or_feature="export_csv",
            action_type=TelemetryActionType.EXPORT_DOWNLOADED,
            result="SUCCESS",
            tenant_context=tenant_context,
        )
        adoption_service.record_usage(
            role="DEVELOPER",
            team_id="TEAM_CORE",
            screen_or_feature="export_csv",
            action_type=TelemetryActionType.EXPORT_DOWNLOADED,
            result="FAILED",
            tenant_context=tenant_context,
        )

        report = adoption_service.get_usage_report("2026-Q4", tenant_context=tenant_context)
        assert report.total_events == 2
        record = report.aggregations_by_role["DEVELOPER"][0]
        assert record.success_count == 1
        assert record.failure_count == 1
        assert record.success_rate == 50.0

    def test_governance_zero_metrics_and_closed_overdue_immunity(
        self, adoption_service: AdoptionAnalyticsService, tenant_context: TenantContext
    ) -> None:
        """Handles empty alerts/tasks safely and does not count closed tasks as overdue."""
        now = dt.datetime.now(dt.UTC)
        empty_gov = adoption_service.compute_governance_report(
            period="2026-Q4",
            alerts=[],
            tasks=[],
            tenant_context=tenant_context,
        )
        assert empty_gov.alerts.raised_count == 0
        assert empty_gov.alerts.mean_time_to_acknowledge_hours == 0.0
        assert empty_gov.alerts.acknowledgement_rate == 100.0
        assert empty_gov.tasks.created_count == 0
        assert empty_gov.tasks.mean_time_to_close_hours == 0.0
        assert empty_gov.tasks.closure_rate == 100.0
        assert empty_gov.overdue_aging.total_overdue == 0

        # Create a task whose due_date is in the past, but state is CLOSED or RESOLVED
        closed_past_due = RemediationTask(
            tenant_id="tenant-acme-corp",
            source=TaskSource.MANUAL,
            assignee_id="team-finops",
            title="Old closed task",
            description="Completed on time originally",
            subject_entity=SubjectEntity(entity_type="instance", entity_id="i-pastdue"),
            due_date=now - dt.timedelta(days=10),  # Past due date!
            priority=TaskPriority.LOW,
            category=TaskCategory.IDLE_RESOURCE,
            state=TaskState.CLOSED,  # But closed!
            created_at=now - dt.timedelta(days=20),
            updated_at=now - dt.timedelta(days=12),
        )

        gov_with_closed = adoption_service.compute_governance_report(
            period="2026-Q4",
            alerts=[],
            tasks=[closed_past_due],
            tenant_context=tenant_context,
        )
        assert gov_with_closed.overdue_aging.total_overdue == 0

    def test_value_ledger_invalid_amount_and_zero_cost_roi(
        self, adoption_service: AdoptionAnalyticsService, tenant_context: TenantContext
    ) -> None:
        """Validates positive amounts and handles zero platform costs gracefully."""
        # Non-positive amount raises ValueError
        with pytest.raises(ValueError) as exc_info:
            adoption_service.record_empirical_saving(
                source=ValueSourceType.REMEDIATION_TASK,
                amount=Decimal("-10.00"),
                billing_reference="REF-NEG",
                tenant_context=tenant_context,
            )
        assert "positive" in str(exc_info.value).lower()

        # Zero saving amount raises ValueError
        with pytest.raises(ValueError):
            adoption_service.record_empirical_saving(
                source=ValueSourceType.REMEDIATION_TASK,
                amount=Decimal("0.00"),
                billing_reference="REF-ZERO",
                tenant_context=tenant_context,
            )

        # Zero platform cost reports 0.0 ROI multiple instead of ZeroDivisionError
        fresh_service = AdoptionAnalyticsService()
        fresh_service.record_empirical_saving(
            source=ValueSourceType.SCHEDULE_ADHERENCE,
            amount=Decimal("5000.00"),
            billing_reference="BILL-5000",
            tenant_context=tenant_context,
        )
        fresh_service.record_platform_cost(
            period="2026-Q4",
            bigquery_query_cost=Decimal("0.00"),
            connector_api_cost=Decimal("0.00"),
            infrastructure_hosting_cost=Decimal("0.00"),
            tenant_context=tenant_context,
        )
        report = fresh_service.get_value_ledger_report("2026-Q4", tenant_context=tenant_context)
        assert report.platform_running_cost.total_platform_cost == Decimal("0.00")
        assert report.net_value_delivered == Decimal("5000.00")
        assert report.roi_multiple == 0.0

    def test_data_quality_score_clamping_and_ratings(
        self, adoption_service: AdoptionAnalyticsService, tenant_context: TenantContext
    ) -> None:
        """Verifies score clamping (0-100) and all 4 rating thresholds."""
        # Critical rating (<60%)
        critical_metrics = {comp: {"score": 40.0} for comp in [
            "ownership_coverage", "tagging_compliance", "budget_coverage",
            "allocation_coverage", "reconciliation_pass_rate", "connector_freshness", "catalogue_gap_rate"
        ]}
        crit_rep = adoption_service.calculate_data_quality(critical_metrics, tenant_context=tenant_context)
        assert crit_rep.headline_score == 40.0
        assert crit_rep.rating == DataQualityRating.CRITICAL

        # Needs attention rating (60-74.9%)
        needs_attn = {comp: {"score": 65.0} for comp in critical_metrics}
        attn_rep = adoption_service.calculate_data_quality(needs_attn, tenant_context=tenant_context)
        assert attn_rep.headline_score == 65.0
        assert attn_rep.rating == DataQualityRating.NEEDS_ATTENTION

        # Good rating (75-89.9%)
        good_metrics = {comp: {"score": 80.0} for comp in critical_metrics}
        good_rep = adoption_service.calculate_data_quality(good_metrics, tenant_context=tenant_context)
        assert good_rep.headline_score == 80.0
        assert good_rep.rating == DataQualityRating.GOOD

        # Clamping test: negative becomes 0.0, >100 becomes 100.0
        extreme_metrics = {comp: {"score": -50.0 if i % 2 == 0 else 150.0} for i, comp in enumerate(critical_metrics)}
        clamped_rep = adoption_service.calculate_data_quality(extreme_metrics, tenant_context=tenant_context)
        for comp in clamped_rep.components:
            assert 0.0 <= comp.score <= 100.0

    def test_feature_adoption_all_dormant_and_low_usage_recommendation(
        self, adoption_service: AdoptionAnalyticsService, tenant_context: TenantContext
    ) -> None:
        """100% dormancy rate when zero features have usage, and low usage recommendation trigger."""
        # All enabled, zero usage -> 100% dormancy
        rep = adoption_service.evaluate_feature_adoption(
            enabled_feature_flags={},
            usage_by_feature={},
            tenant_context=tenant_context,
        )
        assert rep.dormancy_rate == 100.0
        assert len(rep.dormant_features) > 0
        assert len(rep.active_features) == 0

        # Low usage: 3 actions (<5 actions threshold) triggers INVESTIGATE_LOW_ADOPTION
        low_rep = adoption_service.evaluate_feature_adoption(
            enabled_feature_flags={"budget_planning": True},
            usage_by_feature={"budget_planning": 3},
            tenant_context=tenant_context,
        )
        budget_item = next(f for f in low_rep.active_features if f.feature_key == "budget_planning")
        assert budget_item.status == FeatureAdoptionStatus.CONFIGURED_AND_USED
        assert budget_item.recommendation == "INVESTIGATE_LOW_ADOPTION"

    def test_review_pack_without_gaps_omits_section_8(
        self, adoption_service: AdoptionAnalyticsService, tenant_context: TenantContext
    ) -> None:
        """When no governance gaps exist, Section 8 is omitted cleanly."""
        usage_rep = adoption_service.get_usage_report("2026-Q4", tenant_context=tenant_context)
        gov_rep = adoption_service.compute_governance_report("2026-Q4", [], [], tenant_context=tenant_context)
        val_rep = adoption_service.get_value_ledger_report("2026-Q4", tenant_context=tenant_context)
        dq_rep = adoption_service.calculate_data_quality({}, tenant_context=tenant_context)
        feat_rep = adoption_service.evaluate_feature_adoption({}, {}, tenant_context=tenant_context)
        funnel_rep = adoption_service.generate_onboarding_funnel_report([], tenant_context=tenant_context)

        pack = adoption_service.generate_quarterly_review_pack(
            quarter_label="2026-Q4",
            tenant_context=tenant_context,
            adoption_summary=usage_rep,
            governance_operations=gov_rep,
            value_ledger=val_rep,
            data_quality=dq_rep,
            feature_adoption=feat_rep,
            onboarding_funnel=funnel_rep,
            outstanding_governance_gaps=None,
        )

        assert "## 7. Onboarding Maturity Funnel" in pack.document_markdown
        assert "## 8. Outstanding Governance Gaps" not in pack.document_markdown

