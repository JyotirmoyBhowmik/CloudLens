"""Workflow, Approval and Delegation Domain Models (Prompt 50).

Enforces:
- Generic workflow engine with 8 states:
  Draft, Submitted, In Review, Approved, Rejected, Withdrawn, Expired, Applied.
- Master-data-driven workflow definitions (serial, parallel, quorum, SLA, escalation, auto-approve, auto-reject).
- Dynamic approver resolution (role, scope ownership, cost-centre owner, business-unit owner, budget owner, explicit list).
- Delegation, out-of-office, and automatic escalation.
- Approver inbox and requester view with context, diff, financial impact, and mandatory rejection comment.
- Atomic apply-on-approval with error state reversion to In Review.
- Workflow audit trail and operational metrics.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from domain.models.base import CanonicalEntity
from domain.models.enums import (
    ApprovalChainMode,
    ApproverResolutionType,
    DecisionOutcome,
    WorkflowState,
)
from domain.models.exceptions import WorkflowMandatoryCommentException


class SubjectEntity(BaseModel):
    """Target entity or resource subject to the workflow request."""

    entity_type: str = Field(
        ..., description="Target entity type, e.g. budget, override, policy_exemption, role"
    )
    entity_id: str = Field(..., description="Unique identifier of target entity")
    scope_type: str | None = Field(default=None, description="Optional organizational scope level")
    scope_id: str | None = Field(default=None, description="Optional target scope identifier")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional context metadata"
    )


class RequesterInfo(BaseModel):
    """Actor identity who initiated the workflow request."""

    requester_id: str = Field(..., description="Principal user ID or service identity")
    requester_email: str | None = Field(default=None, description="Requester email address")
    requester_name: str | None = Field(default=None, description="Display name of requester")


class WorkflowDecision(BaseModel):
    """Immutable record of an approver's formal decision."""

    decision_id: str = Field(
        default_factory=lambda: f"dec-{uuid.uuid4().hex[:8]}",
        description="Unique decision record identifier",
    )
    stage_id: str = Field(..., description="Stage where decision was rendered")
    decision: DecisionOutcome = Field(
        ..., description="Decision outcome: APPROVE, REJECT, REQUEST_MORE_INFO"
    )
    decided_by: str = Field(..., description="Actor ID who rendered the decision")
    on_behalf_of: str | None = Field(
        default=None, description="Original approver ID if acting via delegation"
    )
    delegation_id: str | None = Field(
        default=None, description="Delegation rule ID if acting on behalf of another"
    )
    comment: str | None = Field(
        default=None, description="Decision rationale (mandatory on rejection)"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Decision UTC timestamp"
    )


class WorkflowApproverSpec(BaseModel):
    """Specification for dynamically resolving approvers at a workflow stage."""

    resolution_type: ApproverResolutionType = Field(
        default=ApproverResolutionType.ROLE,
        description="Resolution strategy: ROLE, SCOPE_OWNERSHIP, COST_CENTRE_OWNER, BUSINESS_UNIT_OWNER, BUDGET_OWNER, EXPLICIT_LIST",
    )
    target_role: str | None = Field(
        default=None,
        description="Target role code when resolving by ROLE (e.g. FINOPS_ADMIN, SECURITY_ADMIN)",
    )
    explicit_approvers: list[str] = Field(
        default_factory=list,
        description="Explicit approver IDs or fallback list",
    )
    fallback_role: str = Field(
        default="TENANT_ADMIN",
        description="Fallback role if primary resolution yields no individual",
    )


class WorkflowStageDefinition(BaseModel):
    """Definition of an approval stage within a workflow chain."""

    stage_id: str = Field(..., description="Stable stage identifier")
    name: str = Field(..., description="Stage title, e.g. Line Manager Approval")
    sequence_order: int = Field(default=1, description="Execution sequence index (1, 2, ...)")
    mode: ApprovalChainMode = Field(
        default=ApprovalChainMode.SERIAL,
        description="Execution mode: SERIAL or PARALLEL",
    )
    quorum: int = Field(
        default=1,
        ge=1,
        description="Minimum number of approvals required if PARALLEL",
    )
    approver_spec: WorkflowApproverSpec = Field(
        default_factory=WorkflowApproverSpec,
        description="Dynamic approver resolution rule",
    )


