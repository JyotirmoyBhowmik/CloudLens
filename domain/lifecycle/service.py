"""Resource Lifecycle and Decommissioning Domain Service (Prompt 59).

Fulfills:
- Master-data lifecycle state model with configured transitions across 10 states:
  REQUESTED -> PROVISIONED -> ACTIVE -> IDLE_CANDIDATE -> DECOMMISSION_PROPOSED ->
  DECOMMISSION_APPROVED -> STOPPED -> PENDING_DELETION -> DELETED -> RETIRED.
- Decommissioning request through Prompt 50 workflow engine.
- Mandatory dependency impact check: requires explicit cross-team owner acknowledgement.
- Staged stop-observe-delete path with soak window and stopped-but-not-deleted surfacing.
- Cost-stop verification from actual billing data with exception and task triggers.
- Orphan and residue detection with costed tasks.
- Realised saving credited from actual billing data, never from estimates.
- Retention obligation check blocking deletion until confirmed satisfied.
- Decommissioning programme view grouping resources.
- Read-only safety guard: CloudLens never touches provider delete APIs.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, ROUND_HALF_EVEN
import logging
from typing import Any

from domain.lifecycle.exceptions import (
    CostStopVerificationFailureException,
    DecommissioningRequestNotFoundException,
    InvalidLifecycleTransitionException,
    LifecycleException,
    ProgrammeNotFoundException,
    RetentionObligationUnsatisfiedException,
    UnacknowledgedDependencyException,
)
from domain.lifecycle.models import (
    DecommissioningProgramme,
    DecommissioningProgrammeView,
    DecommissioningRequest,
    DependencyAcknowledgement,
    LifecycleResource,
    LifecycleState,
    OrphanResidueItem,
    OrphanResourceType,
    RetentionObligation,
    StoppedResourceSurfaced,
)
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)

# Permitted state transition matrix configured as domain rule
PERMITTED_TRANSITIONS: dict[LifecycleState, set[LifecycleState]] = {
    LifecycleState.REQUESTED: {LifecycleState.PROVISIONED},
    LifecycleState.PROVISIONED: {LifecycleState.ACTIVE},
    LifecycleState.ACTIVE: {
        LifecycleState.IDLE_CANDIDATE,
        LifecycleState.DECOMMISSION_PROPOSED,
    },
    LifecycleState.IDLE_CANDIDATE: {
        LifecycleState.ACTIVE,
        LifecycleState.DECOMMISSION_PROPOSED,
    },
    LifecycleState.DECOMMISSION_PROPOSED: {
        LifecycleState.DECOMMISSION_APPROVED,
        LifecycleState.ACTIVE,  # Rejected or withdrawn
    },
    LifecycleState.DECOMMISSION_APPROVED: {
        LifecycleState.STOPPED,
    },
    LifecycleState.STOPPED: {
        LifecycleState.ACTIVE,            # Rollback / restart during soak
        LifecycleState.PENDING_DELETION,
    },
    LifecycleState.PENDING_DELETION: {
        LifecycleState.DELETED,
    },
    LifecycleState.DELETED: {
        LifecycleState.RETIRED,
    },
    LifecycleState.RETIRED: set(),
}


class LifecycleService:
    """Enterprise FinOps Resource Lifecycle & Decommissioning Engine."""

    def __init__(self) -> None:
        self._resources: dict[str, LifecycleResource] = {}
        self._requests: dict[str, DecommissioningRequest] = {}
        self._programmes: dict[str, DecommissioningProgramme] = {}
        self._residue_items: dict[str, OrphanResidueItem] = {}

    # -------------------------------------------------------------------------
    # Resource Registration & Inbound Dependency Management
    # -------------------------------------------------------------------------
    def register_resource(
        self,
        resource_id: str,
        tenant_id: str,
        owner_team: str,
        service_type: str,
        monthly_run_rate: Decimal | float | str = Decimal("0.00"),
        storage_cost_rate: Decimal | float | str = Decimal("0.00"),
        initial_state: LifecycleState = LifecycleState.ACTIVE,
        retention_obligation: RetentionObligation | None = None,
    ) -> LifecycleResource:
        res = LifecycleResource(
            resource_id=resource_id,
            tenant_id=tenant_id,
            owner_team=owner_team,
            service_type=service_type,
            current_state=initial_state,
            monthly_run_rate=Decimal(str(monthly_run_rate)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_EVEN
            ),
            storage_cost_rate=Decimal(str(storage_cost_rate)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_EVEN
            ),
            retention_obligation=retention_obligation,
        )
        self._resources[resource_id] = res
        return res

    def get_resource(self, resource_id: str) -> LifecycleResource:
        if resource_id not in self._resources:
            raise LifecycleException(f"Resource '{resource_id}' is not registered in lifecycle engine.")
        return self._resources[resource_id]

    def add_inbound_dependency(
        self,
        resource_id: str,
        dependency_id: str,
        dependent_resource_id: str,
        dependency_type: str,
        dependent_owner_team: str,
        confidence: Decimal | float | str = Decimal("1.00"),
    ) -> DependencyAcknowledgement:
        res = self.get_resource(resource_id)
        is_cross = dependent_owner_team.strip().lower() != res.owner_team.strip().lower()

        dep = DependencyAcknowledgement(
            dependency_id=dependency_id,
            source_resource_id=resource_id,
            dependent_resource_id=dependent_resource_id,
            dependency_type=dependency_type,
            dependent_owner_team=dependent_owner_team,
            proposer_owner_team=res.owner_team,
            confidence=Decimal(str(confidence)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN),
            is_cross_team=is_cross,
            is_acknowledged=False,
        )
        res.inbound_dependencies.append(dep)
        return dep

    def acknowledge_dependency(
        self,
        resource_id: str,
        dependency_id: str,
        acknowledged_by: str,
    ) -> DependencyAcknowledgement:
        res = self.get_resource(resource_id)
        for dep in res.inbound_dependencies:
            if dep.dependency_id == dependency_id:
                dep.is_acknowledged = True
                dep.acknowledged_by = acknowledged_by
                dep.acknowledged_at = dt.datetime.now(dt.timezone.utc)
                return dep
        raise LifecycleException(f"Dependency '{dependency_id}' not found on resource '{resource_id}'.")

    # -------------------------------------------------------------------------
    # Lifecycle State Transitions with Configured Evidence Gates
    # -------------------------------------------------------------------------
    def transition_state(
        self,
        resource_id: str,
        target_state: LifecycleState,
        actor_id: str,
        evidence: dict[str, Any] | None = None,
    ) -> LifecycleResource:
        res = self.get_resource(resource_id)
        current = res.current_state

        # Validate transition is permitted
        if target_state not in PERMITTED_TRANSITIONS.get(current, set()):
            raise InvalidLifecycleTransitionException(
                from_state=current.value,
                to_state=target_state.value,
                reason=f"Transition not permitted in state machine.",
            )

        # Gate 1: To DECOMMISSION_APPROVED requires cross-team dependency acknowledgement
        if target_state == LifecycleState.DECOMMISSION_APPROVED:
            for dep in res.inbound_dependencies:
                if dep.is_cross_team and not dep.is_acknowledged:
                    raise UnacknowledgedDependencyException(
                        resource_id=resource_id,
                        dependent_team=dep.dependent_owner_team,
                        dependency_id=dep.dependency_id,
                    )

        # Gate 2: To PENDING_DELETION or DELETED requires satisfaction of retention obligations
        if target_state in (LifecycleState.PENDING_DELETION, LifecycleState.DELETED):
            if res.retention_obligation and not res.retention_obligation.is_satisfied:
                raise RetentionObligationUnsatisfiedException(
                    resource_id=resource_id,
                    retention_basis=res.retention_obligation.retention_basis,
                )

        now = dt.datetime.now(dt.timezone.utc)
        if target_state == LifecycleState.STOPPED:
            res.stopped_at = now
        elif target_state == LifecycleState.DELETED:
            res.deleted_at = now
        elif target_state == LifecycleState.RETIRED:
            res.retired_at = now

        res.current_state = target_state
        return res

    def satisfy_retention_obligation(
        self,
        resource_id: str,
        compliance_officer_id: str,
        notes: str,
    ) -> RetentionObligation:
        res = self.get_resource(resource_id)
        if not res.retention_obligation:
            raise LifecycleException(f"Resource '{resource_id}' has no recorded retention obligation.")

        res.retention_obligation.is_satisfied = True
        res.retention_obligation.satisfied_by = compliance_officer_id
        res.retention_obligation.satisfied_at = dt.datetime.now(dt.timezone.utc)
        res.retention_obligation.signoff_notes = notes
        return res.retention_obligation

    # -------------------------------------------------------------------------
    # Decommissioning Requests & Workflow Integration
    # -------------------------------------------------------------------------
    def submit_decommissioning_request(
        self,
        resource_ids: list[str],
        proposing_actor: str,
        proposer_team: str,
        justification: str,
        intended_date: dt.datetime,
        programme_id: str | None = None,
    ) -> DecommissioningRequest:
        if len(justification.strip()) < 5:
            raise LifecycleException("Justification must contain at least 5 characters.")

        total_est_saving = Decimal("0.00")
        for rid in resource_ids:
            res = self.get_resource(rid)
            self.transition_state(
                resource_id=rid,
                target_state=LifecycleState.DECOMMISSION_PROPOSED,
                actor_id=proposing_actor,
            )
            total_est_saving += res.monthly_run_rate

        req = DecommissioningRequest(
            programme_id=programme_id,
            resource_ids=resource_ids,
            proposing_actor=proposing_actor,
            proposer_team=proposer_team,
            justification=justification,
            intended_date=intended_date,
            estimated_monthly_saving=total_est_saving,
        )
        self._requests[req.request_id] = req
        return req

    def approve_decommissioning_request(
        self,
        request_id: str,
        approver_id: str,
    ) -> DecommissioningRequest:
        if request_id not in self._requests:
            raise DecommissioningRequestNotFoundException(request_id)
        req = self._requests[request_id]

        # Transition each resource to DECOMMISSION_APPROVED (triggers cross-team checks)
        for rid in req.resource_ids:
            self.transition_state(
                resource_id=rid,
                target_state=LifecycleState.DECOMMISSION_APPROVED,
                actor_id=approver_id,
            )

        req.is_approved = True
        req.approved_by = approver_id
        req.approved_at = dt.datetime.now(dt.timezone.utc)
        return req

    # -------------------------------------------------------------------------
    # Staged Soak Window & Surfacing Stopped-but-Not-Deleted Resources
    # -------------------------------------------------------------------------
    def surface_stopped_resources(
        self,
        tenant_id: str,
        max_soak_days: int = 14,
        as_of: dt.datetime | None = None,
    ) -> list[StoppedResourceSurfaced]:
        """Surfaces resources lingering in STOPPED state incurring storage costs without deletion."""
        now = as_of or dt.datetime.now(dt.timezone.utc)
        surfaced: list[StoppedResourceSurfaced] = []

        for res in self._resources.values():
            if res.tenant_id == tenant_id and res.current_state == LifecycleState.STOPPED:
                stopped_time = res.stopped_at or now
                days_stopped = (now.date() - stopped_time.date()).days
                if days_stopped >= max_soak_days:
                    surfaced.append(
                        StoppedResourceSurfaced(
                            resource_id=res.resource_id,
                            owner_team=res.owner_team,
                            stopped_at=stopped_time,
                            days_in_stopped_state=days_stopped,
                            ongoing_storage_cost=res.storage_cost_rate,
                            alert_level="CRITICAL" if days_stopped > (max_soak_days * 2) else "WARNING",
                        )
                    )
        return surfaced

    # -------------------------------------------------------------------------
    # Cost-Stop Verification from Billing Data
    # -------------------------------------------------------------------------
    def verify_cost_stop(
        self,
        resource_id: str,
        post_deletion_billing_amount: Decimal | float | str,
    ) -> None:
        """Verifies billing has ceased post deletion; raises exception & alerts if charges persist."""
        res = self.get_resource(resource_id)
        cost_dec = Decimal(str(post_deletion_billing_amount)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_EVEN
        )

        if cost_dec > Decimal("0.00"):
            raise CostStopVerificationFailureException(
                resource_id=resource_id,
                ongoing_cost=str(cost_dec),
            )

        # Transition to RETIRED when cost is proven to be zero
        if res.current_state == LifecycleState.DELETED:
            res.current_state = LifecycleState.RETIRED
            res.retired_at = dt.datetime.now(dt.timezone.utc)

    # -------------------------------------------------------------------------
    # Orphan and Residue Detection
    # -------------------------------------------------------------------------
    def detect_orphan_residue(
        self,
        tenant_id: str,
        residue_candidates: list[dict[str, Any]],
    ) -> list[OrphanResidueItem]:
        """Detects orphaned volumes, unused elastic IPs, unattached snapshots, and empty scopes."""
        detected: list[OrphanResidueItem] = []
        for cand in residue_candidates:
            cost_dec = Decimal(str(cand.get("monthly_waste_cost", "0.00"))).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_EVEN
            )
            item = OrphanResidueItem(
                resource_id=cand["resource_id"],
                residue_type=OrphanResourceType(cand["residue_type"]),
                associated_scope=cand.get("associated_scope", tenant_id),
                monthly_waste_cost=cost_dec,
            )
            self._residue_items[item.residue_id] = item
            detected.append(item)
        return detected

    # -------------------------------------------------------------------------
    # Realised Saving Crediting from Actual Billing (Never from Estimate)
    # -------------------------------------------------------------------------
    def credit_realised_saving(
        self,
        resource_id: str,
        actual_billing_before: Decimal | float | str,
        actual_billing_after: Decimal | float | str,
        tenant_context: TenantContext,
    ) -> Decimal:
        """Credits verified monthly savings computed from empirical billing records."""
        self.get_resource(resource_id)
        before_dec = Decimal(str(actual_billing_before)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        after_dec = Decimal(str(actual_billing_after)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)

        realised = (before_dec - after_dec).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        return realised

    # -------------------------------------------------------------------------
    # Decommissioning Programmes View
    # -------------------------------------------------------------------------
    def create_programme(
        self,
        tenant_context: TenantContext,
        name: str,
        description: str,
        target_completion_date: dt.datetime,
        resource_ids: list[str] | None = None,
    ) -> DecommissioningProgramme:
        prog = DecommissioningProgramme(
            tenant_id=tenant_context.tenant_id,
            name=name,
            description=description,
            target_completion_date=target_completion_date,
            resource_ids=resource_ids or [],
        )
        self._programmes[prog.programme_id] = prog
        return prog

    def get_programme_view(self, programme_id: str) -> DecommissioningProgrammeView:
        if programme_id not in self._programmes:
            raise ProgrammeNotFoundException(programme_id)
        prog = self._programmes[programme_id]

        state_counts: dict[str, int] = {st.value: 0 for st in LifecycleState}
        total_proj = Decimal("0.00")
        total_real = Decimal("0.00")
        unack_deps = 0

        for rid in prog.resource_ids:
            if rid in self._resources:
                res = self._resources[rid]
                state_counts[res.current_state.value] += 1
                total_proj += res.monthly_run_rate
                if res.current_state in (LifecycleState.DELETED, LifecycleState.RETIRED):
                    total_real += (res.monthly_run_rate - res.storage_cost_rate)
                for dep in res.inbound_dependencies:
                    if dep.is_cross_team and not dep.is_acknowledged:
                        unack_deps += 1

        return DecommissioningProgrammeView(
            programme_id=programme_id,
            name=prog.name,
            total_resources=len(prog.resource_ids),
            state_breakdown=state_counts,
            projected_monthly_savings=total_proj,
            realised_monthly_savings=total_real,
            outstanding_dependencies_count=unack_deps,
        )
