"""Dependency Model, Edge Entities, and Graph Traversal Data Structures (Prompt 32).

Enforces BBP Section 24:
1. Eight Relationship Types:
   - LOGICAL_DEPENDENCY
   - NETWORK_CONNECTIVITY
   - APPLICATION_DEPENDENCY
   - DATA_FLOW
   - SECURITY_RELATIONSHIP
   - SHARED_SERVICE
   - BILLING_RELATIONSHIP
   - PARENT_CHILD
2. Full Edge Attributes:
   - Source & Target Typed References (RESOURCE, SERVICE, APPLICATION, SCOPE)
   - Relationship Type & Direction
   - Provenance (Discovered with rule ID, Manual with user ID, Imported from CMDB)
   - Confidence, Criticality, First-Seen & Last-Seen, Status, Notes
3. Merge Rule & Conflict Representation (Surfaced with both versions visible)
4. Point-in-time Edge History and Stale-marking
5. Impact Analysis & Cycle Detection Data Contracts
6. Billing Allocation Linkage
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field

from domain.models.base import CanonicalEntity
from domain.models.enums import (
    ConflictResolutionAction,
    DependencyDirection,
    DiscoveryLayer,
    EdgeConfidenceLevel,
    EdgeCriticality,
    EdgeProvenanceType,
    EdgeStatus,
    EntityReferenceType,
    RelationshipType,
)


class TypedEntityRef(BaseModel):
    """Typed reference to a node in the dependency graph (Prompt 32)."""

    model_config = ConfigDict(frozen=True)

    entity_type: EntityReferenceType = Field(
        ..., description="Entity classification (RESOURCE, SERVICE, APPLICATION, SCOPE)"
    )
    entity_id: str = Field(..., min_length=1, description="Unique identifier of referenced entity")
    name: str | None = Field(default=None, description="Human-readable entity name")

    @property
    def key(self) -> str:
        """Normalized unique graph node key: TYPE:ID."""
        return f"{self.entity_type.value}:{self.entity_id}"


class EdgeProvenance(BaseModel):
    """Origin, layer, and rule provenance of a dependency relationship edge (Prompt 32)."""

    provenance_type: EdgeProvenanceType = Field(
        ..., description="DISCOVERED, MANUAL, IMPORTED, or INFERRED"
    )
    rule_id: str | None = Field(
        default=None, description="Identifier of the discovery or inference rule"
    )
    actor_id: str | None = Field(
        default=None, description="Accountable user ID for manually curated edges"
    )
    import_source: str | None = Field(
        default=None, description="CMDB system name or source file identifier"
    )
    import_job_id: str | None = Field(
        default=None, description="Identifier of the batch import job"
    )
    layer: DiscoveryLayer | None = Field(
        default=None, description="Discovery layer (STRUCTURAL, NETWORK, etc.)"
    )
    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC),
        description="Timestamp when provenance was established UTC",
    )


class BillingAttributes(BaseModel):
    """Allocation and shared-service metadata for BILLING_RELATIONSHIP edges (Prompt 32)."""

    allocation_percentage: float = Field(
        default=100.0, ge=0.0, le=100.0, description="Apportionment percentage (0.0 - 100.0%)"
    )
    allocation_rule: str = Field(
        default="FIXED_RATIO",
        description="Method used for cost distribution (PRO_RATA, FIXED_RATIO, TAG_BASED)",
    )
    shared_service_id: str | None = Field(
        default=None, description="Associated shared platform service identifier"
    )
    cost_centre_id: str | None = Field(default=None, description="Target accounting cost center ID")


class EdgeHistoryEntry(BaseModel):
    """Immutable point-in-time audit record for edge evolution and history (Prompt 32)."""

    timestamp: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC), description="Change timestamp UTC"
    )
    action: str = Field(
        ..., description="Action taken: CREATED, UPDATED, MARKED_STALE, CONFLICT, RESOLVED"
    )
    actor_id: str = Field(..., description="User or automated system component identifier")
    from_status: str | None = Field(default=None, description="Prior edge status")
    to_status: str | None = Field(default=None, description="New edge status")
    note: str | None = Field(default=None, description="Contextual note or justification")
    details: dict[str, Any] = Field(default_factory=dict, description="Metadata diff")


class EdgeConflict(BaseModel):
    """Surfaced conflict between a manual edge and a candidate discovered edge (Prompt 32).

    Rule: A discovered edge never silently overwrites a manual edge. Both versions are
    visible until human resolution.
    """

    conflict_id: str = Field(..., description="Unique conflict identifier (conf-*)")
    tenant_id: str = Field(..., description="Owning tenant ID")
    source_ref: TypedEntityRef = Field(..., description="Source entity under conflict")
    manual_edge_id: str = Field(..., description="Existing protected manual edge ID")
    discovered_edge_id: str = Field(..., description="Candidate discovered edge ID")
    manual_version: dict[str, Any] = Field(
        ..., description="Serialized payload of the manual edge (target, type, actor, notes)"
    )
    discovered_version: dict[str, Any] = Field(
        ...,
        description="Serialized payload of the discovered candidate edge (target, rule_id, layer)",
    )
    conflict_reason: str = Field(..., description="Detailed description of the discrepancy")
    detected_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC), description="Detection timestamp UTC"
    )
    is_resolved: bool = Field(default=False, description="Whether conflict has been addressed")
    resolved_by: str | None = Field(default=None, description="User who resolved the conflict")
    resolved_at: dt.datetime | None = Field(default=None, description="Resolution timestamp UTC")
    resolution_action: ConflictResolutionAction | None = Field(
        default=None, description="KEEP_MANUAL, ACCEPT_DISCOVERED, or MERGE"
    )
    resolution_notes: str | None = Field(default=None, description="Human resolution rationale")


class DependencyEdge(CanonicalEntity):
    """Typed, directed relationship edge with provenance, confidence, and history (Prompt 32)."""

    tenant_id: str = Field(..., description="Owning tenant ID")
    source_ref: TypedEntityRef = Field(..., description="Origin node typed reference")
    target_ref: TypedEntityRef = Field(..., description="Destination node typed reference")
    relationship_type: RelationshipType = Field(
        ..., description="One of eight canonical relationship types"
    )
    direction: DependencyDirection = Field(
        default=DependencyDirection.OUTBOUND, description="OUTBOUND, INBOUND, or BIDIRECTIONAL"
    )
    provenance: EdgeProvenance = Field(..., description="Discovery or curation provenance")
    confidence: EdgeConfidenceLevel = Field(
        ..., description="Honest confidence rating (HIGH, MEDIUM, LOW, AS_ASSERTED)"
    )
    criticality: EdgeCriticality = Field(
        default=EdgeCriticality.MEDIUM, description="Operational failure criticality"
    )
    first_seen: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC),
        description="First observation timestamp UTC",
    )
    last_seen: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC),
        description="Last confirmed observation timestamp UTC",
    )
    status: EdgeStatus = Field(
        default=EdgeStatus.ACTIVE,
        description="ACTIVE, STALE, CONFLICT, RESOLVED, DELETED, SUPERSEDED",
    )
    notes: str | None = Field(default=None, description="Descriptive notes or human comments")
    effective_from: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC), description="Effective start timestamp UTC"
    )
    effective_to: dt.datetime | None = Field(
        default=None, description="Effective termination timestamp UTC (None if current)"
    )
    conflict_id: str | None = Field(
        default=None, description="Linked EdgeConflict identifier if status is CONFLICT"
    )
    billing_attributes: BillingAttributes | None = Field(
        default=None, description="Apportionment metadata if BILLING_RELATIONSHIP"
    )
    history: list[EdgeHistoryEntry] = Field(
        default_factory=list, description="Immutable modification history"
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_manual(self) -> bool:
        """True if the edge was explicitly asserted by human curation."""
        return self.provenance.provenance_type == EdgeProvenanceType.MANUAL

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_active(self) -> bool:
        """True if status is ACTIVE and effective window encompasses current time."""
        now = dt.datetime.now(dt.UTC)
        if self.status != EdgeStatus.ACTIVE:
            return False
        if self.effective_to is not None and self.effective_to <= now:
            return False
        return self.effective_from <= now

    def add_history(
        self,
        action: str,
        actor_id: str,
        from_status: str | None = None,
        to_status: str | None = None,
        note: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Appends an immutable history entry to this edge."""
        entry = EdgeHistoryEntry(
            timestamp=dt.datetime.now(dt.UTC),
            action=action,
            actor_id=actor_id,
            from_status=from_status,
            to_status=to_status,
            note=note,
            details=details or {},
        )
        self.history.append(entry)


