"""Remediation Service Orchestrating Assignment, Verification, Accountability, and Ledger (Prompt 51).

Enforces:
- Prompt 51 / BBP Sections 34, 35, 36: Remediation as a first-class operational loop.
- Master-Data-Driven Taxonomies & Creation Rules: Tasks are classified and instantiated
  through master data, never hardcoded.
- Mandatory Automated Verification: Never close a task on assignee's word alone.
  Re-tests underlying condition; persistent problem reopens to OPEN with note;
  cleared condition transitions to VERIFIED -> CLOSED.
- Bidirectional Alert Sync: Resolving a verified task resolves the linked alert;
  acknowledging an alert optionally creates a linked task.
- Realised-Saving Ledger: Confirmed savings are ledgered with method attribution
  and reported across periods, teams, categories, and methods.
- Accountability Without Blame: Views by user, team, app, BU, ageing brackets, and
  leaderboard-free trends over time (reporting trends, not people).
- Resilient Deferral & Risk Acceptance: Time-boxed justifications, optional Prompt 50
  workflow approvals, and automatic reopening upon deferral expiry.
- Outbound ITSM Mirroring: Gated behind feature flag.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from typing import Any

from domain.audit.service import AuditService, get_audit_service
from domain.models.enums import (
    AuditEventType,
    TaskAssignmentRule,
    TaskCategory,
    TaskClosureCode,
    TaskPriority,
    TaskSource,
    TaskState,
)
from domain.models.exceptions import (
    InvalidTaskTransitionException,
    MandatoryReasonException,
    RemediationTaskNotFoundException,
    TaskAlreadyClosedException,
)
from domain.remediation.assignment import AssignmentResolver
from domain.remediation.creator import TaskCreationEngine
from domain.remediation.itsm import ITSMAdapter, get_itsm_adapter
from domain.remediation.ledger import RealisedSavingLedger, get_realised_saving_ledger
from domain.remediation.models import (
    AgeingReport,
    BulkAssignRequest,
    BulkDeferRequest,
    BulkDuplicateRequest,
    BulkReprioritiseRequest,
    RealisedSavingReport,
    RemediationTask,
    SubjectEntity,
    TaskCreateRequest,
    TaskVerificationResult,
    TrendReport,
)
from domain.remediation.repository import RemediationRepository, get_remediation_repository
from domain.remediation.verifier import TaskVerifier
from domain.remediation.views import AccountabilityEngine
from domain.tenant.context import TenantContext, require_tenant_context
from domain.workflows.sla import SLAEngine
from masterdata.service import MasterDataService, get_master_data_service

logger = logging.getLogger(__name__)

# Allowed state transition graph
VALID_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.OPEN: {
        TaskState.ASSIGNED,
        TaskState.IN_PROGRESS,
        TaskState.DEFERRED,
        TaskState.DUPLICATE,
        TaskState.REJECTED,
    },
    TaskState.ASSIGNED: {
        TaskState.IN_PROGRESS,
        TaskState.BLOCKED,
        TaskState.AWAITING_VERIFICATION,
        TaskState.RESOLVED,
        TaskState.DEFERRED,
        TaskState.DUPLICATE,
        TaskState.REJECTED,
    },
    TaskState.IN_PROGRESS: {
        TaskState.BLOCKED,
        TaskState.AWAITING_VERIFICATION,
        TaskState.RESOLVED,
        TaskState.DEFERRED,
        TaskState.DUPLICATE,
    },
    TaskState.BLOCKED: {
        TaskState.IN_PROGRESS,
        TaskState.AWAITING_VERIFICATION,
        TaskState.RESOLVED,
        TaskState.DEFERRED,
    },
    TaskState.AWAITING_VERIFICATION: {
        TaskState.VERIFIED,
        TaskState.CLOSED,
        TaskState.OPEN,  # Verification failed: reopens
    },
    TaskState.RESOLVED: {
        TaskState.AWAITING_VERIFICATION,
        TaskState.VERIFIED,
        TaskState.CLOSED,
        TaskState.OPEN,  # Verification failed: reopens
    },
    TaskState.VERIFIED: {
        TaskState.CLOSED,
    },
    TaskState.DEFERRED: {
        TaskState.OPEN,  # Expired or un-deferred
        TaskState.IN_PROGRESS,
    },
    TaskState.CLOSED: {
        TaskState.OPEN,  # Admin reopen if problem recurs
    },
    TaskState.REJECTED: set(),
    TaskState.DUPLICATE: set(),
}


class RemediationService:
    """Core domain service orchestrating the remediation and accountability lifecycle."""

    def __init__(
        self,
        repository: RemediationRepository | None = None,
        creation_engine: TaskCreationEngine | None = None,
        assignment_resolver: AssignmentResolver | None = None,
        verifier: TaskVerifier | None = None,
        ledger: RealisedSavingLedger | None = None,
        views_engine: AccountabilityEngine | None = None,
        itsm_adapter: ITSMAdapter | None = None,
        audit_service: AuditService | None = None,
        sla_engine: SLAEngine | None = None,
        master_data_service: MasterDataService | None = None,
        alert_service: Any | None = None,
    ) -> None:
        self.repository = repository or get_remediation_repository()
        self.master_data_service = master_data_service or get_master_data_service()
        self.resolver = assignment_resolver or AssignmentResolver(self.master_data_service)
        self.sla_engine = sla_engine or SLAEngine(self.master_data_service)
        self.creation_engine = creation_engine or TaskCreationEngine(
            repository=self.repository,
            resolver=self.resolver,
            sla_engine=self.sla_engine,
            master_data_service=self.master_data_service,
        )
        self.verifier = verifier or TaskVerifier()
        self.ledger = ledger or get_realised_saving_ledger(self.repository)
        self.views_engine = views_engine or AccountabilityEngine(self.repository)
        self.itsm_adapter = itsm_adapter or get_itsm_adapter()
        self.audit_service = audit_service or get_audit_service()
        self.alert_service = alert_service

    # ==========================================================================
    # 1. Task Creation & Source Processing
    # ==========================================================================

    def create_task(
        self,
        req: TaskCreateRequest,
        actor: str,
        *,
        tenant_context: TenantContext,
    ) -> RemediationTask:
        """Manually or programmatically creates a remediation task."""
        tc = require_tenant_context(tenant_context)
        now = dt.datetime.now(dt.UTC)

        # Resolve assignee if not explicitly supplied
        assignee_id = req.assignee_id
        assignee_type = req.assignee_type
        rule_used = TaskAssignmentRule.MANUAL

        if not assignee_id:
            assignee_id, assignee_type, rule_used = self.resolver.resolve(
                subject=req.subject_entity,
                tags=req.evidence_linkage.get("tags") if req.evidence_linkage else None,
            )

        # Compute SLA due date
        sla_hours = req.sla_working_hours or 48.0
        due_date = self.sla_engine.calculate_due_date(
            start_time=now,
            sla_working_hours=int(sla_hours),
            tenant_id=tc.tenant_id,
        )

        task_id = f"rem-task-{tc.tenant_id[:8]}-{uuid.uuid4().hex[:8]}"
        initial_state = TaskState.ASSIGNED if assignee_id else TaskState.OPEN

        task = RemediationTask(
            id=task_id,
            tenant_id=tc.tenant_id,
            source=req.source,
            subject_entity=req.subject_entity,
            title=req.title,
            description=req.description,
            evidence_linkage=req.evidence_linkage,
            assignee_id=assignee_id,
            assignee_type=assignee_type,
            assigning_actor=actor,
            assignment_rule=rule_used,
            priority=req.priority,
            due_date=due_date,
            sla_working_hours=sla_hours,
            estimated_saving=req.estimated_saving,
            state=initial_state,
            category=req.category,
            alert_id=req.alert_id,
            finding_id=req.finding_id,
        )

        task.add_history(
            action="CREATED",
            actor_id=actor,
            from_state=None,
            to_state=initial_state.value,
            note=f"Created task with priority {req.priority.value}.",
            details={"sla_hours": sla_hours, "assignee": assignee_id},
        )

        saved = self.repository.save(task, tenant_context=tc)

        self._record_audit(
            event_type=AuditEventType.REMEDIATION_TASK_CREATED,
            actor_id=actor,
            task_id=saved.id,
            details={
                "title": saved.title,
                "category": saved.category.value,
                "priority": saved.priority.value,
                "assignee": saved.assignee_id,
                "source": saved.source.value,
            },
            tenant_context=tc,
        )

        # Mirror to ITSM if feature is enabled
        self._try_itsm_mirror(saved, tenant_context=tc)
        return saved

    def create_from_source(
        self,
        source: TaskSource,
        subject: SubjectEntity,
        evidence: dict[str, Any],
        payload: dict[str, Any] | None = None,
        *,
        tenant_context: TenantContext,
    ) -> RemediationTask | None:
        """Instantiates a task from a platform detection trigger via master data rules."""
        tc = require_tenant_context(tenant_context)
        created = self.creation_engine.create_from_source(
            source=source,
            subject=subject,
            evidence=evidence,
            payload=payload,
            tenant_context=tc,
        )
        if created:
            self._record_audit(
                event_type=AuditEventType.REMEDIATION_TASK_CREATED,
                actor_id="SYSTEM_CREATION_ENGINE",
                task_id=created.id,
                details={
                    "source": source.value,
                    "entity_id": subject.entity_id,
                    "category": created.category.value,
                    "priority": created.priority.value,
                    "assignee": created.assignee_id,
                },
                tenant_context=tc,
            )
            self._try_itsm_mirror(created, tenant_context=tc)
        return created

    # ==========================================================================
    # 2. Retrieval & State Transitions
    # ==========================================================================

    def get_task(self, task_id: str, *, tenant_context: TenantContext) -> RemediationTask:
        """Retrieves a single remediation task by ID within tenant boundary."""
        tc = require_tenant_context(tenant_context)
        task = self.repository.get(task_id, tenant_context=tc)
        if not task:
            raise RemediationTaskNotFoundException(task_id)
        return task

    def list_tasks(
        self,
        *,
        tenant_context: TenantContext,
        state: TaskState | None = None,
        priority: TaskPriority | None = None,
        category: TaskCategory | None = None,
        assignee_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RemediationTask]:
        """Lists remediation tasks with optional filtering."""
        tc = require_tenant_context(tenant_context)
        return self.repository.list(
            tenant_context=tc,
            state=state,
            priority=priority,
            category=category,
            assignee_id=assignee_id,
            limit=limit,
            offset=offset,
        )

    def transition_state(
        self,
        task_id: str,
        to_state: TaskState,
        actor: str,
        *,
        tenant_context: TenantContext,
        reason: str | None = None,
        note: str | None = None,
    ) -> RemediationTask:
        """Transitions task lifecycle state with strict validation."""
        tc = require_tenant_context(tenant_context)
        task = self.get_task(task_id, tenant_context=tc)

        if task.is_terminal and to_state != TaskState.OPEN:
            raise TaskAlreadyClosedException(task_id, task.state.value)

        # Enforce valid state transitions
        allowed = VALID_TRANSITIONS.get(task.state, set())
        if to_state not in allowed:
            raise InvalidTaskTransitionException(
                task_id=task_id,
                from_state=task.state.value,
                to_state=to_state.value,
            )

        # Do not allow skipping verification into CLOSED or VERIFIED
        if to_state in {TaskState.VERIFIED, TaskState.CLOSED} and task.state not in {
            TaskState.AWAITING_VERIFICATION,
            TaskState.RESOLVED,
            TaskState.VERIFIED,
        }:
            raise InvalidTaskTransitionException(
                task_id=task_id,
                from_state=task.state.value,
                to_state=to_state.value,
            )

        from_state = task.state
        task.state = to_state
        task.reason_code = reason or task.reason_code
        task.add_history(
            action="STATUS_CHANGED",
            actor_id=actor,
            from_state=from_state.value,
            to_state=to_state.value,
            reason=reason,
            note=note,
        )

        saved = self.repository.save(task, tenant_context=tc)

        self._record_audit(
            event_type=AuditEventType.REMEDIATION_TASK_STATUS_CHANGED,
            actor_id=actor,
            task_id=saved.id,
            details={"from_state": from_state.value, "to_state": to_state.value, "reason": reason},
            tenant_context=tc,
        )
        return saved

    def assign_task(
        self,
        task_id: str,
        assignee_id: str,
        actor: str,
        *,
        tenant_context: TenantContext,
        assignee_type: str = "USER",
        reason: str | None = None,
    ) -> RemediationTask:
        """Assigns or re-assigns a task to an accountable entity."""
        tc = require_tenant_context(tenant_context)
        task = self.get_task(task_id, tenant_context=tc)

        if task.is_terminal:
            raise TaskAlreadyClosedException(task_id, task.state.value)

        old_assignee = task.assignee_id
        task.assignee_id = assignee_id
        task.assignee_type = assignee_type
        task.assigning_actor = actor

        from_state = task.state
        if task.state == TaskState.OPEN:
            task.state = TaskState.ASSIGNED

        task.add_history(
            action="ASSIGNED",
            actor_id=actor,
            from_state=from_state.value,
            to_state=task.state.value,
            reason=reason,
            note=f"Reassigned from '{old_assignee}' to '{assignee_id}'.",
        )

        saved = self.repository.save(task, tenant_context=tc)

        self._record_audit(
            event_type=AuditEventType.REMEDIATION_TASK_ASSIGNED,
            actor_id=actor,
            task_id=saved.id,
            details={"prior_assignee": old_assignee, "new_assignee": assignee_id, "reason": reason},
            tenant_context=tc,
        )
        return saved

    # ==========================================================================
    # 3. Mandatory Automated Verification & Closure Loop
    # ==========================================================================

    def resolve_task(
        self,
        task_id: str,
        actor: str,
        *,
        tenant_context: TenantContext,
        resolution_note: str,
    ) -> tuple[RemediationTask, TaskVerificationResult]:
        """Assignee marks problem resolved, triggering mandatory automated verification.

        Enforces:
        - Never close on assignee's word alone.
        - Moves state to AWAITING_VERIFICATION and immediately executes verification.
        """
        tc = require_tenant_context(tenant_context)
        task = self.get_task(task_id, tenant_context=tc)

        if task.is_terminal:
            raise TaskAlreadyClosedException(task_id, task.state.value)

        # Mark awaiting verification
        from_state = task.state
        task.state = TaskState.AWAITING_VERIFICATION
        task.add_history(
            action="RESOLVED_PENDING_VERIFICATION",
            actor_id=actor,
            from_state=from_state.value,
            to_state=TaskState.AWAITING_VERIFICATION.value,
            note=resolution_note,
        )
        self.repository.save(task, tenant_context=tc)

        self._record_audit(
            event_type=AuditEventType.REMEDIATION_TASK_RESOLVED,
            actor_id=actor,
            task_id=task.id,
            details={"resolution_note": resolution_note},
            tenant_context=tc,
        )

        # Execute automated verification
        return self.verify_task(task.id, actor=actor, tenant_context=tc)

    def verify_task(
        self,
        task_id: str,
        actor: str,
        *,
        tenant_context: TenantContext,
    ) -> tuple[RemediationTask, TaskVerificationResult]:
        """Executes automated condition re-testing for a task.

        Outcomes:
        - Cleared: Advances to VERIFIED -> CLOSED, ledgers realised saving, resolves alert.
        - Persistent: Reopens to OPEN with explanation note. Never closes on word alone.
        """
        tc = require_tenant_context(tenant_context)
        task = self.get_task(task_id, tenant_context=tc)

        task.verification_attempts += 1
        result = self.verifier.verify(task, tenant_context=tc)
        now = dt.datetime.now(dt.UTC)

        if result.is_cleared:
            # Condition genuinely resolved!
            from_state = task.state
            task.state = TaskState.CLOSED
            task.closure_code = TaskClosureCode.FIXED_AND_VERIFIED
            task.closed_at = now
            task.verification_notes.append(f"Pass {task.verification_attempts}: {result.message}")

            task.add_history(
                action="VERIFIED_AND_CLOSED",
                actor_id=actor,
                from_state=from_state.value,
                to_state=TaskState.CLOSED.value,
                note=f"Condition verified cleared: {result.message}",
            )

            # Record in Realised-Saving Ledger if financial saving is present
            saving_amount = task.estimated_saving or 0.0
            if saving_amount > 0.0:
                saving_method = self.ledger._infer_method(task.category)
                task.realised_saving = saving_amount
                task.realised_saving_method = saving_method
                period_str = now.strftime("%Y-%m")
                saving_entry = self.ledger.record_saving(
                    task=task,
                    amount=saving_amount,
                    method=saving_method,
                    period=period_str,
                    tenant_context=tc,
                    verified_by=actor,
                )
                self._record_audit(
                    event_type=AuditEventType.REMEDIATION_SAVING_REALISED,
                    actor_id=actor,
                    task_id=task.id,
                    details={
                        "saving_id": saving_entry.id,
                        "amount": saving_amount,
                        "method": saving_method.value,
                        "period": period_str,
                    },
                    tenant_context=tc,
                )

            # Bidirectional Alert Sync: Resolve linked alert if present
            if task.alert_id and self.alert_service:
                try:
                    self.alert_service.resolve_alert(
                        task.alert_id,
                        actor="remediation-verifier",
                        tenant_context=tc,
                        reason=f"Remediation task '{task.id}' verified and closed.",
                    )
                except Exception as e:
                    logger.warning(f"Failed resolving linked alert '{task.alert_id}': {e}")

            saved = self.repository.save(task, tenant_context=tc)

            self._record_audit(
                event_type=AuditEventType.REMEDIATION_TASK_VERIFIED,
                actor_id=actor,
                task_id=saved.id,
                details={"message": result.message, "attempts": task.verification_attempts},
                tenant_context=tc,
            )
            self._record_audit(
                event_type=AuditEventType.REMEDIATION_TASK_CLOSED,
                actor_id=actor,
                task_id=saved.id,
                details={"closure_code": TaskClosureCode.FIXED_AND_VERIFIED.value},
                tenant_context=tc,
            )
            return saved, result

        # Condition still active: REOPEN TO OPEN WITH NOTE
        from_state = task.state
        task.state = TaskState.OPEN
        reopen_note = (
            f"Automated verification failed (Attempt {task.verification_attempts}): {result.message}. "
            f"Underlying condition still exists. Task reopened for correction."
        )
        task.verification_notes.append(reopen_note)
        task.add_history(
            action="VERIFICATION_FAILED_REOPENED",
            actor_id="system-verifier",
            from_state=from_state.value,
            to_state=TaskState.OPEN.value,
            note=reopen_note,
        )

        saved = self.repository.save(task, tenant_context=tc)

        self._record_audit(
            event_type=AuditEventType.REMEDIATION_TASK_REOPENED,
            actor_id="system-verifier",
            task_id=saved.id,
            details={"message": result.message, "attempts": task.verification_attempts},
            tenant_context=tc,
        )
        return saved, result

    # ==========================================================================
    # 4. Deferral & Risk Acceptance Paths
    # ==========================================================================

    def defer_task(
        self,
        task_id: str,
        actor: str,
        *,
        tenant_context: TenantContext,
        reason: str,
        deferral_expiry: dt.datetime,
        approval_workflow_id: str | None = None,
    ) -> RemediationTask:
        """Formally defers a task until a specific expiry date with mandatory reason."""
        tc = require_tenant_context(tenant_context)
        task = self.get_task(task_id, tenant_context=tc)

        if task.is_terminal:
            raise TaskAlreadyClosedException(task_id, task.state.value)

        if not reason or not reason.strip():
            raise MandatoryReasonException("deferral")

        now = dt.datetime.now(dt.UTC)
        if deferral_expiry <= now:
            raise MandatoryReasonException("Deferral expiry must be a future timestamp.")

        from_state = task.state
        task.state = TaskState.DEFERRED
        task.reason_code = reason.strip()
        task.deferral_expiry = deferral_expiry
        task.approval_workflow_id = approval_workflow_id

        task.add_history(
            action="DEFERRED",
            actor_id=actor,
            from_state=from_state.value,
            to_state=TaskState.DEFERRED.value,
            reason=reason.strip(),
            note=f"Deferred until {deferral_expiry.isoformat()}.",
            details={"approval_workflow_id": approval_workflow_id},
        )

        saved = self.repository.save(task, tenant_context=tc)

        self._record_audit(
            event_type=AuditEventType.REMEDIATION_TASK_DEFERRED,
            actor_id=actor,
            task_id=saved.id,
            details={
                "reason": reason.strip(),
                "deferral_expiry": deferral_expiry.isoformat(),
                "approval_workflow_id": approval_workflow_id,
            },
            tenant_context=tc,
        )
        return saved

    def accept_risk(
        self,
        task_id: str,
        actor: str,
        *,
        tenant_context: TenantContext,
        reason: str,
        risk_expiry: dt.datetime,
        approved_by: str | None = None,
    ) -> RemediationTask:
        """Formally accepts organizational risk for a remediation issue with time-boxed expiry."""
        tc = require_tenant_context(tenant_context)
        task = self.get_task(task_id, tenant_context=tc)

        if not reason or not reason.strip():
            raise MandatoryReasonException("risk_acceptance")

        now = dt.datetime.now(dt.UTC)
        from_state = task.state
        task.state = TaskState.CLOSED
        task.closure_code = TaskClosureCode.RISK_ACCEPTED
        task.closed_at = now
        task.risk_accepted = True
        task.risk_accepted_expiry = risk_expiry
        task.reason_code = reason.strip()

        task.add_history(
            action="RISK_ACCEPTED",
            actor_id=actor,
            from_state=from_state.value,
            to_state=TaskState.CLOSED.value,
            reason=reason.strip(),
            note=f"Risk accepted until {risk_expiry.isoformat()} by {approved_by or actor}.",
        )

        saved = self.repository.save(task, tenant_context=tc)

        self._record_audit(
            event_type=AuditEventType.REMEDIATION_TASK_RISK_ACCEPTED,
            actor_id=actor,
            task_id=saved.id,
            details={
                "reason": reason.strip(),
                "risk_expiry": risk_expiry.isoformat(),
                "approved_by": approved_by or actor,
            },
            tenant_context=tc,
        )
        return saved

    def check_expired_deferrals(
        self,
        *,
        tenant_context: TenantContext,
        now: dt.datetime | None = None,
    ) -> list[RemediationTask]:
        """Scans for deferred tasks whose deferral period has expired and reopens them to OPEN."""
        tc = require_tenant_context(tenant_context)
        current_time = now or dt.datetime.now(dt.UTC)
        deferred_tasks = self.repository.list(
            tenant_context=tc, state=TaskState.DEFERRED, limit=500
        )

        reopened: list[RemediationTask] = []
        for task in deferred_tasks:
            if task.deferral_expiry and task.deferral_expiry <= current_time:
                task.state = TaskState.OPEN
                exp_str = task.deferral_expiry.isoformat()
                task.deferral_expiry = None
                task.add_history(
                    action="DEFERRAL_EXPIRED_REOPENED",
                    actor_id="system-deferral-scheduler",
                    from_state=TaskState.DEFERRED.value,
                    to_state=TaskState.OPEN.value,
                    note=f"Deferral expired on {exp_str}. Reopened automatically for remediation.",
                )
                saved = self.repository.save(task, tenant_context=tc)
                reopened.append(saved)

                self._record_audit(
                    event_type=AuditEventType.REMEDIATION_TASK_REOPENED,
                    actor_id="system-deferral-scheduler",
                    task_id=saved.id,
                    details={"reason": "Deferral period expired"},
                    tenant_context=tc,
                )
        return reopened

    # ==========================================================================
    # 5. Bulk Operations
    # ==========================================================================

    def bulk_assign(
        self,
        req: BulkAssignRequest,
        actor: str,
        *,
        tenant_context: TenantContext,
    ) -> list[RemediationTask]:
        """Bulk reassigns multiple tasks."""
        tc = require_tenant_context(tenant_context)
        updated: list[RemediationTask] = []
        for task_id in req.task_ids:
            try:
                task = self.assign_task(
                    task_id=task_id,
                    assignee_id=req.new_assignee_id,
                    actor=actor,
                    tenant_context=tc,
                    assignee_type=req.assignee_type,
                    reason=req.reason,
                )
                updated.append(task)
            except Exception as e:
                logger.warning(f"Failed bulk assigning task '{task_id}': {e}")
        return updated

    def bulk_reprioritise(
        self,
        req: BulkReprioritiseRequest,
        actor: str,
        *,
        tenant_context: TenantContext,
    ) -> list[RemediationTask]:
        """Bulk updates priority for multiple tasks."""
        tc = require_tenant_context(tenant_context)
        updated: list[RemediationTask] = []
        for task_id in req.task_ids:
            try:
                task = self.get_task(task_id, tenant_context=tc)
                old_prio = task.priority
                task.priority = req.new_priority
                task.add_history(
                    action="REPRIORITISED",
                    actor_id=actor,
                    from_state=task.state.value,
                    to_state=task.state.value,
                    reason=req.reason,
                    note=f"Priority adjusted from {old_prio.value} to {req.new_priority.value}.",
                )
                saved = self.repository.save(task, tenant_context=tc)
                updated.append(saved)
            except Exception as e:
                logger.warning(f"Failed reprioritising task '{task_id}': {e}")
        return updated

    def bulk_defer(
        self,
        req: BulkDeferRequest,
        actor: str,
        *,
        tenant_context: TenantContext,
    ) -> list[RemediationTask]:
        """Bulk defers multiple tasks with mandatory reason."""
        tc = require_tenant_context(tenant_context)
        updated: list[RemediationTask] = []
        for task_id in req.task_ids:
            try:
                task = self.defer_task(
                    task_id=task_id,
                    actor=actor,
                    tenant_context=tc,
                    reason=req.reason,
                    deferral_expiry=req.deferral_expiry,
                )
                updated.append(task)
            except Exception as e:
                logger.warning(f"Failed bulk deferring task '{task_id}': {e}")
        return updated

    def bulk_close_duplicate(
        self,
        req: BulkDuplicateRequest,
        actor: str,
        *,
        tenant_context: TenantContext,
    ) -> list[RemediationTask]:
        """Closes duplicate tasks referencing a single canonical parent task."""
        tc = require_tenant_context(tenant_context)
        updated: list[RemediationTask] = []
        now = dt.datetime.now(dt.UTC)

        for task_id in req.duplicate_task_ids:
            if task_id == req.canonical_task_id:
                continue
            try:
                task = self.get_task(task_id, tenant_context=tc)
                from_state = task.state
                task.state = TaskState.DUPLICATE
                task.closure_code = TaskClosureCode.DUPLICATE_SUPERSEDED
                task.closed_at = now
                task.add_history(
                    action="MARKED_DUPLICATE",
                    actor_id=actor,
                    from_state=from_state.value,
                    to_state=TaskState.DUPLICATE.value,
                    reason=req.reason,
                    note=f"Closed as duplicate of canonical task '{req.canonical_task_id}'.",
                )
                saved = self.repository.save(task, tenant_context=tc)
                updated.append(saved)

                self._record_audit(
                    event_type=AuditEventType.REMEDIATION_TASK_DUPLICATED,
                    actor_id=actor,
                    task_id=saved.id,
                    details={"canonical_task_id": req.canonical_task_id, "reason": req.reason},
                    tenant_context=tc,
                )
            except Exception as e:
                logger.warning(f"Failed closing duplicate task '{task_id}': {e}")
        return updated

    # ==========================================================================
    # 6. SLA Overdue & Escalation Tracking
    # ==========================================================================

    def check_overdue_and_escalate(
        self,
        *,
        tenant_context: TenantContext,
        now: dt.datetime | None = None,
    ) -> list[RemediationTask]:
        """Scans active tasks, flags overdue breaches, and logs escalation events."""
        tc = require_tenant_context(tenant_context)
        current_time = now or dt.datetime.now(dt.UTC)
        active_states = [
            TaskState.OPEN,
            TaskState.ASSIGNED,
            TaskState.IN_PROGRESS,
            TaskState.BLOCKED,
        ]

        escalated: list[RemediationTask] = []
        for state in active_states:
            tasks = self.repository.list(tenant_context=tc, state=state, limit=500)
            for t in tasks:
                if current_time > t.due_date:
                    t.add_history(
                        action="ESCALATED",
                        actor_id="system-sla-scheduler",
                        from_state=t.state.value,
                        to_state=t.state.value,
                        note=f"Task overdue by {(current_time - t.due_date).total_seconds() / 3600:.1f} hours.",
                    )
                    saved = self.repository.save(t, tenant_context=tc)
                    escalated.append(saved)

                    self._record_audit(
                        event_type=AuditEventType.REMEDIATION_TASK_ESCALATED,
                        actor_id="system-sla-scheduler",
                        task_id=t.id,
                        details={"due_date": t.due_date.isoformat(), "state": t.state.value},
                        tenant_context=tc,
                    )
        return escalated

    # ==========================================================================
    # 7. Accountability Views & Reporting (No Blame / Leaderboard-Free)
    # ==========================================================================

    def get_my_tasks(self, user_id: str, *, tenant_context: TenantContext) -> list[RemediationTask]:
        """Retrieves active tasks assigned to the current user."""
        tc = require_tenant_context(tenant_context)
        return self.views_engine.get_my_tasks(user_id, tenant_context=tc)

    def get_team_tasks(
        self, team_id: str, *, tenant_context: TenantContext
    ) -> list[RemediationTask]:
        """Retrieves active tasks assigned to the user's team or fallback queue."""
        tc = require_tenant_context(tenant_context)
        return self.views_engine.get_team_tasks(team_id, tenant_context=tc)

    def get_tasks_by_application(
        self, app_id: str, *, tenant_context: TenantContext
    ) -> list[RemediationTask]:
        """Retrieves active tasks linked to an application."""
        tc = require_tenant_context(tenant_context)
        return self.views_engine.get_tasks_by_application(app_id, tenant_context=tc)

    def get_tasks_by_business_unit(
        self, bu_id: str, *, tenant_context: TenantContext
    ) -> list[RemediationTask]:
        """Retrieves active tasks linked to a business unit."""
        tc = require_tenant_context(tenant_context)
        return self.views_engine.get_tasks_by_business_unit(bu_id, tenant_context=tc)

    def get_overdue_tasks(self, *, tenant_context: TenantContext) -> list[RemediationTask]:
        """Retrieves all tasks that have breached their SLA due date."""
        tc = require_tenant_context(tenant_context)
        return self.views_engine.get_overdue_tasks(tenant_context=tc)

    def get_ageing_report(self, *, tenant_context: TenantContext) -> AgeingReport:
        """Retrieves open task ageing bracket distribution."""
        tc = require_tenant_context(tenant_context)
        return self.views_engine.get_ageing_report(tenant_context=tc)

    def get_trend_report(
        self,
        *,
        tenant_context: TenantContext,
        window_days: int = 30,
    ) -> TrendReport:
        """Retrieves leaderboard-free open-vs-closed trend report over time."""
        tc = require_tenant_context(tenant_context)
        return self.views_engine.get_trend_report(window_days=window_days, tenant_context=tc)

    def get_savings_report(
        self,
        *,
        tenant_context: TenantContext,
        period: str | None = None,
    ) -> RealisedSavingReport:
        """Retrieves cumulative realised savings report across periods, teams, and categories."""
        tc = require_tenant_context(tenant_context)
        return self.ledger.get_report(tenant_context=tc, period=period)

    # ==========================================================================
    # 8. ITSM Outbound Mirroring
    # ==========================================================================

    def mirror_to_itsm(self, task_id: str, *, tenant_context: TenantContext) -> RemediationTask:
        """Manually or explicitly triggers ITSM mirroring for a task."""
        tc = require_tenant_context(tenant_context)
        task = self.get_task(task_id, tenant_context=tc)
        res = self.itsm_adapter.mirror_task(task, tenant_context=tc)
        if res and res.mirrored and res.external_ticket_id:
            task.itsm_ticket_id = res.external_ticket_id
            task.add_history(
                action="ITSM_MIRRORED",
                actor_id="system-itsm-adapter",
                from_state=task.state.value,
                to_state=task.state.value,
                note=f"Task mirrored to external ITSM system: {res.external_ticket_id}.",
                details={"system": res.system_name, "ticket_id": res.external_ticket_id},
            )
            saved = self.repository.save(task, tenant_context=tc)
            self._record_audit(
                event_type=AuditEventType.REMEDIATION_TASK_ITSM_MIRRORED,
                actor_id="system-itsm-adapter",
                task_id=saved.id,
                details={"system": res.system_name, "ticket_id": res.external_ticket_id},
                tenant_context=tc,
            )
            return saved
        return task

    def _try_itsm_mirror(self, task: RemediationTask, *, tenant_context: TenantContext) -> None:
        """Attempts background ITSM sync without blocking task creation."""
        if not self.itsm_adapter.is_enabled():
            return
        try:
            res = self.itsm_adapter.mirror_task(task, tenant_context=tenant_context)
            if res and res.mirrored and res.external_ticket_id:
                task.itsm_ticket_id = res.external_ticket_id
                self.repository.save(task, tenant_context=tenant_context)
        except Exception as e:
            logger.debug(f"ITSM background mirror skipped/failed: {e}")

    # ==========================================================================
    # 9. Audit Logging Helper
    # ==========================================================================

    def _record_audit(
        self,
        event_type: AuditEventType,
        actor_id: str,
        task_id: str,
        details: dict[str, Any],
        *,
        tenant_context: TenantContext,
    ) -> None:
        """Safely records an audit event without failing the primary business operation."""
        try:
            self.audit_service.record_event(
                tenant_context=tenant_context,
                event_type=event_type,
                actor=actor_id,
                payload=details,
                resource_type="REMEDIATION_TASK",
                resource_id=task_id,
            )
        except Exception as e:
            logger.debug(f"Failed appending remediation audit event: {e}")


_remediation_service_instance: RemediationService | None = None


def get_remediation_service() -> RemediationService:
    """Returns singleton RemediationService instance."""
    global _remediation_service_instance
    if _remediation_service_instance is None:
        _remediation_service_instance = RemediationService()
    return _remediation_service_instance


def reset_remediation_service() -> None:
    """Resets service singleton for test isolation."""
    global _remediation_service_instance
    _remediation_service_instance = None
