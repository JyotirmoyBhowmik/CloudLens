"""Cost-Aware Topology Domain Service Facade (Prompt 33 / BBP Section 25).

Coordinates:
- Eight canonical graph projections (service, application, account, subscription, project, compartment, resource, cost-aware).
- Deep node enrichment with operational, runtime, threshold, and FinOps telemetry.
- Chain cost aggregation with shared-service apportionment adhering to FinOps allocation rules.
- Multi-chain portfolio rollups deduplicating shared services with zero double-counting.
- Restricted node evaluation rendering privacy placeholders without omitting graph topology.
- Interactive clustering (<2.0s response limit for 500+ nodes).
- Multi-format graph export (JSON, CSV, GraphML, DOT, SVG).
- Full audit event logging for all operations.
"""

from __future__ import annotations

import datetime as dt
import logging
from decimal import Decimal
from typing import Any

from domain.audit.service import AuditService, get_audit_service
from domain.dependency.models import TypedEntityRef
from domain.dependency.repository import (
    DependencyRepository,
    get_dependency_repository,
)
from domain.models.enums import (
    AuditEventType,
    EntityReferenceType,
)
from domain.rbac.models import ScopeGrant
from domain.tenant.context import TenantContext, require_tenant_context
from domain.topology.chain_cost import ChainCostCalculator
from domain.topology.clustering import GraphClusteringEngine
from domain.topology.enricher import NodeEnrichmentService
from domain.topology.exporter import GraphExportService
from domain.topology.models import (
    ChainCostDecomposition,
    GraphExportRequest,
    GraphExportResult,
    MultiChainAggregationRequest,
    MultiChainAggregationResult,
    TopologyGraphView,
    TopologyProjectionRequest,
)
from domain.topology.projection import VIEW_DEFAULT_DEPTHS, GraphProjectionService
from domain.topology.restricted import RestrictedNodeEvaluator

logger = logging.getLogger(__name__)