# ==============================================================================
# Graph Traversal & Impact Analysis Contracts
# ==============================================================================


class ImpactNode(BaseModel):
    """An impacted downstream dependent entity encountered during traversal (Prompt 32)."""

    entity_ref: TypedEntityRef = Field(..., description="Referenced dependent entity")
    depth: int = Field(..., ge=1, description="Hops from originating entity")
    criticality: EdgeCriticality = Field(..., description="Criticality of the dependent edge")
    via_relationship: RelationshipType = Field(
        ..., description="Relationship type connecting to this node"
    )
    edge_id: str = Field(..., description="Edge identifier traversed")
    direction: DependencyDirection = Field(..., description="Direction of traversed edge")


class ImpactSet(BaseModel):
    """Complete downstream impact set and blast radius for a given entity (Prompt 32)."""

    root_entity: TypedEntityRef = Field(..., description="Originating entity examined")
    total_dependents: int = Field(
        ..., ge=0, description="Total unique downstream dependent entities"
    )
    max_depth_reached: int = Field(..., ge=0, description="Deepest dependency level traversed")
    critical_dependents_count: int = Field(
        ..., ge=0, description="Count of dependents marked CRITICAL"
    )
    dependents: list[ImpactNode] = Field(
        default_factory=list, description="Ordered list of impacted nodes"
    )
    edges_traversed: list[str] = Field(
        default_factory=list, description="IDs of all edges traversed in the impact path"
    )
    has_cycle: bool = Field(default=False, description="Whether a cyclic dependency was detected")
    cycle_nodes: list[str] = Field(
        default_factory=list, description="Entity IDs involved in cyclic loops if any"
    )


