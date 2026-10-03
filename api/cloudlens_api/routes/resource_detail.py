"""CloudLens Resource Detail, Cost Exploration, Usage, Runtime & Investigation REST API Endpoints (Prompt 39).

Enforces:
- Master brief Section 29 (Resource detail answering all 15 core questions).
- Master brief Section 51 (Cost detail, drivers, investigation).
- BBP Section 30.3 (Resource detail panels).
- BBP Section 31.3 (Cost exploration & Largest Increases investigation).
- Six distinct unblended cost values: current, actual, estimated, forecast, budget, variance.
- Cost driver decomposition where drivers sum strictly to total spend.
- Usage gap discipline: explicit gap rendered as NO_DATA, never zero.
- Schedule adherence with excess hours and excess monetary valuation.
- Investigation view with highlighted change point, contributing resources, changed dimensions, inventory diffs, and restatement flags.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from domain.resource_detail.exceptions import (
    FinancialDetailAccessDeniedException,
    ResourceDetailNotFoundException,
)
from domain.resource_detail.models import (
    ChargeLinesResponse,
    CostExplorerQuery,
    CostExplorerResponse,
    CostInvestigationReport,
    ResourceDetailFull,
    RuntimeEstateOverview,
)
from domain.resource_detail.service import ResourceDetailService, get_resource_detail_service
from domain.tenant.context import TenantContext

router = APIRouter(prefix="/api/v1/resource-detail", tags=["Resource Detail & Cost Exploration"])


@router.get(
    "/runtime-overview", response_model=RuntimeEstateOverview, status_code=status.HTTP_200_OK
)
async def get_runtime_overview(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ResourceDetailService = Depends(get_resource_detail_service),
) -> RuntimeEstateOverview:
    """Retrieves estate-wide runtime schedule adherence, excess hours, and monetary valuation."""
    return service.get_runtime_estate_overview(tenant_context=tenant_context)


@router.get("/{resource_id}", response_model=ResourceDetailFull, status_code=status.HTTP_200_OK)
async def get_resource_detail(
    resource_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ResourceDetailService = Depends(get_resource_detail_service),
) -> ResourceDetailFull:
    """Retrieves full 15-panel resource detail answering all 15 core questions."""
    try:
        return service.get_resource_detail(resource_id=resource_id, tenant_context=tenant_context)
    except ResourceDetailNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.message,
        ) from exc


@router.post("/explorer", response_model=CostExplorerResponse, status_code=status.HTTP_200_OK)
async def explore_costs(
    query: CostExplorerQuery,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ResourceDetailService = Depends(get_resource_detail_service),
) -> CostExplorerResponse:
    """Executes multi-dimensional cost exploration with grouping, filtering, and time granularity."""
    return service.explore_costs(query=query, tenant_context=tenant_context)


@router.get(
    "/explorer/charge-lines", response_model=ChargeLinesResponse, status_code=status.HTTP_200_OK
)
async def get_contributing_charge_lines(
    group_id: str | None = Query(default=None, description="Group or resource ID to filter"),
    dimension: str | None = Query(default=None, description="Grouping dimension"),
    limit: int = Query(default=50, ge=1, le=500, description="Page size limit"),
    offset: int = Query(default=0, ge=0, description="Offset"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ResourceDetailService = Depends(get_resource_detail_service),
) -> ChargeLinesResponse:
    """Retrieves itemized contributing charge lines with financial details."""
    try:
        return service.get_contributing_charge_lines(
            group_id=group_id,
            dimension=dimension,
            tenant_context=tenant_context,
            limit=limit,
            offset=offset,
        )
    except FinancialDetailAccessDeniedException as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=exc.message,
        ) from exc


@router.get(
    "/investigate/{entity_id}",
    response_model=CostInvestigationReport,
    status_code=status.HTTP_200_OK,
)
async def investigate_cost_increase(
    entity_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: ResourceDetailService = Depends(get_resource_detail_service),
) -> CostInvestigationReport:
    """Generates detailed Cost Investigation Report for Largest Increases."""
    try:
        return service.investigate_cost_increase(entity_id=entity_id, tenant_context=tenant_context)
    except ResourceDetailNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.message,
        ) from exc
