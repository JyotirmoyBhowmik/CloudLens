"""Cost-Aware Topology and Dependency Graph REST API Endpoints (Prompt 33 / BBP Section 25).

Enforces:
1. Eight Canonical Views graph projection (/api/v1/topology/project).
2. Decomposed dependency chain cost (/api/v1/topology/chain-cost/{entity_id}).
3. Multi-chain portfolio rollups with shared service deduplication (/api/v1/topology/multi-chain-cost).
4. Multi-format graph export (/api/v1/topology/export).
5. Canonical view catalogue metadata (/api/v1/topology/views).
6. 100% TenantContext validation and enterprise error response compliance.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from fastapi import APIRouter, Depends, Path, Query

from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from domain.models.enums import EntityReferenceType
from domain.tenant.context import TenantContext
from domain.topology.models import (
    ChainCostDecomposition,
    GraphExportRequest,
    GraphExportResult,
    MultiChainAggregationRequest,
    MultiChainAggregationResult,
    TopologyGraphView,
    TopologyProjectionRequest,
)
from domain.topology.service import TopologyService, get_topology_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/topology", tags=["Cost-Aware Topology & Dependency Graph"])


# ==============================================================================
# 1. Canonical Views Metadata
# ==============================================================================


@router.get("/views", response_model=list[dict[str, Any]])
def list_canonical_views(
    service: TopologyService = Depends(get_topology_service),
) -> list[dict[str, Any]]:
    """Lists metadata and default depths for all eight canonical topology views."""
    return service.list_canonical_views()


# ==============================================================================
# 2. Graph Projection
# ==============================================================================


@router.post("/project", response_model=TopologyGraphView)
def project_topology_view(
    payload: TopologyProjectionRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: TopologyService = Depends(get_topology_service),
) -> TopologyGraphView:
    """Projects a canonical topology view enforcing depth, RBAC masking, and enrichment."""
    return service.project_view(payload, tenant_context=tenant_context)


# ==============================================================================
# 3. Chain Cost Decomposition
# ==============================================================================


@router.get("/chain-cost/{entity_id}", response_model=ChainCostDecomposition)
def get_chain_cost(
    entity_id: str = Path(..., description="Root application or service entity ID"),
    entity_type: EntityReferenceType = Query(
        default=EntityReferenceType.APPLICATION, description="Root entity reference classification"
    ),
    max_depth: int = Query(default=10, ge=1, le=10, description="Max traversal depth"),
    period_start: dt.datetime | None = Query(default=None, description="Start date UTC"),
    period_end: dt.datetime | None = Query(default=None, description="End date UTC"),
    currency: str = Query(default="USD", description="Currency ISO 4217 code"),
    as_of: dt.datetime | None = Query(default=None, description="Point-in-time timestamp UTC"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: TopologyService = Depends(get_topology_service),
) -> ChainCostDecomposition:
    """Computes granular chain spend decomposition beneath a specific root entity."""
    return service.calculate_chain_cost(
        entity_id,
        root_entity_type=entity_type,
        max_depth=max_depth,
        period_start=period_start,
        period_end=period_end,
        currency=currency,
        as_of=as_of,
        tenant_context=tenant_context,
    )


@router.post("/multi-chain-cost", response_model=MultiChainAggregationResult)
def aggregate_multi_chain_cost(
    payload: MultiChainAggregationRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: TopologyService = Depends(get_topology_service),
) -> MultiChainAggregationResult:
    """Aggregates multiple dependency chains ensuring shared services are deduplicated."""
    return service.aggregate_multi_chain(payload, tenant_context=tenant_context)


# ==============================================================================
# 4. Multi-Format Graph Export
# ==============================================================================


@router.post("/export", response_model=GraphExportResult)
def export_topology_graph(
    payload: GraphExportRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    service: TopologyService = Depends(get_topology_service),
) -> GraphExportResult:
    """Exports projected topology graph to JSON, CSV, GraphML, DOT, or SVG formats."""
    return service.export_graph(payload, tenant_context=tenant_context)