class TopologyGraph(BaseModel):
    """Point-in-time rendering of the dependency topology graph (Prompt 32)."""

    tenant_id: str = Field(..., description="Owning tenant ID")
    as_of: dt.datetime = Field(..., description="Point-in-time timestamp evaluated UTC")
    nodes: list[TypedEntityRef] = Field(default_factory=list, description="Distinct graph nodes")
    edges: list[DependencyEdge] = Field(
        default_factory=list, description="Active edges at timestamp"
    )
    conflicts_count: int = Field(default=0, ge=0, description="Number of unresolved edge conflicts")
    stale_edges_count: int = Field(default=0, ge=0, description="Number of stale edges")


# ==============================================================================
# DTOs & Discovery Configuration
# ==============================================================================


class ManualEdgeCreateRequest(BaseModel):
    """Payload to create a manual or curated dependency edge (Prompt 32)."""

    source_ref: TypedEntityRef = Field(..., description="Source entity")
    target_ref: TypedEntityRef = Field(..., description="Target entity")
    relationship_type: RelationshipType = Field(..., description="Relationship type")
    direction: DependencyDirection = Field(
        default=DependencyDirection.OUTBOUND, description="Direction"
    )
    criticality: EdgeCriticality = Field(
        default=EdgeCriticality.MEDIUM, description="Edge criticality"
    )
    confidence: EdgeConfidenceLevel = Field(
        default=EdgeConfidenceLevel.AS_ASSERTED, description="Assertion confidence"
    )
    notes: str | None = Field(default=None, description="Human rationale or notes")
    billing_attributes: BillingAttributes | None = Field(
        default=None, description="Billing allocation attributes if BILLING_RELATIONSHIP"
    )


class EdgeUpdateRequest(BaseModel):
    """Payload to update attributes of an existing edge."""

    relationship_type: RelationshipType | None = None
    direction: DependencyDirection | None = None
    criticality: EdgeCriticality | None = None
    notes: str | None = None
    billing_attributes: BillingAttributes | None = None


class BulkImportItem(BaseModel):
    """Single relationship definition inside a bulk import payload (Prompt 32)."""

    source_type: EntityReferenceType
    source_id: str
    target_type: EntityReferenceType
    target_id: str
    relationship_type: RelationshipType
    direction: DependencyDirection = DependencyDirection.OUTBOUND
    criticality: EdgeCriticality = EdgeCriticality.MEDIUM
    confidence: EdgeConfidenceLevel = EdgeConfidenceLevel.AS_ASSERTED
    notes: str | None = None
    billing_attributes: BillingAttributes | None = None


