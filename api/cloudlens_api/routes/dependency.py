"""Dependency Model, Discovery, and Impact Analysis REST API Endpoints (Prompt 32).

Enforces:
- BBP Section 24: Relationship types, multi-layer discovery, manual edge protection,
  point-in-time graph views, impact-set analysis, bulk import, and billing sync.
- 100% TenantContext validation on all routes.
- Sanitized enterprise error handling with standardized JSON structures.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Response, status

from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from domain.dependency.models import (
    BillingAllocationSyncRequest,
    BillingAllocationSyncResult,
    BulkImportRequest,
    BulkImportResult,
    ConflictResolveRequest,
    DependencyEdge,
    DiscoveryConfiguration,
    DiscoveryRunResult,
    EdgeConflict,
    EdgeUpdateRequest,
    ImpactSet,
    ManualEdgeCreateRequest,
    TopologyGraph,
)
from domain.dependency.service import DependencyService, get_dependency_service
from domain.models.enums import EdgeStatus, RelationshipType
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/dependencies", tags=["Dependency Model & Discovery"])


# ==============================================================================
# 1. Manual Edge Lifecycle
# ==============================================================================


@router.post("/edges/manual", response_model=DependencyEdge, status_code=status.HTTP_201_CREATED)
def create_manual_edge(
    payload: ManualEdgeCreateRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: DependencyService = Depends(get_dependency_service),
) -> DependencyEdge:
    """Creates a manually asserted dependency edge with human curation provenance."""
    actor = tenant_context.user_id or "human-operator"
    return service.create_manual_edge(payload, actor=actor, tenant_context=tenant_context)


@router.get("/edges", response_model=list[DependencyEdge])
def list_edges(
    status_filter: EdgeStatus | None = Query(
        default=None, alias="status", description="Filter by status"
    ),
    relationship_type: RelationshipType | None = Query(
        default=None, description="Filter by canonical relationship type"
    ),
    source_id: str | None = Query(default=None, description="Filter by source entity ID"),
    target_id: str | None = Query(default=None, description="Filter by target entity ID"),
    as_of: dt.datetime | None = Query(
        default=None, description="Point-in-time temporal evaluation timestamp UTC"
    ),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: DependencyService = Depends(get_dependency_service),
) -> list[DependencyEdge]:
    """Lists dependency edges matching filters and point-in-time criterion."""
    return service.list_edges(
        status=status_filter,
        relationship_type=relationship_type,
        as_of=as_of,
        source_id=source_id,
        target_id=target_id,
        tenant_context=tenant_context,
    )


@router.get("/edges/{edge_id}", response_model=DependencyEdge)
def get_edge(
    edge_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: DependencyService = Depends(get_dependency_service),
) -> DependencyEdge:
    """Retrieves an edge by ID."""
    return service.get_edge(edge_id, tenant_context=tenant_context)


@router.put("/edges/{edge_id}", response_model=DependencyEdge)
@router.patch("/edges/{edge_id}", response_model=DependencyEdge)
def update_edge(
    edge_id: str,
    payload: EdgeUpdateRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: DependencyService = Depends(get_dependency_service),
) -> DependencyEdge:
    """Updates attributes of an existing dependency edge."""
    actor = tenant_context.user_id or "system-admin"
    return service.update_edge(edge_id, payload, actor=actor, tenant_context=tenant_context)


@router.delete(
    "/edges/{edge_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_edge(
    edge_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: DependencyService = Depends(get_dependency_service),
) -> Response:
    """Soft-deletes a dependency relationship edge."""
    actor = tenant_context.user_id or "system-admin"
    service.delete_edge(edge_id, actor=actor, tenant_context=tenant_context)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ==============================================================================
# 2. Automated Multi-Layer Discovery
# ==============================================================================


@router.post("/discovery/run", response_model=DiscoveryRunResult)
def run_discovery(
    payload: Any = Body(...),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: DependencyService = Depends(get_dependency_service),
) -> DiscoveryRunResult:
    """Triggers an automated discovery cycle across inventory items and enabled layers."""
    actor = tenant_context.user_id or "discovery-scheduler"
    if isinstance(payload, list):
        items = payload
        config = None
    elif isinstance(payload, dict):
        items = payload.get("inventory_items", [])
        cfg_dict = payload.get("config")
        config = DiscoveryConfiguration.model_validate(cfg_dict) if cfg_dict else None
    else:
        items = []
        config = None
    return service.run_discovery(items, config=config, actor=actor, tenant_context=tenant_context)


# ==============================================================================
# 3. Conflict Surfacing & Human Resolution
# ==============================================================================


@router.get("/conflicts", response_model=list[EdgeConflict])
def list_conflicts(
    unresolved_only: bool = Query(default=True, description="List only unresolved conflicts"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: DependencyService = Depends(get_dependency_service),
) -> list[EdgeConflict]:
    """Lists surfaced conflicts between manual and discovered edges."""
    return service.list_conflicts(unresolved_only=unresolved_only, tenant_context=tenant_context)


@router.post("/conflicts/{conflict_id}/resolve", response_model=EdgeConflict)
def resolve_conflict(
    conflict_id: str,
    payload: ConflictResolveRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: DependencyService = Depends(get_dependency_service),
) -> EdgeConflict:
    """Human resolves a surfaced conflict via KEEP_MANUAL, ACCEPT_DISCOVERED, or MERGE."""
    actor = tenant_context.user_id or "conflict-resolver"
    return service.resolve_conflict(
        conflict_id, payload, actor=actor, tenant_context=tenant_context
    )


# ==============================================================================
# 4. Point-in-Time Topology Graph Rendering
# ==============================================================================


@router.get("/graph", response_model=TopologyGraph)
def get_topology_graph(
    as_of: dt.datetime | None = Query(
        default=None, description="Point-in-time timestamp evaluated UTC"
    ),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: DependencyService = Depends(get_dependency_service),
) -> TopologyGraph:
    """Renders the topology graph as of a past date or current state."""
    return service.get_topology_graph(as_of=as_of, tenant_context=tenant_context)


# ==============================================================================
# 5. Impact-Set Analysis
# ==============================================================================


@router.get("/impact/{entity_id}", response_model=ImpactSet)
def compute_downstream_impact(
    entity_id: str,
    max_depth: int | None = Query(default=None, ge=1, description="Depth limit for traversal"),
    as_of: dt.datetime | None = Query(
        default=None, description="Point-in-time evaluation timestamp UTC"
    ),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: DependencyService = Depends(get_dependency_service),
) -> ImpactSet:
    """Computes downstream dependents of an entity (blast radius)."""
    return service.compute_downstream_impact(
        entity_id, max_depth=max_depth, as_of=as_of, tenant_context=tenant_context
    )


@router.get("/upstream/{entity_id}", response_model=ImpactSet)
def compute_upstream_dependencies(
    entity_id: str,
    max_depth: int | None = Query(default=None, ge=1, description="Depth limit for traversal"),
    as_of: dt.datetime | None = Query(
        default=None, description="Point-in-time evaluation timestamp UTC"
    ),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: DependencyService = Depends(get_dependency_service),
) -> ImpactSet:
    """Computes all upstream dependencies an entity relies upon."""
    return service.compute_upstream_dependencies(
        entity_id, max_depth=max_depth, as_of=as_of, tenant_context=tenant_context
    )


# ==============================================================================
# 6. Bulk Import & Billing Synchronization
# ==============================================================================


@router.post("/bulk-import", response_model=BulkImportResult)
def bulk_import_relationships(
    payload: BulkImportRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: DependencyService = Depends(get_dependency_service),
) -> BulkImportResult:
    """Bulk imports relationships from external CMDBs, CSV, or JSON sources."""
    actor = tenant_context.user_id or "cmdb-sync"
    return service.bulk_import(payload, actor=actor, tenant_context=tenant_context)


@router.post("/billing-sync", response_model=BillingAllocationSyncResult)
def sync_billing_relationships(
    payload: BillingAllocationSyncRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: DependencyService = Depends(get_dependency_service),
) -> BillingAllocationSyncResult:
    """Links shared-service costs to consumer applications/scopes in the graph."""
    actor = tenant_context.user_id or "finops-allocator"
    return service.sync_billing_relationships(payload, actor=actor, tenant_context=tenant_context)
