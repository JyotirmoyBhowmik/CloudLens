"""Commitment Renewal and Coverage Management Service (Prompt 58).

Fulfills:
- Coverage and utilisation analysis with trends and over/under-commitment distinction.
- Lead-time-driven renewal pipeline ranked by value at risk.
- Recommendation with full inspectable reasoning (never a bare instruction).
- What-if comparison against forecast workload including do-nothing option.
- Decision record through workflow engine.
- Expiry alerting and assigned tasks.
- Post-expiry verification quantifying on-demand impact.
- Cross-provider commitment portfolio view.
"""

from __future__ import annotations

import datetime as dt
import logging
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from domain.commitments.exceptions import (
    CommitmentNotFoundException,
)
from domain.commitments.models import (
    CommitmentAssessment,
    CommitmentCoverageAnalysis,
    CommitmentDecisionRecord,
    CommitmentEntity,
    CommitmentType,
    ExpiryAlertRecord,
    HistoricalTrend,
    PortfolioSummary,
    PostExpiryImpact,
    RenewalAction,
    RenewalPipelineItem,
    RenewalRecommendation,
    WhatIfOption,
)
from domain.models.enums import (
    ProviderType,
    TaskCategory,
    TaskPriority,
    TaskSource,
    WorkflowRequestType,
)
from domain.remediation.models import (
    SubjectEntity as RemediationSubjectEntity,
)
from domain.remediation.models import (
    TaskCreateRequest,
)
from domain.tenant.context import TenantContext
from domain.workflows.models import (
    SubjectEntity as WorkflowSubjectEntity,
)
from domain.workflows.models import (
    WorkflowSubmitRequest,
)

logger = logging.getLogger(__name__)


