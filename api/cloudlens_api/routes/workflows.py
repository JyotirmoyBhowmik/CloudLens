"""Workflow, Approval, and Delegation REST API Endpoints (Prompt 50).

Enforces:
- POST /api/v1/workflows/requests - Submit new change request into workflow engine
- GET /api/v1/workflows/requests - List workflow requests
- GET /api/v1/workflows/requests/{id} - Get single workflow request
- POST /api/v1/workflows/requests/{id}/decide - Approve, reject, or request more information
- POST /api/v1/workflows/requests/{id}/withdraw - Withdraw submission
- GET /api/v1/workflows/inbox - Approver inbox across all request types
- GET /api/v1/workflows/my-requests - Requester status tracking view
- POST /api/v1/workflows/delegations - Register out-of-office delegation rule
- GET /api/v1/workflows/delegations - List active delegations
- DELETE /api/v1/workflows/delegations/{id} - Delete delegation
- GET /api/v1/workflows/definitions - List master data workflow definitions
- POST /api/v1/workflows/definitions - Register/override master data workflow definition
- GET /api/v1/workflows/metrics - Workflow operational and SLA metrics
- Prompt 13 Item 84: 100% TenantContext validation.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query, Response, status

from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from domain.tenant.context import TenantContext
from domain.workflows.models import (
    ApproverInboxItem,
    DelegationCreateRequest,
    DelegationRule,
    RequesterViewItem,
    WorkflowDecisionRequest,
    WorkflowDefinition,
    WorkflowMetricsReport,
    WorkflowRequest,
    WorkflowSubmitRequest,
    WorkflowWithdrawRequest,
)
from domain.workflows.service import WorkflowService, get_workflow_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workflows", tags=["Workflows & Approvals"])


# ==============================================================================
# 1. Workflow Request Lifecycle Endpoints
# ==============================================================================


@router.post(
    "/requests",
    response_model=WorkflowRequest,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a proposed change into the workflow engine",
)
def submit_workflow_request(
    request: WorkflowSubmitRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowRequest:
    """Submits a change request for automated evaluation and approval routing."""
    return service.submit_request(request, tenant_context=tenant_context)


@router.get(
    "/requests",
    response_model=list[WorkflowRequest],
    status_code=status.HTTP_200_OK,
    summary="List workflow requests",
)
def list_workflow_requests(
    state: str | None = Query(None, description="Optional workflow state filter"),
    request_type: str | None = Query(None, description="Optional request type filter"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: WorkflowService = Depends(get_workflow_service),
) -> list[WorkflowRequest]:
    """Lists tenant workflow requests with optional filtering."""
    filter_params: dict[str, Any] = {}
    if state:
        filter_params["state"] = state
    if request_type:
        filter_params["request_type"] = request_type
    return service.list_requests(
        tenant_context=tenant_context,
        filter_params=filter_params,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/requests/{request_id}",
    response_model=WorkflowRequest,
    status_code=status.HTTP_200_OK,
    summary="Get single workflow request details",
)
def get_workflow_request(
    request_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowRequest:
    """Retrieves full workflow request details with approval stages and audit history."""
    return service.get_request(request_id, tenant_context=tenant_context)


@router.post(
    "/requests/{request_id}/decide",
    response_model=WorkflowRequest,
    status_code=status.HTTP_200_OK,
    summary="Render formal decision on a workflow request",
)
def record_workflow_decision(
    request_id: str,
    decision_req: WorkflowDecisionRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowRequest:
    """Approve, reject, or request more information on a pending workflow stage."""
    return service.record_decision(request_id, decision_req, tenant_context=tenant_context)


@router.post(
    "/requests/{request_id}/withdraw",
    response_model=WorkflowRequest,
    status_code=status.HTTP_200_OK,
    summary="Withdraw an open workflow request",
)
def withdraw_workflow_request(
    request_id: str,
    withdraw_req: WorkflowWithdrawRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowRequest:
    """Formally withdraws an in-flight submission."""
    return service.withdraw_request(request_id, withdraw_req, tenant_context=tenant_context)


# ==============================================================================
# 2. Views: Approver Inbox & Requester View
# ==============================================================================


@router.get(
    "/inbox",
    response_model=list[ApproverInboxItem],
    status_code=status.HTTP_200_OK,
    summary="Approver inbox across all request types",
)
def get_approver_inbox(
    user_id: str | None = Query(
        None, description="Optional override user ID; defaults to authenticated actor"
    ),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: WorkflowService = Depends(get_workflow_service),
) -> list[ApproverInboxItem]:
    """Single aggregated inbox showing all pending decisions across all request types."""
    target_user = user_id or tenant_context.user_id
    return service.get_approver_inbox(target_user, tenant_context=tenant_context)


@router.get(
    "/my-requests",
    response_model=list[RequesterViewItem],
    status_code=status.HTTP_200_OK,
    summary="Requester tracking view",
)
def get_requester_view(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: WorkflowService = Depends(get_workflow_service),
) -> list[RequesterViewItem]:
    """Requester view showing everything submitted, its state, who it is with, and escalation ETA."""
    return service.get_requester_view(tenant_context.user_id, tenant_context=tenant_context)


# ==============================================================================
# 3. Delegations & Out-of-Office Rules
# ==============================================================================


@router.post(
    "/delegations",
    response_model=DelegationRule,
    status_code=status.HTTP_201_CREATED,
    summary="Register out-of-office delegation rule",
)
def create_delegation(
    request: DelegationCreateRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: WorkflowService = Depends(get_workflow_service),
) -> DelegationRule:
    """Establishes temporary approval authority delegation."""
    return service.register_delegation(request, tenant_context=tenant_context)


@router.get(
    "/delegations",
    response_model=list[DelegationRule],
    status_code=status.HTTP_200_OK,
    summary="List active delegation rules",
)
def list_delegations(
    user_id: str | None = Query(None, description="Optional user ID filter"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: WorkflowService = Depends(get_workflow_service),
) -> list[DelegationRule]:
    """Lists configured delegations in tenant scope."""
    return service.repository.list_delegations(tenant_context=tenant_context, user_id=user_id)


@router.delete(
    "/delegations/{delegation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete delegation rule",
)
def delete_delegation(
    delegation_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: WorkflowService = Depends(get_workflow_service),
) -> Response:
    """Removes an out-of-office delegation rule."""
    service.repository.delete_delegation(delegation_id, tenant_context=tenant_context)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ==============================================================================
# 4. Master Data Workflow Definitions
# ==============================================================================


@router.get(
    "/definitions",
    response_model=list[WorkflowDefinition],
    status_code=status.HTTP_200_OK,
    summary="List master data workflow definitions",
)
def list_workflow_definitions(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: WorkflowService = Depends(get_workflow_service),
) -> list[WorkflowDefinition]:
    """Lists all active master-data workflow definitions."""
    return service.repository.list_definitions(tenant_context=tenant_context)


@router.post(
    "/definitions",
    response_model=WorkflowDefinition,
    status_code=status.HTTP_201_CREATED,
    summary="Create or override a master data workflow definition",
)
def create_workflow_definition(
    definition: WorkflowDefinition,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowDefinition:
    """Registers a new master-data workflow definition without requiring code changes."""
    return service.repository.save_definition(definition, tenant_context=tenant_context)


# ==============================================================================
# 5. Operational Metrics
# ==============================================================================


@router.get(
    "/metrics",
    response_model=WorkflowMetricsReport,
    status_code=status.HTTP_200_OK,
    summary="Workflow throughput, SLA breaches, and approver velocity metrics",
)
def get_workflow_metrics(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowMetricsReport:
    """Calculates operational workflow metrics."""
    return service.get_metrics(tenant_context=tenant_context)
