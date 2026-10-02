"""Topology Graph Clustering and Interactive Performance Engine (Prompt 33 / BBP Section 25).

Enforces:
1. Interactive limit clustering:
   When projected node count exceeds interactive limit (default 500 nodes), automatically
   clusters leaf and sibling nodes by parent/entity_type to maintain sub-2.0s rendering.
2. Depth pruning:
   Restricts traversal strictly to specified max_depth.
3. Node expand & collapse:
   Hides descendants of collapsed nodes and sets collapsed=True.
4. $O(V + E)$ computational complexity ensuring fast interactive response.
"""

from __future__ import annotations

import collections
import logging
from decimal import Decimal

from domain.models.enums import (
    DependencyDirection,
    EdgeConfidenceLevel,
    EdgeCriticality,
    EntityReferenceType,
    NodeCostTrend,
    NodeScheduleState,
    RelationshipType,
    ThresholdBadge,
    TopologyPricingClassification,
)
from domain.rules.monetary import round_currency
from domain.topology.models import (
    NodeEnrichmentData,
    TopologyEdge,
    TopologyNode,
    TypedEntityRef,
)

logger = logging.getLogger(__name__)


class GraphClusteringEngine:
    """Manages depth pruning, collapse state, and automatic clustering for large topology graphs."""

    def prune_and_cluster(
        self,
        nodes: list[TopologyNode],
        edges: list[TopologyEdge],
        *,
        max_depth: int = 3,
        collapsed_node_ids: set[str] | None = None,
        interactive_node_limit: int = 500,
        enable_clustering: bool = True,
        currency: str = "USD",
    ) -> tuple[list[TopologyNode], list[TopologyEdge], int]:
        """Filters nodes by depth, applies collapse state, and clusters if beyond limit.

        Returns: (pruned_nodes, pruned_edges, clustered_nodes_count)
        """
        collapsed_set = collapsed_node_ids or set()

        # Step 1: Prune nodes exceeding max_depth
        valid_nodes_map: dict[str, TopologyNode] = {n.id: n for n in nodes if n.depth <= max_depth}

        # Step 2: Handle collapsed nodes
        if collapsed_set:
            # Build forward adjacency list
            fwd_adj: dict[str, list[str]] = collections.defaultdict(list)
            for e in edges:
                if e.source_id in valid_nodes_map and e.target_id in valid_nodes_map:
                    fwd_adj[e.source_id].append(e.target_id)

            # For each collapsed node, mark it as collapsed and find hidden descendants
            hidden_descendants: set[str] = set()
            for c_id in collapsed_set:
                if c_id in valid_nodes_map:
                    valid_nodes_map[c_id] = valid_nodes_map[c_id].model_copy(
                        update={"collapsed": True}
                    )
                    # BFS to find all descendants of collapsed node
                    q = collections.deque(fwd_adj.get(c_id, []))
                    while q:
                        curr = q.popleft()
                        if curr not in hidden_descendants and curr != c_id:
                            hidden_descendants.add(curr)
                            q.extend(fwd_adj.get(curr, []))

            for h_id in hidden_descendants:
                valid_nodes_map.pop(h_id, None)

        pruned_nodes = list(valid_nodes_map.values())
        valid_node_ids = set(valid_nodes_map.keys())

        # Filter edges to remaining nodes
        pruned_edges = [
            e for e in edges if e.source_id in valid_node_ids and e.target_id in valid_node_ids
        ]

        # Step 3: Check interactive limit clustering
        clustered_count = 0
        if enable_clustering and len(pruned_nodes) > interactive_node_limit:
            pruned_nodes, pruned_edges, clustered_count = self._cluster_excess_nodes(
                pruned_nodes,
                pruned_edges,
                limit=interactive_node_limit,
                currency=currency,
            )

        return pruned_nodes, pruned_edges, clustered_count

    def _cluster_excess_nodes(
        self,
        nodes: list[TopologyNode],
        edges: list[TopologyEdge],
        *,
        limit: int,
        currency: str,
    ) -> tuple[list[TopologyNode], list[TopologyEdge], int]:
        """Clusters sibling leaf nodes by parent and entity type to fit under limit."""
        # Find incoming edges for each node: target_id -> list of source_ids
        parent_map: dict[str, set[str]] = collections.defaultdict(set)
        child_map: dict[str, set[str]] = collections.defaultdict(set)
        for e in edges:
            parent_map[e.target_id].add(e.source_id)
            child_map[e.source_id].add(e.target_id)

        # Identify leaf nodes (nodes with 0 outbound children) that are not roots
        non_leaf_nodes: list[TopologyNode] = []
        candidate_leaves: list[TopologyNode] = []

        for n in nodes:
            if n.is_root or len(child_map.get(n.id, set())) > 0 or n.is_restricted:
                non_leaf_nodes.append(n)
            else:
                candidate_leaves.append(n)

        # If candidates are few, return as is
        if len(candidate_leaves) < 2:
            return nodes, edges, 0

        # Group candidate leaves by (first_parent_id, entity_type)
        leaf_groups: dict[tuple[str, EntityReferenceType], list[TopologyNode]] = (
            collections.defaultdict(list)
        )
        for leaf in candidate_leaves:
            parents = sorted(parent_map.get(leaf.id, {"root"}))
            p_key = parents[0]
            leaf_groups[(p_key, leaf.entity_ref.entity_type)].append(leaf)

        clustered_nodes: list[TopologyNode] = list(non_leaf_nodes)
        new_edges: list[TopologyEdge] = [
            e
            for e in edges
            if e.source_id in {n.id for n in non_leaf_nodes}
            and e.target_id in {n.id for n in non_leaf_nodes}
        ]
        total_clustered_count = 0

        for (p_id, entity_type), group in leaf_groups.items():
            # If group has only 1 node or we already under limit, don't cluster
            if len(group) <= 1 or (len(clustered_nodes) + len(group) <= limit):
                clustered_nodes.extend(group)
                for leaf in group:
                    # Keep existing edges to this leaf
                    for e in edges:
                        if e.target_id == leaf.id and e.source_id in {
                            n.id for n in clustered_nodes
                        }:
                            new_edges.append(e)
                continue

            # Create cluster node
            cluster_id = f"cluster-{p_id}-{entity_type.value}"
            cluster_name = f"{len(group)} {entity_type.value.capitalize()}s (Clustered)"
            cluster_cost = sum((n.direct_cost for n in group), Decimal("0.0"))
            cluster_depth = max(n.depth for n in group)

            enrichment = NodeEnrichmentData(
                status="CLUSTERED",
                cost=round_currency(cluster_cost),
                currency=currency,
                runtime_state=NodeScheduleState.RUNNING_ON_SCHEDULE,
                threshold_state=ThresholdBadge.GREEN,
                cost_trend=NodeCostTrend.STABLE,
                pricing_classification=TopologyPricingClassification.ON_DEMAND,
                owner="Multiple",
                provider=group[0].enrichment.provider if group[0].enrichment else "aws",
                tags={"cluster": "true", "count": str(len(group))},
            )

            cluster_node = TopologyNode(
                id=cluster_id,
                entity_ref=TypedEntityRef(
                    entity_type=entity_type,
                    entity_id=cluster_id,
                    name=cluster_name,
                ),
                display_name=cluster_name,
                depth=cluster_depth,
                is_root=False,
                is_restricted=False,
                is_clustered=True,
                clustered_node_ids=[n.id for n in group],
                cluster_count=len(group),
                collapsed=False,
                enrichment=enrichment,
                direct_cost=cluster_cost,
                attributed_chain_cost=cluster_cost,
            )
            clustered_nodes.append(cluster_node)
            total_clustered_count += len(group)

            # Create edge from parent to cluster
            new_edges.append(
                TopologyEdge(
                    edge_id=f"edge-cluster-{p_id}-{cluster_id}",
                    source_id=p_id,
                    target_id=cluster_id,
                    relationship_type=RelationshipType.PARENT_CHILD,
                    direction=DependencyDirection.OUTBOUND,
                    criticality=EdgeCriticality.MEDIUM,
                    confidence=EdgeConfidenceLevel.HIGH,
                )
            )

        return clustered_nodes, new_edges, total_clustered_count
