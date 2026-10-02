"""Graph Traversal, Impact-Set Computation, and Cycle Detection Engine (Prompt 32).

Enforces BBP Section 24:
1. Impact-set computation: All downstream dependents of any entity, with depth control.
2. Supports shared services returning all downstream consumers.
3. Cyclic dependency detection without entering infinite recursion.
4. Point-in-time graph traversal honoring as_of temporal filters.
"""

from __future__ import annotations

import collections
import datetime as dt
import logging

from domain.dependency.models import (
    DependencyEdge,
    ImpactNode,
    ImpactSet,
    TypedEntityRef,
)
from domain.dependency.repository import DependencyRepository
from domain.models.enums import (
    DependencyDirection,
    EdgeCriticality,
    EdgeStatus,
    EntityReferenceType,
    RelationshipType,
)
from domain.tenant.context import TenantContext, require_tenant_context

logger = logging.getLogger(__name__)


class ImpactAnalysisEngine:
    """Computes downstream blast radius, dependency trees, and cyclic path analysis."""

    def __init__(self, repository: DependencyRepository) -> None:
        self.repository = repository

    def compute_downstream_impact(
        self,
        entity_id: str,
        *,
        max_depth: int | None = None,
        relationship_types: list[RelationshipType] | None = None,
        as_of: dt.datetime | None = None,
        tenant_context: TenantContext,
    ) -> ImpactSet:
        """Computes all downstream dependents of an entity (blast radius).

        Traverses:
        - Outbound dependencies where entity is target: entity <- dependent
        - Shared services or billing allocations where entity is provider: entity -> consumer
        - Inbound dependencies where entity is source: entity -> dependent
        - Bidirectional connections in either direction.
        """
        tc = require_tenant_context(tenant_context)
        edges = self.repository.list_edges(
            status=EdgeStatus.ACTIVE if as_of is None else None,
            as_of=as_of,
            tenant_context=tc,
        )

        # Filter by relationship types if specified
        if relationship_types:
            edges = [e for e in edges if e.relationship_type in relationship_types]

        # Build adjacency mapping for downstream impact
        # adj[node_id] -> list of (dependent_ref, edge)
        downstream_adj: dict[str, list[tuple[TypedEntityRef, DependencyEdge]]] = (
            collections.defaultdict(list)
        )

        root_ref: TypedEntityRef | None = None

        for edge in edges:
            s_id = edge.source_ref.entity_id
            t_id = edge.target_ref.entity_id

            if s_id == entity_id:
                root_ref = edge.source_ref
            elif t_id == entity_id:
                root_ref = edge.target_ref

            # Case A: Shared Service or Billing Relationship
            # Provider is source, consumer is target -> consumer is dependent
            if edge.relationship_type in (
                RelationshipType.SHARED_SERVICE,
                RelationshipType.BILLING_RELATIONSHIP,
            ):
                downstream_adj[s_id].append((edge.target_ref, edge))

            # Case B: Standard OUTBOUND dependency (A depends on B)
            # A (source) depends on B (target). If B fails, A (source) is impacted!
            elif edge.direction == DependencyDirection.OUTBOUND:
                downstream_adj[t_id].append((edge.source_ref, edge))

            # Case C: INBOUND dependency (A is fed by B)
            # If A fails, B (target) is impacted!
            elif edge.direction == DependencyDirection.INBOUND:
                downstream_adj[s_id].append((edge.target_ref, edge))

            # Case D: BIDIRECTIONAL
            elif edge.direction == DependencyDirection.BIDIRECTIONAL:
                downstream_adj[t_id].append((edge.source_ref, edge))
                downstream_adj[s_id].append((edge.target_ref, edge))

        if root_ref is None:
            # Fallback if entity has no edges
            root_ref = TypedEntityRef(entity_type=EntityReferenceType.RESOURCE, entity_id=entity_id)

        # Breadth-First Traversal with depth tracking and cycle detection
        visited: set[str] = set()
        queue: collections.deque[tuple[str, int, list[str]]] = collections.deque(
            [(entity_id, 0, [entity_id])]
        )
        impacted_nodes: list[ImpactNode] = []
        edges_traversed: list[str] = []
        cycle_detected = False
        cycle_nodes_set: set[str] = set()

        max_depth_reached = 0

        while queue:
            curr_id, curr_depth, path = queue.popleft()

            if max_depth is not None and curr_depth >= max_depth:
                continue

            for next_ref, edge in downstream_adj.get(curr_id, []):
                next_id = next_ref.entity_id

                # Cycle Detection
                if next_id in path:
                    cycle_detected = True
                    cycle_nodes_set.add(next_id)
                    continue

                if edge.id not in edges_traversed:
                    edges_traversed.append(edge.id)

                if next_id not in visited:
                    visited.add(next_id)
                    hop_depth = curr_depth + 1
                    max_depth_reached = max(max_depth_reached, hop_depth)

                    impacted_nodes.append(
                        ImpactNode(
                            entity_ref=next_ref,
                            depth=hop_depth,
                            criticality=edge.criticality,
                            via_relationship=edge.relationship_type,
                            edge_id=edge.id,
                            direction=edge.direction,
                        )
                    )

                    queue.append((next_id, hop_depth, path + [next_id]))

        critical_count = sum(1 for n in impacted_nodes if n.criticality == EdgeCriticality.CRITICAL)

        return ImpactSet(
            root_entity=root_ref,
            total_dependents=len(impacted_nodes),
            max_depth_reached=max_depth_reached,
            critical_dependents_count=critical_count,
            dependents=impacted_nodes,
            edges_traversed=edges_traversed,
            has_cycle=cycle_detected,
            cycle_nodes=sorted(cycle_nodes_set),
        )

    def compute_upstream_dependencies(
        self,
        entity_id: str,
        *,
        max_depth: int | None = None,
        as_of: dt.datetime | None = None,
        tenant_context: TenantContext,
    ) -> ImpactSet:
        """Computes all upstream infrastructure dependencies required by this entity."""
        tc = require_tenant_context(tenant_context)
        edges = self.repository.list_edges(
            status=EdgeStatus.ACTIVE if as_of is None else None,
            as_of=as_of,
            tenant_context=tc,
        )

        upstream_adj: dict[str, list[tuple[TypedEntityRef, DependencyEdge]]] = (
            collections.defaultdict(list)
        )
        root_ref: TypedEntityRef | None = None

        for edge in edges:
            s_id = edge.source_ref.entity_id
            t_id = edge.target_ref.entity_id

            if s_id == entity_id:
                root_ref = edge.source_ref
            elif t_id == entity_id:
                root_ref = edge.target_ref

            # Upstream: What does this entity rely upon?
            if edge.direction == DependencyDirection.OUTBOUND:
                # Source depends on target
                upstream_adj[s_id].append((edge.target_ref, edge))
            elif edge.direction == DependencyDirection.INBOUND:
                upstream_adj[t_id].append((edge.source_ref, edge))
            elif edge.direction == DependencyDirection.BIDIRECTIONAL:
                upstream_adj[s_id].append((edge.target_ref, edge))
                upstream_adj[t_id].append((edge.source_ref, edge))

        if root_ref is None:
            root_ref = TypedEntityRef(entity_type=EntityReferenceType.RESOURCE, entity_id=entity_id)

        visited: set[str] = set()
        queue: collections.deque[tuple[str, int, list[str]]] = collections.deque(
            [(entity_id, 0, [entity_id])]
        )
        nodes: list[ImpactNode] = []
        edges_traversed: list[str] = []
        cycle_detected = False
        cycle_nodes_set: set[str] = set()
        max_depth_reached = 0

        while queue:
            curr_id, curr_depth, path = queue.popleft()

            if max_depth is not None and curr_depth >= max_depth:
                continue

            for next_ref, edge in upstream_adj.get(curr_id, []):
                next_id = next_ref.entity_id

                if next_id in path:
                    cycle_detected = True
                    cycle_nodes_set.add(next_id)
                    continue

                if edge.id not in edges_traversed:
                    edges_traversed.append(edge.id)

                if next_id not in visited:
                    visited.add(next_id)
                    hop_depth = curr_depth + 1
                    max_depth_reached = max(max_depth_reached, hop_depth)

                    nodes.append(
                        ImpactNode(
                            entity_ref=next_ref,
                            depth=hop_depth,
                            criticality=edge.criticality,
                            via_relationship=edge.relationship_type,
                            edge_id=edge.id,
                            direction=edge.direction,
                        )
                    )

                    queue.append((next_id, hop_depth, path + [next_id]))

        critical_count = sum(1 for n in nodes if n.criticality == EdgeCriticality.CRITICAL)

        return ImpactSet(
            root_entity=root_ref,
            total_dependents=len(nodes),
            max_depth_reached=max_depth_reached,
            critical_dependents_count=critical_count,
            dependents=nodes,
            edges_traversed=edges_traversed,
            has_cycle=cycle_detected,
            cycle_nodes=sorted(cycle_nodes_set),
        )
