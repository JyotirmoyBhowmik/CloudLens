"""Unified Domain Service Facade for Dependency Model and Discovery (Prompt 32).

Coordinates:
- Manual edge lifecycle with immutable audit trail.
- Multi-layer automated discovery (Layers 1-4 with honest confidence ratings).
- Merge rule enforcement and conflict surfacing/resolution.
- Point-in-time graph queries (as_of) and stale-edge marking.
- Downstream impact set analysis with depth control and cycle detection.
- Bulk CMDB/file import.
- Billing allocation relationship synchronization.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from typing import Any

from domain.audit.service import AuditService, get_audit_service
from domain.dependency.discovery import DependencyDiscoveryEngine
from domain.dependency.impact import ImpactAnalysisEngine
from domain.dependency.importer import BulkDependencyImporter
from domain.dependency.merger import EdgeMergeEngine
from domain.dependency.models import (
    BillingAllocationSyncRequest,
    BillingAllocationSyncResult,
    BillingAttributes,
    BulkImportRequest,
    BulkImportResult,
    ConflictResolveRequest,
    DependencyEdge,
    DiscoveryConfiguration,
    DiscoveryRunResult,
    EdgeConflict,
    EdgeProvenance,
    EdgeUpdateRequest,
    ImpactSet,
    ManualEdgeCreateRequest,
    TopologyGraph,
    TypedEntityRef,
)
from domain.dependency.repository import (
    DependencyRepository,
    get_dependency_repository,
)
from domain.models.enums import (
    AuditEventType,
    DependencyDirection,
    DiscoveryLayer,
    EdgeConfidenceLevel,
    EdgeCriticality,
    EdgeProvenanceType,
    EdgeStatus,
    RelationshipType,
)
from domain.models.exceptions import (
    DependencyEdgeNotFoundException,
    InvalidEdgeReferenceException,
)
from domain.tenant.context import TenantContext, require_tenant_context

logger = logging.getLogger(__name__)


class DependencyService:
    """Enterprise domain service for dependency topology, discovery, and impact analysis."""

    def __init__(
        self,
        repository: DependencyRepository | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self.repository = repository or get_dependency_repository()
        self.audit_service = audit_service or get_audit_service()
        self.merge_engine = EdgeMergeEngine(self.repository)
        self.discovery_engine = DependencyDiscoveryEngine(self.repository, self.merge_engine)
        self.impact_engine = ImpactAnalysisEngine(self.repository)
        self.importer = BulkDependencyImporter(self.repository, self.merge_engine)

    # ==========================================================================
    # 1. Manual Edge Lifecycle (Human Curation)
    # ==========================================================================

    def create_manual_edge(
        self,
        req: ManualEdgeCreateRequest,
        actor: str,
        *,
        tenant_context: TenantContext,
    ) -> DependencyEdge:
        """Creates a manually asserted dependency edge with high provenance priority."""
        tc = require_tenant_context(tenant_context)
        now = dt.datetime.now(dt.UTC)

        if req.source_ref.entity_id == req.target_ref.entity_id:
            raise InvalidEdgeReferenceException(
                req.source_ref.entity_id, "Source and target entity IDs cannot be identical."
            )

        edge_id = f"dep-man-{tc.tenant_id[:6]}-{uuid.uuid4().hex[:8]}"
        edge = DependencyEdge(
            id=edge_id,
            tenant_id=tc.tenant_id,
            source_ref=req.source_ref,
            target_ref=req.target_ref,
            relationship_type=req.relationship_type,
            direction=req.direction,
            provenance=EdgeProvenance(
                provenance_type=EdgeProvenanceType.MANUAL,
                actor_id=actor,
                layer=DiscoveryLayer.CURATED_APPLICATION,
                created_at=now,
            ),
            confidence=req.confidence,
            criticality=req.criticality,
            status=EdgeStatus.ACTIVE,
            notes=req.notes,
            first_seen=now,
            last_seen=now,
            effective_from=now,
            billing_attributes=req.billing_attributes,
        )

        edge.add_history(
            action="MANUAL_CREATED",
            actor_id=actor,
            from_status=None,
            to_status=EdgeStatus.ACTIVE.value,
            note=req.notes or "Manually asserted relationship edge.",
        )

        saved = self.repository.save_edge(edge, tenant_context=tc)

        self._record_audit(
            event_type=AuditEventType.DEPENDENCY_EDGE_CREATED,
            actor_id=actor,
            edge_id=saved.id,
            details={
                "source": saved.source_ref.key,
                "target": saved.target_ref.key,
                "relationship_type": saved.relationship_type.value,
                "provenance": saved.provenance.provenance_type.value,
            },
            tenant_context=tc,
        )
        return saved

    def get_edge(self, edge_id: str, *, tenant_context: TenantContext) -> DependencyEdge:
        """Retrieves a dependency edge by ID or raises NotFound."""
        tc = require_tenant_context(tenant_context)
        edge = self.repository.get_edge(edge_id, tenant_context=tc)
        if not edge:
            raise DependencyEdgeNotFoundException(edge_id)
        return edge

    def update_edge(
        self,
        edge_id: str,
        req: EdgeUpdateRequest,
        actor: str,
        *,
        tenant_context: TenantContext,
    ) -> DependencyEdge:
        """Updates attributes of an existing dependency edge."""
        tc = require_tenant_context(tenant_context)
        edge = self.get_edge(edge_id, tenant_context=tc)
        now = dt.datetime.now(dt.UTC)

        changes: dict[str, Any] = {}
        if req.relationship_type is not None and req.relationship_type != edge.relationship_type:
            changes["relationship_type"] = (
                edge.relationship_type.value,
                req.relationship_type.value,
            )
            edge.relationship_type = req.relationship_type

        if req.direction is not None and req.direction != edge.direction:
            changes["direction"] = (edge.direction.value, req.direction.value)
            edge.direction = req.direction

        if req.criticality is not None and req.criticality != edge.criticality:
            changes["criticality"] = (edge.criticality.value, req.criticality.value)
            edge.criticality = req.criticality

        if req.notes is not None:
            edge.notes = req.notes

        if req.billing_attributes is not None:
            edge.billing_attributes = req.billing_attributes

        edge.last_seen = now
        edge.add_history(
            action="MANUAL_UPDATED",
            actor_id=actor,
            from_status=edge.status.value,
            to_status=edge.status.value,
            note=req.notes or "Edge attributes modified.",
            details=changes,
        )

        saved = self.repository.save_edge(edge, tenant_context=tc)
        self._record_audit(
            event_type=AuditEventType.DEPENDENCY_EDGE_UPDATED,
            actor_id=actor,
            edge_id=saved.id,
            details=changes,
            tenant_context=tc,
        )
        return saved

    def delete_edge(
        self,
        edge_id: str,
        actor: str,
        *,
        tenant_context: TenantContext,
    ) -> bool:
        """Soft-terminates a dependency edge with audit tracking."""
        tc = require_tenant_context(tenant_context)
        edge = self.get_edge(edge_id, tenant_context=tc)
        success = self.repository.delete_edge(edge_id, tenant_context=tc, hard=False)
        if success:
            self._record_audit(
                event_type=AuditEventType.DEPENDENCY_EDGE_DELETED,
                actor_id=actor,
                edge_id=edge_id,
                details={"source": edge.source_ref.key, "target": edge.target_ref.key},
                tenant_context=tc,
            )
        return success

    def list_edges(
        self,
        *,
        status: EdgeStatus | None = None,
        relationship_type: RelationshipType | None = None,
        as_of: dt.datetime | None = None,
        source_id: str | None = None,
        target_id: str | None = None,
        include_deleted: bool = False,
        tenant_context: TenantContext,
    ) -> list[DependencyEdge]:
        """Lists dependency edges matching filters for the calling tenant."""
        tc = require_tenant_context(tenant_context)
        return self.repository.list_edges(
            status=status,
            relationship_type=relationship_type,
            as_of=as_of,
            source_id=source_id,
            target_id=target_id,
            include_deleted=include_deleted,
            tenant_context=tc,
        )

    # ==========================================================================
    # 2. Automated Multi-Layer Discovery
    # ==========================================================================

    def run_discovery(
        self,
        inventory_items: list[dict[str, Any]],
        *,
        config: DiscoveryConfiguration | None = None,
        actor: str = "discovery-scheduler",
        tenant_context: TenantContext,
    ) -> DiscoveryRunResult:
        """Executes automated 4-layer dependency discovery with merge protection."""
        tc = require_tenant_context(tenant_context)
        result = self.discovery_engine.execute_discovery(
            inventory_items, config=config, tenant_context=tc
        )

        self._record_audit(
            event_type=AuditEventType.DEPENDENCY_DISCOVERY_COMPLETED,
            actor_id=actor,
            edge_id=result.run_id,
            details={
                "total_observed": result.total_edges_observed,
                "conflicts_surfaced": result.conflicts_surfaced,
                "stale_marked": result.stale_edges_marked,
            },
            tenant_context=tc,
        )
        return result

    # ==========================================================================
    # 3. Conflict Resolution
    # ==========================================================================

    def list_conflicts(
        self, *, unresolved_only: bool = True, tenant_context: TenantContext
    ) -> list[EdgeConflict]:
        """Lists surfaced conflicts between manual and discovered edges."""
        tc = require_tenant_context(tenant_context)
        return self.repository.list_conflicts(unresolved_only=unresolved_only, tenant_context=tc)

    def resolve_conflict(
        self,
        conflict_id: str,
        req: ConflictResolveRequest,
        actor: str,
        *,
        tenant_context: TenantContext,
    ) -> EdgeConflict:
        """Resolves a surfaced conflict via KEEP_MANUAL, ACCEPT_DISCOVERED, or MERGE."""
        tc = require_tenant_context(tenant_context)
        resolved = self.merge_engine.resolve_conflict(
            conflict_id, req, actor_id=actor, tenant_context=tc
        )

        self._record_audit(
            event_type=AuditEventType.DEPENDENCY_CONFLICT_RESOLVED,
            actor_id=actor,
            edge_id=conflict_id,
            details={
                "action": req.resolution_action.value,
                "notes": req.resolution_notes,
            },
            tenant_context=tc,
        )
        return resolved

    # ==========================================================================
    # 4. Point-in-Time Graph Rendering (as_of)
    # ==========================================================================

    def get_topology_graph(
        self,
        *,
        as_of: dt.datetime | None = None,
        tenant_context: TenantContext,
    ) -> TopologyGraph:
        """Renders the topology graph as of a past date or current state."""
        tc = require_tenant_context(tenant_context)
        target_time = as_of or dt.datetime.now(dt.UTC)

        edges = self.repository.list_edges(as_of=target_time, tenant_context=tc)

        # Collect distinct nodes
        nodes_map: dict[str, TypedEntityRef] = {}
        for e in edges:
            nodes_map[e.source_ref.key] = e.source_ref
            nodes_map[e.target_ref.key] = e.target_ref

        conflicts = self.repository.list_conflicts(unresolved_only=True, tenant_context=tc)
        stale_edges = [e for e in edges if e.status == EdgeStatus.STALE]

        return TopologyGraph(
            tenant_id=tc.tenant_id,
            as_of=target_time,
            nodes=list(nodes_map.values()),
            edges=edges,
            conflicts_count=len(conflicts),
            stale_edges_count=len(stale_edges),
        )

    # ==========================================================================
    # 5. Impact-Set Computation
    # ==========================================================================

    def compute_downstream_impact(
        self,
        entity_id: str,
        *,
        max_depth: int | None = None,
        relationship_types: list[RelationshipType] | None = None,
        as_of: dt.datetime | None = None,
        tenant_context: TenantContext,
    ) -> ImpactSet:
        """Computes downstream dependents of an entity with depth and cycle control."""
        tc = require_tenant_context(tenant_context)
        return self.impact_engine.compute_downstream_impact(
            entity_id=entity_id,
            max_depth=max_depth,
            relationship_types=relationship_types,
            as_of=as_of,
            tenant_context=tc,
        )

    def compute_upstream_dependencies(
        self,
        entity_id: str,
        *,
        max_depth: int | None = None,
        as_of: dt.datetime | None = None,
        tenant_context: TenantContext,
    ) -> ImpactSet:
        """Computes all upstream dependencies an entity relies upon."""
        tc = require_tenant_context(tenant_context)
        return self.impact_engine.compute_upstream_dependencies(
            entity_id=entity_id,
            max_depth=max_depth,
            as_of=as_of,
            tenant_context=tc,
        )

    # ==========================================================================
    # 6. Bulk Import
    # ==========================================================================

    def bulk_import(
        self,
        request: BulkImportRequest,
        actor: str,
        *,
        tenant_context: TenantContext,
    ) -> BulkImportResult:
        """Bulk imports relationships from CMDB or structured external sources."""
        tc = require_tenant_context(tenant_context)
        result = self.importer.import_relationships(request, tenant_context=tc)

        self._record_audit(
            event_type=AuditEventType.DEPENDENCY_BULK_IMPORTED,
            actor_id=actor,
            edge_id=result.import_job_id,
            details={
                "source": result.import_source,
                "created": result.edges_created,
                "updated": result.edges_updated,
                "conflicts": result.conflicts_surfaced,
            },
            tenant_context=tc,
        )
        return result

    # ==========================================================================
    # 7. Billing Relationship Synchronization
    # ==========================================================================

    def sync_billing_relationships(
        self,
        request: BillingAllocationSyncRequest,
        actor: str,
        *,
        tenant_context: TenantContext,
    ) -> BillingAllocationSyncResult:
        """Links shared-service costs to consumer applications/scopes in the graph.

        Ensures dependency graph and cost allocation models agree rather than telling two stories.
        """
        tc = require_tenant_context(tenant_context)
        now = dt.datetime.now(dt.UTC)

        created = 0
        updated = 0
        total_pct = sum(item.allocation_percentage for item in request.allocations)

        for item in request.allocations:
            existing = self.repository.find_edge(
                source_id=request.shared_service_ref.entity_id,
                target_id=item.consumer_ref.entity_id,
                relationship_type=RelationshipType.BILLING_RELATIONSHIP,
                tenant_context=tc,
            )

            b_attrs = BillingAttributes(
                allocation_percentage=item.allocation_percentage,
                allocation_rule=item.allocation_rule,
                shared_service_id=request.shared_service_ref.entity_id,
                cost_centre_id=item.cost_centre_id,
            )

            if existing is not None:
                existing.billing_attributes = b_attrs
                existing.last_seen = now
                existing.add_history(
                    action="BILLING_SYNCED",
                    actor_id=actor,
                    note=request.notes or "Updated shared-service billing allocation.",
                    details={"allocation_percentage": item.allocation_percentage},
                )
                self.repository.save_edge(existing, tenant_context=tc)
                updated += 1
            else:
                edge_id = f"dep-bill-{tc.tenant_id[:6]}-{uuid.uuid4().hex[:8]}"
                edge = DependencyEdge(
                    id=edge_id,
                    tenant_id=tc.tenant_id,
                    source_ref=request.shared_service_ref,
                    target_ref=item.consumer_ref,
                    relationship_type=RelationshipType.BILLING_RELATIONSHIP,
                    direction=DependencyDirection.OUTBOUND,
                    provenance=EdgeProvenance(
                        provenance_type=EdgeProvenanceType.MANUAL,
                        actor_id=actor,
                        layer=DiscoveryLayer.CURATED_APPLICATION,
                        created_at=now,
                    ),
                    confidence=EdgeConfidenceLevel.HIGH,
                    criticality=EdgeCriticality.MEDIUM,
                    status=EdgeStatus.ACTIVE,
                    notes=request.notes or "Shared service billing cost allocation link.",
                    first_seen=now,
                    last_seen=now,
                    effective_from=now,
                    billing_attributes=b_attrs,
                )
                edge.add_history(
                    action="BILLING_SYNCED",
                    actor_id=actor,
                    note=request.notes or "Created shared-service billing allocation edge.",
                    details={"allocation_percentage": item.allocation_percentage},
                )
                self.repository.save_edge(edge, tenant_context=tc)
                created += 1

        self._record_audit(
            event_type=AuditEventType.DEPENDENCY_BILLING_SYNCED,
            actor_id=actor,
            edge_id=request.shared_service_ref.entity_id,
            details={
                "shared_service": request.shared_service_ref.key,
                "allocations_count": len(request.allocations),
                "total_percentage": total_pct,
            },
            tenant_context=tc,
        )

        return BillingAllocationSyncResult(
            shared_service_id=request.shared_service_ref.entity_id,
            total_allocations_synced=len(request.allocations),
            edges_created=created,
            edges_updated=updated,
            total_percentage=total_pct,
        )

    # ==========================================================================
    # Internal Audit Helper
    # ==========================================================================

    def _record_audit(
        self,
        event_type: AuditEventType,
        actor_id: str,
        edge_id: str,
        details: dict[str, Any],
        *,
        tenant_context: TenantContext,
    ) -> None:
        """Safely records an audit event without failing business operations."""
        try:
            self.audit_service.record_event(
                tenant_context=tenant_context,
                event_type=event_type,
                actor=actor_id,
                payload=details,
                resource_type="DEPENDENCY_EDGE",
                resource_id=edge_id,
            )
        except Exception as e:
            logger.debug(f"Failed to record dependency audit event: {e}")


_dependency_service_instance: DependencyService | None = None


def get_dependency_service() -> DependencyService:
    """Singleton provider for DependencyService."""
    global _dependency_service_instance
    if _dependency_service_instance is None:
        _dependency_service_instance = DependencyService()
    return _dependency_service_instance


def reset_dependency_service() -> None:
    """Resets singleton instance for test teardown."""
    global _dependency_service_instance
    _dependency_service_instance = None
