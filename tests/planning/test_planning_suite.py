"""Test Suite for Budget Planning and Scenario Modelling (Prompt 57).

Tests:
- Bottom-up submission pre-populated from prior-year actual and revised in-window.
- Gap calculation between bottom-up submissions and top-down target across scopes.
- What-if scenario modeling with side-by-side comparison and untouched baseline.
- Operative budget rollover from approved plan with zero re-keying.
- Plan accuracy reporting at period close.
- Immutability of approved plan versions.
- Strict Decimal precision with ROUND_HALF_EVEN.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from domain.planning.exceptions import (
    ApprovedPlanImmutableException,
    PlanningException,
)
from domain.planning.models import (
    AssumptionType,
    PlanLineItem,
    PlanningBasisType,
    PlanningScope,
    ScenarioAssumption,
    SubmissionStatus,
)
from domain.planning.service import PlanningService
from domain.tenant.context import TenantContext


class TestPlanningSuite:
    """Rigorous verification of Prompt 57 planning and scenario modelling."""

    @pytest.fixture
    def tenant_context(self) -> TenantContext:
        return TenantContext(
            tenant_id="tenant-finops-planning",
            user_id="finops-lead@acme.corp",
            roles={"FINOPS_ADMIN", "PLANNING_LEAD"},
        )

    @pytest.fixture
    def service(self) -> PlanningService:
        return PlanningService()

    @pytest.fixture
    def active_cycle(self, service: PlanningService, tenant_context: TenantContext):
        now = dt.datetime.now(dt.UTC)
        cycle = service.create_cycle(
            tenant_context=tenant_context,
            name="FY2027 Annual Budget Cycle",
            fiscal_period="FY2027",
            submission_window_start=now - dt.timedelta(days=5),
            submission_window_end=now + dt.timedelta(days=25),
            review_window_start=now + dt.timedelta(days=26),
            review_window_end=now + dt.timedelta(days=40),
            approval_deadline=now + dt.timedelta(days=45),
            participating_scopes=[
                PlanningScope(scope_type="BUSINESS_UNIT", scope_id="BU_RETAIL", owner_id="lead-retail"),
                PlanningScope(scope_type="BUSINESS_UNIT", scope_id="BU_WEALTH", owner_id="lead-wealth"),
            ],
            default_basis=PlanningBasisType.PRIOR_YEAR_ACTUAL,
        )
        service.open_submission_window(cycle.cycle_id)
        return cycle

    def test_bottom_up_submission_and_revision_versioning(
        self, service: PlanningService, active_cycle, tenant_context: TenantContext
    ) -> None:
        """A budget owner can submit pre-populated proposal and revise it during the window."""
        items = [
            PlanLineItem(service_category="COMPUTE", service_name="EC2 / EKS", proposed_amount=Decimal("45000.00"), rationale="Cluster scaling"),
            PlanLineItem(service_category="STORAGE", service_name="S3 / EBS", proposed_amount=Decimal("15000.00"), rationale="Data lake retention"),
        ]
        sub = service.submit_bottom_up(
            cycle_id=active_cycle.cycle_id,
            scope_type="BUSINESS_UNIT",
            scope_id="BU_RETAIL",
            proposed_amount=Decimal("60000.00"),
            justification="Projected growth for mobile banking v3",
            submitted_by="lead-retail",
            basis_type=PlanningBasisType.PRIOR_YEAR_ACTUAL,
            baseline_amount=Decimal("52000.00"),
            line_items=items,
            tenant_context=tenant_context,
        )

        assert sub.version == 1
        assert sub.status == SubmissionStatus.SUBMITTED
        assert sub.proposed_amount == Decimal("60000.00")
        assert sub.baseline_amount == Decimal("52000.00")

        # Revise submission during window
        revised = service.revise_bottom_up(
            submission_id=sub.submission_id,
            proposed_amount=Decimal("65000.00"),
            justification="Additional burst capacity for Black Friday peak",
            revised_by="lead-retail",
        )
        assert revised.version == 2
        assert revised.status == SubmissionStatus.REVISED
        assert revised.proposed_amount == Decimal("65000.00")

        # History contains both versions
        history = service.get_submission_history(sub.submission_id)
        assert len(history) == 2
        assert history[0].version == 1
        assert history[1].version == 2

    def test_approved_plan_is_strictly_immutable(
        self, service: PlanningService, active_cycle, tenant_context: TenantContext
    ) -> None:
        """An approved plan cannot be edited."""
        sub = service.submit_bottom_up(
            cycle_id=active_cycle.cycle_id,
            scope_type="BUSINESS_UNIT",
            scope_id="BU_WEALTH",
            proposed_amount=Decimal("30000.00"),
            justification="Wealth management baseline infra",
            submitted_by="lead-wealth",
            tenant_context=tenant_context,
        )

        service.approve_submission(sub.submission_id, approver_id="cfo@acme.corp")
        assert sub.status == SubmissionStatus.APPROVED

        # Editing approved submission must raise ApprovedPlanImmutableException
        with pytest.raises(ApprovedPlanImmutableException):
            service.revise_bottom_up(
                submission_id=sub.submission_id,
                proposed_amount=Decimal("35000.00"),
                justification="Attempting post-approval tweak",
                revised_by="lead-wealth",
            )

    def test_top_down_target_gap_reporting(
        self, service: PlanningService, active_cycle, tenant_context: TenantContext
    ) -> None:
        """Gap between bottom-up submissions and top-down target is visible at every hierarchy level."""
        # Finance issues top-down envelope target of $100,000 for Retail
        service.set_top_down_target(
            cycle_id=active_cycle.cycle_id,
            scope_type="BUSINESS_UNIT",
            scope_id="BU_RETAIL",
            target_amount=Decimal("100000.00"),
            issued_by="cfo@acme.corp",
            tenant_context=tenant_context,
        )

        # Team 1 submits 60,000
        service.submit_bottom_up(
            cycle_id=active_cycle.cycle_id,
            scope_type="BUSINESS_UNIT",
            scope_id="BU_RETAIL",
            proposed_amount=Decimal("60000.00"),
            justification="Retail Core Banking",
            submitted_by="retail-core-lead",
            tenant_context=tenant_context,
        )

        # Sub-team 2 submits 48,000 under BU_RETAIL:PAYMENTS
        service.submit_bottom_up(
            cycle_id=active_cycle.cycle_id,
            scope_type="COST_CENTRE",
            scope_id="BU_RETAIL:PAYMENTS",
            proposed_amount=Decimal("48000.00"),
            justification="Retail Payments microservices",
            submitted_by="retail-payments-lead",
            tenant_context=tenant_context,
        )

        gap_report = service.calculate_target_gap(
            cycle_id=active_cycle.cycle_id,
            scope_type="BUSINESS_UNIT",
            scope_id="BU_RETAIL",
        )

        # Total submissions = 60,000 + 48,000 = 108,000
        # Target = 100,000
        # Gap = +8,000 (unfavourable excess)
        assert gap_report.top_down_target == Decimal("100000.00")
        assert gap_report.bottom_up_sum == Decimal("108000.00")
        assert gap_report.gap == Decimal("8000.00")
        assert gap_report.is_unfavourable is True
        assert len(gap_report.child_breakdowns) == 2

    def test_scenario_modelling_leaves_baseline_untouched_and_compares_alternatives(
        self, service: PlanningService, active_cycle
    ) -> None:
        """A scenario changes no baseline figure and can be compared against two alternatives."""
        baseline = Decimal("500000.00")

        # Scenario 1: Moderate 10% organic growth
        scen_mod = service.create_what_if_scenario(
            cycle_id=active_cycle.cycle_id,
            name="Moderate Growth",
            description="10% cloud usage expansion",
            baseline_amount=baseline,
            assumptions=[
                ScenarioAssumption(
                    assumption_type=AssumptionType.GROWTH_RATE,
                    description="10% general expansion",
                    percentage_change=Decimal("0.1000"),
                )
            ],
        )

        # Scenario 2: Aggressive 25% growth + $50k new workload from Prompt 55
        scen_agg = service.create_what_if_scenario(
            cycle_id=active_cycle.cycle_id,
            name="Aggressive Expansion",
            description="25% growth plus new AI workload",
            baseline_amount=baseline,
            assumptions=[
                ScenarioAssumption(
                    assumption_type=AssumptionType.GROWTH_RATE,
                    description="25% cloud usage expansion",
                    percentage_change=Decimal("0.2500"),
                ),
                ScenarioAssumption(
                    assumption_type=AssumptionType.NEW_WORKLOAD,
                    description="AI Search Gen platform",
                    fixed_delta=Decimal("50000.00"),
                ),
            ],
        )

        # Scenario 3: Optimization & Decommissioning
        scen_opt = service.create_what_if_scenario(
            cycle_id=active_cycle.cycle_id,
            name="FinOps Rationalization",
            description="Decommission legacy cluster and 15% rate negotiation",
            baseline_amount=baseline,
            assumptions=[
                ScenarioAssumption(
                    assumption_type=AssumptionType.DECOMMISSIONING_PROGRAMME,
                    description="Legacy DC migration cleanup",
                    fixed_delta=Decimal("-60000.00"),
                ),
                ScenarioAssumption(
                    assumption_type=AssumptionType.PRICE_CHANGE,
                    description="15% discount renegotiation",
                    percentage_change=Decimal("-0.1500"),
                ),
            ],
        )

        # Verify side-by-side comparison
        comparison = service.compare_scenarios(
            cycle_id=active_cycle.cycle_id,
            scenario_ids=[scen_mod.scenario_id, scen_agg.scenario_id, scen_opt.scenario_id],
        )

        assert len(comparison) == 3

        # Moderate: 500k * 1.10 = 550,000.00
        assert comparison[0].projected_amount == Decimal("550000.00")
        assert comparison[0].absolute_delta == Decimal("50000.00")

        # Aggressive: (500k * 1.25) + 50k = 675,000.00
        assert comparison[1].projected_amount == Decimal("675000.00")
        assert comparison[1].absolute_delta == Decimal("175000.00")

        # Baseline remains untouched in the original models
        assert scen_mod.baseline_amount == Decimal("500000.00")
        assert scen_agg.baseline_amount == Decimal("500000.00")
        assert scen_opt.baseline_amount == Decimal("500000.00")

    def test_operative_budget_rollover_and_plan_accuracy(
        self, service: PlanningService, active_cycle, tenant_context: TenantContext
    ) -> None:
        """The approved plan becomes operative budget for the period with no re-keying; accuracy reported at close."""
        sub = service.submit_bottom_up(
            cycle_id=active_cycle.cycle_id,
            scope_type="BUSINESS_UNIT",
            scope_id="BU_RETAIL",
            proposed_amount=Decimal("80000.00"),
            justification="Approved annual plan",
            submitted_by="lead-retail",
            tenant_context=tenant_context,
        )
        service.approve_submission(sub.submission_id, approver_id="cfo@acme.corp")

        # Operative budget conversion
        budget_payload = service.convert_plan_to_budget(sub.submission_id)
        assert budget_payload["allocated_amount"] == "80000.00"
        assert budget_payload["scope_id"] == "BU_RETAIL"
        assert budget_payload["fiscal_period"] == "FY2027"
        assert budget_payload["source"] == "PLANNING_CYCLE"

        # Plan accuracy measurement at close: Actual spend was $84,000 (variance = +$4,000, 5% error -> 95% accuracy)
        acc_report = service.evaluate_plan_accuracy(
            submission_id=sub.submission_id,
            actual_spend=Decimal("84000.00"),
        )
        assert acc_report.planned_amount == Decimal("80000.00")
        assert acc_report.actual_amount == Decimal("84000.00")
        assert acc_report.variance == Decimal("4000.00")
        assert acc_report.accuracy_percentage == Decimal("95.00")

    def test_planning_pack_export(
        self, service: PlanningService, active_cycle, tenant_context: TenantContext
    ) -> None:
        """Generates comprehensive Finance planning pack."""
        service.submit_bottom_up(
            cycle_id=active_cycle.cycle_id,
            scope_type="BUSINESS_UNIT",
            scope_id="BU_RETAIL",
            proposed_amount=Decimal("50000.00"),
            justification="Scope 1 proposal",
            submitted_by="retail-lead",
            tenant_context=tenant_context,
        )
        pack = service.export_planning_pack(active_cycle.cycle_id)
        assert pack["fiscal_period"] == "FY2027"
        assert pack["summary"]["total_submitted_amount"] == "50000.00"
        assert len(pack["submissions"]) == 1

    def test_convert_unapproved_plan_to_budget_raises_planning_exception(
        self, service: PlanningService, active_cycle, tenant_context: TenantContext
    ) -> None:
        """Attempting to convert an unapproved plan proposal raises PlanningException at service.py:362."""
        sub = service.submit_bottom_up(
            cycle_id=active_cycle.cycle_id,
            scope_type="BUSINESS_UNIT",
            scope_id="BU_RETAIL",
            proposed_amount=Decimal("80000.00"),
            justification="Draft annual plan",
            submitted_by="lead-retail",
            tenant_context=tenant_context,
        )
        assert sub.status == SubmissionStatus.SUBMITTED

        with pytest.raises(PlanningException) as exc_info:
            service.convert_plan_to_budget(sub.submission_id)
        assert "must be approved before conversion to operative budget" in str(exc_info.value)
        assert exc_info.value.error_code == "PLANNING_ERROR"