class WorkflowEscalationPath(BaseModel):
    """Escalation routing and threshold when a request remains unacted upon."""

    escalate_to_role: str = Field(
        default="TENANT_ADMIN",
        description="Role or manager group to escalate to",
    )
    escalate_after_hours: int = Field(
        default=24,
        ge=1,
        description="Working hours elapsed before automatic escalation triggers",
    )
    escalated_to: list[str] = Field(
        default_factory=list,
        description="Specific identities escalated to",
    )
    escalated_at: datetime | None = Field(
        default=None,
        description="Timestamp when escalation occurred",
    )
    is_escalated: bool = Field(
        default=False,
        description="Whether this stage/request has escalated",
    )


class WorkflowTriggerCondition(BaseModel):
    """Condition that determines whether a request triggers this workflow."""

    amount_gt: float | None = Field(
        default=None,
        description="Trigger if financial amount strictly exceeds threshold (e.g. Budget > $10,000)",
    )
    attributes_match: dict[str, Any] = Field(
        default_factory=dict,
        description="Attribute matching rules on payload",
    )
    always: bool = Field(
        default=False,
        description="If True, unconditionally triggers approval workflow",
    )

    def matches(self, payload: dict[str, Any], financial_impact: float | None = None) -> bool:
        """Evaluates whether the given payload/impact satisfies the trigger condition."""
        if self.always:
            return True
        if self.amount_gt is not None:
            amt = financial_impact
            if amt is None:
                amt = float(payload.get("amount", payload.get("new_amount", 0.0)))
            if amt <= self.amount_gt:
                return False
        if self.attributes_match:
            for k, expected_v in self.attributes_match.items():
                if payload.get(k) != expected_v:
                    return False
        return True


class WorkflowDefinition(BaseModel):
    """Master Data definition of a governance workflow process (Prompt 50)."""

    id: str = Field(
        default_factory=lambda: f"wf-def-{uuid.uuid4().hex[:8]}",
        description="Unique workflow definition identifier",
    )
    tenant_id: str | None = Field(
        default=None,
        description="Tenant identifier (None for global system master)",
    )
    request_type: str = Field(
        ...,
        description="Request type code (e.g. BUDGET_APPROVAL, OVERRIDE_APPROVAL)",
    )
    entity_type: str = Field(
        ...,
        description="Entity type governed (e.g. budget, override, policy_exemption)",
    )
    name: str = Field(..., description="Human-readable title")
    description: str = Field(default="", description="Detailed purpose of workflow")
    trigger_condition: WorkflowTriggerCondition = Field(
        default_factory=WorkflowTriggerCondition,
        description="Trigger rules",
    )
    stages: list[WorkflowStageDefinition] = Field(
        default_factory=list,
        description="Ordered approval stages",
    )
    approval_mode: ApprovalChainMode = Field(
        default=ApprovalChainMode.SERIAL,
        description="Default chain mode",
    )
    quorum: int = Field(default=1, ge=1, description="Default chain quorum")
    sla_working_hours: int = Field(
        default=24,
        ge=1,
        description="SLA in operational working hours",
    )
    working_schedule_id: str = Field(
        default="WW_STANDARD_MON_FRI",
        description="Reference to working-week master definition",
    )
    escalation_path: WorkflowEscalationPath = Field(
        default_factory=WorkflowEscalationPath,
        description="Default escalation configuration",
    )
    auto_approve_conditions: dict[str, Any] | None = Field(
        default=None,
        description="Conditions under which the request is automatically approved",
    )
    auto_reject_on_expiry: bool = Field(
        default=True,
        description="Whether to automatically transition to REJECTED once SLA/due date expires",
    )
    is_active: bool = Field(default=True, description="Whether definition is active")
    version: int = Field(default=1, description="Definition version")


class WorkflowStage(BaseModel):
    """Runtime representation and state of an approval stage."""

    stage_id: str = Field(..., description="Stage identifier matching definition")
    name: str = Field(..., description="Stage title")
    sequence_order: int = Field(default=1, description="Stage sequence index")
    mode: ApprovalChainMode = Field(default=ApprovalChainMode.SERIAL, description="Execution mode")
    quorum: int = Field(default=1, ge=1, description="Approvals needed to advance")
    approver_spec: WorkflowApproverSpec = Field(default_factory=WorkflowApproverSpec)
    assigned_approvers: list[str] = Field(
        default_factory=list,
        description="Resolved user IDs authorized to approve this stage",
    )
    status: str = Field(
        default="PENDING",
        description="Stage lifecycle: PENDING, IN_REVIEW, APPROVED, REJECTED, SKIPPED",
    )
    decisions: list[WorkflowDecision] = Field(
        default_factory=list,
        description="Decisions recorded at this stage",
    )

    @property
    def approved_count(self) -> int:
        return sum(1 for d in self.decisions if d.decision == DecisionOutcome.APPROVE)

    @property
    def is_quorum_met(self) -> bool:
        return self.approved_count >= self.quorum


