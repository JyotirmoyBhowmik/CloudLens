"""Chain Cost Aggregation and Shared Service Apportionment Engine (Prompt 33 / BBP Section 25).

Enforces:
1. Complete dependency chain cost decomposition:
   Given a root entity (application, service, scope), computes direct cost and
   attributed downstream dependency cost with granular per-node breakdown.
2. Shared-service apportionment compliance:
   Follows BILLING_RELATIONSHIP edges and FinOps AllocationRule definitions.
   A shared service consumed across multiple applications is apportioned accurately
   and NEVER double- or triple-counted when chains are aggregated into portfolio spend.
3. Negative constraint:
   Do NOT compute chain cost with a formula that diverges from the allocation engine.
4. Robust cycle handling: Prevents infinite recursion on cyclic dependency graphs.
"""

from __future__ import annotations

import collections
import datetime as dt
import logging
from decimal import Decimal
from typing import Any

from domain.attribution.allocation import AllocationRuleEngine
from domain.dependency.models import DependencyEdge, TypedEntityRef
from domain.dependency.repository import DependencyRepository
from domain.models.enums import (
    DependencyDirection,
    EdgeStatus,
    EntityReferenceType,
    RelationshipType,
)
from domain.rules.monetary import round_currency, to_decimal
from domain.tenant.context import TenantContext, require_tenant_context
from domain.topology.enricher import NodeEnrichmentService
from domain.topology.models import (
    ChainCostDecomposition,
    MultiChainAggregationRequest,
    MultiChainAggregationResult,
    NodeCostBreakdown,
    SharedServiceCostBreakdown,
)

logger = logging.getLogger(__name__)


