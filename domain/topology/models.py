"""Cost-Aware Topology and Dependency Graph Data Contracts (Prompt 33 / BBP Section 25).

Enforces:
1. Eight Canonical Views:
   - SERVICE_DEPENDENCY, APPLICATION_DEPENDENCY, ACCOUNT_TOPOLOGY, SUBSCRIPTION_TOPOLOGY,
     PROJECT_TOPOLOGY, COMPARTMENT_TOPOLOGY, RESOURCE_RELATIONSHIP, COST_AWARE_DEPENDENCY.
2. Full Node Enrichment Telemetry:
   - status, period cost, budget utilisation, runtime state, usage metrics,
     threshold state, cost trend, forecast, pricing classification, owner, and provider.
3. Chain Cost Decomposition & Multi-Chain Portfolio Aggregation with correct shared-service
   apportionment avoiding double/triple counting.
4. Restricted Node Placeholders ensuring unentitled nodes are never silently omitted.
5. Interactive clustering beyond performance limit and multi-format graph export.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from domain.dependency.models import BillingAttributes, TypedEntityRef
from domain.models.enums import (
    DependencyDirection,
    EdgeConfidenceLevel,
    EdgeCriticality,
    EntityReferenceType,
    GraphExportFormat,
    NodeCostTrend,
    NodeScheduleState,
    RelationshipType,
    ThresholdBadge,
    TopologyBudgetStatus,
    TopologyPricingClassification,
    TopologyViewType,
)


class NodeEnrichmentData(BaseModel):
    """Multi-dimensional operational, runtime, and financial telemetry on a topology node."""

    model_config = ConfigDict(frozen=True)

    status: str = Field(
        default="RUNNING", description="Operational status (e.g. RUNNING, HEALTHY, STOPPED)"
    )
    cost: Decimal = Field(default=Decimal("0.0"), description="Spend for selected period")
    currency: str = Field(default="USD", description="Currency ISO 4217 code")
    budget_utilisation_pct: float | None = Field(
        default=None, ge=0.0, description="Percentage of assigned budget consumed"
    )
    budget_status: TopologyBudgetStatus = Field(
        default=TopologyBudgetStatus.OK, description="Budget compliance state"
    )
    runtime_state: NodeScheduleState = Field(
        default=NodeScheduleState.RUNNING_ON_SCHEDULE,
        description="Schedule compliance and idle/orphaned detection state",
    )
    usage: dict[str, float] = Field(
        default_factory=dict,
        description="Core metrics summary: cpu_utilization, memory_utilization, storage_bytes, iops",
    )
    threshold_state: ThresholdBadge = Field(
        default=ThresholdBadge.GREEN, description="Operational health badge: GREEN, AMBER, RED"
    )
    cost_trend: NodeCostTrend = Field(
        default=NodeCostTrend.STABLE, description="Cost movement direction vs baseline period"
    )
    cost_trend_pct: float | None = Field(
        default=0.0, description="Percentage cost change relative to prior period"
    )
    forecast_cost: Decimal | None = Field(
        default=None, description="Extrapolated projected spend for remainder of billing cycle"
    )
    pricing_classification: TopologyPricingClassification = Field(
        default=TopologyPricingClassification.ON_DEMAND,
        description="Pricing construct: ON_DEMAND, SPOT, RESERVED, SAVINGS_PLAN",
    )
    owner: str | None = Field(default=None, description="Accountable owner or engineering team")
    business_unit: str | None = Field(default=None, description="Associated business unit")
    cost_center: str | None = Field(default=None, description="Financial accounting cost center")
    provider: str | None = Field(
        default="aws", description="Cloud provider identifier (aws, azure, gcp, oci)"
    )
    tags: dict[str, str] = Field(default_factory=dict, description="Normalized entity tags")


class TopologyNode(BaseModel):
    """A projected vertex in the cost-aware topology graph."""

    id: str = Field(..., description="Unique graph node key (TYPE:ID or entity_id)")
    entity_ref: TypedEntityRef = Field(..., description="Canonical typed entity reference")
    display_name: str = Field(..., description="Human-readable node label")
    depth: int = Field(default=0, ge=0, description="Traversal hop distance from the view root")
    is_root: bool = Field(
        default=False, description="True if this node is the root of the projection"
    )
    is_restricted: bool = Field(
        default=False,
        description="True if caller lacks RBAC scope grant; rendered as placeholder with masked attributes",
    )
    is_clustered: bool = Field(
        default=False, description="True if node represents an aggregated cluster of child nodes"
    )
    clustered_node_ids: list[str] = Field(
        default_factory=list, description="IDs of aggregated child nodes if clustered"
    )
    cluster_count: int = Field(
        default=1, ge=1, description="Number of underlying entities represented"
    )
    collapsed: bool = Field(
        default=False, description="Whether node's children are collapsed in UI"
    )
    enrichment: NodeEnrichmentData | None = Field(
        default=None, description="Operational, runtime, threshold, and financial telemetry"
    )
    direct_cost: Decimal = Field(
        default=Decimal("0.0"), description="Direct unapportioned period spend of this entity"
    )
    attributed_chain_cost: Decimal = Field(
        default=Decimal("0.0"), description="Cost contributed to root dependency chain"
    )
    cost_share_pct: float = Field(
        default=0.0, ge=0.0, le=100.0, description="Share percentage of total root chain spend"
    )
    is_shared_service: bool = Field(
        default=False, description="True if service is consumed across multiple application chains"
    )
    apportioned_share_pct: float = Field(
        default=100.0,
        ge=0.0,
        le=100.0,
        description="Apportioned percentage attributed to this chain",
    )


class TopologyEdge(BaseModel):
    """A directed edge in the cost-aware topology projection."""

    edge_id: str = Field(..., description="Underlying dependency edge identifier")
    source_id: str = Field(..., description="Origin node identifier")
    target_id: str = Field(..., description="Destination node identifier")
    relationship_type: RelationshipType = Field(..., description="Canonical relationship type")
    direction: DependencyDirection = Field(
        default=DependencyDirection.OUTBOUND, description="OUTBOUND, INBOUND, or BIDIRECTIONAL"
    )
    criticality: EdgeCriticality = Field(
        default=EdgeCriticality.MEDIUM, description="Operational criticality of relationship"
    )
    confidence: EdgeConfidenceLevel = Field(
        default=EdgeConfidenceLevel.HIGH, description="Honest discovery confidence rating"
    )
    is_restricted: bool = Field(
        default=False, description="True if edge links to or from a restricted node"
    )
    billing_attributes: BillingAttributes | None = Field(
        default=None, description="Apportionment rule and percentage if billing link"
    )


class NodeCostBreakdown(BaseModel):
    """Granular cost breakdown for a node contributing to a chain."""

    entity_id: str = Field(..., description="Entity identifier")
    entity_type: EntityReferenceType = Field(..., description="Entity classification")
    display_name: str = Field(..., description="Entity name or masked placeholder")
    relationship_path: list[str] = Field(
        default_factory=list, description="Chain path from root to this node"
    )
    depth: int = Field(default=0, ge=0, description="Hops from root")
    raw_period_cost: Decimal = Field(
        default=Decimal("0.0"), description="Raw period spend before apportionment"
    )
    apportionment_pct: float = Field(
        default=100.0,
        ge=0.0,
        le=100.0,
        description="Apportionment percentage applied (100% if dedicated)",
    )
    effective_contributed_cost: Decimal = Field(
        default=Decimal("0.0"), description="Cost contributed to root application chain"
    )
    cost_share_percentage: float = Field(
        default=0.0, ge=0.0, le=100.0, description="Proportion of total chain spend"
    )
    is_shared: bool = Field(
        default=False, description="Whether node is shared across multiple consumers"
    )
    is_restricted: bool = Field(
        default=False, description="Whether node is restricted under caller scope"
    )


class SharedServiceCostBreakdown(BaseModel):
    """Accounting allocation detail for a shared platform service consumed by chains."""

    service_id: str = Field(..., description="Shared service identifier")
    display_name: str = Field(..., description="Shared service display name")
    total_service_cost: Decimal = Field(
        ..., description="Total unfragmented period spend of the shared service"
    )
    consumers_count: int = Field(
        default=1, ge=1, description="Number of consumer chains sharing cost"
    )
    apportioned_pct_to_this_chain: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Apportionment percentage assigned to this specific chain",
    )
    apportioned_cost_to_this_chain: Decimal = Field(
        ..., description="Dollar amount attributed to this specific chain"
    )
    allocation_rule: str = Field(
        default="FIXED_RATIO",
        description="Allocation methodology (FIXED_RATIO, PRO_RATA, TAG_BASED)",
    )


class ChainCostDecomposition(BaseModel):
    """Complete financial decomposition of a business or application dependency chain (Prompt 33)."""

    root_entity: TypedEntityRef = Field(..., description="Root application or service entity")
    period_start: dt.datetime = Field(..., description="Evaluation window start UTC")
    period_end: dt.datetime = Field(..., description="Evaluation window end UTC")
    currency: str = Field(default="USD", description="Currency ISO 4217 code")
    total_chain_cost: Decimal = Field(
        ..., description="Total aggregated cost of the chain decomposed across nodes"
    )
    direct_root_cost: Decimal = Field(
        ..., description="Direct period spend of the root node itself"
    )
    attributed_downstream_cost: Decimal = Field(
        ...,
        description="Spend contributed by downstream dependencies (compute, db, storage, shared)",
    )
    contributing_nodes: list[NodeCostBreakdown] = Field(
        default_factory=list, description="Per-node contribution breakdown"
    )
    shared_services_included: list[SharedServiceCostBreakdown] = Field(
        default_factory=list, description="Shared service apportionment details"
    )


class TopologyGraphView(BaseModel):
    """Projected cost-aware topology graph view rendered for client consumption."""

    tenant_id: str = Field(..., description="Owning tenant ID")
    view_type: TopologyViewType = Field(..., description="One of eight canonical views")
    root_entity: TypedEntityRef | None = Field(default=None, description="View root if rooted")
    as_of: dt.datetime = Field(..., description="Point-in-time topology timestamp UTC")
    period_start: dt.datetime | None = Field(default=None, description="Cost evaluation start UTC")
    period_end: dt.datetime | None = Field(default=None, description="Cost evaluation end UTC")
    currency: str = Field(default="USD", description="Currency code")
    max_depth: int = Field(default=3, ge=1, description="Configured projection depth")
    total_nodes: int = Field(default=0, ge=0, description="Total node count in projection")
    total_edges: int = Field(default=0, ge=0, description="Total edge count in projection")
    restricted_nodes_count: int = Field(
        default=0, ge=0, description="Number of restricted placeholder nodes rendered"
    )
    clustered_nodes_count: int = Field(
        default=0, ge=0, description="Number of nodes aggregated into clusters"
    )
    total_view_cost: Decimal = Field(
        default=Decimal("0.0"), description="Total spend aggregated across visible nodes"
    )
    nodes: list[TopologyNode] = Field(default_factory=list, description="Projected nodes")
    edges: list[TopologyEdge] = Field(default_factory=list, description="Projected edges")
    chain_cost: ChainCostDecomposition | None = Field(
        default=None, description="Chain cost decomposition if root specified"
    )


class TopologyProjectionRequest(BaseModel):
    """Parameters for projecting a topology graph view."""

    view_type: TopologyViewType = Field(
        default=TopologyViewType.SERVICE_DEPENDENCY, description="Target canonical view"
    )
    root_entity_id: str | None = Field(default=None, description="Optional root entity ID")
    root_entity_type: EntityReferenceType | None = Field(
        default=None, description="Root entity type if root_entity_id provided"
    )
    max_depth: int | None = Field(
        default=None, ge=1, le=10, description="Override default traversal depth"
    )
    as_of: dt.datetime | None = Field(default=None, description="Point-in-time timestamp UTC")
    period_start: dt.datetime | None = Field(default=None, description="Cost period start UTC")
    period_end: dt.datetime | None = Field(default=None, description="Cost period end UTC")
    relationship_types: list[RelationshipType] | None = Field(
        default=None, description="Filter to specific relationship types"
    )
    collapsed_node_ids: list[str] | None = Field(
        default=None, description="IDs of nodes whose children should be collapsed"
    )
    interactive_node_limit: int = Field(
        default=500, ge=10, le=5000, description="Threshold above which leaf nodes cluster"
    )
    enable_clustering: bool = Field(
        default=True, description="Enable automatic clustering beyond node limit"
    )
    currency: str = Field(default="USD", description="Currency ISO 4217 code")


class MultiChainAggregationRequest(BaseModel):
    """Request to aggregate multiple application chains without double counting shared services."""

    root_entity_ids: list[str] = Field(
        ..., min_length=1, description="List of root application/service entity IDs"
    )
    period_start: dt.datetime | None = Field(default=None, description="Cost period start UTC")
    period_end: dt.datetime | None = Field(default=None, description="Cost period end UTC")
    currency: str = Field(default="USD", description="Currency code")


class MultiChainAggregationResult(BaseModel):
    """Result of aggregating multiple dependency chains with deduplicated shared services."""

    total_portfolio_cost: Decimal = Field(
        ..., description="Total deduplicated portfolio spend across all specified chains"
    )
    chain_totals: dict[str, Decimal] = Field(
        default_factory=dict, description="Individual chain costs indexed by root entity ID"
    )
    shared_services_deduplicated: list[SharedServiceCostBreakdown] = Field(
        default_factory=list,
        description="Shared platform services consumed by multiple chains with respective shares",
    )
    sum_of_chains_matches_portfolio: bool = Field(
        default=True, description="True if chain sum equals portfolio total without double-counting"
    )


class GraphExportRequest(BaseModel):
    """Parameters for exporting a projected topology graph."""

    format: GraphExportFormat = Field(
        default=GraphExportFormat.SVG,
        description="Export format: SVG, PNG, JSON, CSV, GRAPHML, DOT",
    )
    projection: TopologyProjectionRequest = Field(
        default_factory=TopologyProjectionRequest, description="Graph projection parameters"
    )


class GraphExportResult(BaseModel):
    """Exported graph artifact."""

    format: GraphExportFormat
    content_type: str
    content: str
    filename: str
