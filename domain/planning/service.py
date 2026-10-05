"""Budget Planning and Scenario Modelling Service (Prompt 57).

Fulfills:
- Master-data-driven planning cycle with windows and participants.
- Bottom-up submission with configurable basis (prior year, run-rate, forecast, zero-base) and justification.
- Top-down target setting with gap reporting at every level of the hierarchy.
- Versioned drafts with an immutable approved version.
- Scenario modelling with side-by-side comparison and an untouched baseline.
- Roll-up and reconciliation view.
- Plan-to-actual tracking once period opens.
- Planning pack export.
"""

from __future__ import annotations

import datetime as dt
import logging
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from domain.planning.exceptions import (
    ApprovedPlanImmutableException,
    PlanningCycleNotFoundException,
    PlanningException,
    PlanningWindowClosedException,
    ScenarioNotFoundException,
    SubmissionNotFoundException,
    TargetNotFoundException,
)
from domain.planning.models import (
    BottomUpSubmission,
    CycleStatus,
    PlanAccuracyReport,
    PlanLineItem,
    PlanningBasisType,
    PlanningCycle,
    PlanningScope,
    ScenarioAssumption,
    ScenarioEvaluationResult,
    SubmissionStatus,
    TargetGapReport,
    TopDownTarget,
    WhatIfScenario,
)
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)