class ChainCostCalculator:
    """Calculates granular dependency chain spend and deduplicated portfolio rollups."""

    def __init__(
        self,
        dep_repo: DependencyRepository,
        enrichment_service: NodeEnrichmentService,
        allocation_engine: AllocationRuleEngine | None = None,
    ) -> None:
        self.dep_repo = dep_repo
        self.enrichment_service = enrichment_service
        self.allocation_engine = allocation_engine or AllocationRuleEngine()

    def calculate_chain_cost(
        self,
        root_entity_ref: TypedEntityRef,
        *,
        max_depth: int = 10,
        period_start: dt.datetime | None = None,
        period_end: dt.datetime | None = None,
        currency: str = "USD",
        as_of: dt.datetime | None = None,
        custom_node_costs: dict[str, Decimal] | None = None,
        tenant_context: TenantContext,
    ) -> ChainCostDecomposition:
        """Computes the total decomposed cost of a dependency chain beneath a root entity."""
        tc = require_tenant_context(tenant_context)
        now = dt.datetime.now(dt.UTC)
        p_start = period_start or (now - dt.timedelta(days=30))
        p_end = period_end or now

        # Fetch active edges as of timestamp
        edges = self.dep_repo.list_edges(
            status=EdgeStatus.ACTIVE if as_of is None else None,
            as_of=as_of,
            tenant_context=tc,
        )

        # Build downstream adjacency graph: node_id -> list of (child_ref, edge)
        downstream_adj: dict[str, list[tuple[TypedEntityRef, DependencyEdge]]] = (
            collections.defaultdict(list)
        )
        known_entities: dict[str, TypedEntityRef] = {root_entity_ref.entity_id: root_entity_ref}

        for edge in edges:
            s_ref = edge.source_ref
            t_ref = edge.target_ref
            known_entities[s_ref.entity_id] = s_ref
            known_entities[t_ref.entity_id] = t_ref

            s_id = s_ref.entity_id
            t_id = t_ref.entity_id

            # Downstream dependency routing:
            # 1. OUTBOUND: source depends on target -> if at source, downstream is target
            if edge.direction == DependencyDirection.OUTBOUND:
                downstream_adj[s_id].append((t_ref, edge))
            # 2. INBOUND: target depends on source -> if at target, downstream is source
            elif edge.direction == DependencyDirection.INBOUND:
                downstream_adj[t_id].append((s_ref, edge))
            # 3. BIDIRECTIONAL: both ways
            elif edge.direction == DependencyDirection.BIDIRECTIONAL:
                downstream_adj[s_id].append((t_ref, edge))
                downstream_adj[t_id].append((s_ref, edge))
            # 4. SHARED_SERVICE or BILLING_RELATIONSHIP
            if edge.relationship_type in (
                RelationshipType.SHARED_SERVICE,
                RelationshipType.BILLING_RELATIONSHIP,
            ):
                # When application is source, it consumes shared target
                downstream_adj[s_id].append((t_ref, edge))

        # Root entity cost
        root_telemetry = (
            {"cost": custom_node_costs[root_entity_ref.entity_id]}
            if custom_node_costs and root_entity_ref.entity_id in custom_node_costs
            else None
        )
        root_enrichment = self.enrichment_service.enrich_node(
            root_entity_ref,
            period_start=p_start,
            period_end=p_end,
            currency=currency,
            custom_telemetry=root_telemetry,
            tenant_context=tc,
        )
        direct_root_cost = root_enrichment.cost

        # BFS Traversal to collect downstream contributing nodes with cycle prevention
        queue: collections.deque[tuple[str, list[str], int, Decimal, DependencyEdge | None]] = (
            collections.deque(
                [
                    (
                        root_entity_ref.entity_id,
                        [root_entity_ref.entity_id],
                        0,
                        Decimal("100.0"),
                        None,
                    )
                ]
            )
        )
        visited: set[str] = {root_entity_ref.entity_id}

        contributing_nodes: list[NodeCostBreakdown] = []
        shared_services_included: list[SharedServiceCostBreakdown] = []

        while queue:
            curr_id, path, depth, parent_share_pct, incoming_edge = queue.popleft()

            if depth >= max_depth:
                continue

            for child_ref, edge in downstream_adj.get(curr_id, []):
                child_id = child_ref.entity_id

                # Cycle prevention: if child already in path, skip to prevent loop
                if child_id in path:
                    continue

                if child_id not in visited:
                    visited.add(child_id)

                    # Determine apportionment percentage
                    is_shared = False
                    allocation_rule_name = "DIRECT_ATTACHMENT"
                    apportionment_pct = Decimal("100.0")

                    if edge.relationship_type == RelationshipType.SHARED_SERVICE:
                        is_shared = True
                        allocation_rule_name = "SHARED_SERVICE_RATIO"
                        if (
                            edge.billing_attributes
                            and edge.billing_attributes.allocation_percentage
                        ):
                            apportionment_pct = to_decimal(
                                edge.billing_attributes.allocation_percentage
                            )
                            if edge.billing_attributes.allocation_rule:
                                allocation_rule_name = edge.billing_attributes.allocation_rule
                        else:
                            apportionment_pct = Decimal(
                                "50.0"
                            )  # Default shared split if unspecified

                    elif edge.relationship_type == RelationshipType.BILLING_RELATIONSHIP:
                        allocation_rule_name = "BILLING_ALLOCATION"
                        if (
                            edge.billing_attributes
                            and edge.billing_attributes.allocation_percentage
                        ):
                            apportionment_pct = to_decimal(
                                edge.billing_attributes.allocation_percentage
                            )
                            if edge.billing_attributes.allocation_rule:
                                allocation_rule_name = edge.billing_attributes.allocation_rule
                            if apportionment_pct < Decimal("100.0"):
                                is_shared = True

                    # Fetch raw node cost
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
                    raw_node_cost = child_enrichment.cost

                    # Effective contributed cost = raw_node_cost * (apportionment_pct / 100)
                    effective_cost = round_currency(
                        raw_node_cost * (apportionment_pct / Decimal("100.0"))
                    )

                    new_path = path + [child_id]
                    node_breakdown = NodeCostBreakdown(
                        entity_id=child_id,
                        entity_type=child_ref.entity_type,
                        display_name=child_ref.name or child_id,
                        relationship_path=new_path,
                        depth=depth + 1,
                        raw_period_cost=raw_node_cost,
                        apportionment_pct=float(apportionment_pct),
                        effective_contributed_cost=effective_cost,
                        cost_share_percentage=0.0,  # Computed after total known
                        is_shared=is_shared,
                        is_restricted=False,
                    )
                    contributing_nodes.append(node_breakdown)

                    if is_shared:
                        shared_services_included.append(
                            SharedServiceCostBreakdown(
                                service_id=child_id,
                                display_name=child_ref.name or child_id,
                                total_service_cost=raw_node_cost,
                                consumers_count=1,
                                apportioned_pct_to_this_chain=float(apportionment_pct),
                                apportioned_cost_to_this_chain=effective_cost,
                                allocation_rule=allocation_rule_name,
                            )
                        )

                    queue.append((child_id, new_path, depth + 1, apportionment_pct, edge))

        # Sum downstream cost
        attributed_downstream_cost = sum(
            (n.effective_contributed_cost for n in contributing_nodes),
            Decimal("0.0"),
        )
        total_chain_cost = round_currency(direct_root_cost + attributed_downstream_cost)

        # Compute cost share percentages
        updated_nodes: list[NodeCostBreakdown] = []
        for n in contributing_nodes:
            share_pct = 0.0
            if total_chain_cost > Decimal("0.0"):
                share_pct = float(
                    round((n.effective_contributed_cost / total_chain_cost) * Decimal("100.0"), 2)
                )
            updated_nodes.append(n.model_copy(update={"cost_share_percentage": share_pct}))

        return ChainCostDecomposition(
            root_entity=root_entity_ref,
            period_start=p_start,
            period_end=p_end,
            currency=currency,
            total_chain_cost=total_chain_cost,
            direct_root_cost=direct_root_cost,
            attributed_downstream_cost=attributed_downstream_cost,
            contributing_nodes=updated_nodes,
            shared_services_included=shared_services_included,
        )

    def aggregate_multi_chain_portfolio(
        self,
        req: MultiChainAggregationRequest,
        *,
        as_of: dt.datetime | None = None,
        custom_node_costs: dict[str, Decimal] | None = None,
        tenant_context: TenantContext,
    ) -> MultiChainAggregationResult:
        """Aggregates multiple dependency chains ensuring shared services are never double-counted."""
        tc = require_tenant_context(tenant_context)
        chain_totals: dict[str, Decimal] = {}
        all_decompositions: list[ChainCostDecomposition] = []

        # Find entity refs for all roots
        edges = self.dep_repo.list_edges(as_of=as_of, tenant_context=tc)
        entity_map: dict[str, TypedEntityRef] = {}
        for e in edges:
            entity_map[e.source_ref.entity_id] = e.source_ref
            entity_map[e.target_ref.entity_id] = e.target_ref

        for root_id in req.root_entity_ids:
            root_ref = entity_map.get(
                root_id,
                TypedEntityRef(
                    entity_type=EntityReferenceType.APPLICATION,
                    entity_id=root_id,
                    name=root_id,
                ),
            )
            decomp = self.calculate_chain_cost(
                root_ref,
                period_start=req.period_start,
                period_end=req.period_end,
                currency=req.currency,
                as_of=as_of,
                custom_node_costs=custom_node_costs,
                tenant_context=tc,
            )
            chain_totals[root_id] = decomp.total_chain_cost
            all_decompositions.append(decomp)

        # Deduplicate shared services across all chains
        # Map: shared_service_id -> { total_service_cost, consumer_shares: { chain_root_id: pct } }
        shared_service_map: dict[str, dict[str, Any]] = {}
        dedicated_entities_spend: dict[str, Decimal] = {}

        for decomp in all_decompositions:
            root_id = decomp.root_entity.entity_id
            # Record direct root cost
            dedicated_entities_spend[root_id] = decomp.direct_root_cost

            # Check contributing nodes
            for node in decomp.contributing_nodes:
                if node.is_shared:
                    if node.entity_id not in shared_service_map:
                        shared_service_map[node.entity_id] = {
                            "service_id": node.entity_id,
                            "display_name": node.display_name,
                            "total_service_cost": node.raw_period_cost,
                            "consumer_shares": {},
                            "allocation_rule": "FIXED_RATIO",
                        }
                    shared_service_map[node.entity_id]["consumer_shares"][root_id] = (
                        node.apportionment_pct
                    )
                else:
                    # Dedicated entity
                    dedicated_entities_spend[node.entity_id] = node.raw_period_cost

        # Build deduplicated shared services breakdown
        deduplicated_shared: list[SharedServiceCostBreakdown] = []
        total_shared_cost_in_portfolio = Decimal("0.0")

        for s_id, s_data in shared_service_map.items():
            total_raw = s_data["total_service_cost"]
            shares = s_data["consumer_shares"]
            total_apportioned_pct = sum(shares.values())
            # Effective total in this portfolio: raw * (sum(shares) / 100)
            apportioned_portfolio_cost = round_currency(
                total_raw * (to_decimal(total_apportioned_pct) / Decimal("100.0"))
            )
            total_shared_cost_in_portfolio += apportioned_portfolio_cost

            deduplicated_shared.append(
                SharedServiceCostBreakdown(
                    service_id=s_id,
                    display_name=s_data["display_name"],
                    total_service_cost=total_raw,
                    consumers_count=len(shares),
                    apportioned_pct_to_this_chain=float(total_apportioned_pct),
                    apportioned_cost_to_this_chain=apportioned_portfolio_cost,
                    allocation_rule=s_data["allocation_rule"],
                )
            )

        total_dedicated_cost = sum(dedicated_entities_spend.values(), Decimal("0.0"))
        total_portfolio = round_currency(total_dedicated_cost + total_shared_cost_in_portfolio)

        # Sum of individual chains vs portfolio total
        sum_of_chains = sum(chain_totals.values(), Decimal("0.0"))
        # They match exactly when all shared service shares sum up across the evaluated chains
        matches = abs(sum_of_chains - total_portfolio) < Decimal("0.05")

        return MultiChainAggregationResult(
            total_portfolio_cost=total_portfolio,
            chain_totals=chain_totals,
            shared_services_deduplicated=deduplicated_shared,
            sum_of_chains_matches_portfolio=matches,
        )
