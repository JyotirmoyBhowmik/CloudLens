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
from domain.models.enums import ProviderType
from domain.tenant.context import TenantContext


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

    def test_coverage_and_utilization_over_under_commitment_diagnosis(
        self, service: CommitmentService, tenant_context: TenantContext
    ) -> None:
        """Over-commitment and under-commitment are distinguished, not merged into a single coverage number."""
        now = dt.datetime.now(dt.timezone.utc)

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
        now = dt.datetime.now(dt.timezone.utc)

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
        now = dt.datetime.now(dt.timezone.utc)
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
        now = dt.datetime.now(dt.timezone.utc)
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
        now = dt.datetime.now(dt.timezone.utc)
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
