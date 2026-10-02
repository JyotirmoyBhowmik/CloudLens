"""Graph Projection Service for Eight Canonical Topology Views (Prompt 33 / BBP Section 25).

Enforces:
1. Eight Canonical Views:
   - SERVICE_DEPENDENCY: root SERVICE, default depth 3
   - APPLICATION_DEPENDENCY: root APPLICATION, default depth 4
   - ACCOUNT_TOPOLOGY: root SCOPE, default depth 2
   - SUBSCRIPTION_TOPOLOGY: root SCOPE, default depth 2
   - PROJECT_TOPOLOGY: root SCOPE, default depth 2
   - COMPARTMENT_TOPOLOGY: root SCOPE, default depth 2
   - RESOURCE_RELATIONSHIP: root RESOURCE, default depth 2
   - COST_AWARE_DEPENDENCY: root any, default depth 3, with visual spend overlay
2. Full node telemetry enrichment and restricted-node masking.
3. Interactive performance clustering and depth limits.
4. Chain cost decomposition attached when view is rooted.
"""

from __future__ import annotations

import collections
import datetime as dt
import logging
from decimal import Decimal

from domain.dependency.models import DependencyEdge, TypedEntityRef
from domain.dependency.repository import DependencyRepository
from domain.models.enums import (
    DependencyDirection,
    EdgeStatus,
    EntityReferenceType,
    TopologyViewType,
)
from domain.models.exceptions import (
    InvalidTraversalDepthException,
    TopologyViewNotFoundException,
)
from domain.rbac.models import ScopeGrant
from domain.rules.monetary import round_currency
from domain.tenant.context import TenantContext, require_tenant_context
from domain.topology.chain_cost import ChainCostCalculator
from domain.topology.clustering import GraphClusteringEngine
from domain.topology.enricher import NodeEnrichmentService
from domain.topology.models import (
    ChainCostDecomposition,
    TopologyEdge,
    TopologyGraphView,
    TopologyNode,
    TopologyProjectionRequest,
)
from domain.topology.restricted import RestrictedNodeEvaluator

logger = logging.getLogger(__name__)

VIEW_DEFAULT_DEPTHS: dict[TopologyViewType, tuple[EntityReferenceType | None, int]] = {
    TopologyViewType.SERVICE_DEPENDENCY: (EntityReferenceType.SERVICE, 3),
    TopologyViewType.APPLICATION_DEPENDENCY: (EntityReferenceType.APPLICATION, 4),
    TopologyViewType.ACCOUNT_TOPOLOGY: (EntityReferenceType.SCOPE, 2),
    TopologyViewType.SUBSCRIPTION_TOPOLOGY: (EntityReferenceType.SCOPE, 2),
    TopologyViewType.PROJECT_TOPOLOGY: (EntityReferenceType.SCOPE, 2),
    TopologyViewType.COMPARTMENT_TOPOLOGY: (EntityReferenceType.SCOPE, 2),
    TopologyViewType.RESOURCE_RELATIONSHIP: (EntityReferenceType.RESOURCE, 2),
    TopologyViewType.COST_AWARE_DEPENDENCY: (None, 3),
}


