"""Test Suite for Commitment Renewal and Coverage Management (Prompt 58).

Tests:
- Commitment coverage and utilisation analysis with clear OVER vs UNDER commitment distinction.
- Renewal pipeline driven by expiry dates and lead time, ranked by value at risk.
- Inspectable renewal recommendations supported by trends, workload forecasts, and what-if options.
- What-if comparison against forecast workload including the do-nothing option.
- Decision record creation and workflow recording.
- Post-expiry check quantifying actual on-demand rate increases.
- Cross-provider portfolio view.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from domain.commitments.models import (
    CommitmentAssessment,
    CommitmentType,
    RenewalAction,
)
from domain.commitments.service import CommitmentService
from domain.models.enums import ProviderType, TaskPriority, WorkflowState
from domain.remediation.service import RemediationService
from domain.tenant.context import TenantContext
from domain.workflows.service import WorkflowService


class TestCommitmentRenewalSuite:
    """Rigorous verification of Prompt 58 commitment renewal and coverage management."""

    @pytest.fixture
    def tenant_context(self) -> TenantContext:
        return TenantContext(
            tenant_id="tenant-commitments-corp",
            user_id="procurement-lead@acme.corp",
            roles={"PROCUREMENT", "FINOPS_ADMIN"},
        )

    @pytest.fixture
    def service(self) -> CommitmentService:
        return CommitmentService()

    @pytest.fixture
    def remediation_service(self) -> RemediationService:
        return RemediationService()

    @pytest.fixture
    def workflow_service(self) -> WorkflowService:
        return WorkflowService()

    def test_coverage_and_utilization_over_under_commitment_diagnosis(
        self, service: CommitmentService, tenant_context: TenantContext
    ) -> None:
        """Over-commitment and under-commitment are distinguished, not merged into a single coverage number."""
        now = dt.datetime.now(dt.UTC)

        # Commitment 1: Over-committed (High coverage 90%, but low utilization 60%) -> Waste
        comm_over = service.register_commitment(
            tenant_context=tenant_context,
            commitment_id="comm-aws-sp-over",
            provider=ProviderType.AWS,
            account_id="111222333444",
            commitment_type=CommitmentType.SAVINGS_PLAN,
            service_category="COMPUTE",
            start_date=now - dt.timedelta(days=300),
            expiry_date=now + dt.timedelta(days=30),
            hourly_committed_rate=Decimal("50.00"),
            annual_committed_cost=Decimal("438000.00"),
            owner_id="procurement-lead",
            scope_id="BU_RETAIL",
        )
        analysis_over = service.analyze_coverage_and_utilization(
            commitment_id=comm_over.commitment_id,
            eligible_usage_cost=Decimal("400000.00"),
            covered_usage_cost=Decimal("360000.00"),  # 90% coverage
            commitment_cost=Decimal("438000.00"),
            actual_consumed_cost=Decimal("262800.00"), # 60% utilization
            list_price_cost=Decimal("480000.00"),
        )
        assert analysis_over.assessment == CommitmentAssessment.OVER_COMMITMENT
        assert analysis_over.coverage_ratio == Decimal("0.9000")
        assert analysis_over.utilization_ratio == Decimal("0.6000")

        # Commitment 2: Under-committed (High utilization 98%, but poor coverage 45%) -> Missed savings
        comm_under = service.register_commitment(
            tenant_context=tenant_context,
            commitment_id="comm-gcp-cud-under",
            provider=ProviderType.GCP,
            account_id="gcp-prod-proj",
            commitment_type=CommitmentType.COMMITTED_USE_DISCOUNT,
            service_category="COMPUTE",
            start_date=now - dt.timedelta(days=320),
            expiry_date=now + dt.timedelta(days=40),
            hourly_committed_rate=Decimal("20.00"),
            annual_committed_cost=Decimal("175200.00"),
            owner_id="procurement-lead",
            scope_id="BU_WEALTH",
        )
        analysis_under = service.analyze_coverage_and_utilization(
            commitment_id=comm_under.commitment_id,
            eligible_usage_cost=Decimal("380000.00"),
            covered_usage_cost=Decimal("171000.00"),  # 45% coverage
            commitment_cost=Decimal("175200.00"),
            actual_consumed_cost=Decimal("173448.00"), # 99% utilization
            list_price_cost=Decimal("240000.00"),
        )
        assert analysis_under.assessment == CommitmentAssessment.UNDER_COMMITMENT
        assert analysis_under.coverage_ratio == Decimal("0.4500")
        assert analysis_under.utilization_ratio >= Decimal("0.9800")

    def test_lead_time_driven_renewal_pipeline_ranked_by_value_at_risk(
        self, service: CommitmentService, tenant_context: TenantContext
    ) -> None:
        """Commitments entering decision window appear ranked strictly by value at risk."""
        now = dt.datetime.now(dt.UTC)

        # High value at risk ($150,000 exposure), expiring in 25 days
        c1 = service.register_commitment(
            tenant_context=tenant_context,
            commitment_id="comm-high-risk",
            provider=ProviderType.AWS,
            account_id="111222333444",
            commitment_type=CommitmentType.SAVINGS_PLAN,
            service_category="COMPUTE",
            start_date=now - dt.timedelta(days=330),
            expiry_date=now + dt.timedelta(days=25),
            hourly_committed_rate=Decimal("40.00"),
            annual_committed_cost=Decimal("350000.00"),
            owner_id="procurement-lead",
            scope_id="BU_RETAIL",
        )
        service.analyze_coverage_and_utilization(
            commitment_id=c1.commitment_id,
            eligible_usage_cost=Decimal("500000.00"),
            covered_usage_cost=Decimal("350000.00"),
            commitment_cost=Decimal("350000.00"),
            actual_consumed_cost=Decimal("340000.00"),
            list_price_cost=Decimal("500000.00"), # Value at risk = 500k - 350k = 150k
        )

        # Medium value at risk ($30,000 exposure), expiring in 15 days
        c2 = service.register_commitment(
            tenant_context=tenant_context,
            commitment_id="comm-med-risk",
            provider=ProviderType.AZURE,
            account_id="sub-azure-123",
            commitment_type=CommitmentType.RESERVED_INSTANCE,
            service_category="DATABASE",
            start_date=now - dt.timedelta(days=340),
            expiry_date=now + dt.timedelta(days=15),
            hourly_committed_rate=Decimal("10.00"),
            annual_committed_cost=Decimal("87600.00"),
            owner_id="procurement-lead",
            scope_id="BU_WEALTH",
        )
        service.analyze_coverage_and_utilization(
            commitment_id=c2.commitment_id,
            eligible_usage_cost=Decimal("120000.00"),
            covered_usage_cost=Decimal("87600.00"),
            commitment_cost=Decimal("87600.00"),
            actual_consumed_cost=Decimal("87000.00"),
            list_price_cost=Decimal("117600.00"), # Value at risk = 117.6k - 87.6k = 30k
        )

        pipeline = service.get_renewal_pipeline(
            tenant_id=tenant_context.tenant_id,
            lead_time_days=60,
            as_of=now,
        )
        assert len(pipeline) == 2
        # c1 has higher value at risk ($150k vs $30k) -> Must be Rank 1
        assert pipeline[0].commitment_id == "comm-high-risk"
        assert pipeline[0].rank == 1
        assert pipeline[0].value_at_risk == Decimal("150000.00")

        assert pipeline[1].commitment_id == "comm-med-risk"
        assert pipeline[1].rank == 2
        assert pipeline[1].value_at_risk == Decimal("30000.00")

    def test_renewal_recommendation_with_full_inspectable_reasoning_and_what_if_options(
        self, service: CommitmentService, tenant_context: TenantContext
    ) -> None:
        """Recommendation includes inspectable reasons, what-if comparison, and the do-nothing option."""
        now = dt.datetime.now(dt.UTC)
        comm = service.register_commitment(
            tenant_context=tenant_context,
            commitment_id="comm-rec-test",
            provider=ProviderType.AWS,
            account_id="111222333444",
            commitment_type=CommitmentType.SAVINGS_PLAN,
            service_category="COMPUTE",
            start_date=now - dt.timedelta(days=330),
            expiry_date=now + dt.timedelta(days=30),
            hourly_committed_rate=Decimal("25.00"),
            annual_committed_cost=Decimal("219000.00"),
            owner_id="procurement-lead",
            scope_id="BU_RETAIL",
        )
        service.analyze_coverage_and_utilization(
            commitment_id=comm.commitment_id,
            eligible_usage_cost=Decimal("400000.00"),
            covered_usage_cost=Decimal("219000.00"),
            commitment_cost=Decimal("219000.00"),
            actual_consumed_cost=Decimal("215000.00"),
            list_price_cost=Decimal("300000.00"),
        )

        rec = service.generate_recommendation(
            commitment_id=comm.commitment_id,
            forward_growth_pct=Decimal("0.1500"),  # 15% forward growth
            planned_decommission_pct=Decimal("0.00"),
        )

        # Verify inspectable reasoning
        assert len(rec.reasoning) >= 5
        assert any("Coverage ratio" in r for r in rec.reasoning)
        assert any("Utilisation ratio" in r for r in rec.reasoning)
        assert any("Realised saving" in r for r in rec.reasoning)

        # Verify what-if options includes DO_NOTHING
        actions = [opt.action for opt in rec.what_if_options]
        assert RenewalAction.DO_NOTHING in actions
        assert RenewalAction.RENEW_SAME in actions
        assert RenewalAction.RENEW_HIGHER in actions
        assert RenewalAction.RENEW_LOWER in actions

        do_nothing_opt = next(opt for opt in rec.what_if_options if opt.action == RenewalAction.DO_NOTHING)
        assert do_nothing_opt.projected_annual_cost > Decimal("219000.00")
        assert do_nothing_opt.projected_annual_saving == Decimal("0.00")

    def test_decision_recording_and_post_expiry_check(
        self, service: CommitmentService, tenant_context: TenantContext
    ) -> None:
        """A lapsed commitment triggers a post-expiry check quantifying the on-demand increase."""
        now = dt.datetime.now(dt.UTC)
        comm = service.register_commitment(
            tenant_context=tenant_context,
            commitment_id="comm-lapsed-check",
            provider=ProviderType.AWS,
            account_id="111222333444",
            commitment_type=CommitmentType.SAVINGS_PLAN,
            service_category="COMPUTE",
            start_date=now - dt.timedelta(days=390),
            expiry_date=now - dt.timedelta(days=15), # Lapsed 15 days ago
            hourly_committed_rate=Decimal("10.00"),
            annual_committed_cost=Decimal("87600.00"), # Monthly = 7,300.00
            owner_id="procurement-lead",
            scope_id="BU_RETAIL",
        )

        # Record decision to let lapse
        dec = service.record_renewal_decision(
            commitment_id=comm.commitment_id,
            chosen_action=RenewalAction.ALLOW_TO_LAPSE,
            approver_id="procurement-director@acme.corp",
            justification="Workload decommissioning planned for Q1",
            tenant_context=tenant_context,
        )
        assert dec.chosen_action == RenewalAction.ALLOW_TO_LAPSE

        # Post-expiry verification: in January, on-demand cost was $11,500
        # Monthly committed was $7,300. On-demand increase = $4,200
        impact = service.evaluate_post_expiry_impact(
            commitment_id=comm.commitment_id,
            on_demand_actual_cost=Decimal("11500.00"),
            evaluation_period="2027-01",
        )
        assert impact.previous_committed_cost == Decimal("7300.00")
        assert impact.on_demand_rate_cost == Decimal("11500.00")
        assert impact.on_demand_increase == Decimal("4200.00")

    def test_cross_provider_commitment_portfolio_view(
        self, service: CommitmentService, tenant_context: TenantContext
    ) -> None:
        """Cross-provider commitment portfolio aggregates AWS, Azure, GCP with metrics."""
        now = dt.datetime.now(dt.UTC)
        service.register_commitment(
            tenant_context=tenant_context,
            commitment_id="c-aws",
            provider=ProviderType.AWS,
            account_id="aws-1",
            commitment_type=CommitmentType.SAVINGS_PLAN,
            service_category="COMPUTE",
            start_date=now - dt.timedelta(days=100),
            expiry_date=now + dt.timedelta(days=265),
            hourly_committed_rate=Decimal("10.00"),
            annual_committed_cost=Decimal("87600.00"),
            owner_id="p-lead",
            scope_id="BU_RETAIL",
        )
        service.register_commitment(
            tenant_context=tenant_context,
            commitment_id="c-azure",
            provider=ProviderType.AZURE,
            account_id="az-1",
            commitment_type=CommitmentType.RESERVED_INSTANCE,
            service_category="DATABASE",
            start_date=now - dt.timedelta(days=100),
            expiry_date=now + dt.timedelta(days=265),
            hourly_committed_rate=Decimal("15.00"),
            annual_committed_cost=Decimal("131400.00"),
            owner_id="p-lead",
            scope_id="BU_WEALTH",
        )

        portfolio = service.get_portfolio_view(tenant_context.tenant_id)
        assert portfolio.total_commitments == 2
        assert portfolio.total_annual_committed_value == Decimal("219000.00")
        assert "AWS" in portfolio.provider_breakdowns
        assert "AZURE" in portfolio.provider_breakdowns

    def test_expiry_alerting_and_remediation_task_assignment(
        self,
        service: CommitmentService,
        tenant_context: TenantContext,
        remediation_service: RemediationService,
    ) -> None:
        """Approaching expiry emits an alert and creates an assigned remediation task with due date at decision deadline."""
        now = dt.datetime.now(dt.UTC)
        comm = service.register_commitment(
            tenant_context=tenant_context,
            commitment_id="comm-alert-test",
            provider=ProviderType.AWS,
            account_id="111222333444",
            commitment_type=CommitmentType.SAVINGS_PLAN,
            service_category="COMPUTE",
            start_date=now - dt.timedelta(days=340),
            expiry_date=now + dt.timedelta(days=25),  # 25 days left
            hourly_committed_rate=Decimal("30.00"),
            annual_committed_cost=Decimal("262800.00"),
            owner_id="procurement-lead@acme.corp",
            scope_id="BU_RETAIL",
        )
        service.analyze_coverage_and_utilization(
            commitment_id=comm.commitment_id,
            eligible_usage_cost=Decimal("400000.00"),
            covered_usage_cost=Decimal("262800.00"),
            commitment_cost=Decimal("262800.00"),
            actual_consumed_cost=Decimal("250000.00"),
            list_price_cost=Decimal("350000.00"),
        )

        alert = service.trigger_expiry_alerts_and_tasks(
            commitment_id=comm.commitment_id,
            lead_time_days=60,
            as_of=now,
            tenant_context=tenant_context,
            remediation_service=remediation_service,
        )

        assert alert.commitment_id == comm.commitment_id
        assert alert.days_until_expiry == 25
        assert alert.value_at_risk == Decimal("87200.00")  # 350,000 - 262,800
        assert alert.remediation_task_id is not None

        # Verify linked remediation task in RemediationService
        task = remediation_service.repository.get(
            alert.remediation_task_id, tenant_context=tenant_context
        )
        assert task is not None
        assert task.assignee_id == "procurement-lead@acme.corp"
        assert task.priority == TaskPriority.HIGH
        assert task.estimated_saving == 87200.0
        assert "Commitment Expiry Decision Required" in task.title

    def test_decision_routed_to_workflow_under_authority_rules(
        self,
        service: CommitmentService,
        tenant_context: TenantContext,
        workflow_service: WorkflowService,
    ) -> None:
        """Renewal decision requiring approval under AM-12 authority rules is routed through Prompt 50 workflow engine."""
        now = dt.datetime.now(dt.UTC)
        comm = service.register_commitment(
            tenant_context=tenant_context,
            commitment_id="comm-high-value-renewal",
            provider=ProviderType.AWS,
            account_id="111222333444",
            commitment_type=CommitmentType.SAVINGS_PLAN,
            service_category="COMPUTE",
            start_date=now - dt.timedelta(days=340),
            expiry_date=now + dt.timedelta(days=20),
            hourly_committed_rate=Decimal("50.00"),
            annual_committed_cost=Decimal("438000.00"),  # > $50,000 threshold
            owner_id="procurement-lead@acme.corp",
            scope_id="BU_RETAIL",
        )

        # Record decision with workflow routing
        decision = service.record_renewal_decision(
            commitment_id=comm.commitment_id,
            chosen_action=RenewalAction.RENEW_HIGHER,
            approver_id="procurement-director@acme.corp",
            justification="Workload growth warrants 20% commitment upsize",
            tenant_context=tenant_context,
            workflow_service=workflow_service,
            authority_threshold=Decimal("50000.00"),
        )

        assert decision.requires_approval is True
        assert decision.approval_status == "PENDING_WORKFLOW"
        assert decision.workflow_request_id is not None

        # Verify WorkflowRequest created in Prompt 50 engine
        wf_req = workflow_service.repository.get(
            decision.workflow_request_id, tenant_context=tenant_context
        )
        assert wf_req is not None
        assert wf_req.state == WorkflowState.IN_REVIEW
        assert wf_req.financial_impact == 438000.0
        assert "Commitment Renewal Decision" in wf_req.title

    def test_post_expiry_incident_raised_when_lapsed_without_decision(
        self, service: CommitmentService, tenant_context: TenantContext
    ) -> None:
        """Commitment expiring without a deliberate decision raises an operational incident upon post-expiry evaluation."""
        now = dt.datetime.now(dt.UTC)
        comm = service.register_commitment(
            tenant_context=tenant_context,
            commitment_id="comm-unintended-lapse",
            provider=ProviderType.AWS,
            account_id="111222333444",
            commitment_type=CommitmentType.SAVINGS_PLAN,
            service_category="COMPUTE",
            start_date=now - dt.timedelta(days=390),
            expiry_date=now - dt.timedelta(days=10),  # Lapsed 10 days ago
            hourly_committed_rate=Decimal("20.00"),
            annual_committed_cost=Decimal("175200.00"),  # Monthly = $14,600
            owner_id="procurement-lead@acme.corp",
            scope_id="BU_RETAIL",
        )

        # Do NOT record any renewal decision
        impact = service.evaluate_post_expiry_impact(
            commitment_id=comm.commitment_id,
            on_demand_actual_cost=Decimal("21000.00"),
            evaluation_period="2027-02",
        )

        assert impact.has_deliberate_decision is False
        assert impact.incident_raised is True
        assert "lapsed without a deliberate renewal or lapse decision recorded" in impact.incident_details
        assert impact.on_demand_increase == Decimal("6400.00")

    def test_post_expiry_incident_raised_when_renewal_missing_in_inventory(
        self, service: CommitmentService, tenant_context: TenantContext
    ) -> None:
        """When renewal decision was RENEW_SAME but replacement commitment is missing in inventory, raise incident."""
        now = dt.datetime.now(dt.UTC)
        comm = service.register_commitment(
            tenant_context=tenant_context,
            commitment_id="comm-missing-renewal",
            provider=ProviderType.GCP,
            account_id="gcp-prod-proj",
            commitment_type=CommitmentType.COMMITTED_USE_DISCOUNT,
            service_category="COMPUTE",
            start_date=now - dt.timedelta(days=380),
            expiry_date=now - dt.timedelta(days=5),
            hourly_committed_rate=Decimal("15.00"),
            annual_committed_cost=Decimal("131400.00"),  # Monthly = $10,950
            owner_id="procurement-lead@acme.corp",
            scope_id="BU_WEALTH",
        )

        # Record decision to renew
        service.record_renewal_decision(
            commitment_id=comm.commitment_id,
            chosen_action=RenewalAction.RENEW_SAME,
            approver_id="procurement-lead@acme.corp",
            justification="Baseline capacity required",
            tenant_context=tenant_context,
        )

        # Check post-expiry when replacement was NOT provisioned in cloud provider
        impact_missing = service.evaluate_post_expiry_impact(
            commitment_id=comm.commitment_id,
            on_demand_actual_cost=Decimal("16000.00"),
            evaluation_period="2027-02",
            replacement_commitment_id=None,
        )
        assert impact_missing.has_deliberate_decision is True
        assert impact_missing.incident_raised is True
        assert "no replacement commitment was found in inventory" in impact_missing.incident_details

        # Now register replacement commitment in inventory
        service.register_commitment(
            tenant_context=tenant_context,
            commitment_id="comm-gcp-replacement-1",
            provider=ProviderType.GCP,
            account_id="gcp-prod-proj",
            commitment_type=CommitmentType.COMMITTED_USE_DISCOUNT,
            service_category="COMPUTE",
            start_date=comm.expiry_date,
            expiry_date=comm.expiry_date + dt.timedelta(days=365),
            hourly_committed_rate=Decimal("15.00"),
            annual_committed_cost=Decimal("131400.00"),
            owner_id="procurement-lead@acme.corp",
            scope_id="BU_WEALTH",
        )

        # Re-evaluate with replacement commitment present
        impact_verified = service.evaluate_post_expiry_impact(
            commitment_id=comm.commitment_id,
            on_demand_actual_cost=Decimal("11000.00"),
            evaluation_period="2027-02",
            replacement_commitment_id="comm-gcp-replacement-1",
        )
        assert impact_verified.incident_raised is False
        assert "Renewal verified" in impact_verified.incident_details
