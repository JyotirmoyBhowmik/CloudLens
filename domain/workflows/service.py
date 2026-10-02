"""Workflow, Approval and Delegation Domain Service (Prompt 50).

Enforces:
- Generic workflow engine with 8 states:
  DRAFT, SUBMITTED, IN_REVIEW, APPROVED, REJECTED, WITHDRAWN, EXPIRED, APPLIED.
- Master-data-driven workflow definitions (serial, parallel, quorum, SLA, escalation).
- Dynamic approver resolution from master data with fallback and governance exception.
- Delegation, out-of-office, and automatic escalation.
- Approver inbox and requester view with context, diff, and financial impact.
- Atomic apply-on-approval with error state reversion to IN_REVIEW.
- Complete audit trail and workflow operational metrics.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from domain.audit.models import AuditEventCreate
from domain.audit.service import AuditService, get_audit_service
from domain.models.enums import (
    ApprovalChainMode,
    AuditEventType,
    DecisionOutcome,
    WorkflowState,
)
from domain.models.exceptions import (
    InvalidWorkflowTransitionException,
    UnauthorizedApproverException,
    WorkflowAlreadyFinalizedException,
    WorkflowDefinitionNotFoundException,
    WorkflowMandatoryCommentException,
    WorkflowNotFoundException,
)
from domain.tenant.context import TenantContext, require_tenant_context
from domain.workflows.appliers import WorkflowApplierRegistry, get_applier_registry
from domain.workflows.definitions import (
    get_default_workflow_definition_by_type,
)
from domain.workflows.models import (
    ApproverInboxItem,
    DelegationCreateRequest,
    DelegationRule,
    RequesterInfo,
    RequesterViewItem,
    WorkflowDecision,
    WorkflowDecisionRequest,
    WorkflowMetricsReport,
    WorkflowRequest,
    WorkflowStage,
    WorkflowSubmitRequest,
    WorkflowWithdrawRequest,
)
from domain.workflows.repository import WorkflowRepository, get_workflow_repository
from domain.workflows.resolver import ApproverResolver
from domain.workflows.sla import SLAEngine
from masterdata.service import MasterDataService, get_master_data_service

logger = logging.getLogger(__name__)


class WorkflowService:
    """Core enterprise orchestration service for approvals, delegations, and workflows."""

    def __init__(
        self,
        repository: WorkflowRepository | None = None,
        sla_engine: SLAEngine | None = None,
        resolver: ApproverResolver | None = None,
        appliers: WorkflowApplierRegistry | None = None,
        audit_service: AuditService | None = None,
        master_data_service: MasterDataService | None = None,
    ) -> None:
        self.repository = repository or get_workflow_repository()
        self.master_data_service = master_data_service or get_master_data_service()
        self.sla_engine = sla_engine or SLAEngine(self.master_data_service)
        self.resolver = resolver or ApproverResolver(self.master_data_service)
        self.appliers = appliers or get_applier_registry()
        self.audit_service = audit_service or get_audit_service()

    # ==========================================================================
    # 1. Submission & Stage Initialization
    # ==========================================================================

    def submit_request(
        self,
        request: WorkflowSubmitRequest,
        *,
        tenant_context: TenantContext,
    ) -> WorkflowRequest:
        """Submits a proposed change for governance workflow evaluation."""
        tc = require_tenant_context(tenant_context)
        now = datetime.now(UTC)

        # 1. Lookup governing definition (master data)
        definition = self.repository.get_definition_by_type(request.request_type, tenant_context=tc)
        if not definition:
            definition = get_default_workflow_definition_by_type(request.request_type)
        if not definition:
            raise WorkflowDefinitionNotFoundException(request.request_type)

        req_id = f"wf-req-{tc.tenant_id[:8]}-{uuid.uuid4().hex[:8]}"

        # 2. Check trigger condition
        triggers = definition.trigger_condition.matches(
            payload=request.payload, financial_impact=request.financial_impact
        )

        # Build runtime stages from definition
        stages: list[WorkflowStage] = []
        for s_def in definition.stages:
            stages.append(
                WorkflowStage(
                    stage_id=s_def.stage_id,
                    name=s_def.name,
                    sequence_order=s_def.sequence_order,
                    mode=s_def.mode,
                    quorum=s_def.quorum,
                    approver_spec=s_def.approver_spec,
                    assigned_approvers=[],
                    status="PENDING",
                    decisions=[],
                )
            )

        # Calculate SLA and escalation deadlines
        due_date = self.sla_engine.calculate_due_date(
            start_time=now,
            sla_working_hours=definition.sla_working_hours,
            schedule_id=definition.working_schedule_id,
            tenant_id=tc.tenant_id,
        )
        escalation_due_at = self.sla_engine.calculate_due_date(
            start_time=now,
            sla_working_hours=definition.escalation_path.escalate_after_hours,
            schedule_id=definition.working_schedule_id,
            tenant_id=tc.tenant_id,
        )

        requester = RequesterInfo(
            requester_id=tc.user_id,
            requester_email=tc.email,
        )

        entity = WorkflowRequest(
            id=req_id,
            tenant_id=tc.tenant_id,
            definition_id=definition.id,
            request_type=request.request_type,
            title=request.title,
            subject_entity=request.subject_entity,
            requester=requester,
            justification=request.justification,
            payload=request.payload,
            previous_values=request.previous_values,
            financial_impact=request.financial_impact,
            state=WorkflowState.SUBMITTED,
            current_stage_index=0,
            stages=stages,
            created_at=now,
            submitted_at=now,
            due_date=due_date,
            sla_working_hours=definition.sla_working_hours,
            working_schedule_id=definition.working_schedule_id,
            escalation_path=definition.escalation_path,
            escalation_due_at=escalation_due_at,
            history=[],
        )

        entity.add_history(
            actor_id=tc.user_id,
            action="SUBMIT",
            previous_state=None,
            new_state=WorkflowState.SUBMITTED,
            details={"request_type": request.request_type, "title": request.title},
        )

        # Check if condition did NOT trigger -> auto-approve or direct pass
        if not triggers:
            logger.info("Request '%s' did not trigger approval condition; auto-passing", req_id)
            entity.state = WorkflowState.APPROVED
            entity.add_history(
                actor_id="system",
                action="AUTO_APPROVE",
                previous_state=WorkflowState.SUBMITTED,
                new_state=WorkflowState.APPROVED,
                details={"reason": "Below threshold or condition not met"},
            )
            # Apply immediately
            self._apply_approved_request(entity, actor_id="system", tenant_context=tc)
            return self.repository.save(entity, tenant_context=tc)

        # If triggered, resolve approvers for Stage 0 and advance to IN_REVIEW
        if stages:
            delegations = self.repository.list_delegations(tenant_context=tc)
            res = self.resolver.resolve_approvers(
                request_id=entity.id,
                stage_def=definition.stages[0],
                subject_entity=entity.subject_entity,
                tenant_context=tc,
                delegations=delegations,
                as_of=now,
                request_type=entity.request_type,
            )
            stages[0].assigned_approvers = res.effective_approvers
            stages[0].status = "IN_REVIEW"
            entity.state = WorkflowState.IN_REVIEW
            entity.add_history(
                actor_id="system",
                action="INITIALIZE_STAGE",
                previous_state=WorkflowState.SUBMITTED,
                new_state=WorkflowState.IN_REVIEW,
                stage_id=stages[0].stage_id,
                details={"assigned_approvers": res.effective_approvers},
            )

            # If assigned approver is unavailable without delegate, flag immediate escalation
            if res.unavailable_without_delegate:
                logger.warning(
                    "Approver(s) %s unavailable on leave with no delegation; escalating request %s",
                    res.unavailable_without_delegate,
                    entity.id,
                )
                entity.is_escalated = True
                entity.escalation_path.is_escalated = True
                entity.escalation_path.escalated_at = now
                entity.escalation_path.escalated_to = [entity.escalation_path.escalate_to_role]
                entity.add_history(
                    actor_id="system",
                    action="AUTO_ESCALATE",
                    details={"reason": "Approver on leave without active delegation"},
                )

        saved = self.repository.save(entity, tenant_context=tc)

        self._record_audit(
            event_type=AuditEventType.WORKFLOW_REQUEST_SUBMITTED,
            actor_id=tc.user_id,
            action="WORKFLOW_SUBMITTED",
            resource_id=saved.id,
            details={
                "request_type": saved.request_type,
                "title": saved.title,
                "state": saved.state.value,
                "financial_impact": saved.financial_impact,
            },
            tenant_context=tc,
        )

        return saved

    # ==========================================================================
    # 2. Decision Processing (Approve, Reject, Request More Info)
    # ==========================================================================

    def record_decision(
        self,
        request_id: str,
        decision_req: WorkflowDecisionRequest,
        *,
        tenant_context: TenantContext,
    ) -> WorkflowRequest:
        """Records an approver's formal decision and advances the workflow chain."""
        tc = require_tenant_context(tenant_context)
        now = datetime.now(UTC)

        entity = self.repository.get(request_id, tenant_context=tc)
        if not entity:
            raise WorkflowNotFoundException(request_id)

        # 1. State integrity check
        if entity.state in {
            WorkflowState.APPROVED,
            WorkflowState.REJECTED,
            WorkflowState.WITHDRAWN,
            WorkflowState.EXPIRED,
            WorkflowState.APPLIED,
        }:
            raise WorkflowAlreadyFinalizedException(request_id, entity.state.value)

        curr_stage = entity.current_stage
        if not curr_stage:
            raise InvalidWorkflowTransitionException(request_id, entity.state.value, "DECIDE")

        # 2. Authorization check (Actor, Role, or Delegation)
        actor_id = tc.user_id
        delegations = self.repository.list_delegations(tenant_context=tc)

        # Lookup stage definition
        definition = self.repository.get_definition_by_type(entity.request_type, tenant_context=tc)
        if not definition:
            definition = get_default_workflow_definition_by_type(entity.request_type)
        stage_def = definition.stages[entity.current_stage_index] if definition else None

        on_behalf_of: str | None = None
        delegation_id: str | None = None

        if stage_def:
            res = self.resolver.resolve_approvers(
                request_id=entity.id,
                stage_def=stage_def,
                subject_entity=entity.subject_entity,
                tenant_context=tc,
                delegations=delegations,
                as_of=now,
                request_type=entity.request_type,
            )
            target_role = stage_def.approver_spec.target_role if stage_def else None
            user_has_target_role = bool(target_role and target_role in tc.roles)
            fallback_has_role = bool(
                stage_def
                and stage_def.approver_spec.fallback_role
                and stage_def.approver_spec.fallback_role in tc.roles
            )

            # Check authorization
            is_auth = (
                res.is_authorized(actor_id)
                or actor_id in curr_stage.assigned_approvers
                or user_has_target_role
                or fallback_has_role
                or tc.is_superuser
                or "GLOBAL_ADMIN" in tc.roles
                or "TENANT_ADMIN" in tc.roles
            )
            if not is_auth:
                raise UnauthorizedApproverException(request_id, actor_id, curr_stage.name)

            del_rule = res.get_delegation_for(actor_id)
            if del_rule:
                on_behalf_of = del_rule.original_approver_id
                delegation_id = del_rule.id
            elif actor_id not in res.primary_approvers and actor_id in res.effective_approvers:
                del_rule = next(
                    (
                        d
                        for d in delegations
                        if d.delegate_approver_id == actor_id
                        and d.is_currently_active(as_of=now, req_type=entity.request_type)
                    ),
                    None,
                )
                if del_rule:
                    on_behalf_of = del_rule.original_approver_id
                    delegation_id = del_rule.id

        # 3. Action handling
        if decision_req.decision == DecisionOutcome.REJECT:
            # Mandatory rejection comment rule (Enterprise Standard & Prompt 50)
            if not decision_req.comment or not decision_req.comment.strip():
                raise WorkflowMandatoryCommentException(request_id)

            decision = WorkflowDecision(
                stage_id=curr_stage.stage_id,
                decision=DecisionOutcome.REJECT,
                decided_by=actor_id,
                on_behalf_of=on_behalf_of,
                delegation_id=delegation_id,
                comment=decision_req.comment.strip(),
                timestamp=now,
            )
            curr_stage.decisions.append(decision)
            curr_stage.status = "REJECTED"
            prev_state = entity.state
            entity.state = WorkflowState.REJECTED

            entity.add_history(
                actor_id=actor_id,
                action="REJECT",
                previous_state=prev_state,
                new_state=WorkflowState.REJECTED,
                stage_id=curr_stage.stage_id,
                details={
                    "comment": decision.comment,
                    "on_behalf_of": on_behalf_of,
                    "delegation_id": delegation_id,
                },
            )

            self._record_audit(
                event_type=AuditEventType.WORKFLOW_REQUEST_REJECTED,
                actor_id=actor_id,
                action="WORKFLOW_REJECTED",
                resource_id=entity.id,
                details={"stage_id": curr_stage.stage_id, "comment": decision.comment},
                tenant_context=tc,
            )
            return self.repository.save(entity, tenant_context=tc)

        elif decision_req.decision == DecisionOutcome.REQUEST_MORE_INFO:
            if not decision_req.comment or not decision_req.comment.strip():
                raise WorkflowMandatoryCommentException(
                    f"A comment specifying requested information is required for request '{request_id}'."
                )

            decision = WorkflowDecision(
                stage_id=curr_stage.stage_id,
                decision=DecisionOutcome.REQUEST_MORE_INFO,
                decided_by=actor_id,
                on_behalf_of=on_behalf_of,
                delegation_id=delegation_id,
                comment=decision_req.comment.strip(),
                timestamp=now,
            )
            curr_stage.decisions.append(decision)
            entity.add_history(
                actor_id=actor_id,
                action="REQUEST_MORE_INFO",
                stage_id=curr_stage.stage_id,
                details={"comment": decision.comment},
            )
            self._record_audit(
                event_type=AuditEventType.WORKFLOW_INFO_REQUESTED,
                actor_id=actor_id,
                action="WORKFLOW_INFO_REQUESTED",
                resource_id=entity.id,
                details={"comment": decision.comment},
                tenant_context=tc,
            )
            return self.repository.save(entity, tenant_context=tc)

        elif decision_req.decision == DecisionOutcome.APPROVE:
            decision = WorkflowDecision(
                stage_id=curr_stage.stage_id,
                decision=DecisionOutcome.APPROVE,
                decided_by=actor_id,
                on_behalf_of=on_behalf_of,
                delegation_id=delegation_id,
                comment=decision_req.comment,
                timestamp=now,
            )
            curr_stage.decisions.append(decision)

            # Check stage completion (serial vs parallel quorum)
            if curr_stage.mode == ApprovalChainMode.SERIAL or curr_stage.is_quorum_met:
                curr_stage.status = "APPROVED"
                entity.add_history(
                    actor_id=actor_id,
                    action="STAGE_APPROVED",
                    stage_id=curr_stage.stage_id,
                    details={
                        "approvals": curr_stage.approved_count,
                        "quorum": curr_stage.quorum,
                        "on_behalf_of": on_behalf_of,
                    },
                )
                self._record_audit(
                    event_type=AuditEventType.WORKFLOW_STAGE_APPROVED,
                    actor_id=actor_id,
                    action="WORKFLOW_STAGE_APPROVED",
                    resource_id=entity.id,
                    details={"stage_id": curr_stage.stage_id},
                    tenant_context=tc,
                )

                # Check if further stages exist
                if entity.current_stage_index + 1 < len(entity.stages):
                    entity.current_stage_index += 1
                    next_stage = entity.stages[entity.current_stage_index]
                    next_stage.status = "IN_REVIEW"

                    # Resolve approvers for next stage
                    if definition and entity.current_stage_index < len(definition.stages):
                        next_def = definition.stages[entity.current_stage_index]
                        next_res = self.resolver.resolve_approvers(
                            request_id=entity.id,
                            stage_def=next_def,
                            subject_entity=entity.subject_entity,
                            tenant_context=tc,
                            delegations=delegations,
                            as_of=now,
                            request_type=entity.request_type,
                        )
                        next_stage.assigned_approvers = next_res.effective_approvers

                    entity.add_history(
                        actor_id="system",
                        action="ADVANCE_STAGE",
                        stage_id=next_stage.stage_id,
                        details={"next_stage_name": next_stage.name},
                    )
                else:
                    # Final stage completed: Request APPROVED!
                    entity.state = WorkflowState.APPROVED
                    entity.add_history(
                        actor_id=actor_id,
                        action="WORKFLOW_APPROVED",
                        previous_state=WorkflowState.IN_REVIEW,
                        new_state=WorkflowState.APPROVED,
                    )
                    self._record_audit(
                        event_type=AuditEventType.WORKFLOW_REQUEST_APPROVED,
                        actor_id=actor_id,
                        action="WORKFLOW_APPROVED",
                        resource_id=entity.id,
                        details={"request_type": entity.request_type},
                        tenant_context=tc,
                    )

                    # 4. ATOMIC APPLICATION ON APPROVAL
                    self._apply_approved_request(entity, actor_id=actor_id, tenant_context=tc)

            else:
                # Quorum not yet met in parallel mode
                entity.add_history(
                    actor_id=actor_id,
                    action="PARTIAL_APPROVAL",
                    stage_id=curr_stage.stage_id,
                    details={
                        "approvals_so_far": curr_stage.approved_count,
                        "quorum_required": curr_stage.quorum,
                    },
                )

            return self.repository.save(entity, tenant_context=tc)

        raise InvalidWorkflowTransitionException(
            request_id, entity.state.value, str(decision_req.decision)
        )

    def _apply_approved_request(
        self, entity: WorkflowRequest, *, actor_id: str, tenant_context: TenantContext
    ) -> None:
        """Executes atomic change application.

        Rule: "A failure to apply reverts to In Review with the error attached, never silently."
        """
        now = datetime.now(UTC)
        try:
            self.appliers.apply(entity, tenant_context=tenant_context)
            entity.state = WorkflowState.APPLIED
            entity.applied_at = now
            entity.applied_by = actor_id
            entity.error_message = None
            entity.add_history(
                actor_id=actor_id,
                action="APPLY",
                previous_state=WorkflowState.APPROVED,
                new_state=WorkflowState.APPLIED,
            )
            self._record_audit(
                event_type=AuditEventType.WORKFLOW_REQUEST_APPLIED,
                actor_id=actor_id,
                action="WORKFLOW_APPLIED",
                resource_id=entity.id,
                details={"request_type": entity.request_type},
                tenant_context=tenant_context,
            )
        except Exception as e:
            logger.error("Failed to atomically apply workflow '%s': %s", entity.id, e)
            entity.state = WorkflowState.IN_REVIEW
            entity.error_message = f"Application failed: {str(e)}"
            entity.add_history(
                actor_id="system",
                action="APPLICATION_FAILED",
                previous_state=WorkflowState.APPROVED,
                new_state=WorkflowState.IN_REVIEW,
                details={"error": str(e)},
            )
            self._record_audit(
                event_type=AuditEventType.WORKFLOW_APPLICATION_FAILED,
                actor_id=actor_id,
                action="WORKFLOW_APPLICATION_FAILED",
                resource_id=entity.id,
                details={"error": str(e)},
                tenant_context=tenant_context,
            )

    # ==========================================================================
    # 3. Withdrawal & Delegations
    # ==========================================================================

    def withdraw_request(
        self,
        request_id: str,
        withdraw_req: WorkflowWithdrawRequest,
        *,
        tenant_context: TenantContext,
    ) -> WorkflowRequest:
        """Allows requester to formally withdraw an in-flight submission."""
        tc = require_tenant_context(tenant_context)
        entity = self.repository.get(request_id, tenant_context=tc)
        if not entity:
            raise WorkflowNotFoundException(request_id)

        if entity.state in {
            WorkflowState.APPROVED,
            WorkflowState.REJECTED,
            WorkflowState.WITHDRAWN,
            WorkflowState.EXPIRED,
            WorkflowState.APPLIED,
        }:
            raise WorkflowAlreadyFinalizedException(request_id, entity.state.value)

        prev = entity.state
        entity.state = WorkflowState.WITHDRAWN
        entity.add_history(
            actor_id=tc.user_id,
            action="WITHDRAW",
            previous_state=prev,
            new_state=WorkflowState.WITHDRAWN,
            details={"reason": withdraw_req.reason},
        )
        saved = self.repository.save(entity, tenant_context=tc)

        self._record_audit(
            event_type=AuditEventType.WORKFLOW_REQUEST_WITHDRAWN,
            actor_id=tc.user_id,
            action="WORKFLOW_WITHDRAWN",
            resource_id=saved.id,
            details={"reason": withdraw_req.reason},
            tenant_context=tc,
        )
        return saved

    def register_delegation(
        self,
        req: DelegationCreateRequest,
        *,
        tenant_context: TenantContext,
    ) -> DelegationRule:
        """Registers a temporary out-of-office delegation rule."""
        tc = require_tenant_context(tenant_context)
        if req.start_date >= req.end_date:
            raise ValueError("Delegation start date must precede end date.")

        rule = DelegationRule(
            tenant_id=tc.tenant_id,
            original_approver_id=tc.user_id,
            delegate_approver_id=req.delegate_approver_id,
            start_date=req.start_date,
            end_date=req.end_date,
            request_types=req.request_types,
            reason=req.reason,
            is_active=True,
        )
        saved = self.repository.save_delegation(rule, tenant_context=tc)

        self._record_audit(
            event_type=AuditEventType.WORKFLOW_DELEGATION_REGISTERED,
            actor_id=tc.user_id,
            action="DELEGATION_REGISTERED",
            resource_id=saved.id,
            details={
                "delegate": req.delegate_approver_id,
                "start": req.start_date.isoformat(),
                "end": req.end_date.isoformat(),
            },
            tenant_context=tc,
        )
        return saved

    # ==========================================================================
    # 4. Approver Inbox & Requester View
    # ==========================================================================

    def get_approver_inbox(
        self,
        user_id: str,
        *,
        tenant_context: TenantContext,
    ) -> list[ApproverInboxItem]:
        """Returns all open decisions awaiting action by this user (directly or via delegation)."""
        tc = require_tenant_context(tenant_context)
        now = datetime.now(UTC)

        all_requests = self.repository.list(
            tenant_context=tc,
            filter_params={"state": WorkflowState.IN_REVIEW},
            limit=500,
        )

        delegations = self.repository.list_delegations(tenant_context=tc)
        inbox_items: list[ApproverInboxItem] = []

        for req in all_requests:
            stage = req.current_stage
            if not stage:
                continue

            # Check definition and stage spec
            definition = self.repository.get_definition_by_type(req.request_type, tenant_context=tc)
            if not definition:
                definition = get_default_workflow_definition_by_type(req.request_type)
            stage_def = (
                definition.stages[req.current_stage_index]
                if definition and req.current_stage_index < len(definition.stages)
                else None
            )

            target_role = stage_def.approver_spec.target_role if stage_def else None
            user_has_role = bool(
                target_role
                and (
                    target_role in tc.roles
                    or user_id in self.resolver._get_users_by_role(target_role, tc.tenant_id)
                )
            )

            is_assigned = (user_id in stage.assigned_approvers) or user_has_role

            # Check active delegation
            delegated_from: str | None = None
            is_del = False
            for d in delegations:
                if d.delegate_approver_id == user_id and d.is_currently_active(
                    as_of=now, req_type=req.request_type
                ):
                    if d.original_approver_id in stage.assigned_approvers or (
                        target_role
                        and d.original_approver_id
                        in self.resolver._get_users_by_role(target_role, tc.tenant_id)
                    ):
                        is_del = True
                        delegated_from = d.original_approver_id
                        break

            if is_assigned or is_del or tc.is_superuser or "TENANT_ADMIN" in tc.roles:
                rem_hours = self.sla_engine.calculate_remaining_working_hours(
                    now, req.due_date, req.working_schedule_id, tenant_id=tc.tenant_id
                )
                inbox_items.append(
                    ApproverInboxItem(
                        request_id=req.id,
                        request_type=req.request_type,
                        title=req.title,
                        state=req.state,
                        stage_id=stage.stage_id,
                        stage_name=stage.name,
                        requester=req.requester,
                        justification=req.justification,
                        payload=req.payload,
                        previous_values=req.previous_values,
                        financial_impact=req.financial_impact,
                        created_at=req.created_at,
                        submitted_at=req.submitted_at,
                        due_date=req.due_date,
                        sla_remaining_hours=rem_hours,
                        is_delegated=is_del,
                        delegated_from=delegated_from,
                        is_escalated=req.is_escalated,
                    )
                )

        return inbox_items

    def get_requester_view(
        self,
        user_id: str,
        *,
        tenant_context: TenantContext,
    ) -> list[RequesterViewItem]:
        """Returns tracking list of all requests submitted by the current user."""
        tc = require_tenant_context(tenant_context)
        now = datetime.now(UTC)

        user_requests = self.repository.list(
            tenant_context=tc,
            filter_params={"requester_id": user_id},
            limit=500,
        )

        view_items: list[RequesterViewItem] = []
        for req in user_requests:
            stage = req.current_stage
            duration = (now - req.created_at).total_seconds() / 3600.0

            view_items.append(
                RequesterViewItem(
                    request_id=req.id,
                    request_type=req.request_type,
                    title=req.title,
                    state=req.state,
                    current_stage_name=stage.name if stage else None,
                    pending_approvers=stage.assigned_approvers if stage else [],
                    duration_in_current_state_hours=round(duration, 2),
                    escalation_due_at=req.escalation_due_at,
                    due_date=req.due_date,
                    is_escalated=req.is_escalated,
                    created_at=req.created_at,
                )
            )
        return view_items

    # ==========================================================================
    # 5. Escalation & Expiration Background Evaluators
    # ==========================================================================

    def evaluate_escalations(self, *, tenant_context: TenantContext) -> list[WorkflowRequest]:
        """Identifies and executes automatic escalation for stalled in-review requests."""
        tc = require_tenant_context(tenant_context)
        now = datetime.now(UTC)

        open_requests = self.repository.list(
            tenant_context=tc,
            filter_params={"state": WorkflowState.IN_REVIEW},
            limit=500,
        )

        escalated: list[WorkflowRequest] = []
        for req in open_requests:
            if not req.is_escalated and req.escalation_due_at and now >= req.escalation_due_at:
                req.is_escalated = True
                req.escalation_path.is_escalated = True
                req.escalation_path.escalated_at = now
                req.escalation_path.escalated_to = [req.escalation_path.escalate_to_role]
                req.add_history(
                    actor_id="system",
                    action="AUTO_ESCALATE",
                    details={"escalated_to": req.escalation_path.escalate_to_role},
                )
                saved = self.repository.save(req, tenant_context=tc)
                escalated.append(saved)
                self._record_audit(
                    event_type=AuditEventType.WORKFLOW_REQUEST_ESCALATED,
                    actor_id="system",
                    action="WORKFLOW_ESCALATED",
                    resource_id=req.id,
                    details={"escalated_to": req.escalation_path.escalate_to_role},
                    tenant_context=tc,
                )

        return escalated

    def evaluate_expirations(self, *, tenant_context: TenantContext) -> list[WorkflowRequest]:
        """Automatically expires or rejects requests exceeding configured SLA."""
        tc = require_tenant_context(tenant_context)
        now = datetime.now(UTC)

        open_requests = self.repository.list(
            tenant_context=tc,
            filter_params={"state": WorkflowState.IN_REVIEW},
            limit=500,
        )

        expired: list[WorkflowRequest] = []
        for req in open_requests:
            if req.due_date and now >= req.due_date:
                req.sla_breached = True
                definition = self.repository.get_definition_by_type(
                    req.request_type, tenant_context=tc
                )
                if not definition:
                    definition = get_default_workflow_definition_by_type(req.request_type)

                if definition and definition.auto_reject_on_expiry:
                    req.state = WorkflowState.EXPIRED
                    req.add_history(
                        actor_id="system",
                        action="AUTO_EXPIRE",
                        previous_state=WorkflowState.IN_REVIEW,
                        new_state=WorkflowState.EXPIRED,
                        details={"due_date": req.due_date.isoformat()},
                    )
                    saved = self.repository.save(req, tenant_context=tc)
                    expired.append(saved)
                    self._record_audit(
                        event_type=AuditEventType.WORKFLOW_REQUEST_EXPIRED,
                        actor_id="system",
                        action="WORKFLOW_EXPIRED",
                        resource_id=req.id,
                        details={"due_date": req.due_date.isoformat()},
                        tenant_context=tc,
                    )

        return expired

    # ==========================================================================
    # 6. Workflow Operational Metrics
    # ==========================================================================

    def get_metrics(self, *, tenant_context: TenantContext) -> WorkflowMetricsReport:
        """Calculates workflow throughput, SLA breaches, and approver velocity metrics."""
        tc = require_tenant_context(tenant_context)
        now = datetime.now(UTC)

        all_requests = self.repository.list(tenant_context=tc, limit=1000)

        by_type: dict[str, int] = {}
        by_age: dict[str, int] = {"< 24h": 0, "24-48h": 0, "48-72h": 0, "> 72h": 0}
        decision_durations: list[float] = []
        sla_breaches = 0
        approvals_by_user: dict[str, int] = {}
        rejections_by_user: dict[str, int] = {}

        for r in all_requests:
            if r.state in {WorkflowState.SUBMITTED, WorkflowState.IN_REVIEW}:
                by_type[r.request_type] = by_type.get(r.request_type, 0) + 1
                age_hrs = (now - r.created_at).total_seconds() / 3600.0
                if age_hrs < 24:
                    by_age["< 24h"] += 1
                elif age_hrs < 48:
                    by_age["24-48h"] += 1
                elif age_hrs < 72:
                    by_age["48-72h"] += 1
                else:
                    by_age["> 72h"] += 1

            if r.sla_breached or (
                r.due_date
                and now > r.due_date
                and r.state in {WorkflowState.SUBMITTED, WorkflowState.IN_REVIEW}
            ):
                sla_breaches += 1

            # Count decisions and measure durations
            for s in r.stages:
                for d in s.decisions:
                    dur = (d.timestamp - r.created_at).total_seconds() / 3600.0
                    decision_durations.append(max(0.0, dur))
                    if d.decision == DecisionOutcome.APPROVE:
                        approvals_by_user[d.decided_by] = approvals_by_user.get(d.decided_by, 0) + 1
                    elif d.decision == DecisionOutcome.REJECT:
                        rejections_by_user[d.decided_by] = (
                            rejections_by_user.get(d.decided_by, 0) + 1
                        )

        avg_time = sum(decision_durations) / len(decision_durations) if decision_durations else 0.0
        worst_time = max(decision_durations) if decision_durations else 0.0
        total_reqs = len(all_requests)
        breach_rate = (sla_breaches / total_reqs * 100.0) if total_reqs > 0 else 0.0

        return WorkflowMetricsReport(
            open_requests_by_type=by_type,
            open_requests_by_age=by_age,
            average_time_to_decision_hours=round(avg_time, 2),
            worst_time_to_decision_hours=round(worst_time, 2),
            sla_breaches_count=sla_breaches,
            sla_breach_rate_pct=round(breach_rate, 2),
            approvals_by_approver=approvals_by_user,
            rejections_by_approver=rejections_by_user,
        )

    # ==========================================================================
    # 7. Helper CRUD
    # ==========================================================================

    def get_request(self, request_id: str, *, tenant_context: TenantContext) -> WorkflowRequest:
        """Retrieves request or raises WorkflowNotFoundException."""
        tc = require_tenant_context(tenant_context)
        req = self.repository.get(request_id, tenant_context=tc)
        if not req:
            raise WorkflowNotFoundException(request_id)
        return req

    def list_requests(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowRequest]:
        """Lists workflow requests."""
        tc = require_tenant_context(tenant_context)
        return self.repository.list(
            tenant_context=tc, filter_params=filter_params, limit=limit, offset=offset
        )

    def _record_audit(
        self,
        event_type: AuditEventType,
        actor_id: str,
        action: str,
        resource_id: str,
        details: dict[str, Any],
        tenant_context: TenantContext,
    ) -> None:
        """Emits audit event into audit trail."""
        try:
            self.audit_service.append_event(
                tenant_context=tenant_context,
                event_in=AuditEventCreate(
                    event_type=event_type,
                    actor_id=actor_id,
                    actor_roles=tenant_context.roles,
                    action=action,
                    resource_type="WORKFLOW_REQUEST",
                    resource_id=resource_id,
                    details=details,
                ),
            )
        except Exception as e:
            logger.debug("Failed appending workflow audit event: %s", e)


_workflow_service_instance: WorkflowService | None = None


def get_workflow_service() -> WorkflowService:
    """Returns singleton WorkflowService instance."""
    global _workflow_service_instance
    if _workflow_service_instance is None:
        _workflow_service_instance = WorkflowService()
    return _workflow_service_instance


def reset_workflow_service() -> None:
    """Resets service singleton for test isolation."""
    global _workflow_service_instance
    _workflow_service_instance = None