class TopologyService:
    """Enterprise domain service facade for cost-aware topology and dependency graphs."""

    def __init__(
        self,
        dep_repo: DependencyRepository | None = None,
        enrichment_service: NodeEnrichmentService | None = None,
        chain_calculator: ChainCostCalculator | None = None,
        clustering_engine: GraphClusteringEngine | None = None,
        restricted_evaluator: RestrictedNodeEvaluator | None = None,
        projection_service: GraphProjectionService | None = None,
        export_service: GraphExportService | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self.dep_repo = dep_repo or get_dependency_repository()
        self.enrichment_service = enrichment_service or NodeEnrichmentService()
        self.chain_calculator = chain_calculator or ChainCostCalculator(
            self.dep_repo, self.enrichment_service
        )
        self.clustering_engine = clustering_engine or GraphClusteringEngine()
        self.restricted_evaluator = restricted_evaluator or RestrictedNodeEvaluator()
        self.projection_service = projection_service or GraphProjectionService(
            self.dep_repo,
            self.enrichment_service,
            self.chain_calculator,
            self.clustering_engine,
            self.restricted_evaluator,
        )
        self.export_service = export_service or GraphExportService()
        self.audit_service = audit_service or get_audit_service()

    # ==========================================================================
    # 1. Graph Projection
    # ==========================================================================

    def project_view(
        self,
        req: TopologyProjectionRequest,
        *,
        grants: list[ScopeGrant] | None = None,
        custom_node_costs: dict[str, Decimal] | None = None,
        tenant_context: TenantContext,
    ) -> TopologyGraphView:
        """Projects a canonical topology view enforcing depth, RBAC masking, and enrichment."""
        tc = require_tenant_context(tenant_context)
        view = self.projection_service.project_view(
            req,
            grants=grants,
            custom_node_costs=custom_node_costs,
            tenant_context=tc,
        )

        self._record_audit(
            event_type=AuditEventType.TOPOLOGY_VIEW_PROJECTED,
            actor_id=tc.user_id,
            details={
                "view_type": req.view_type.value,
                "root_entity_id": req.root_entity_id,
                "total_nodes": view.total_nodes,
                "total_edges": view.total_edges,
                "restricted_nodes": view.restricted_nodes_count,
                "clustered_nodes": view.clustered_nodes_count,
                "total_cost": str(view.total_view_cost),
            },
            tenant_context=tc,
        )
        return view

    # ==========================================================================
    # 2. Chain Cost Aggregation
    # ==========================================================================

    def calculate_chain_cost(
        self,
        root_entity_id: str,
        *,
        root_entity_type: EntityReferenceType = EntityReferenceType.APPLICATION,
        max_depth: int = 10,
        period_start: dt.datetime | None = None,
        period_end: dt.datetime | None = None,
        currency: str = "USD",
        as_of: dt.datetime | None = None,
        custom_node_costs: dict[str, Decimal] | None = None,
        tenant_context: TenantContext,
    ) -> ChainCostDecomposition:
        """Computes decomposed dependency chain spend beneath a specific root."""
        tc = require_tenant_context(tenant_context)
        root_ref = TypedEntityRef(
            entity_type=root_entity_type,
            entity_id=root_entity_id,
            name=root_entity_id,
        )
        decomp = self.chain_calculator.calculate_chain_cost(
            root_ref,
            max_depth=max_depth,
            period_start=period_start,
            period_end=period_end,
            currency=currency,
            as_of=as_of,
            custom_node_costs=custom_node_costs,
            tenant_context=tc,
        )

        self._record_audit(
            event_type=AuditEventType.TOPOLOGY_CHAIN_COST_CALCULATED,
            actor_id=tc.user_id,
            details={
                "root_entity_id": root_entity_id,
                "total_chain_cost": str(decomp.total_chain_cost),
                "direct_cost": str(decomp.direct_root_cost),
                "attributed_cost": str(decomp.attributed_downstream_cost),
                "contributing_nodes_count": len(decomp.contributing_nodes),
                "shared_services_count": len(decomp.shared_services_included),
            },
            tenant_context=tc,
        )
        return decomp

    def aggregate_multi_chain(
        self,
        req: MultiChainAggregationRequest,
        *,
        as_of: dt.datetime | None = None,
        custom_node_costs: dict[str, Decimal] | None = None,
        tenant_context: TenantContext,
    ) -> MultiChainAggregationResult:
        """Aggregates multiple dependency chains ensuring shared services are never double-counted."""
        tc = require_tenant_context(tenant_context)
        return self.chain_calculator.aggregate_multi_chain_portfolio(
            req,
            as_of=as_of,
            custom_node_costs=custom_node_costs,
            tenant_context=tc,
        )

    # ==========================================================================
    # 3. Graph Export
    # ==========================================================================

    def export_graph(
        self,
        req: GraphExportRequest,
        *,
        grants: list[ScopeGrant] | None = None,
        custom_node_costs: dict[str, Decimal] | None = None,
        tenant_context: TenantContext,
    ) -> GraphExportResult:
        """Projects and exports the topology graph in the specified format."""
        tc = require_tenant_context(tenant_context)
        view = self.projection_service.project_view(
            req.projection,
            grants=grants,
            custom_node_costs=custom_node_costs,
            tenant_context=tc,
        )
        result = self.export_service.export_graph(view, req.format)

        self._record_audit(
            event_type=AuditEventType.TOPOLOGY_GRAPH_EXPORTED,
            actor_id=tc.user_id,
            details={
                "format": req.format.value,
                "view_type": req.projection.view_type.value,
                "filename": result.filename,
            },
            tenant_context=tc,
        )
        return result

    # ==========================================================================
    # 4. Canonical Views Catalogue
    # ==========================================================================

    def list_canonical_views(self) -> list[dict[str, Any]]:
        """Returns metadata for the eight canonical topology views."""
        views = []
        for vt, (r_type, depth) in VIEW_DEFAULT_DEPTHS.items():
            views.append(
                {
                    "view_type": vt.value,
                    "root_node_type": r_type.value if r_type else None,
                    "default_depth": depth,
                    "supports_cost_overlay": True,
                }
            )
        return views

    # ==========================================================================
    # Audit Helper
    # ==========================================================================

    def _record_audit(
        self,
        *,
        event_type: AuditEventType,
        actor_id: str,
        details: dict[str, Any],
        tenant_context: TenantContext,
    ) -> None:
        try:
            self.audit_service.record_event(
                tenant_context=tenant_context,
                event_type=event_type,
                actor=actor_id,
                payload=details,
                resource_type="TOPOLOGY",
            )
        except Exception as e:
            logger.warning("Audit recording failed: %s", e)


# Global Singleton Facade
_TOPOLOGY_SERVICE: TopologyService | None = None


def get_topology_service() -> TopologyService:
    global _TOPOLOGY_SERVICE
    if _TOPOLOGY_SERVICE is None:
        _TOPOLOGY_SERVICE = TopologyService()
    return _TOPOLOGY_SERVICE


def reset_topology_service() -> None:
    global _TOPOLOGY_SERVICE
    _TOPOLOGY_SERVICE = None