class GraphProjectionService:
    """Projects, enriches, masks, and clusters the cost-aware topology graph."""

    def __init__(
        self,
        dep_repo: DependencyRepository,
        enrichment_service: NodeEnrichmentService,
        chain_calculator: ChainCostCalculator,
        clustering_engine: GraphClusteringEngine | None = None,
        restricted_evaluator: RestrictedNodeEvaluator | None = None,
    ) -> None:
        self.dep_repo = dep_repo
        self.enrichment_service = enrichment_service
        self.chain_calculator = chain_calculator
        self.clustering_engine = clustering_engine or GraphClusteringEngine()
        self.restricted_evaluator = restricted_evaluator or RestrictedNodeEvaluator()

    def project_view(
        self,
        req: TopologyProjectionRequest,
        *,
        grants: list[ScopeGrant] | None = None,
        custom_node_costs: dict[str, Decimal] | None = None,
        tenant_context: TenantContext,
    ) -> TopologyGraphView:
        """Projects a canonical topology graph view matching requested constraints."""
        tc = require_tenant_context(tenant_context)
        now = dt.datetime.now(dt.UTC)
        as_of = req.as_of or now
        period_start = req.period_start or (now - dt.timedelta(days=30))
        period_end = req.period_end or now

        # Validate view type
        if req.view_type not in VIEW_DEFAULT_DEPTHS:
            raise TopologyViewNotFoundException(req.view_type.value)

        expected_root_type, default_depth = VIEW_DEFAULT_DEPTHS[req.view_type]
        depth = req.max_depth or default_depth
        if depth < 1 or depth > 10:
            raise InvalidTraversalDepthException(depth, 10)

        # List all active edges for tenant as of timestamp
        raw_edges = self.dep_repo.list_edges(
            status=EdgeStatus.ACTIVE if req.as_of is None else None,
            as_of=as_of,
            tenant_context=tc,
        )

        # Filter by relationship types if specified
        if req.relationship_types:
            raw_edges = [e for e in raw_edges if e.relationship_type in req.relationship_types]

        # Build index of known entity references
        known_entities: dict[str, TypedEntityRef] = {}
        for edge in raw_edges:
            known_entities[edge.source_ref.entity_id] = edge.source_ref
            known_entities[edge.target_ref.entity_id] = edge.target_ref

        # Determine root entity ref
        root_ref: TypedEntityRef | None = None
        if req.root_entity_id:
            if req.root_entity_id in known_entities:
                root_ref = known_entities[req.root_entity_id]
            else:
                # Construct from params if not directly in edges
                r_type = (
                    req.root_entity_type or expected_root_type or EntityReferenceType.APPLICATION
                )
                root_ref = TypedEntityRef(
                    entity_type=r_type,
                    entity_id=req.root_entity_id,
                    name=req.root_entity_id,
                )
                known_entities[req.root_entity_id] = root_ref

        # If no explicit root given, select an appropriate root matching expected_root_type or first source
        if not root_ref and req.view_type != TopologyViewType.COST_AWARE_DEPENDENCY:
            for ref in known_entities.values():
                if expected_root_type is None or ref.entity_type == expected_root_type:
                    root_ref = ref
                    break

        # Collect reachable nodes and edges via BFS traversal
        projected_nodes_map: dict[str, TopologyNode] = {}
        projected_edges: list[TopologyEdge] = []

        if root_ref:
            # Traversal rooted at root_ref
            projected_nodes_map, projected_edges = self._traverse_from_root(
                root_ref,
                raw_edges,
                known_entities,
                max_depth=depth,
                p_start=period_start,
                p_end=period_end,
                currency=req.currency,
                custom_node_costs=custom_node_costs,
                tc=tc,
            )
        else:
            # Whole-graph projection (e.g. general cost-aware dependency view without single root)
            projected_nodes_map, projected_edges = self._project_all(
                raw_edges,
                known_entities,
                _max_depth=depth,
                p_start=period_start,
                p_end=period_end,
                currency=req.currency,
                custom_node_costs=custom_node_costs,
                tc=tc,
            )

        # Evaluate RBAC for each node and mask restricted nodes
        restricted_count = 0
        restricted_node_ids: set[str] = set()
        final_nodes: list[TopologyNode] = []

        for node in projected_nodes_map.values():
            is_allowed = self.restricted_evaluator.evaluate_access(
                node, grants=grants, tenant_context=tc
            )
            if not is_allowed:
                masked = self.restricted_evaluator.mask_node(node)
                final_nodes.append(masked)
                restricted_count += 1
                restricted_node_ids.add(node.id)
            else:
                final_nodes.append(node)

        # Mark restricted edges
        final_edges = self.restricted_evaluator.mask_edges_for_restricted_nodes(
            projected_edges, restricted_node_ids
        )

        # Clustering and collapse filtering
        collapsed_set = set(req.collapsed_node_ids) if req.collapsed_node_ids else None
        clustered_nodes, clustered_edges, clustered_count = (
            self.clustering_engine.prune_and_cluster(
                final_nodes,
                final_edges,
                max_depth=depth,
                collapsed_node_ids=collapsed_set,
                interactive_node_limit=req.interactive_node_limit,
                enable_clustering=req.enable_clustering,
                currency=req.currency,
            )
        )

        # Calculate chain cost decomposition if root specified
        chain_decomp: ChainCostDecomposition | None = None
        if root_ref:
            try:
                chain_decomp = self.chain_calculator.calculate_chain_cost(
                    root_ref,
                    max_depth=depth,
                    period_start=period_start,
                    period_end=period_end,
                    currency=req.currency,
                    as_of=as_of,
                    custom_node_costs=custom_node_costs,
                    tenant_context=tc,
                )
            except Exception as e:
                logger.warning(
                    "Chain cost calculation could not be completed for root %s: %s", root_ref.key, e
                )

        # Compute total visible spend
        total_view_cost = sum((n.direct_cost for n in clustered_nodes), Decimal("0.0"))

        return TopologyGraphView(
            tenant_id=tc.tenant_id,
            view_type=req.view_type,
            root_entity=root_ref,
            as_of=as_of,
            period_start=period_start,
            period_end=period_end,
            currency=req.currency,
            max_depth=depth,
            total_nodes=len(clustered_nodes),
            total_edges=len(clustered_edges),
            restricted_nodes_count=restricted_count,
            clustered_nodes_count=clustered_count,
            total_view_cost=round_currency(total_view_cost),
            nodes=clustered_nodes,
            edges=clustered_edges,
            chain_cost=chain_decomp,
        )

    def _traverse_from_root(
        self,
        root_ref: TypedEntityRef,
        raw_edges: list[DependencyEdge],
        _known_entities: dict[str, TypedEntityRef],
        *,
        max_depth: int,
        p_start: dt.datetime,
        p_end: dt.datetime,
        currency: str,
        custom_node_costs: dict[str, Decimal] | None,
        tc: TenantContext,
    ) -> tuple[dict[str, TopologyNode], list[TopologyEdge]]:
        """Traverses out from root node up to max_depth."""
        # Adjacency map: source_id -> list of (target_ref, edge)
        adj: dict[str, list[tuple[TypedEntityRef, DependencyEdge]]] = collections.defaultdict(list)
        for e in raw_edges:
            s_id = e.source_ref.entity_id
            t_id = e.target_ref.entity_id
            adj[s_id].append((e.target_ref, e))
            if e.direction == DependencyDirection.BIDIRECTIONAL:
                adj[t_id].append((e.source_ref, e))

        nodes_map: dict[str, TopologyNode] = {}
        edges_list: list[TopologyEdge] = []
        edge_ids_seen: set[str] = set()

        # Root node
        root_telemetry = (
            {"cost": custom_node_costs[root_ref.entity_id]}
            if custom_node_costs and root_ref.entity_id in custom_node_costs
            else None
        )
        root_enrichment = self.enrichment_service.enrich_node(
            root_ref,
            period_start=p_start,
            period_end=p_end,
            currency=currency,
            custom_telemetry=root_telemetry,
            tenant_context=tc,
        )

        nodes_map[root_ref.entity_id] = TopologyNode(
            id=root_ref.entity_id,
            entity_ref=root_ref,
            display_name=root_ref.name or root_ref.entity_id,
            depth=0,
            is_root=True,
            is_restricted=False,
            enrichment=root_enrichment,
            direct_cost=root_enrichment.cost,
            attributed_chain_cost=root_enrichment.cost,
        )

        queue = collections.deque([(root_ref.entity_id, 0)])
        visited = {root_ref.entity_id}

        while queue:
            curr_id, d = queue.popleft()
            if d >= max_depth:
                continue

            for child_ref, edge in adj.get(curr_id, []):
                child_id = child_ref.entity_id

                if edge.id not in edge_ids_seen:
                    edge_ids_seen.add(edge.id)
                    edges_list.append(
                        TopologyEdge(
                            edge_id=edge.id,
                            source_id=edge.source_ref.entity_id,
                            target_id=edge.target_ref.entity_id,
                            relationship_type=edge.relationship_type,
                            direction=edge.direction,
                            criticality=edge.criticality,
                            confidence=edge.confidence,
                            is_restricted=False,
                            billing_attributes=edge.billing_attributes,
                        )
                    )

                if child_id not in visited:
                    visited.add(child_id)
                    child_telemetry = (
                        {"cost": custom_node_costs[child_id]}
                        if custom_node_costs and child_id in custom_node_costs
                        else None
                    )
                    child_enrichment = self.enrichment_service.enrich_node(
                        child_ref,
                        period_start=p_start,
                        period_end=p_end,
                        currency=currency,
                        custom_telemetry=child_telemetry,
                        tenant_context=tc,
                    )

                    nodes_map[child_id] = TopologyNode(
                        id=child_id,
                        entity_ref=child_ref,
                        display_name=child_ref.name or child_id,
                        depth=d + 1,
                        is_root=False,
                        is_restricted=False,
                        enrichment=child_enrichment,
                        direct_cost=child_enrichment.cost,
                        attributed_chain_cost=child_enrichment.cost,
                    )
                    queue.append((child_id, d + 1))

        return nodes_map, edges_list

    def _project_all(
        self,
        raw_edges: list[DependencyEdge],
        known_entities: dict[str, TypedEntityRef],
        *,
        _max_depth: int,
        p_start: dt.datetime,
        p_end: dt.datetime,
        currency: str,
        custom_node_costs: dict[str, Decimal] | None,
        tc: TenantContext,
    ) -> tuple[dict[str, TopologyNode], list[TopologyEdge]]:
        """Projects all entities and active edges up to limit."""
        nodes_map: dict[str, TopologyNode] = {}
        edges_list: list[TopologyEdge] = []

        for ref in known_entities.values():
            custom_telemetry = (
                {"cost": custom_node_costs[ref.entity_id]}
                if custom_node_costs and ref.entity_id in custom_node_costs
                else None
            )
            enrichment = self.enrichment_service.enrich_node(
                ref,
                period_start=p_start,
                period_end=p_end,
                currency=currency,
                custom_telemetry=custom_telemetry,
                tenant_context=tc,
            )
            nodes_map[ref.entity_id] = TopologyNode(
                id=ref.entity_id,
                entity_ref=ref,
                display_name=ref.name or ref.entity_id,
                depth=1,
                is_root=False,
                is_restricted=False,
                enrichment=enrichment,
                direct_cost=enrichment.cost,
                attributed_chain_cost=enrichment.cost,
            )

        for edge in raw_edges:
            edges_list.append(
                TopologyEdge(
                    edge_id=edge.id,
                    source_id=edge.source_ref.entity_id,
                    target_id=edge.target_ref.entity_id,
                    relationship_type=edge.relationship_type,
                    direction=edge.direction,
                    criticality=edge.criticality,
                    confidence=edge.confidence,
                    is_restricted=False,
                    billing_attributes=edge.billing_attributes,
                )
            )

        return nodes_map, edges_list
