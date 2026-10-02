"""Remediation and Accountability REST API Endpoints (Prompt 51).

Enforces:
- Prompt 51 / BBP Sections 34, 35, 36: Remediation task lifecycle, automated condition re-testing,
  ownership resolution, realised-saving ledger, and accountability reporting.
- Mandatory Automated Verification: Never close a task on assignee's word alone.
- Accountability Without Blame: Views for users, teams, apps, BUs, ageing brackets,
  and leaderboard-free trend metrics over time.
- Prompt 13 Item 84: 100% TenantContext validation.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from domain.models.enums import TaskCategory, TaskPriority, TaskState
from domain.remediation.models import (
    AgeingReport,
    BulkAssignRequest,
    BulkDeferRequest,
    BulkDuplicateRequest,
    BulkReprioritiseRequest,
    RealisedSavingReport,
    RemediationTask,
    TaskAcceptRiskRequest,
    TaskCreateRequest,
    TaskDeferRequest,
    TaskResolveRequest,
    TaskTransitionRequest,
    TaskVerificationResult,
    TrendReport,
)
from domain.remediation.service import RemediationService, get_remediation_service
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/remediation", tags=["Remediation & Accountability"])


class AssignTaskPayload(BaseModel):
    """Payload to assign or reassign a remediation task."""

    assignee_id: str = Field(..., min_length=1, description="Accountable owner ID")
    assignee_type: str = Field(default="USER", description="Assignee type: USER, TEAM, or QUEUE")
    reason: str | None = Field(default=None, description="Optional assignment explanation")


class TaskVerificationResponse(BaseModel):
    """Response returned upon resolving or re-testing a task."""

    task: RemediationTask
    verification: TaskVerificationResult


# ==============================================================================
# 1. Task Lifecycle & CRUD Endpoints
# ==============================================================================


@router.post(
    "/tasks",
    response_model=RemediationTask,
    status_code=status.HTTP_201_CREATED,
    summary="Create a remediation task manually or from a trigger",
)
def create_remediation_task(
    request: TaskCreateRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: RemediationService = Depends(get_remediation_service),
) -> RemediationTask:
    """Creates a new remediation task with SLA calculation and ownership assignment."""
    actor = tenant_context.user_id or "user:authenticated"
    return service.create_task(request, actor=actor, tenant_context=tenant_context)


@router.get(
    "/tasks",
    response_model=list[RemediationTask],
    status_code=status.HTTP_200_OK,
    summary="List remediation tasks with filtering",
)
def list_remediation_tasks(
    state: TaskState | None = Query(None, description="Filter by lifecycle state"),
    priority: TaskPriority | None = Query(None, description="Filter by urgency priority"),
    category: TaskCategory | None = Query(None, description="Filter by category"),
    assignee_id: str | None = Query(None, description="Filter by assignee ID"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: RemediationService = Depends(get_remediation_service),
) -> list[RemediationTask]:
    """Retrieves remediation tasks isolated to the caller's tenant."""
    return service.list_tasks(
        tenant_context=tenant_context,
        state=state,
        priority=priority,
        category=category,
        assignee_id=assignee_id,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/tasks/{task_id}",
    response_model=RemediationTask,
    status_code=status.HTTP_200_OK,
    summary="Get single remediation task",
)
def get_remediation_task(
    task_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: RemediationService = Depends(get_remediation_service),
) -> RemediationTask:
    """Retrieves full task details, including empirical evidence and transition history."""
    return service.get_task(task_id, tenant_context=tenant_context)


@router.post(
    "/tasks/{task_id}/assign",
    response_model=RemediationTask,
    status_code=status.HTTP_200_OK,
    summary="Assign or reassign a remediation task",
)
def assign_remediation_task(
    task_id: str,
    payload: AssignTaskPayload,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: RemediationService = Depends(get_remediation_service),
) -> RemediationTask:
    """Assigns the task to an owner or team with audit logging."""
    actor = tenant_context.user_id or "user:authenticated"
    return service.assign_task(
        task_id=task_id,
        assignee_id=payload.assignee_id,
        actor=actor,
        tenant_context=tenant_context,
        assignee_type=payload.assignee_type,
        reason=payload.reason,
    )


@router.post(
    "/tasks/{task_id}/transition",
    response_model=RemediationTask,
    status_code=status.HTTP_200_OK,
    summary="Transition task lifecycle state",
)
def transition_remediation_task_state(
    task_id: str,
    request: TaskTransitionRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: RemediationService = Depends(get_remediation_service),
) -> RemediationTask:
    """Executes a validated lifecycle transition."""
    actor = tenant_context.user_id or "user:authenticated"
    return service.transition_state(
        task_id=task_id,
        to_state=request.to_state,
        actor=actor,
        tenant_context=tenant_context,
        reason=request.reason,
        note=request.note,
    )


