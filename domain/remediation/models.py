"""Domain Models for Remediation, Task Assignment, and Accountability (Prompt 51).

Enforces:
- BBP Section 34 (Findings) & BBP Section 35 (Alerts) & BBP Section 36 (Governance Exceptions).
- Remediation task as a first-class entity with full lifecycle, evidence linkage,
  ownership resolution, working-hours SLA, automated verification, and realised-saving ledger.
- Master-data-driven states (minimum 11 states), priorities, categories, and closure codes.
- Accountability views and leaderboard-free trends over time (report trends, not people).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, Field, field_validator

from domain.models.base import CanonicalEntity
from domain.models.enums import (
    RealisedSavingMethod,
    TaskAssignmentRule,
    TaskCategory,
    TaskClosureCode,
    TaskPriority,
    TaskSource,
    TaskState,
)
from domain.models.exceptions import MandatoryReasonException

# ==============================================================================
# 1. Subject Entity & History Models
# ==============================================================================


class SubjectEntity(BaseModel):
    """Reference to the target entity requiring remediation."""

    entity_type: str = Field(
        ..., description="Target entity kind (e.g. resource, connector, budget, policy)"
    )
    entity_id: str = Field(..., description="Identifier of the target entity")
    entity_name: str = Field(default="", description="Display name of target entity")
    scope_type: str | None = Field(
        default=None, description="Scope dimension (subscription, account, project)"
    )
    scope_id: str | None = Field(default=None, description="Scope identifier")
    provider: str | None = Field(
        default=None, description="Cloud provider code (AWS, AZURE, GCP, OCI)"
    )
    application_id: str | None = Field(
        default=None, description="Associated application identifier"
    )
    business_unit_id: str | None = Field(
        default=None, description="Associated business unit identifier"
    )
    cost_centre_id: str | None = Field(
        default=None, description="Associated cost centre identifier"
    )


class RemediationHistoryEntry(BaseModel):
    """Immutable audit entry recording a state change, action, or note."""

    id: str = Field(
        default_factory=lambda: f"hist-rem-{uuid.uuid4().hex[:8]}",
        description="Unique history record identifier",
    )
    timestamp: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC),
        description="Event UTC timestamp",
    )
    actor_id: str = Field(..., description="Actor identity or system rule executing transition")
    action: str = Field(
        ..., description="Action name (e.g. CREATED, ASSIGNED, RESOLVED, VERIFIED, REOPENED)"
    )
    from_state: str | None = Field(default=None, description="Prior task state")
    to_state: str | None = Field(default=None, description="New task state")
    reason: str | None = Field(
        default=None, description="Mandatory or explanatory reason code/note"
    )
    note: str | None = Field(default=None, description="Additional context or system explanation")
    details: dict[str, Any] = Field(
        default_factory=dict, description="Metadata snapshot at transition"
    )


# ==============================================================================
# 2. First-Class Remediation Task Entity
# ==============================================================================


class RemediationTask(CanonicalEntity):
    """Canonical Remediation Task representing an actionable problem or violation (Prompt 51)."""

    tenant_id: str = Field(..., description="Tenant boundary isolating task state")
    source: TaskSource = Field(..., description="Detection trigger source")
    subject_entity: SubjectEntity = Field(..., description="Target cloud entity under remediation")
    title: str = Field(..., min_length=3, description="Concise human-readable headline")
    description: str = Field(
        ..., description="Clear explanation of problem and remediation guidance"
    )
    evidence_linkage: dict[str, Any] = Field(
        default_factory=dict,
        description="Empirical metric records, snapshots, or alert evidence backing the task",
    )
    assignee_id: str = Field(..., description="Accountable owner user ID, team ID, or queue ID")
    assignee_type: str = Field(
        default="USER", description="Assignee category: USER, TEAM, or QUEUE"
    )
    assigning_actor: str = Field(
        default="SYSTEM_RULE",
        description="Actor or automated rule that established assignment",
    )
    assignment_rule: TaskAssignmentRule = Field(
        default=TaskAssignmentRule.TECHNICAL_OWNER,
        description="Precedence rule that produced the assignee",
    )
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM, description="Task urgency priority")
    due_date: dt.datetime = Field(..., description="Working-hours SLA deadline in UTC")
    sla_working_hours: float = Field(
        default=48.0, description="Allocated working hours for remediation"
    )
    estimated_saving: float | None = Field(
        default=None,
        description="Estimated excess cost, potential saving, or financial impact",
    )
    realised_saving: float | None = Field(
        default=None,
        description="Actual empirical saving confirmed upon verified resolution",
    )
    realised_saving_method: RealisedSavingMethod | None = Field(
        default=None,
        description="Calculation method used to compute realised saving",
    )
    state: TaskState = Field(
        default=TaskState.OPEN, description="Lifecycle state (11 canonical states)"
    )
    category: TaskCategory = Field(
        default=TaskCategory.CUSTOM, description="Problem taxonomy category"
    )
    reason_code: str | None = Field(
        default=None,
        description="Justification code required on rejection or deferral",
    )
    closure_code: TaskClosureCode | None = Field(
        default=None,
        description="Final disposition code upon task closure",
    )
    deferral_expiry: dt.datetime | None = Field(
        default=None,
        description="Expiration timestamp UTC for deferred tasks (reopens upon expiry)",
    )
    risk_accepted: bool = Field(
        default=False, description="True if organizational risk was formally accepted"
    )
    risk_accepted_expiry: dt.datetime | None = Field(
        default=None,
        description="Expiration timestamp UTC for accepted risk",
    )
    approval_workflow_id: str | None = Field(
        default=None,
        description="Linked Prompt 50 workflow request ID if deferral/acceptance requires approval",
    )
    alert_id: str | None = Field(
        default=None, description="Bidirectional link to originating alert"
    )
    finding_id: str | None = Field(default=None, description="Link to originating policy finding")
    governance_exception_id: str | None = Field(
        default=None,
        description="Governance exception record ID if assignment had to use fallback",
    )
    itsm_ticket_id: str | None = Field(
        default=None,
        description="External ticketing ticket reference (Jira, ServiceNow)",
    )
    verification_attempts: int = Field(
        default=0, ge=0, description="Count of verification passes executed"
    )
    verification_notes: list[str] = Field(
        default_factory=list, description="Notes from verification passes"
    )
    history: list[RemediationHistoryEntry] = Field(
        default_factory=list, description="Audit transition trail"
    )
    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC),
        description="Creation timestamp",
    )
    updated_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC),
        description="Last update timestamp",
    )
    closed_at: dt.datetime | None = Field(
        default=None, description="Timestamp when task reached terminal state"
    )

    def add_history(
        self,
        action: str,
        actor_id: str,
        from_state: str | None = None,
        to_state: str | None = None,
        reason: str | None = None,
        note: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Appends an immutable audit event to the task history."""
        self.history.append(
            RemediationHistoryEntry(
                actor_id=actor_id,
                action=action,
                from_state=from_state or self.state.value,
                to_state=to_state or self.state.value,
                reason=reason,
                note=note,
                details=details or {},
            )
        )
        self.updated_at = dt.datetime.now(dt.UTC)

    @property
    def is_overdue(self) -> bool:
        """Determines if the task has breached its SLA due date."""
        if self.state in {TaskState.CLOSED, TaskState.REJECTED, TaskState.DUPLICATE}:
            return False
        return dt.datetime.now(dt.UTC) > self.due_date

    @property
    def is_terminal(self) -> bool:
        """Returns True if the task has reached a terminal lifecycle state."""
        return self.state in {TaskState.CLOSED, TaskState.REJECTED, TaskState.DUPLICATE}