class CommitmentService:
    """Enterprise FinOps Commitment Renewal & Coverage Engine."""

    def __init__(self) -> None:
        self._commitments: dict[str, CommitmentEntity] = {}
        self._analyses: dict[str, CommitmentCoverageAnalysis] = {}
        self._decisions: dict[str, CommitmentDecisionRecord] = {}
        self._alerts: dict[str, ExpiryAlertRecord] = {}

    def register_commitment(
        self,
        tenant_context: TenantContext,
        commitment_id: str,
        provider: ProviderType,
        account_id: str,
        commitment_type: CommitmentType,
        service_category: str,
        start_date: dt.datetime,
        expiry_date: dt.datetime,
        hourly_committed_rate: Decimal | float | str,
        annual_committed_cost: Decimal | float | str,
        owner_id: str,
        scope_id: str,
        term_months: int = 12,
    ) -> CommitmentEntity:
        entity = CommitmentEntity(
            commitment_id=commitment_id,
            tenant_id=tenant_context.tenant_id,
            provider=provider,
            account_id=account_id,
            commitment_type=commitment_type,
            service_category=service_category,
            term_months=term_months,
            start_date=start_date,
            expiry_date=expiry_date,
            hourly_committed_rate=Decimal(str(hourly_committed_rate)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_EVEN
            ),
            annual_committed_cost=Decimal(str(annual_committed_cost)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_EVEN
            ),
            owner_id=owner_id,
            scope_id=scope_id,
            is_active=True,
        )
        self._commitments[commitment_id] = entity
        return entity

    def get_commitment(self, commitment_id: str) -> CommitmentEntity:
        if commitment_id not in self._commitments:
            raise CommitmentNotFoundException(commitment_id)
        return self._commitments[commitment_id]

    def list_commitments(self, tenant_id: str) -> list[CommitmentEntity]:
        return [c for c in self._commitments.values() if c.tenant_id == tenant_id]

    # -------------------------------------------------------------------------
    # Coverage & Utilisation Analysis with Over/Under-Commitment Diagnosis
    # -------------------------------------------------------------------------
    def analyze_coverage_and_utilization(
        self,
        commitment_id: str,
        eligible_usage_cost: Decimal | float | str,
        covered_usage_cost: Decimal | float | str,
        commitment_cost: Decimal | float | str,
        actual_consumed_cost: Decimal | float | str,
        list_price_cost: Decimal | float | str,
        trend_history: list[HistoricalTrend] | None = None,
    ) -> CommitmentCoverageAnalysis:
        comm = self.get_commitment(commitment_id)

        el_dec = Decimal(str(eligible_usage_cost)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        cov_dec = Decimal(str(covered_usage_cost)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        cost_dec = Decimal(str(commitment_cost)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        act_dec = Decimal(str(actual_consumed_cost)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        list_dec = Decimal(str(list_price_cost)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)

        coverage_ratio = (cov_dec / el_dec) if el_dec > Decimal("0.00") else Decimal("0.0000")
        coverage_ratio = coverage_ratio.quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN)

        utilization_ratio = (act_dec / cost_dec) if cost_dec > Decimal("0.00") else Decimal("0.0000")
        utilization_ratio = utilization_ratio.quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN)

        realized_saving = (list_dec - act_dec).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)

        # Distinguish over-commitment vs under-commitment
        # Rule: Coverage without utilisation is OVER_COMMITMENT
        #       Utilisation without coverage is UNDER_COMMITMENT
        if coverage_ratio >= Decimal("0.8000") and utilization_ratio < Decimal("0.8500"):
            assessment = CommitmentAssessment.OVER_COMMITMENT
        elif utilization_ratio >= Decimal("0.9500") and coverage_ratio < Decimal("0.7000"):
            assessment = CommitmentAssessment.UNDER_COMMITMENT
        else:
            assessment = CommitmentAssessment.OPTIMAL

        analysis = CommitmentCoverageAnalysis(
            commitment_id=commitment_id,
            provider=comm.provider,
            commitment_type=comm.commitment_type,
            term_months=comm.term_months,
            expiry_date=comm.expiry_date,
            eligible_usage_cost=el_dec,
            covered_usage_cost=cov_dec,
            commitment_cost=cost_dec,
            actual_consumed_cost=act_dec,
            list_price_cost=list_dec,
            coverage_ratio=coverage_ratio,
            utilization_ratio=utilization_ratio,
            realized_saving=realized_saving,
            assessment=assessment,
            trend_history=trend_history or [],
        )
        self._analyses[commitment_id] = analysis
        return analysis

    # -------------------------------------------------------------------------
    # Lead-Time-Driven Renewal Pipeline Ranked by Value at Risk
    # -------------------------------------------------------------------------
    def get_renewal_pipeline(
        self,
        tenant_id: str,
        lead_time_days: int = 60,
        as_of: dt.datetime | None = None,
    ) -> list[RenewalPipelineItem]:
        now = as_of or dt.datetime.now(dt.UTC)
        items: list[RenewalPipelineItem] = []

        for comm in self.list_commitments(tenant_id):
            days_left = (comm.expiry_date.date() - now.date()).days
            is_in_window = 0 <= days_left <= lead_time_days

            analysis = self._analyses.get(comm.commitment_id)
            if not analysis:
                analysis = self.analyze_coverage_and_utilization(
                    commitment_id=comm.commitment_id,
                    eligible_usage_cost=comm.annual_committed_cost * Decimal("1.30"),
                    covered_usage_cost=comm.annual_committed_cost,
                    commitment_cost=comm.annual_committed_cost,
                    actual_consumed_cost=comm.annual_committed_cost * Decimal("0.90"),
                    list_price_cost=comm.annual_committed_cost * Decimal("1.40"),
                )

            # Value at risk = on-demand exposure difference
            var = (analysis.list_price_cost - analysis.commitment_cost).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_EVEN
            )
            if var < Decimal("0.00"):
                var = analysis.commitment_cost

            if is_in_window:
                items.append(
                    RenewalPipelineItem(
                        commitment_id=comm.commitment_id,
                        provider=comm.provider,
                        commitment_type=comm.commitment_type,
                        expiry_date=comm.expiry_date,
                        days_until_expiry=days_left,
                        is_in_decision_window=True,
                        value_at_risk=var,
                        analysis=analysis,
                    )
                )

        # Rank strictly by Value at Risk descending
        items.sort(key=lambda x: x.value_at_risk, reverse=True)
        for idx, item in enumerate(items, start=1):
            item.rank = idx

        return items

    # -------------------------------------------------------------------------
    # Recommendation with Inspectable Reasoning & What-If Options
    # -------------------------------------------------------------------------
    def generate_recommendation(
        self,
        commitment_id: str,
        forward_growth_pct: Decimal = Decimal("0.00"),
        planned_decommission_pct: Decimal = Decimal("0.00"),
    ) -> RenewalRecommendation:
        comm = self.get_commitment(commitment_id)
        analysis = self._analyses.get(commitment_id)
        if not analysis:
            analysis = self.analyze_coverage_and_utilization(
                commitment_id=comm.commitment_id,
                eligible_usage_cost=comm.annual_committed_cost * Decimal("1.25"),
                covered_usage_cost=comm.annual_committed_cost,
                commitment_cost=comm.annual_committed_cost,
                actual_consumed_cost=comm.annual_committed_cost * Decimal("0.95"),
                list_price_cost=comm.annual_committed_cost * Decimal("1.35"),
            )

        reasoning: list[str] = [
            f"Coverage ratio is {analysis.coverage_ratio * Decimal('100.00'):.1f}% of eligible spend.",
            f"Utilisation ratio is {analysis.utilization_ratio * Decimal('100.00'):.1f}% of commitment capacity.",
            f"Realised saving to date is ${analysis.realized_saving:,.2f} against list prices.",
            f"Forward workload forecast reflects {forward_growth_pct * Decimal('100.00'):.1f}% organic growth.",
            f"Planned decommissioning will release {planned_decommission_pct * Decimal('100.00'):.1f}% of capacity.",
        ]

        # Calculate what-if options including DO_NOTHING
        annual_base = comm.annual_committed_cost
        list_rate = analysis.list_price_cost

        # Option 1: Do Nothing (100% on demand list rate)
        do_nothing_cost = (list_rate * (Decimal("1.00") + forward_growth_pct - planned_decommission_pct)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_EVEN
        )
        opt_do_nothing = WhatIfOption(
            action=RenewalAction.DO_NOTHING,
            description="Allow commitment to lapse; run all workload on on-demand rates",
            projected_annual_cost=do_nothing_cost,
            projected_annual_saving=Decimal("0.00"),
            delta_vs_do_nothing=Decimal("0.00"),
        )

        # Option 2: Renew Same Level
        same_cost = annual_base
        same_saving = (do_nothing_cost - same_cost).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        opt_same = WhatIfOption(
            action=RenewalAction.RENEW_SAME,
            description=f"Renew identical level at ${same_cost:,.2f}/yr",
            projected_annual_cost=same_cost,
            projected_annual_saving=same_saving,
            delta_vs_do_nothing=same_saving,
        )

        # Option 3: Upsize (Higher Level)
        upsize_cost = (annual_base * Decimal("1.20")).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        upsize_saving = (do_nothing_cost - upsize_cost).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        opt_higher = WhatIfOption(
            action=RenewalAction.RENEW_HIGHER,
            description="Upsize commitment by 20% to capture unreserved burst capacity",
            projected_annual_cost=upsize_cost,
            projected_annual_saving=upsize_saving,
            delta_vs_do_nothing=upsize_saving,
        )

        # Option 4: Downsize (Lower Level)
        downsize_cost = (annual_base * Decimal("0.80")).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        downsize_saving = (do_nothing_cost - downsize_cost).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        opt_lower = WhatIfOption(
            action=RenewalAction.RENEW_LOWER,
            description="Downsize commitment by 20% to right-size capacity and prevent idle waste",
            projected_annual_cost=downsize_cost,
            projected_annual_saving=downsize_saving,
            delta_vs_do_nothing=downsize_saving,
        )

        # Option 5: Change Term
        term_cost = (annual_base * Decimal("0.85")).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        term_saving = (do_nothing_cost - term_cost).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        opt_term = WhatIfOption(
            action=RenewalAction.CHANGE_TERM,
            description="Extend to 3-year term for deeper multi-year rate reduction",
            projected_annual_cost=term_cost,
            projected_annual_saving=term_saving,
            delta_vs_do_nothing=term_saving,
        )

        # Option 6: Change Scope
        scope_cost = annual_base
        scope_saving = same_saving
        opt_scope = WhatIfOption(
            action=RenewalAction.CHANGE_SCOPE,
            description="Broaden scope to tenant-wide billing pool to eliminate single-account underutilisation",
            projected_annual_cost=scope_cost,
            projected_annual_saving=scope_saving,
            delta_vs_do_nothing=scope_saving,
        )

        # Option 7: Allow to Lapse
        opt_lapse = WhatIfOption(
            action=RenewalAction.ALLOW_TO_LAPSE,
            description="Deliberately allow commitment to lapse to accommodate planned workload decommissioning",
            projected_annual_cost=do_nothing_cost,
            projected_annual_saving=Decimal("0.00"),
            delta_vs_do_nothing=Decimal("0.00"),
        )

        options = [opt_do_nothing, opt_same, opt_higher, opt_lower, opt_term, opt_scope, opt_lapse]

        # Determine recommendation
        if planned_decommission_pct >= Decimal("0.80"):
            recommended_action = RenewalAction.ALLOW_TO_LAPSE
            rec_amount = Decimal("0.00")
            rec_saving = Decimal("0.00")
            reasoning.append("Recommendation: ALLOW_TO_LAPSE due to complete or near-total workload decommissioning (Prompt 59).")
        elif analysis.assessment == CommitmentAssessment.OVER_COMMITMENT or planned_decommission_pct > Decimal("0.15"):
            recommended_action = RenewalAction.RENEW_LOWER
            rec_amount = downsize_cost
            rec_saving = downsize_saving
            reasoning.append("Recommendation: RENEW_LOWER due to over-commitment and low historical utilisation.")
        elif analysis.assessment == CommitmentAssessment.UNDER_COMMITMENT and forward_growth_pct >= Decimal("0.00"):
            recommended_action = RenewalAction.RENEW_HIGHER
            rec_amount = upsize_cost
            rec_saving = upsize_saving
            reasoning.append("Recommendation: RENEW_HIGHER due to under-commitment with strong workload demand.")
        else:
            recommended_action = RenewalAction.RENEW_SAME
            rec_amount = same_cost
            rec_saving = same_saving
            reasoning.append("Recommendation: RENEW_SAME maintaining steady-state baseline commitments.")

        return RenewalRecommendation(
            commitment_id=commitment_id,
            recommended_action=recommended_action,
            recommended_commitment_amount=rec_amount,
            projected_annual_saving=rec_saving,
            reasoning=reasoning,
            what_if_options=options,
        )

    # -------------------------------------------------------------------------
    # Decision Recording, Expiry Alerting & Workflow Routing
    # -------------------------------------------------------------------------
    def record_renewal_decision(
        self,
        commitment_id: str,
        chosen_action: RenewalAction,
        approver_id: str,
        justification: str,
        tenant_context: TenantContext,
        workflow_service: Any | None = None,
        authority_threshold: Decimal = Decimal("50000.00"),
    ) -> CommitmentDecisionRecord:
        """Records a deliberate renewal or lapse decision, routing to Prompt 50 workflow if above threshold."""
        comm = self.get_commitment(commitment_id)
        requires_approval = comm.annual_committed_cost >= authority_threshold
        wf_req_id = None
        approval_status = "APPROVED"

        if requires_approval and workflow_service is not None:
            approval_status = "PENDING_WORKFLOW"
            provider_str = comm.provider.value if hasattr(comm.provider, "value") else str(comm.provider)
            submit_req = WorkflowSubmitRequest(
                request_type=WorkflowRequestType.BUDGET_APPROVAL.value,
                title=f"Commitment Renewal Decision: {comm.commitment_id} ({chosen_action.value})",
                subject_entity=WorkflowSubjectEntity(
                    entity_type="commitment",
                    entity_id=comm.commitment_id,
                    scope_type="scope",
                    scope_id=comm.scope_id,
                    metadata={
                        "provider": provider_str,
                        "action": chosen_action.value,
                    },
                ),
                justification=justification,
                payload={
                    "commitment_id": comm.commitment_id,
                    "chosen_action": chosen_action.value,
                    "annual_committed_cost": str(comm.annual_committed_cost),
                    "scope_id": comm.scope_id,
                },
                financial_impact=float(comm.annual_committed_cost),
            )
            wf_res = workflow_service.submit_request(submit_req, tenant_context=tenant_context)
            wf_req_id = wf_res.id

        record = CommitmentDecisionRecord(
            commitment_id=commitment_id,
            tenant_id=tenant_context.tenant_id,
            chosen_action=chosen_action,
            approver_id=approver_id,
            justification=justification,
            requires_approval=requires_approval,
            approval_status=approval_status,
            workflow_request_id=wf_req_id,
        )
        self._decisions[commitment_id] = record
        return record

    def route_decision_to_workflow(
        self,
        commitment_id: str,
        chosen_action: RenewalAction,
        approver_id: str,
        justification: str,
        tenant_context: TenantContext,
        workflow_service: Any,
    ) -> CommitmentDecisionRecord:
        """Explicitly routes a renewal decision through Prompt 50 governance workflow engine under AM-12 rules."""
        return self.record_renewal_decision(
            commitment_id=commitment_id,
            chosen_action=chosen_action,
            approver_id=approver_id,
            justification=justification,
            tenant_context=tenant_context,
            workflow_service=workflow_service,
            authority_threshold=Decimal("0.00"),
        )

    def trigger_expiry_alerts_and_tasks(
        self,
        commitment_id: str,
        lead_time_days: int = 60,
        as_of: dt.datetime | None = None,
        tenant_context: TenantContext | None = None,
        remediation_service: Any | None = None,
    ) -> ExpiryAlertRecord:
        """Emits expiry alert and creates assigned remediation task with due date at decision deadline."""
        now = as_of or dt.datetime.now(dt.UTC)
        comm = self.get_commitment(commitment_id)
        days_left = (comm.expiry_date.date() - now.date()).days
        if days_left > lead_time_days:
            logger.info(
                "Commitment %s not within renewal lead time window (%d > %d days)",
                commitment_id,
                days_left,
                lead_time_days,
            )

        analysis = self._analyses.get(commitment_id)
        if not analysis:
            analysis = self.analyze_coverage_and_utilization(
                commitment_id=comm.commitment_id,
                eligible_usage_cost=comm.annual_committed_cost * Decimal("1.30"),
                covered_usage_cost=comm.annual_committed_cost,
                commitment_cost=comm.annual_committed_cost,
                actual_consumed_cost=comm.annual_committed_cost * Decimal("0.90"),
                list_price_cost=comm.annual_committed_cost * Decimal("1.40"),
            )

        var = (analysis.list_price_cost - analysis.commitment_cost).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_EVEN
        )
        if var < Decimal("0.00"):
            var = analysis.commitment_cost

        # Decision deadline: 14 days before expiry (or immediate if within 14 days)
        decision_days = max(1, days_left - 14)
        decision_deadline = now + dt.timedelta(days=decision_days)

        task_id = None
        if remediation_service is not None and tenant_context is not None:
            provider_str = comm.provider.value if hasattr(comm.provider, "value") else str(comm.provider)
            task_req = TaskCreateRequest(
                source=TaskSource.ALERT,
                subject_entity=RemediationSubjectEntity(
                    entity_type="commitment",
                    entity_id=comm.commitment_id,
                    entity_name=f"{provider_str} {comm.commitment_type} ({comm.commitment_id})",
                    scope_type="scope",
                    scope_id=comm.scope_id,
                    provider=provider_str,
                ),
                title=f"Commitment Expiry Decision Required: {comm.commitment_id}",
                description=(
                    f"Commitment {comm.commitment_id} expires in {days_left} days. "
                    f"Value at risk is ${var:,.2f}. Decision must be recorded before {decision_deadline.strftime('%Y-%m-%d')}."
                ),
                category=TaskCategory.BUDGET_BREACH,
                priority=TaskPriority.HIGH if var > Decimal("50000.00") else TaskPriority.MEDIUM,
                assignee_id=comm.owner_id,
                assignee_type="USER",
                estimated_saving=float(var),
                sla_working_hours=48.0,
            )
            task = remediation_service.create_task(
                req=task_req,
                actor="SYSTEM_ALERT_ENGINE",
                tenant_context=tenant_context,
            )
            task_id = task.id

        alert = ExpiryAlertRecord(
            commitment_id=comm.commitment_id,
            tenant_id=comm.tenant_id,
            owner_id=comm.owner_id,
            days_until_expiry=days_left,
            decision_deadline=decision_deadline,
            value_at_risk=var,
            remediation_task_id=task_id,
        )
        self._alerts[comm.commitment_id] = alert
        return alert

    def get_alert(self, commitment_id: str) -> ExpiryAlertRecord | None:
        return self._alerts.get(commitment_id)

    def evaluate_post_expiry_impact(
        self,
        commitment_id: str,
        on_demand_actual_cost: Decimal | float | str,
        evaluation_period: str = "2027-01",
        replacement_commitment_id: str | None = None,
    ) -> PostExpiryImpact:
        """Verifies post-lapse actuals against past committed rates to quantify financial surge and verify implementation."""
        comm = self.get_commitment(commitment_id)
        ondemand_dec = Decimal(str(on_demand_actual_cost)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_EVEN
        )
        prev_monthly = (comm.annual_committed_cost / Decimal("12.00")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_EVEN
        )
        increase = (ondemand_dec - prev_monthly).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)

        decision = self._decisions.get(commitment_id)
        if not decision:
            has_deliberate_decision = False
            incident_raised = True
            incident_details = (
                f"INCIDENT: Commitment {commitment_id} lapsed without a deliberate renewal or lapse decision recorded. "
                f"Uncommitted cost spiked by ${increase:,.2f}."
            )
        else:
            has_deliberate_decision = True
            if decision.chosen_action in {
                RenewalAction.RENEW_SAME,
                RenewalAction.RENEW_HIGHER,
                RenewalAction.RENEW_LOWER,
            }:
                if not replacement_commitment_id or replacement_commitment_id not in self._commitments:
                    incident_raised = True
                    incident_details = (
                        f"INCIDENT: Commitment {commitment_id} decision was {decision.chosen_action.value}, "
                        f"but no replacement commitment was found in inventory. On-demand cost spiked by ${increase:,.2f}."
                    )
                else:
                    incident_raised = False
                    incident_details = (
                        f"Renewal verified. Replacement commitment {replacement_commitment_id} active in inventory."
                    )
            else:
                incident_raised = False
                incident_details = (
                    f"Deliberate lapse decision recorded by {decision.approver_id}. "
                    f"Expected on-demand delta: ${increase:,.2f}."
                )

        return PostExpiryImpact(
            commitment_id=commitment_id,
            lapsed_at=comm.expiry_date,
            evaluation_period=evaluation_period,
            on_demand_rate_cost=ondemand_dec,
            previous_committed_cost=prev_monthly,
            on_demand_increase=increase,
            has_deliberate_decision=has_deliberate_decision,
            incident_raised=incident_raised,
            incident_details=incident_details,
        )

    def get_portfolio_view(self, tenant_id: str) -> PortfolioSummary:
        """Generates cross-provider portfolio view for executive and procurement review."""
        comms = self.list_commitments(tenant_id)
        if not comms:
            return PortfolioSummary(
                total_commitments=0,
                total_annual_committed_value=Decimal("0.00"),
                overall_coverage_ratio=Decimal("0.0000"),
                overall_utilization_ratio=Decimal("0.0000"),
                total_realized_savings=Decimal("0.00"),
                total_value_at_risk=Decimal("0.00"),
                provider_breakdowns={},
            )

        total_annual = sum((c.annual_committed_cost for c in comms), Decimal("0.00"))
        all_analyses = [self._analyses.get(c.commitment_id) for c in comms if c.commitment_id in self._analyses]

        if all_analyses:
            avg_cov = (sum((a.coverage_ratio for a in all_analyses), Decimal("0.00")) / len(all_analyses)).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_EVEN
            )
            avg_util = (sum((a.utilization_ratio for a in all_analyses), Decimal("0.00")) / len(all_analyses)).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_EVEN
            )
            tot_sav = sum((a.realized_saving for a in all_analyses), Decimal("0.00"))
        else:
            avg_cov = Decimal("0.0000")
            avg_util = Decimal("0.0000")
            tot_sav = Decimal("0.00")

        pipeline = self.get_renewal_pipeline(tenant_id, lead_time_days=365)
        total_var = sum((p.value_at_risk for p in pipeline), Decimal("0.00"))

        provider_map: dict[str, Any] = {}
        for c in comms:
            p_raw = c.provider.value if hasattr(c.provider, "value") else str(c.provider)
            p_val = p_raw.upper()
            if p_val not in provider_map:
                provider_map[p_val] = {"count": 0, "annual_committed": Decimal("0.00")}
            provider_map[p_val]["count"] += 1
            provider_map[p_val]["annual_committed"] += c.annual_committed_cost

        return PortfolioSummary(
            total_commitments=len(comms),
            total_annual_committed_value=total_annual,
            overall_coverage_ratio=avg_cov,
            overall_utilization_ratio=avg_util,
            total_realized_savings=tot_sav,
            total_value_at_risk=total_var,
            provider_breakdowns={
                k: {"count": v["count"], "annual_committed": str(v["annual_committed"])}
                for k, v in provider_map.items()
            },
        )