class WorkflowHistoryEntry(BaseModel):
    """Immutable audit record of a state transition, decision, or event."""

    id: str = Field(
        default_factory=lambda: f"hist-{uuid.uuid4().hex[:8]}",
        description="Unique history record identifier",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Event UTC timestamp",
    )
    actor_id: str = Field(..., description="Identity responsible for the action")
    action: str = Field(
        ..., description="Action name, e.g. SUBMIT, APPROVE, REJECT, ESCALATE, APPLY"
    )
    previous_state: WorkflowState | None = Field(
        default=None, description="Previous workflow state"
    )
    new_state: WorkflowState | None = Field(default=None, description="New workflow state")
    stage_id: str | None = Field(default=None, description="Associated stage ID")
    details: dict[str, Any] = Field(default_factory=dict, description="Contextual payload details")


class DelegationRule(BaseModel):
    """Out-of-office delegation rule empowering a temporary substitute approver."""

    id: str = Field(
        default_factory=lambda: f"del-{uuid.uuid4().hex[:8]}",
        description="Unique delegation rule ID",
    )
    tenant_id: str = Field(..., description="Tenant boundary")
    original_approver_id: str = Field(..., description="User ID delegating authority")
    delegate_approver_id: str = Field(..., description="User ID receiving temporary authority")
    start_date: datetime = Field(..., description="Delegation start timestamp UTC")
    end_date: datetime = Field(..., description="Delegation end timestamp UTC")
    request_types: list[str] = Field(
        default_factory=list,
        description="Scope of request types (empty implies all)",
    )
    reason: str = Field(..., description="Justification (e.g. Annual leave, Sickness)")
    is_active: bool = Field(default=True, description="Whether rule is active")

    def is_currently_active(
        self, as_of: datetime | None = None, req_type: str | None = None
    ) -> bool:
        """Determines if the delegation is currently in effect."""
        if not self.is_active:
            return False
        now = as_of or datetime.now(UTC)
        if now < self.start_date or now > self.end_date:
            return False
        if self.request_types and req_type and req_type not in self.request_types:
            return False
        return True


