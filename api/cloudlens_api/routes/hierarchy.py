"""CloudLens Hierarchy Explorer, Inventory & Search REST API Endpoints (Prompt 38).

Enforces:
- FR-107: Multi-attribute inventory filtering across provider, account, region, type, status, tag, and owner.
- FR-580: Global search across resources, services, scopes, applications, budgets, owners, connectors, policies, alerts.
- FR-581: Boolean logic: AND across filter types, OR within multi-selects.
- FR-582: URL-synchronizable filter state.
- FR-583: Saved, named, and shareable custom views.
- FR-584: Reactive count preview before full dataset loads.
- FR-585: Scope-safe search: never disclose existence or names of entities outside user scope grants.
- Six lateral lenses: PROVIDER_HIERARCHY, APPLICATION, COST_CENTRE, ENVIRONMENT, OWNER, REGION, TAG.
- Worst child threshold state bubbling and aggregate roll-up at every hierarchy level.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from domain.hierarchy.models import (
    BulkAssignmentRequest,
    BulkAssignmentResponse,
    FilterCountPreview,
    GlobalSearchResponse,
    HierarchyDetailPane,
    HierarchyNode,
    InventoryFilterQuery,
    InventoryResource35,
    LateralLensType,
    SavedInventoryView,
)
from domain.hierarchy.service import HierarchyService, get_hierarchy_service
from domain.tenant.context import TenantContext

router = APIRouter(prefix="/api/v1/hierarchy", tags=["Hierarchy & Inventory"])


class InventoryQueryResponse(BaseModel):
    """Paginated inventory query response containing 35-field records."""

    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1)
    offset: int = Field(..., ge=0)
    items: list[InventoryResource35] = Field(default_factory=list)


@router.get("/tree", response_model=HierarchyNode, status_code=status.HTTP_200_OK)
async def get_hierarchy_tree(
    lens_type: LateralLensType = Query(
        default=LateralLensType.PROVIDER_HIERARCHY,
        description="Hierarchy entry lens (PROVIDER_HIERARCHY, APPLICATION, COST_CENTRE, etc.)",
    ),
    root_id: str | None = Query(default=None, description="Optional root node identifier"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: HierarchyService = Depends(get_hierarchy_service),
) -> HierarchyNode:
    """Retrieves full hierarchical tree with rolled-up spend and worst-child threshold states."""
    return service.get_hierarchy_tree(
        lens_type=lens_type,
        tenant_context=tenant_context,
        root_id=root_id,
    )


@router.get("/nodes/{node_id}", response_model=HierarchyDetailPane, status_code=status.HTTP_200_OK)
async def get_hierarchy_node_detail(
    node_id: str,
    lens_type: LateralLensType = Query(
        default=LateralLensType.PROVIDER_HIERARCHY,
        description="Hierarchy entry lens",
    ),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: HierarchyService = Depends(get_hierarchy_service),
) -> HierarchyDetailPane:
    """Retrieves detail pane for selected hierarchy node with direct resources and contributing services."""
    return service.get_node_detail(
        node_id=node_id,
        lens_type=lens_type,
        tenant_context=tenant_context,
    )


@router.get("/search", response_model=GlobalSearchResponse, status_code=status.HTTP_200_OK)
async def search_global(
    q: str = Query(..., min_length=1, description="Search query string"),
    limit: int = Query(default=25, ge=1, le=100, description="Max result count"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: HierarchyService = Depends(get_hierarchy_service),
) -> GlobalSearchResponse:
    """Performs scope-safe global search across 9 entity types with exact-identifier match priority."""
    return service.search_global(
        query=q,
        tenant_context=tenant_context,
        limit=limit,
    )


@router.post(
    "/inventory/count-preview",
    response_model=FilterCountPreview,
    status_code=status.HTTP_200_OK,
)
async def preview_filter_counts(
    query: InventoryFilterQuery,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: HierarchyService = Depends(get_hierarchy_service),
) -> FilterCountPreview:
    """Reactive count preview before full result pagination loads (FR-584)."""
    return service.preview_filter_counts(
        query=query,
        tenant_context=tenant_context,
    )


@router.post(
    "/inventory/query",
    response_model=InventoryQueryResponse,
    status_code=status.HTTP_200_OK,
)
async def query_inventory(
    query: InventoryFilterQuery,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: HierarchyService = Depends(get_hierarchy_service),
) -> InventoryQueryResponse:
    """Filterable table query over all 35 canonical inventory fields (FR-107, FR-581)."""
    total, items = service.query_inventory(
        query=query,
        tenant_context=tenant_context,
        limit=limit,
        offset=offset,
    )
    return InventoryQueryResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=items,
    )


@router.post(
    "/inventory/bulk-assign",
    response_model=BulkAssignmentResponse,
    status_code=status.HTTP_200_OK,
)
async def bulk_assign_curated_fields(
    request: BulkAssignmentRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: HierarchyService = Depends(get_hierarchy_service),
) -> BulkAssignmentResponse:
    """Bulk assignment of ownership, application, environment, and cost centre (FR-108)."""
    return service.bulk_assign_curated_fields(
        request=request,
        tenant_context=tenant_context,
    )


@router.get(
    "/inventory/views",
    response_model=list[SavedInventoryView],
    status_code=status.HTTP_200_OK,
)
async def list_saved_views(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: HierarchyService = Depends(get_hierarchy_service),
) -> list[SavedInventoryView]:
    """Lists saved custom views (FR-583)."""
    return service.list_saved_views(tenant_context=tenant_context)


@router.post(
    "/inventory/views",
    response_model=SavedInventoryView,
    status_code=status.HTTP_200_OK,
)
async def save_view(
    view: SavedInventoryView,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: HierarchyService = Depends(get_hierarchy_service),
) -> SavedInventoryView:
    """Saves custom named view (FR-583)."""
    return service.save_view(view=view, tenant_context=tenant_context)


@router.delete(
    "/inventory/views/{view_id}",
    status_code=status.HTTP_200_OK,
)
async def delete_saved_view(
    view_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: HierarchyService = Depends(get_hierarchy_service),
) -> dict[str, bool]:
    """Deletes a saved view."""
    success = service.delete_saved_view(view_id=view_id, tenant_context=tenant_context)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Saved view '{view_id}' not found.",
        )
    return {"deleted": True}


@router.post(
    "/inventory/export",
    status_code=status.HTTP_200_OK,
)
async def export_inventory(
    query: InventoryFilterQuery,
    format: str = Query(default="csv", pattern="^(csv|json)$"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: HierarchyService = Depends(get_hierarchy_service),
) -> Response:
    """Exports 35-field inventory matching filter into CSV or JSON respecting scope grants."""
    content, media_type = service.export_inventory(
        query=query,
        export_format=format,
        tenant_context=tenant_context,
    )
    filename = f"cloudlens_inventory.{format.lower()}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