# ==============================================================================
# 3. Realised-Saving Ledger Entity & Reporting
# ==============================================================================


class RealisedSavingEntry(BaseModel):
    """Immutable ledger record documenting an empirical saving achieved through verified remediation."""

    id: str = Field(
        default_factory=lambda: f"save-{uuid.uuid4().hex[:10]}",
        description="Unique saving record identifier",
    )
    tenant_id: str = Field(..., description="Tenant boundary")
    task_id: str = Field(..., description="Associated remediation task ID")
    entity_id: str = Field(..., description="Target cloud entity ID")
    category: str = Field(..., description="Problem category (e.g. SCHEDULE_BREACH, IDLE_RESOURCE)")
    team_id: str = Field(..., description="Accountable team or owner department")
    period: str = Field(
        ..., description="Calendar or fiscal period code (e.g. '2026-10', '2026-Q4')"
    )
    realised_amount: float = Field(
        ..., ge=0.0, description="Realised saving amount in reporting currency"
    )
    currency: str = Field(default="USD", description="Currency code")
    calculation_method: RealisedSavingMethod = Field(
        ...,
        description="Empirical calculation method backing the saving",
    )
    verified_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC),
        description="Timestamp of verified closure",
    )
    verified_by: str = Field(
        default="system-verifier", description="Actor or engine verifying condition"
    )


class RealisedSavingReport(BaseModel):
    """Cumulative realised saving report aggregated across period, team, and category."""

    total_realised_saving: float = 0.0
    currency: str = "USD"
    savings_by_period: dict[str, float] = Field(default_factory=dict)
    savings_by_team: dict[str, float] = Field(default_factory=dict)
    savings_by_category: dict[str, float] = Field(default_factory=dict)
    savings_by_method: dict[str, float] = Field(default_factory=dict)
    entries_count: int = 0
    entries: list[RealisedSavingEntry] = Field(default_factory=list)


# ==============================================================================
# 4. Master Data Creation Rule Model
# ==============================================================================


class TaskCreationRule(BaseModel):
    """Master data rule controlling automatic task creation for a detection source."""

    code: str = Field(..., description="Unique rule code (e.g. RULE_UNOWNED_RESOURCE)")
    source_code: TaskSource = Field(..., description="Detection source trigger")
    enabled: bool = Field(default=True, description="Whether automatic task creation is enabled")
    category: TaskCategory = Field(..., description="Assigned task category")
    default_priority: TaskPriority = Field(
        default=TaskPriority.MEDIUM, description="Default priority"
    )
    estimated_saving_formula: str | None = Field(
        default=None,
        description="Formula or field to extract estimated saving (e.g. excess_cost, idle_cost)",
    )
    auto_assign: bool = Field(
        default=True, description="Whether to execute automatic ownership assignment"
    )
    default_sla_hours: int = Field(default=48, description="Default working hours SLA")


