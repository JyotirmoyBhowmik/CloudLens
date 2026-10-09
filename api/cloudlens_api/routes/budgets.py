"""Budget Model & Allocation API Endpoints (Prompt 28).

Enforces:
- API-037: GET /api/v1/budgets - List budgets with current spend and utilisation.
- API-038: POST /api/v1/budgets - Create a new budget record.
- API-039: PATCH /api/v1/budgets/{id} - Amend an existing budget allocation.
- Prompt 28: Support all seventeen scope types.
- Prompt 28: Overlap, over-allocation, and double-counting warning generation.
- Prompt 28: Formal approval workflow for budgets exceeding the approval limit.
- Prompt 28: Provider-native read-only budget import.
- Prompt 13 Item 84: 100% TenantContext validation.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel

from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from domain.budgets.models import (
    BudgetAmendRequest,
    BudgetApprovalStatus,
    BudgetApproveRequest,
    BudgetCreateRequest,
    BudgetEntity,
    BudgetEvaluationResult,
    BudgetHierarchySummary,
    BudgetOverlapWarning,
    BudgetRejectRequest,
    BudgetScopeType,
    BudgetTemplate,
    NativeBudgetImportRequest,
)
from domain.budgets.service import BudgetService, get_budget_service
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/budgets", tags=["Budgets & Allocations"])


# ==============================================================================
# Response Models
# ==============================================================================


class BudgetListResponse(BaseModel):
    """Paginated list of budget allocations (API-037)."""

    items: list[dict[str, Any]]
    total: int
    limit: int
    offset: int


class BudgetCreateResponse(BaseModel):
    """Response returned upon budget creation including overlap warnings."""

    budget: BudgetEntity
    warnings: list[BudgetOverlapWarning]


# ==============================================================================
# Endpoints
# ==============================================================================


@router.get("", response_model=BudgetListResponse, status_code=status.HTTP_200_OK)
def list_budgets(
    scope_type: BudgetScopeType | None = Query(None, description="Filter by scope type"),
    scope_id: str | None = Query(None, description="Filter by scope node ID"),
    approval_status: BudgetApprovalStatus | None = Query(
        None, description="Filter by approval status"
    ),
    is_native: bool | None = Query(
        None, description="Filter by provider-native vs CloudLens logical"
    ),
    include_evaluation: bool = Query(
        True, description="Whether to include real-time evaluation metrics"
    ),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: BudgetService = Depends(get_budget_service),
) -> BudgetListResponse:
    """Lists budgets for the calling tenant with optional real-time utilisation (API-037)."""
    entities = service.list_budgets(
        tenant_context=tenant_context,
        scope_type=scope_type,
        scope_id=scope_id,
        approval_status=approval_status,
        is_native=is_native,
        limit=limit,
        offset=offset,
    )

    items: list[dict[str, Any]] = []
    for b in entities:
        item = b.model_dump()
        if include_evaluation and b.approval_status != BudgetApprovalStatus.PENDING_APPROVAL:
            try:
                eval_res = service.evaluate_budget(b.id, tenant_context=tenant_context)
                item["evaluation"] = eval_res.model_dump()
            except Exception as e:
                logger.warning("Could not evaluate budget %s: %s", b.id, e)
                item["evaluation"] = None
        else:
            item["evaluation"] = None
        items.append(item)

    all_total = len(service.repository.list_all(tenant_context=tenant_context))
    return BudgetListResponse(items=items, total=all_total, limit=limit, offset=offset)


@router.post("", response_model=BudgetCreateResponse, status_code=status.HTTP_201_CREATED)
def create_budget(
    request: BudgetCreateRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: BudgetService = Depends(get_budget_service),
) -> BudgetCreateResponse:
    """Creates a new budget across any of the seventeen scope types (API-038).

    If amount > approval limit, budget enters PENDING_APPROVAL.
    Detects and returns all overlap warnings (same scope, child over-allocation, logical vs native).
    """
    budget, warnings = service.create_budget(request, tenant_context=tenant_context)
    return BudgetCreateResponse(budget=budget, warnings=warnings)


@router.get("/templates", response_model=list[BudgetTemplate], status_code=status.HTTP_200_OK)
def list_budget_templates(
    _tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: BudgetService = Depends(get_budget_service),
) -> list[BudgetTemplate]:
    """Retrieves standard pre-configured budget templates for all seventeen scope types."""
    return service.get_templates()


@router.get(
    "/templates/{scope_type}",
    response_model=BudgetTemplate,
    status_code=status.HTTP_200_OK,
)
def get_budget_template_by_scope(
    scope_type: BudgetScopeType,
    _tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: BudgetService = Depends(get_budget_service),
) -> BudgetTemplate:
    """Retrieves standard pre-configured budget template for a specific scope type."""
    return service.get_template_for_scope(scope_type)


@router.post(
    "/import-native",
    response_model=BudgetEntity,
    status_code=status.HTTP_201_CREATED,
)
def import_native_budget(
    request: NativeBudgetImportRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: BudgetService = Depends(get_budget_service),
) -> BudgetEntity:
    """Imports a cloud provider native budget (AWS, Azure, GCP, OCI) as read-only for comparison."""
    return service.import_native_budget(request, tenant_context=tenant_context)


@router.get("/{budget_id}", response_model=BudgetEntity, status_code=status.HTTP_200_OK)
def get_budget(
    budget_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: BudgetService = Depends(get_budget_service),
) -> BudgetEntity:
    """Retrieves details of a single budget."""
    return service.get_budget(budget_id, tenant_context=tenant_context)


@router.patch("/{budget_id}", response_model=BudgetEntity, status_code=status.HTTP_200_OK)
def amend_budget(
    budget_id: str,
    request: BudgetAmendRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: BudgetService = Depends(get_budget_service),
) -> BudgetEntity:
    """Amends a budget allocation ceiling, recording full amendment history (API-039)."""
    return service.amend_budget(budget_id, request, tenant_context=tenant_context)


@router.post("/{budget_id}/approve", response_model=BudgetEntity, status_code=status.HTTP_200_OK)
def approve_budget(
    budget_id: str,
    request: BudgetApproveRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: BudgetService = Depends(get_budget_service),
) -> BudgetEntity:
    """Approves a budget in PENDING_APPROVAL state, recording approver identity and comment."""
    return service.approve_budget(budget_id, request, tenant_context=tenant_context)


@router.post("/{budget_id}/reject", response_model=BudgetEntity, status_code=status.HTTP_200_OK)
def reject_budget(
    budget_id: str,
    request: BudgetRejectRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: BudgetService = Depends(get_budget_service),
) -> BudgetEntity:
    """Rejects a budget in PENDING_APPROVAL state."""
    return service.reject_budget(budget_id, request, tenant_context=tenant_context)


@router.get(
    "/{budget_id}/evaluation",
    response_model=BudgetEvaluationResult,
    status_code=status.HTTP_200_OK,
)
def evaluate_budget(
    budget_id: str,
    actual_spend: float | None = Query(
        None, description="Optional current spend override for evaluation"
    ),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: BudgetService = Depends(get_budget_service),
) -> BudgetEvaluationResult:
    """Evaluates actual consumption, forecast burn rate, variance, and threshold state."""
    return service.evaluate_budget(
        budget_id,
        actual_spend=actual_spend,
        tenant_context=tenant_context,
    )


@router.get(
    "/{budget_id}/hierarchy",
    response_model=BudgetHierarchySummary,
    status_code=status.HTTP_200_OK,
)
def get_budget_hierarchy(
    budget_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: BudgetService = Depends(get_budget_service),
) -> BudgetHierarchySummary:
    """Returns child allocations and unallocated remainder of a parent budget."""
    return service.get_budget_hierarchy(budget_id, tenant_context=tenant_context)


@router.get(
    "/{budget_id}/overlaps",
    response_model=list[BudgetOverlapWarning],
    status_code=status.HTTP_200_OK,
)
def get_budget_overlaps(
    budget_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: BudgetService = Depends(get_budget_service),
) -> list[BudgetOverlapWarning]:
    """Returns detected overlaps including logical vs native dual-accounting explanations."""
    return service.get_budget_overlaps(budget_id, tenant_context=tenant_context)


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_budget(
    budget_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: BudgetService = Depends(get_budget_service),
) -> Response:
    """Deletes a budget. Provider-native budgets cannot be deleted."""
    service.delete_budget(budget_id, tenant_context=tenant_context)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/plans", response_model=list[dict[str, Any]], status_code=status.HTTP_200_OK)
def list_budget_plans(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: BudgetService = Depends(get_budget_service),
) -> list[dict[str, Any]]:
    """Returns budget planning cycles and workspaces for tenant."""
    budgets_list = service.list_budgets(tenant_context=tenant_context)
    if not budgets_list:
        return []
    plans = []
    for b in budgets_list:
        amt = float(b.get("amount") or 0.0)
        fc = float(b.get("forecast_spend") or amt)
        cur = float(b.get("current_spend") or 0.0)
        plans.append({
            "id": f"PLAN-{b.get('id', 'item')}",
            "scopeName": b.get("name", "Scope"),
            "scopeType": b.get("scope_type", "APPLICATION"),
            "currentRunRate": cur,
            "baseForecast": fc,
            "proposedBudget": amt,
            "plannedAdjustment": round(amt - fc, 2),
            "variancePct": round(((amt - fc) / fc * 100), 1) if fc > 0 else 0.0,
            "status": "APPROVED" if b.get("approval_status") == "APPROVED" else "DRAFT",
        })
    return plans