class WorkflowRequest(CanonicalEntity):
    """First-class canonical governance workflow request entity (Prompt 50)."""

    tenant_id: str = Field(..., description="Tenant boundary identifier")
    definition_id: str | None = Field(default=None, description="Governing definition ID")
    request_type: str = Field(
        ..., description="Type code (e.g. BUDGET_APPROVAL, OVERRIDE_APPROVAL)"
    )
    title: str = Field(..., description="Summary headline")
    subject_entity: SubjectEntity = Field(..., description="Target entity details")
    requester: RequesterInfo = Field(..., description="Requester identity")
    justification: str = Field(..., description="Mandatory business and technical rationale")
    payload: dict[str, Any] = Field(default_factory=dict, description="Proposed changes / data")
    previous_values: dict[str, Any] | None = Field(
        default=None,
        description="Pre-change snapshot for diff inspection",
    )
    financial_impact: float | None = Field(
        default=None,
        description="Calculable monetary impact in reporting currency",
    )
    state: WorkflowState = Field(
        default=WorkflowState.SUBMITTED,
        description="Current state: Draft, Submitted, In Review, Approved, Rejected, Withdrawn, Expired, Applied",
    )
    current_stage_index: int = Field(default=0, description="Active stage index")
    stages: list[WorkflowStage] = Field(default_factory=list, description="Instantiated stages")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Creation timestamp UTC"
    )
    submitted_at: datetime | None = Field(default=None, description="Submission timestamp UTC")
    due_date: datetime | None = Field(default=None, description="SLA deadline UTC")
    sla_working_hours: int = Field(default=24, description="Configured SLA working hours")
    working_schedule_id: str = Field(
        default="WW_STANDARD_MON_FRI", description="Working week calendar ID"
    )
    sla_breached: bool = Field(default=False, description="Whether SLA deadline was breached")
    escalation_path: WorkflowEscalationPath = Field(
        default_factory=WorkflowEscalationPath,
        description="Escalation routing",
    )
    escalation_due_at: datetime | None = Field(
        default=None, description="Timestamp when escalation triggers"
    )
    is_escalated: bool = Field(default=False, description="Whether request has escalated")
    history: list[WorkflowHistoryEntry] = Field(default_factory=list, description="Audit history")
    error_message: str | None = Field(
        default=None,
        description="Error details if atomic application failed, reverting to IN_REVIEW",
    )
    applied_at: datetime | None = Field(default=None, description="Atomic application timestamp")
    applied_by: str | None = Field(
        default=None, description="Actor or engine that applied the change"
    )

    @property
    def current_stage(self) -> WorkflowStage | None:
        if 0 <= self.current_stage_index < len(self.stages):
            return self.stages[self.current_stage_index]
        return None

    def add_history(
        self,
        actor_id: str,
        action: str,
        previous_state: WorkflowState | None = None,
        new_state: WorkflowState | None = None,
        stage_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Appends an immutable audit history entry."""
        self.history.append(
            WorkflowHistoryEntry(
                actor_id=actor_id,
                action=action,
                previous_state=previous_state or self.state,
                new_state=new_state or self.state,
                stage_id=stage_id,
                details=details or {},
            )
        )


# ==============================================================================
# Request DTOs & Views
# ==============================================================================


class WorkflowSubmitRequest(BaseModel):
    """Payload to submit a proposed change into the workflow engine."""

    request_type: str = Field(..., description="Canonical request type code")
    title: str = Field(..., description="Human-readable headline")
    subject_entity: SubjectEntity = Field(..., description="Target entity")
    justification: str = Field(..., description="Mandatory rationale")
    payload: dict[str, Any] = Field(..., description="Proposed new values")
    previous_values: dict[str, Any] | None = Field(
        default=None, description="Previous values for diff calculation"
    )
    financial_impact: float | None = Field(default=None, description="Calculable financial impact")

    @field_validator("justification")
    @classmethod
    def validate_justification_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise WorkflowMandatoryCommentException("Justification must not be empty.")
        return v.strip()


class WorkflowDecisionRequest(BaseModel):
    """Payload to approve, reject, or request information on a pending request."""

    decision: DecisionOutcome = Field(..., description="APPROVE, REJECT, or REQUEST_MORE_INFO")
    comment: str | None = Field(
        default=None, description="Required for REJECT and REQUEST_MORE_INFO"
    )


class WorkflowWithdrawRequest(BaseModel):
    """Payload to withdraw an open submission."""

    reason: str = Field(..., description="Withdrawal reason")


class DelegationCreateRequest(BaseModel):
    """Payload to establish temporary out-of-office delegation."""

    delegate_approver_id: str = Field(..., description="User ID of authorized delegate")
    start_date: datetime = Field(..., description="Start timestamp UTC")
    end_date: datetime = Field(..., description="End timestamp UTC")
    request_types: list[str] = Field(
        default_factory=list, description="Specific request types or empty for all"
    )
    reason: str = Field(..., description="Reason for delegation")


class ApproverInboxItem(BaseModel):
    """Contextual inbox view item presenting a decision awaiting the actor."""

    request_id: str
    request_type: str
    title: str
    state: WorkflowState
    stage_id: str
    stage_name: str
    requester: RequesterInfo
    justification: str
    payload: dict[str, Any]
    previous_values: dict[str, Any] | None = None
    financial_impact: float | None = None
    created_at: datetime
    submitted_at: datetime | None
    due_date: datetime | None
    sla_remaining_hours: float | None = None
    is_delegated: bool = False
    delegated_from: str | None = None
    is_escalated: bool = False


class RequesterViewItem(BaseModel):
    """Requester tracking view item displaying status and escalation trajectory."""

    request_id: str
    request_type: str
    title: str
    state: WorkflowState
    current_stage_name: str | None = None
    pending_approvers: list[str] = Field(default_factory=list)
    duration_in_current_state_hours: float
    escalation_due_at: datetime | None = None
    due_date: datetime | None = None
    is_escalated: bool = False
    created_at: datetime


class WorkflowMetricsReport(BaseModel):
    """Comprehensive performance and adherence metrics for governance workflows."""

    open_requests_by_type: dict[str, int]
    open_requests_by_age: dict[str, int]
    average_time_to_decision_hours: float
    worst_time_to_decision_hours: float
    sla_breaches_count: int
    sla_breach_rate_pct: float
    approvals_by_approver: dict[str, int]
    rejections_by_approver: dict[str, int]