class PlanningService:
    """Enterprise FinOps Budget Planning and Scenario Modelling Engine."""

    def __init__(self) -> None:
        self._cycles: dict[str, PlanningCycle] = {}
        self._submissions: dict[str, BottomUpSubmission] = {}
        self._submission_history: dict[str, list[BottomUpSubmission]] = {}
        self._targets: dict[str, TopDownTarget] = {}  # key: f"{cycle_id}:{scope_id}"
        self._scenarios: dict[str, WhatIfScenario] = {}

    # -------------------------------------------------------------------------
    # Planning Cycle Lifecycle
    # -------------------------------------------------------------------------
    def create_cycle(
        self,
        tenant_context: TenantContext,
        name: str,
        fiscal_period: str,
        submission_window_start: dt.datetime,
        submission_window_end: dt.datetime,
        review_window_start: dt.datetime,
        review_window_end: dt.datetime,
        approval_deadline: dt.datetime,
        participating_scopes: list[PlanningScope] | None = None,
        default_basis: PlanningBasisType = PlanningBasisType.PRIOR_YEAR_ACTUAL,
    ) -> PlanningCycle:
        cycle = PlanningCycle(
            tenant_id=tenant_context.tenant_id,
            name=name,
            fiscal_period=fiscal_period,
            submission_window_start=submission_window_start,
            submission_window_end=submission_window_end,
            review_window_start=review_window_start,
            review_window_end=review_window_end,
            approval_deadline=approval_deadline,
            participating_scopes=participating_scopes or [],
            status=CycleStatus.DRAFT,
            default_basis=default_basis,
        )
        self._cycles[cycle.cycle_id] = cycle
        return cycle

    def get_cycle(self, cycle_id: str) -> PlanningCycle:
        if cycle_id not in self._cycles:
            raise PlanningCycleNotFoundException(cycle_id)
        return self._cycles[cycle_id]

    def open_submission_window(self, cycle_id: str) -> PlanningCycle:
        cycle = self.get_cycle(cycle_id)
        cycle.status = CycleStatus.OPEN_SUBMISSION
        cycle.updated_at = dt.datetime.now(dt.UTC)
        return cycle

    def close_submission_window(self, cycle_id: str) -> PlanningCycle:
        cycle = self.get_cycle(cycle_id)
        cycle.status = CycleStatus.UNDER_REVIEW
        cycle.updated_at = dt.datetime.now(dt.UTC)
        return cycle

    # -------------------------------------------------------------------------
    # Bottom-up Submission with Versioning and Immutable Approved State
    # -------------------------------------------------------------------------
    def submit_bottom_up(
        self,
        cycle_id: str,
        scope_type: str,
        scope_id: str,
        proposed_amount: Decimal | float | str,
        justification: str,
        submitted_by: str,
        basis_type: PlanningBasisType = PlanningBasisType.PRIOR_YEAR_ACTUAL,
        baseline_amount: Decimal | float | str = Decimal("0.00"),
        line_items: list[PlanLineItem] | None = None,
        tenant_context: TenantContext | None = None,
    ) -> BottomUpSubmission:
        cycle = self.get_cycle(cycle_id)
        tenant_id = tenant_context.tenant_id if tenant_context else cycle.tenant_id

        # Calculate sum of line items if provided and proposed_amount is zero
        prop_dec = Decimal(str(proposed_amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        base_dec = Decimal(str(baseline_amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        items = line_items or []
        if items and prop_dec == Decimal("0.00"):
            prop_dec = sum((item.proposed_amount for item in items), Decimal("0.00"))

        submission = BottomUpSubmission(
            cycle_id=cycle_id,
            tenant_id=tenant_id,
            scope_type=scope_type,
            scope_id=scope_id,
            submitted_by=submitted_by,
            version=1,
            basis_type=basis_type,
            baseline_amount=base_dec,
            proposed_amount=prop_dec,
            justification=justification,
            line_items=items,
            status=SubmissionStatus.SUBMITTED,
        )
        self._submissions[submission.submission_id] = submission
        self._submission_history[submission.submission_id] = [submission.model_copy()]
        return submission

    def revise_bottom_up(
        self,
        submission_id: str,
        proposed_amount: Decimal | float | str,
        justification: str,
        revised_by: str,
        line_items: list[PlanLineItem] | None = None,
    ) -> BottomUpSubmission:
        existing = self.get_submission(submission_id)
        if existing.status == SubmissionStatus.APPROVED:
            raise ApprovedPlanImmutableException(submission_id)

        cycle = self.get_cycle(existing.cycle_id)
        if cycle.status == CycleStatus.CLOSED:
            raise PlanningWindowClosedException(cycle.cycle_id, "submission_window")

        prop_dec = Decimal(str(proposed_amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        items = line_items or existing.line_items
        if items and prop_dec == Decimal("0.00"):
            prop_dec = sum((item.proposed_amount for item in items), Decimal("0.00"))

        existing.version += 1
        existing.proposed_amount = prop_dec
        existing.justification = justification
        existing.submitted_by = revised_by
        existing.line_items = items
        existing.status = SubmissionStatus.REVISED
        existing.updated_at = dt.datetime.now(dt.UTC)

        self._submission_history[submission_id].append(existing.model_copy())
        return existing

    def get_submission(self, submission_id: str) -> BottomUpSubmission:
        if submission_id not in self._submissions:
            raise SubmissionNotFoundException(submission_id)
        return self._submissions[submission_id]

    def get_submission_history(self, submission_id: str) -> list[BottomUpSubmission]:
        if submission_id not in self._submission_history:
            raise SubmissionNotFoundException(submission_id)
        return self._submission_history[submission_id]

    def approve_submission(self, submission_id: str, approver_id: str) -> BottomUpSubmission:
        submission = self.get_submission(submission_id)
        submission.status = SubmissionStatus.APPROVED
        submission.updated_at = dt.datetime.now(dt.UTC)
        return submission

    # -------------------------------------------------------------------------
    # Top-Down Target Setting & Multi-Level Gap Analysis
    # -------------------------------------------------------------------------
    def set_top_down_target(
        self,
        cycle_id: str,
        scope_type: str,
        scope_id: str,
        target_amount: Decimal | float | str,
        issued_by: str,
        tenant_context: TenantContext | None = None,
    ) -> TopDownTarget:
        cycle = self.get_cycle(cycle_id)
        tenant_id = tenant_context.tenant_id if tenant_context else cycle.tenant_id
        tgt_dec = Decimal(str(target_amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)

        target = TopDownTarget(
            cycle_id=cycle_id,
            tenant_id=tenant_id,
            scope_type=scope_type,
            scope_id=scope_id,
            target_amount=tgt_dec,
            issued_by=issued_by,
        )
        self._targets[f"{cycle_id}:{scope_id}"] = target
        return target

    def get_top_down_target(self, cycle_id: str, scope_id: str) -> TopDownTarget:
        key = f"{cycle_id}:{scope_id}"
        if key not in self._targets:
            raise TargetNotFoundException(cycle_id, scope_id)
        return self._targets[key]

    def calculate_target_gap(self, cycle_id: str, scope_type: str, scope_id: str) -> TargetGapReport:
        target = self.get_top_down_target(cycle_id, scope_id)

        # Sum of bottom-up submissions for this scope and any child scopes
        matching_subs = [
            s for s in self._submissions.values()
            if s.cycle_id == cycle_id and (s.scope_id == scope_id or s.scope_id.startswith(f"{scope_id}:"))
        ]
        bottom_up_sum = sum((s.proposed_amount for s in matching_subs), Decimal("0.00"))
        gap = (bottom_up_sum - target.target_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        is_unfavourable = gap > Decimal("0.00")

        breakdowns = [
            {
                "submission_id": s.submission_id,
                "scope_id": s.scope_id,
                "proposed_amount": str(s.proposed_amount),
                "version": s.version,
                "status": s.status.value,
            }
            for s in matching_subs
        ]

        return TargetGapReport(
            cycle_id=cycle_id,
            scope_type=scope_type,
            scope_id=scope_id,
            top_down_target=target.target_amount,
            bottom_up_sum=bottom_up_sum,
            gap=gap,
            is_unfavourable=is_unfavourable,
            child_breakdowns=breakdowns,
        )

    # -------------------------------------------------------------------------
    # Scenario Modelling (Baseline Is Strictly Untouched)
    # -------------------------------------------------------------------------
    def create_what_if_scenario(
        self,
        cycle_id: str,
        name: str,
        description: str,
        baseline_amount: Decimal | float | str,
        assumptions: list[ScenarioAssumption] | None = None,
    ) -> WhatIfScenario:
        self.get_cycle(cycle_id)
        base_dec = Decimal(str(baseline_amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)

        scenario = WhatIfScenario(
            cycle_id=cycle_id,
            name=name,
            description=description,
            baseline_amount=base_dec,
            assumptions=assumptions or [],
        )
        self._scenarios[scenario.scenario_id] = scenario
        return scenario

    def get_scenario(self, scenario_id: str) -> WhatIfScenario:
        if scenario_id not in self._scenarios:
            raise ScenarioNotFoundException(scenario_id)
        return self._scenarios[scenario_id]

    def evaluate_scenario(self, scenario_id: str) -> ScenarioEvaluationResult:
        """Models scenario impacts against baseline without mutating original figures."""
        scenario = self.get_scenario(scenario_id)
        # Deep clone baseline - guarantees baseline never alters
        projected = Decimal(str(scenario.baseline_amount))
        impacts: list[dict[str, Any]] = []

        for asm in scenario.assumptions:
            impact_delta = Decimal("0.00")
            if asm.percentage_change is not None:
                # e.g. +0.10 for 10% growth or -0.15 for 15% discount
                impact_delta = (projected * asm.percentage_change).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_EVEN
                )
                projected = projected + impact_delta
            elif asm.fixed_delta is not None:
                # e.g. -5000.00 monthly decommission or +12000.00 new workload
                impact_delta = asm.fixed_delta.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
                projected = projected + impact_delta

            impacts.append({
                "assumption_id": asm.assumption_id,
                "type": asm.assumption_type.value,
                "description": asm.description,
                "delta": str(impact_delta),
            })

        absolute_delta = (projected - scenario.baseline_amount).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_EVEN
        )
        if scenario.baseline_amount > Decimal("0.00"):
            percentage_delta = ((absolute_delta / scenario.baseline_amount) * Decimal("100.00")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_EVEN
            )
        else:
            percentage_delta = Decimal("0.00")

        return ScenarioEvaluationResult(
            scenario_id=scenario.scenario_id,
            name=scenario.name,
            baseline_amount=scenario.baseline_amount,
            projected_amount=projected,
            absolute_delta=absolute_delta,
            percentage_delta=percentage_delta,
            assumption_impacts=impacts,
        )

    def compare_scenarios(self, cycle_id: str, scenario_ids: list[str]) -> list[ScenarioEvaluationResult]:
        """Performs side-by-side comparison across multiple alternative what-if scenarios."""
        results: list[ScenarioEvaluationResult] = []
        for sid in scenario_ids:
            scen = self.get_scenario(sid)
            if scen.cycle_id != cycle_id:
                raise ScenarioNotFoundException(sid)
            results.append(self.evaluate_scenario(sid))
        return results

    # -------------------------------------------------------------------------
    # Plan-to-Actual Accuracy Tracking & Operative Budget Rollover
    # -------------------------------------------------------------------------
    def convert_plan_to_budget(self, submission_id: str) -> dict[str, Any]:
        """Converts an approved plan proposal into an operative budget record with no re-keying."""
        sub = self.get_submission(submission_id)
        if sub.status != SubmissionStatus.APPROVED:
            raise PlanningException(
                f"Submission '{submission_id}' must be approved before conversion to operative budget."
            )
        cycle = self.get_cycle(sub.cycle_id)

        # Generates payload ready for domain.budgets.models.BudgetEntity
        return {
            "budget_id": f"bgt-plan-{sub.submission_id}",
            "tenant_id": sub.tenant_id,
            "name": f"Operative Budget {cycle.fiscal_period} - {sub.scope_id}",
            "scope_type": sub.scope_type,
            "scope_id": sub.scope_id,
            "fiscal_period": cycle.fiscal_period,
            "allocated_amount": str(sub.proposed_amount),
            "currency": "USD",
            "source": "PLANNING_CYCLE",
            "origin_cycle_id": sub.cycle_id,
            "origin_submission_id": sub.submission_id,
            "status": "ACTIVE",
        }

    def evaluate_plan_accuracy(
        self,
        submission_id: str,
        actual_spend: Decimal | float | str,
    ) -> PlanAccuracyReport:
        """Measures plan vs actual accuracy at period close so the next cycle starts from evidence."""
        sub = self.get_submission(submission_id)
        cycle = self.get_cycle(sub.cycle_id)
        actual_dec = Decimal(str(actual_spend)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        variance = (actual_dec - sub.proposed_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)

        if sub.proposed_amount > Decimal("0.00"):
            abs_err = abs(variance)
            accuracy = max(
                Decimal("0.00"),
                (Decimal("100.00") - ((abs_err / sub.proposed_amount) * Decimal("100.00"))),
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        else:
            accuracy = Decimal("100.00") if actual_dec == Decimal("0.00") else Decimal("0.00")

        return PlanAccuracyReport(
            fiscal_period=cycle.fiscal_period,
            scope_id=sub.scope_id,
            planned_amount=sub.proposed_amount,
            actual_amount=actual_dec,
            variance=variance,
            accuracy_percentage=accuracy,
        )

    def export_planning_pack(self, cycle_id: str) -> dict[str, Any]:
        """Generates a Finance-ready document of the approved plan by scope with its assumptions and basis."""
        cycle = self.get_cycle(cycle_id)
        cycle_subs = [s for s in self._submissions.values() if s.cycle_id == cycle_id]
        targets = [t for t in self._targets.values() if t.cycle_id == cycle_id]

        total_submitted = sum((s.proposed_amount for s in cycle_subs), Decimal("0.00"))
        total_targets = sum((t.target_amount for t in targets), Decimal("0.00"))
        net_gap = (total_submitted - total_targets).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)

        return {
            "pack_title": f"Executive Financial Planning Pack: {cycle.name}",
            "fiscal_period": cycle.fiscal_period,
            "generated_at": dt.datetime.now(dt.UTC).isoformat(),
            "status": cycle.status.value,
            "summary": {
                "total_scopes": len(cycle.participating_scopes),
                "total_submissions": len(cycle_subs),
                "total_submitted_amount": str(total_submitted),
                "total_target_envelope": str(total_targets),
                "net_planning_gap": str(net_gap),
                "gap_status": "UNFAVOURABLE" if net_gap > Decimal("0.00") else "FAVOURABLE",
            },
            "submissions": [
                {
                    "submission_id": s.submission_id,
                    "scope_type": s.scope_type,
                    "scope_id": s.scope_id,
                    "version": s.version,
                    "status": s.status.value,
                    "basis": s.basis_type.value,
                    "baseline": str(s.baseline_amount),
                    "proposed": str(s.proposed_amount),
                    "justification": s.justification,
                    "line_item_count": len(s.line_items),
                }
                for s in cycle_subs
            ],
            "targets": [
                {
                    "scope_id": t.scope_id,
                    "target_amount": str(t.target_amount),
                    "issued_by": t.issued_by,
                }
                for t in targets
            ],
        }
