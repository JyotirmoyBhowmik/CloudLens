"""Cost-Aware Topology and Dependency Service (Prompt 33 / BBP Section 25).

Enforces:
1. Eight Canonical Views with default traversal depths and root entity types.
2. Full node enrichment with operational, runtime, threshold, and FinOps telemetry.
3. Chain cost decomposition and multi-chain portfolio rollups with shared service deduplication.
4. Restricted node rule: Unentitled nodes render as Restricted placeholders, never omitted.
5. Interactive limit clustering (<2.0s for 500+ nodes).
6. Multi-format graph exports (JSON, CSV, GraphML, DOT, SVG).
"""

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
    NodeCostBreakdown,
    NodeEnrichmentData,
    SharedServiceCostBreakdown,
    TopologyEdge,
    TopologyGraphView,
    TopologyNode,
    TopologyProjectionRequest,
)
from domain.topology.projection import VIEW_DEFAULT_DEPTHS, GraphProjectionService
from domain.topology.restricted import RestrictedNodeEvaluator
from domain.topology.service import (
    TopologyService,
    get_topology_service,
    reset_topology_service,
)

__all__ = [
    "ChainCostCalculator",
    "ChainCostDecomposition",
    "GraphClusteringEngine",
    "GraphExportRequest",
    "GraphExportResult",
    "GraphExportService",
    "GraphProjectionService",
    "MultiChainAggregationRequest",
    "MultiChainAggregationResult",
    "NodeCostBreakdown",
    "NodeEnrichmentData",
    "NodeEnrichmentService",
    "RestrictedNodeEvaluator",
    "SharedServiceCostBreakdown",
    "TopologyEdge",
    "TopologyGraphView",
    "TopologyNode",
    "TopologyProjectionRequest",
    "TopologyService",
    "VIEW_DEFAULT_DEPTHS",
    "get_topology_service",
    "reset_topology_service",
]