class BulkImportRequest(BaseModel):
    """Request payload to bulk import relationships from CMDB or file (Prompt 32)."""

    import_source: str = Field(..., min_length=1, description="CMDB name or file identifier")
    import_job_id: str = Field(
        default_factory=lambda: f"job-{uuid.uuid4().hex[:8]}", description="Unique import batch ID"
    )
    items: list[BulkImportItem] = Field(
        ..., min_length=1, description="List of relationship records"
    )


class BulkImportResult(BaseModel):
    """Result summary of a bulk import operation."""

    import_job_id: str
    import_source: str
    total_received: int
    edges_created: int
    edges_updated: int
    conflicts_surfaced: int
    errors: list[str] = Field(default_factory=list)


class ConflictResolveRequest(BaseModel):
    """Payload to resolve a surfaced edge conflict (Prompt 32)."""

    resolution_action: ConflictResolutionAction = Field(
        ..., description="KEEP_MANUAL, ACCEPT_DISCOVERED, or MERGE"
    )
    resolution_notes: str = Field(
        ..., min_length=3, description="Mandatory reason explaining the resolution"
    )
    merged_criticality: EdgeCriticality | None = None
    merged_direction: DependencyDirection | None = None
    merged_billing: BillingAttributes | None = None


class NamingInferenceRule(BaseModel):
    """Configured rule for inferring application dependencies from naming patterns (Prompt 32).

    Rule: Do not infer application dependencies from naming conventions without an
    explicit configured rule, and never present an inferred edge with the same
    confidence as a structural one.
    """

    name: str = Field(..., min_length=1, description="Rule name")
    enabled: bool = Field(default=True, description="Whether rule is active")
    source_pattern: str = Field(
        ..., description="Regex pattern matching source resource name (e.g. app-(.*)-web)"
    )
    target_pattern: str = Field(
        ..., description="Regex replacement or pattern for target resource (e.g. app-\\1-api)"
    )
    relationship_type: RelationshipType = Field(
        default=RelationshipType.APPLICATION_DEPENDENCY, description="Inferred relationship type"
    )
    confidence: EdgeConfidenceLevel = Field(
        default=EdgeConfidenceLevel.LOW,
        description="Confidence level (Strictly LOW or MEDIUM, never HIGH)",
    )


class DiscoveryConfiguration(BaseModel):
    """Controls multi-layer discovery behavior and inference rule activation (Prompt 32)."""

    enable_structural: bool = Field(
        default=True, description="Layer 1: Structural edges from inventory & parent refs"
    )
    enable_network: bool = Field(default=True, description="Layer 2: Network configuration edges")
    enable_provider_platform: bool = Field(
        default=True, description="Layer 3: Provider platform relationship telemetry"
    )
    naming_rules: list[NamingInferenceRule] = Field(
        default_factory=list,
        description="Explicit naming inference rules. Must be empty or configured explicitly.",
    )
    stale_threshold_seconds: int = Field(
        default=86400, ge=60, description="Time without observation before edge is marked STALE"
    )


class DiscoveryRunRequest(BaseModel):
    """Request payload to trigger an automated discovery cycle."""

    scope_id: str | None = Field(default=None, description="Optional target scope filter")
    config: DiscoveryConfiguration = Field(
        default_factory=DiscoveryConfiguration, description="Discovery layer switches and rules"
    )


class DiscoveryRunResult(BaseModel):
    """Execution summary of an automated discovery run (Prompt 32)."""

    run_id: str
    tenant_id: str
    executed_at: dt.datetime
    structural_edges_found: int
    network_edges_found: int
    provider_edges_found: int
    inferred_edges_found: int
    total_edges_observed: int
    conflicts_surfaced: int
    stale_edges_marked: int


class BillingAllocationSyncItem(BaseModel):
    """Allocation specification linking a shared service to a consumer entity."""

    consumer_ref: TypedEntityRef
    allocation_percentage: float = Field(..., ge=0.0, le=100.0)
    allocation_rule: str = "FIXED_RATIO"
    cost_centre_id: str | None = None


class BillingAllocationSyncRequest(BaseModel):
    """Payload to synchronize shared-service billing relationships."""

    shared_service_ref: TypedEntityRef
    allocations: list[BillingAllocationSyncItem] = Field(..., min_length=1)
    notes: str | None = None


class BillingAllocationSyncResult(BaseModel):
    """Result of billing relationship synchronization."""

    shared_service_id: str
    total_allocations_synced: int
    edges_created: int
    edges_updated: int
    total_percentage: float