@router.post(
    "/tasks/{task_id}/resolve",
    response_model=TaskVerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark task resolved and trigger automated condition re-testing",
)
def resolve_remediation_task(
    task_id: str,
    request: TaskResolveRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: RemediationService = Depends(get_remediation_service),
) -> TaskVerificationResponse:
    """Marks task resolved and executes automated condition re-testing.

    Never closes on word alone:
    - Cleared condition: transitions to VERIFIED -> CLOSED, records saving, resolves alert.
    - Persistent condition: reopens to OPEN with explanation note.
    """
    actor = tenant_context.user_id or "user:authenticated"
    task, verification = service.resolve_task(
        task_id=task_id,
        actor=actor,
        tenant_context=tenant_context,
        resolution_note=request.resolution_note,
    )
    return TaskVerificationResponse(task=task, verification=verification)


@router.post(
    "/tasks/{task_id}/verify",
    response_model=TaskVerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger automated condition verification re-test",
)
def verify_remediation_task(
    task_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: RemediationService = Depends(get_remediation_service),
) -> TaskVerificationResponse:
    """Executes automated verification for a resolved or awaiting-verification task."""
    actor = tenant_context.user_id or "user:authenticated"
    task, verification = service.verify_task(
        task_id=task_id, actor=actor, tenant_context=tenant_context
    )
    return TaskVerificationResponse(task=task, verification=verification)


@router.post(
    "/tasks/{task_id}/defer",
    response_model=RemediationTask,
    status_code=status.HTTP_200_OK,
    summary="Formally defer remediation task with mandatory reason and expiry",
)
def defer_remediation_task(
    task_id: str,
    request: TaskDeferRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: RemediationService = Depends(get_remediation_service),
) -> RemediationTask:
    """Defers task until a future timestamp with mandatory justification."""
    actor = tenant_context.user_id or "user:authenticated"
    return service.defer_task(
        task_id=task_id,
        actor=actor,
        tenant_context=tenant_context,
        reason=request.reason,
        deferral_expiry=request.deferral_expiry,
    )


@router.post(
    "/tasks/{task_id}/accept-risk",
    response_model=RemediationTask,
    status_code=status.HTTP_200_OK,
    summary="Formally accept risk for remediation task with expiry",
)
def accept_risk_remediation_task(
    task_id: str,
    request: TaskAcceptRiskRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: RemediationService = Depends(get_remediation_service),
) -> RemediationTask:
    """Closes task with risk acceptance and mandatory justification."""
    actor = tenant_context.user_id or "user:authenticated"
    return service.accept_risk(
        task_id=task_id,
        actor=actor,
        tenant_context=tenant_context,
        reason=request.reason,
        risk_expiry=request.risk_expiry,
    )


@router.post(
    "/tasks/{task_id}/mirror-itsm",
    response_model=RemediationTask,
    status_code=status.HTTP_200_OK,
    summary="Mirror task to external ticketing system (Jira/ServiceNow)",
)
def mirror_remediation_task_to_itsm(
    task_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: RemediationService = Depends(get_remediation_service),
) -> RemediationTask:
    """Dispatches task snapshot to external ITSM webhook/adapter."""
    return service.mirror_to_itsm(task_id=task_id, tenant_context=tenant_context)


# ==============================================================================
# 2. Bulk Operations Endpoints
# ==============================================================================


@router.post(
    "/bulk/assign",
    response_model=list[RemediationTask],
    status_code=status.HTTP_200_OK,
    summary="Bulk assign multiple remediation tasks",
)
def bulk_assign_tasks(
    request: BulkAssignRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: RemediationService = Depends(get_remediation_service),
) -> list[RemediationTask]:
    """Bulk reassigns multiple remediation tasks."""
    actor = tenant_context.user_id or "user:authenticated"
    return service.bulk_assign(request, actor=actor, tenant_context=tenant_context)


@router.post(
    "/bulk/reprioritise",
    response_model=list[RemediationTask],
    status_code=status.HTTP_200_OK,
    summary="Bulk update priority for multiple tasks",
)
def bulk_reprioritise_tasks(
    request: BulkReprioritiseRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: RemediationService = Depends(get_remediation_service),
) -> list[RemediationTask]:
    """Bulk updates priority on multiple remediation tasks."""
    actor = tenant_context.user_id or "user:authenticated"
    return service.bulk_reprioritise(request, actor=actor, tenant_context=tenant_context)


@router.post(
    "/bulk/defer",
    response_model=list[RemediationTask],
    status_code=status.HTTP_200_OK,
    summary="Bulk defer multiple tasks with mandatory reason",
)
def bulk_defer_tasks(
    request: BulkDeferRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: RemediationService = Depends(get_remediation_service),
) -> list[RemediationTask]:
    """Bulk defers multiple remediation tasks."""
    actor = tenant_context.user_id or "user:authenticated"
    return service.bulk_defer(request, actor=actor, tenant_context=tenant_context)