# ==============================================================================
# 5. Accountability & Trend Views
# ==============================================================================


class AgeingBucket(BaseModel):
    """Breakdown of open remediation tasks by age bracket."""

    bucket_name: str
    count: int
    total_estimated_saving: float = 0.0
    task_ids: list[str] = Field(default_factory=list)


class AgeingReport(BaseModel):
    """Accountability ageing distribution for open remediation tasks."""

    total_open_tasks: int
    bracket_0_to_7_days: AgeingBucket
    bracket_8_to_30_days: AgeingBucket
    bracket_31_to_90_days: AgeingBucket
    bracket_over_90_days: AgeingBucket


class TrendPoint(BaseModel):
    """Leaderboard-free trend datapoint comparing opened vs closed tasks over time."""

    date: str = Field(..., description="Date string YYYY-MM-DD")
    opened_count: int = 0
    closed_count: int = 0
    net_backlog_delta: int = 0
    realised_savings_amount: float = 0.0


class TrendReport(BaseModel):
    """Report detailing open vs closed trends over time without individual rankings."""

    window_days: int
    data_points: list[TrendPoint] = Field(default_factory=list)
    total_opened_in_window: int = 0
    total_closed_in_window: int = 0
    net_backlog_change: int = 0


# ==============================================================================
# 6. Request DTOs
# ==============================================================================


class TaskCreateRequest(BaseModel):
    """Payload to create a remediation task manually or from a detection trigger."""

    source: TaskSource = Field(default=TaskSource.MANUAL)
    subject_entity: SubjectEntity
    title: str = Field(..., min_length=3)
    description: str = Field(..., min_length=3)
    evidence_linkage: dict[str, Any] = Field(default_factory=dict)
    category: TaskCategory = Field(default=TaskCategory.CUSTOM)
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM)
    assignee_id: str | None = Field(
        default=None, description="Explicit assignee ID or None to auto-resolve"
    )
    assignee_type: str = Field(default="USER")
    estimated_saving: float | None = Field(default=None, ge=0.0)
    sla_working_hours: float | None = Field(default=None, gt=0.0)
    alert_id: str | None = Field(default=None)
    finding_id: str | None = Field(default=None)


class TaskTransitionRequest(BaseModel):
    """Payload to transition a task state."""

    to_state: TaskState
    reason: str | None = Field(default=None)
    note: str | None = Field(default=None)


class TaskResolveRequest(BaseModel):
    """Payload to mark a task resolved pending automated verification."""

    resolution_note: str = Field(
        ..., min_length=3, description="Explanation of remediation performed"
    )


class TaskDeferRequest(BaseModel):
    """Payload to formally defer a remediation task."""

    reason: str = Field(..., min_length=3, description="Mandatory justification for deferral")
    deferral_expiry: dt.datetime = Field(..., description="Expiration timestamp UTC")

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        if not v or not v.strip():
            raise MandatoryReasonException("deferral")
        return v.strip()


class TaskAcceptRiskRequest(BaseModel):
    """Payload to formally accept risk with expiration."""

    reason: str = Field(
        ..., min_length=3, description="Mandatory justification for risk acceptance"
    )
    risk_expiry: dt.datetime = Field(..., description="Risk acceptance expiration timestamp UTC")

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        if not v or not v.strip():
            raise MandatoryReasonException("risk_acceptance")
        return v.strip()


class BulkAssignRequest(BaseModel):
    """Payload to bulk-assign multiple remediation tasks."""

    task_ids: list[str] = Field(..., min_length=1)
    new_assignee_id: str = Field(..., min_length=1)
    assignee_type: str = Field(default="USER")
    reason: str | None = Field(default=None)


class BulkReprioritiseRequest(BaseModel):
    """Payload to bulk-reprioritize multiple remediation tasks."""

    task_ids: list[str] = Field(..., min_length=1)
    new_priority: TaskPriority
    reason: str | None = Field(default=None)


class BulkDeferRequest(BaseModel):
    """Payload to bulk-defer multiple remediation tasks."""

    task_ids: list[str] = Field(..., min_length=1)
    reason: str = Field(..., min_length=3)
    deferral_expiry: dt.datetime


class BulkDuplicateRequest(BaseModel):
    """Payload to bulk-close tasks as duplicates of a canonical parent task."""

    duplicate_task_ids: list[str] = Field(..., min_length=1)
    canonical_task_id: str = Field(..., min_length=1)
    reason: str | None = Field(default=None)


class TaskVerificationResult(BaseModel):
    """Result of an automated condition verification re-test."""

    is_cleared: bool
    message: str
    retested_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.UTC))
    details: dict[str, Any] = Field(default_factory=dict)