@router.post(
    "/bulk/duplicate",
    response_model=list[RemediationTask],
    status_code=status.HTTP_200_OK,
    summary="Bulk close tasks as duplicates of a canonical parent task",
)
def bulk_close_duplicate_tasks(
    request: BulkDuplicateRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: RemediationService = Depends(get_remediation_service),
) -> list[RemediationTask]:
    """Closes multiple duplicate tasks linking them to a single canonical parent task."""
    actor = tenant_context.user_id or "user:authenticated"
    return service.bulk_close_duplicate(request, actor=actor, tenant_context=tenant_context)


# ==============================================================================
# 3. Accountability Views & Reporting Endpoints (Leaderboard-Free)
# ==============================================================================


@router.get(
    "/views/my-tasks",
    response_model=list[RemediationTask],
    status_code=status.HTTP_200_OK,
    summary="View active tasks assigned to the caller",
)
def get_my_tasks(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: RemediationService = Depends(get_remediation_service),
) -> list[RemediationTask]:
    """Retrieves all non-terminal remediation tasks assigned to the authenticated user."""
    user_id = tenant_context.user_id or "user:authenticated"
    return service.get_my_tasks(user_id=user_id, tenant_context=tenant_context)


@router.get(
    "/views/team-tasks",
    response_model=list[RemediationTask],
    status_code=status.HTTP_200_OK,
    summary="View active tasks assigned to team or fallback queue",
)
def get_team_tasks(
    team_id: str = Query(..., description="Target team or queue ID"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: RemediationService = Depends(get_remediation_service),
) -> list[RemediationTask]:
    """Retrieves all non-terminal tasks assigned to a specific team or fallback queue."""
    return service.get_team_tasks(team_id=team_id, tenant_context=tenant_context)


@router.get(
    "/views/by-application/{app_id}",
    response_model=list[RemediationTask],
    status_code=status.HTTP_200_OK,
    summary="View tasks associated with an application",
)
def get_tasks_by_application(
    app_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: RemediationService = Depends(get_remediation_service),
) -> list[RemediationTask]:
    """Retrieves tasks linked to a specific application."""
    return service.get_tasks_by_application(app_id=app_id, tenant_context=tenant_context)


@router.get(
    "/views/by-business-unit/{bu_id}",
    response_model=list[RemediationTask],
    status_code=status.HTTP_200_OK,
    summary="View tasks associated with a business unit",
)
def get_tasks_by_business_unit(
    bu_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: RemediationService = Depends(get_remediation_service),
) -> list[RemediationTask]:
    """Retrieves tasks linked to a specific business unit."""
    return service.get_tasks_by_business_unit(bu_id=bu_id, tenant_context=tenant_context)


@router.get(
    "/views/overdue",
    response_model=list[RemediationTask],
    status_code=status.HTTP_200_OK,
    summary="View tasks currently breaching SLA deadline",
)
def get_overdue_tasks(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: RemediationService = Depends(get_remediation_service),
) -> list[RemediationTask]:
    """Retrieves tasks whose working-hours SLA deadline has passed."""
    return service.get_overdue_tasks(tenant_context=tenant_context)


@router.get(
    "/reports/ageing",
    response_model=AgeingReport,
    status_code=status.HTTP_200_OK,
    summary="Ageing distribution of open remediation tasks",
)
def get_ageing_report(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: RemediationService = Depends(get_remediation_service),
) -> AgeingReport:
    """Produces ageing brackets (0-7d, 8-30d, 31-90d, >90d) for open tasks."""
    return service.get_ageing_report(tenant_context=tenant_context)


@router.get(
    "/reports/trends",
    response_model=TrendReport,
    status_code=status.HTTP_200_OK,
    summary="Leaderboard-free open-vs-closed trends over time",
)
def get_trend_report(
    window_days: int = Query(30, ge=1, le=365, description="Historical analysis window in days"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: RemediationService = Depends(get_remediation_service),
) -> TrendReport:
    """Produces daily timeseries comparing opened vs closed tasks (reporting trends, not people)."""
    return service.get_trend_report(tenant_context=tenant_context, window_days=window_days)


@router.get(
    "/reports/savings",
    response_model=RealisedSavingReport,
    status_code=status.HTTP_200_OK,
    summary="Cumulative realised savings ledger report",
)
def get_savings_report(
    period: str | None = Query(None, description="Optional period filter (e.g. 2026-10)"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: RemediationService = Depends(get_remediation_service),
) -> RealisedSavingReport:
    """Aggregates confirmed empirical savings by period, team, category, and method."""
    return service.get_savings_report(tenant_context=tenant_context, period=period)
