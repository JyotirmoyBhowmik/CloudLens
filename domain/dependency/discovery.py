"""Multi-Layer Dependency Discovery Engine (Prompt 32).

Enforces BBP Section 24:
1. Four Discovery Layers with Honest Confidence:
   - Layer 1: Structural edges from resource attributes & parent refs (HIGH confidence).
   - Layer 2: Network edges from network config objects (interfaces, subnets, peering, gateways) (HIGH confidence).
   - Layer 3: Provider platform relationship data where exposed and permitted (HIGH confidence, probed not assumed).
   - Layer 4: Manual or CMDB-imported application edges (as asserted).
2. Negative Constraints:
   - Do not infer application dependencies from naming conventions without an explicit configured rule.
   - Do not present an inferred edge with the same confidence as a structural one (strictly LOW or MEDIUM).
"""

from __future__ import annotations

import datetime as dt
import logging
import re
import uuid
from typing import Any

from domain.dependency.merger import EdgeMergeEngine
from domain.dependency.models import (
    DependencyEdge,
    DiscoveryConfiguration,
    DiscoveryRunResult,
    EdgeProvenance,
    NamingInferenceRule,
    TypedEntityRef,
)
from domain.dependency.repository import DependencyRepository
from domain.models.enums import (
    DependencyDirection,
    DiscoveryLayer,
    EdgeConfidenceLevel,
    EdgeCriticality,
    EdgeProvenanceType,
    EdgeStatus,
    EntityReferenceType,
    RelationshipType,
)
from domain.tenant.context import TenantContext, require_tenant_context

logger = logging.getLogger(__name__)


class DependencyDiscoveryEngine:
    """Discovers directional dependency edges across multi-cloud inventory and topology."""

    def __init__(
        self,
        repository: DependencyRepository,
        merge_engine: EdgeMergeEngine,
    ) -> None:
        self.repository = repository
        self.merge_engine = merge_engine

    def execute_discovery(
        self,
        inventory_items: list[dict[str, Any]],
        *,
        config: DiscoveryConfiguration | None = None,
        tenant_context: TenantContext,
    ) -> DiscoveryRunResult:
        """Executes a full discovery cycle across enabled layers and merges candidates.

        Args:
            inventory_items: Raw or normalized inventory records with attributes,
                             tags, network interfaces, parent links, and platform telemetry.
            config: Optional discovery layer toggles and explicit naming rules.
            tenant_context: Strict TenantContext.
        """
        tc = require_tenant_context(tenant_context)
        cfg = config or DiscoveryConfiguration()
        now = dt.datetime.now(dt.UTC)
        run_id = f"disc-run-{uuid.uuid4().hex[:8]}"

        structural_found = 0
        network_found = 0
        provider_found = 0
        inferred_found = 0
        conflicts_count = 0

        # Collect candidate edges across layers
        candidates: list[DependencyEdge] = []

        # Layer 1: Structural edges
        if cfg.enable_structural:
            struct_edges = self._discover_structural_edges(inventory_items, tc)
            candidates.extend(struct_edges)
            structural_found = len(struct_edges)

        # Layer 2: Network edges
        if cfg.enable_network:
            net_edges = self._discover_network_edges(inventory_items, tc)
            candidates.extend(net_edges)
            network_found = len(net_edges)

        # Layer 3: Provider platform edges (probed, not assumed)
        if cfg.enable_provider_platform:
            prov_edges = self._discover_provider_platform_edges(inventory_items, tc)
            candidates.extend(prov_edges)
            provider_found = len(prov_edges)

        # Layer 4 / Explicit Naming Inference:
        # Negative constraint: Do not infer application dependencies from naming conventions
        # without an explicit configured rule!
        if cfg.naming_rules:
            inf_edges = self._infer_naming_convention_edges(inventory_items, cfg.naming_rules, tc)
            candidates.extend(inf_edges)
            inferred_found = len(inf_edges)

        # Pass each candidate through the merge engine (enforcing manual edge protection)
        for cand in candidates:
            _, conflict = self.merge_engine.merge_candidate_edge(cand, tenant_context=tc)
            if conflict is not None:
                conflicts_count += 1

        # Mark stale edges (edges not observed in this cycle and exceeding threshold)
        stale_marked = self._mark_stale_edges(
            scan_time=now,
            threshold_seconds=cfg.stale_threshold_seconds,
            observed_candidates=candidates,
            tenant_context=tc,
        )

        return DiscoveryRunResult(
            run_id=run_id,
            tenant_id=tc.tenant_id,
            executed_at=now,
            structural_edges_found=structural_found,
            network_edges_found=network_found,
            provider_edges_found=provider_found,
            inferred_edges_found=inferred_found,
            total_edges_observed=len(candidates),
            conflicts_surfaced=conflicts_count,
            stale_edges_marked=stale_marked,
        )

    # ==========================================================================
    # Layer 1: Structural Discovery (High Confidence)
    # ==========================================================================

    def _discover_structural_edges(
        self, items: list[dict[str, Any]], tc: TenantContext
    ) -> list[DependencyEdge]:
        """Layer 1: Structural edges from resource attributes and parent references."""
        edges: list[DependencyEdge] = []
        now = dt.datetime.now(dt.UTC)

        for item in items:
            res_id = item.get("id") or item.get("resource_id")
            if not res_id:
                continue

            # 1. Parent Scope / Resource Hierarchy (PARENT_CHILD)
            parent_id = (
                item.get("parent_id") or item.get("parent_resource_id") or item.get("parent")
            )
            if parent_id:
                edge = DependencyEdge(
                    id=f"dep-struct-parent-{tc.tenant_id[:6]}-{uuid.uuid4().hex[:8]}",
                    tenant_id=tc.tenant_id,
                    source_ref=TypedEntityRef(
                        entity_type=EntityReferenceType.RESOURCE,
                        entity_id=str(res_id),
                        name=item.get("name"),
                    ),
                    target_ref=TypedEntityRef(
                        entity_type=EntityReferenceType.RESOURCE,
                        entity_id=str(parent_id),
                    ),
                    relationship_type=RelationshipType.PARENT_CHILD,
                    direction=DependencyDirection.OUTBOUND,
                    provenance=EdgeProvenance(
                        provenance_type=EdgeProvenanceType.DISCOVERED,
                        rule_id="RULE-STRUCT-PARENT-01",
                        layer=DiscoveryLayer.STRUCTURAL,
                    ),
                    confidence=EdgeConfidenceLevel.HIGH,
                    criticality=EdgeCriticality.MEDIUM,
                    status=EdgeStatus.ACTIVE,
                    notes="Discovered structural parent reference.",
                    first_seen=now,
                    last_seen=now,
                    effective_from=now,
                )
                edges.append(edge)

            scope_id = item.get("scope_id")
            if scope_id:
                edge = DependencyEdge(
                    id=f"dep-struct-scope-{tc.tenant_id[:6]}-{uuid.uuid4().hex[:8]}",
                    tenant_id=tc.tenant_id,
                    source_ref=TypedEntityRef(
                        entity_type=EntityReferenceType.RESOURCE,
                        entity_id=str(res_id),
                        name=item.get("name"),
                    ),
                    target_ref=TypedEntityRef(
                        entity_type=EntityReferenceType.SCOPE,
                        entity_id=str(scope_id),
                    ),
                    relationship_type=RelationshipType.PARENT_CHILD,
                    direction=DependencyDirection.OUTBOUND,
                    provenance=EdgeProvenance(
                        provenance_type=EdgeProvenanceType.DISCOVERED,
                        rule_id="RULE-STRUCT-PARENT-01",
                        layer=DiscoveryLayer.STRUCTURAL,
                    ),
                    # Structural edges have HIGH confidence
                    confidence=EdgeConfidenceLevel.HIGH,
                    criticality=EdgeCriticality.MEDIUM,
                    status=EdgeStatus.ACTIVE,
                    notes="Discovered structural parent scope reference.",
                    first_seen=now,
                    last_seen=now,
                    effective_from=now,
                )
                edges.append(edge)

            # 2. Attached Storage / Volumes (LOGICAL_DEPENDENCY)
            attached_disks = item.get("attached_disks") or item.get("storage_volume_ids", [])
            for disk_id in attached_disks:
                edge = DependencyEdge(
                    id=f"dep-struct-disk-{tc.tenant_id[:6]}-{uuid.uuid4().hex[:8]}",
                    tenant_id=tc.tenant_id,
                    source_ref=TypedEntityRef(
                        entity_type=EntityReferenceType.RESOURCE,
                        entity_id=str(res_id),
                        name=item.get("name"),
                    ),
                    target_ref=TypedEntityRef(
                        entity_type=EntityReferenceType.RESOURCE,
                        entity_id=str(disk_id),
                    ),
                    relationship_type=RelationshipType.LOGICAL_DEPENDENCY,
                    direction=DependencyDirection.OUTBOUND,
                    provenance=EdgeProvenance(
                        provenance_type=EdgeProvenanceType.DISCOVERED,
                        rule_id="RULE-STRUCT-STORAGE-01",
                        layer=DiscoveryLayer.STRUCTURAL,
                    ),
                    confidence=EdgeConfidenceLevel.HIGH,
                    criticality=EdgeCriticality.HIGH,
                    status=EdgeStatus.ACTIVE,
                    notes="Discovered structural block storage attachment.",
                    first_seen=now,
                    last_seen=now,
                    effective_from=now,
                )
                edges.append(edge)

        return edges

    # ==========================================================================
    # Layer 2: Network Discovery (High Confidence)
    # ==========================================================================

    def _discover_network_edges(
        self, items: list[dict[str, Any]], tc: TenantContext
    ) -> list[DependencyEdge]:
        """Layer 2: Network edges from interfaces, subnets, gateways, and peering."""
        edges: list[DependencyEdge] = []
        now = dt.datetime.now(dt.UTC)

        for item in items:
            res_id = item.get("id") or item.get("resource_id")
            if not res_id:
                continue

            # Subnet / VPC connectivity
            subnet_id = item.get("subnet_id")
            if subnet_id:
                edge = DependencyEdge(
                    id=f"dep-net-sub-{tc.tenant_id[:6]}-{uuid.uuid4().hex[:8]}",
                    tenant_id=tc.tenant_id,
                    source_ref=TypedEntityRef(
                        entity_type=EntityReferenceType.RESOURCE,
                        entity_id=str(res_id),
                        name=item.get("name"),
                    ),
                    target_ref=TypedEntityRef(
                        entity_type=EntityReferenceType.RESOURCE,
                        entity_id=str(subnet_id),
                    ),
                    relationship_type=RelationshipType.NETWORK_CONNECTIVITY,
                    direction=DependencyDirection.BIDIRECTIONAL,
                    provenance=EdgeProvenance(
                        provenance_type=EdgeProvenanceType.DISCOVERED,
                        rule_id="RULE-NET-INTERFACE-01",
                        layer=DiscoveryLayer.NETWORK,
                    ),
                    confidence=EdgeConfidenceLevel.HIGH,
                    criticality=EdgeCriticality.MEDIUM,
                    status=EdgeStatus.ACTIVE,
                    notes="Discovered network interface subnet attachment.",
                    first_seen=now,
                    last_seen=now,
                    effective_from=now,
                )
                edges.append(edge)

            # Peering / Gateway connections
            peer_connections = item.get("peer_vpc_ids", [])
            for peer_id in peer_connections:
                edge = DependencyEdge(
                    id=f"dep-net-peer-{tc.tenant_id[:6]}-{uuid.uuid4().hex[:8]}",
                    tenant_id=tc.tenant_id,
                    source_ref=TypedEntityRef(
                        entity_type=EntityReferenceType.RESOURCE,
                        entity_id=str(res_id),
                    ),
                    target_ref=TypedEntityRef(
                        entity_type=EntityReferenceType.RESOURCE,
                        entity_id=str(peer_id),
                    ),
                    relationship_type=RelationshipType.NETWORK_CONNECTIVITY,
                    direction=DependencyDirection.BIDIRECTIONAL,
                    provenance=EdgeProvenance(
                        provenance_type=EdgeProvenanceType.DISCOVERED,
                        rule_id="RULE-NET-PEERING-01",
                        layer=DiscoveryLayer.NETWORK,
                    ),
                    confidence=EdgeConfidenceLevel.HIGH,
                    criticality=EdgeCriticality.HIGH,
                    status=EdgeStatus.ACTIVE,
                    notes="Discovered VPC peering network connection.",
                    first_seen=now,
                    last_seen=now,
                    effective_from=now,
                )
                edges.append(edge)

            # Security Groups
            sg_ids = item.get("security_group_ids") or item.get("security_groups", [])
            for sg_id in sg_ids:
                edge = DependencyEdge(
                    id=f"dep-net-sg-{tc.tenant_id[:6]}-{uuid.uuid4().hex[:8]}",
                    tenant_id=tc.tenant_id,
                    source_ref=TypedEntityRef(
                        entity_type=EntityReferenceType.RESOURCE,
                        entity_id=str(res_id),
                    ),
                    target_ref=TypedEntityRef(
                        entity_type=EntityReferenceType.RESOURCE,
                        entity_id=str(sg_id),
                    ),
                    relationship_type=RelationshipType.SECURITY_RELATIONSHIP,
                    direction=DependencyDirection.OUTBOUND,
                    provenance=EdgeProvenance(
                        provenance_type=EdgeProvenanceType.DISCOVERED,
                        rule_id="RULE-NET-SG-01",
                        layer=DiscoveryLayer.NETWORK,
                    ),
                    confidence=EdgeConfidenceLevel.HIGH,
                    criticality=EdgeCriticality.HIGH,
                    status=EdgeStatus.ACTIVE,
                    notes="Discovered attached security group boundary.",
                    first_seen=now,
                    last_seen=now,
                    effective_from=now,
                )
                edges.append(edge)

        return edges

    # ==========================================================================
    # Layer 3: Provider Platform Discovery (Probed Not Assumed)
    # ==========================================================================

    def _discover_provider_platform_edges(
        self, items: list[dict[str, Any]], tc: TenantContext
    ) -> list[DependencyEdge]:
        """Layer 3: Provider platform relationship data where exposed and permitted.

        Rule: Probed not assumed. Does not generate edges unless the provider explicitly
        exposed the platform relationship metadata.
        """
        edges: list[DependencyEdge] = []
        now = dt.datetime.now(dt.UTC)

        for item in items:
            res_id = item.get("id") or item.get("resource_id")
            if not res_id:
                continue

            platform_data = item.get("provider_platform_telemetry") or item.get(
                "platform_metadata", {}
            )
            provider_rels = item.get("provider_relationships") or platform_data.get(
                "relationships", []
            )
            if not platform_data and not provider_rels:
                # Probed not assumed: No telemetry exposed by provider
                continue

            for rel in provider_rels:
                tgt_id = rel.get("target_id") or rel.get("entity_id")
                if not tgt_id:
                    continue
                rel_type_str = str(rel.get("relationship_type", "SECURITY_RELATIONSHIP"))
                rel_type = getattr(
                    RelationshipType, rel_type_str, RelationshipType.SECURITY_RELATIONSHIP
                )
                tgt_type_str = str(rel.get("target_type", "RESOURCE"))
                tgt_type = getattr(EntityReferenceType, tgt_type_str, EntityReferenceType.RESOURCE)
                edge = DependencyEdge(
                    id=f"dep-plat-rel-{tc.tenant_id[:6]}-{uuid.uuid4().hex[:8]}",
                    tenant_id=tc.tenant_id,
                    source_ref=TypedEntityRef(
                        entity_type=EntityReferenceType.RESOURCE,
                        entity_id=str(res_id),
                        name=item.get("name"),
                    ),
                    target_ref=TypedEntityRef(
                        entity_type=tgt_type,
                        entity_id=str(tgt_id),
                    ),
                    relationship_type=rel_type,
                    direction=DependencyDirection.OUTBOUND,
                    provenance=EdgeProvenance(
                        provenance_type=EdgeProvenanceType.DISCOVERED,
                        rule_id="DISCO-L3-PROVIDER-PROBED",
                        layer=DiscoveryLayer.PROVIDER_PLATFORM,
                    ),
                    confidence=EdgeConfidenceLevel.HIGH,
                    criticality=EdgeCriticality.HIGH,
                    status=EdgeStatus.ACTIVE,
                    notes="Discovered provider platform telemetry relationship.",
                    first_seen=now,
                    last_seen=now,
                    effective_from=now,
                )
                edges.append(edge)

            # Check database replication / read-replica pointers
            read_replica_source = platform_data.get("read_replica_source_id")
            if read_replica_source:
                edge = DependencyEdge(
                    id=f"dep-plat-rep-{tc.tenant_id[:6]}-{uuid.uuid4().hex[:8]}",
                    tenant_id=tc.tenant_id,
                    source_ref=TypedEntityRef(
                        entity_type=EntityReferenceType.RESOURCE,
                        entity_id=str(res_id),
                        name=item.get("name"),
                    ),
                    target_ref=TypedEntityRef(
                        entity_type=EntityReferenceType.RESOURCE,
                        entity_id=str(read_replica_source),
                    ),
                    relationship_type=RelationshipType.DATA_FLOW,
                    direction=DependencyDirection.OUTBOUND,
                    provenance=EdgeProvenance(
                        provenance_type=EdgeProvenanceType.DISCOVERED,
                        rule_id="RULE-PROV-REPLICA-01",
                        layer=DiscoveryLayer.PROVIDER_PLATFORM,
                    ),
                    confidence=EdgeConfidenceLevel.HIGH,
                    criticality=EdgeCriticality.CRITICAL,
                    status=EdgeStatus.ACTIVE,
                    notes="Discovered database read-replica data-flow from provider telemetry.",
                    first_seen=now,
                    last_seen=now,
                    effective_from=now,
                )
                edges.append(edge)

            # Check Load Balancer target group backend pointers
            target_backends = platform_data.get("target_backend_ids", [])
            for backend_id in target_backends:
                edge = DependencyEdge(
                    id=f"dep-plat-lb-{tc.tenant_id[:6]}-{uuid.uuid4().hex[:8]}",
                    tenant_id=tc.tenant_id,
                    source_ref=TypedEntityRef(
                        entity_type=EntityReferenceType.RESOURCE,
                        entity_id=str(res_id),
                    ),
                    target_ref=TypedEntityRef(
                        entity_type=EntityReferenceType.RESOURCE,
                        entity_id=str(backend_id),
                    ),
                    relationship_type=RelationshipType.NETWORK_CONNECTIVITY,
                    direction=DependencyDirection.OUTBOUND,
                    provenance=EdgeProvenance(
                        provenance_type=EdgeProvenanceType.DISCOVERED,
                        rule_id="RULE-PROV-LB-01",
                        layer=DiscoveryLayer.PROVIDER_PLATFORM,
                    ),
                    confidence=EdgeConfidenceLevel.HIGH,
                    criticality=EdgeCriticality.HIGH,
                    status=EdgeStatus.ACTIVE,
                    notes="Discovered load balancer target backend from provider metadata.",
                    first_seen=now,
                    last_seen=now,
                    effective_from=now,
                )
                edges.append(edge)

        return edges

    # ==========================================================================
    # Layer 4 / Explicit Naming Inference (Strictly Low/Medium Confidence)
    # ==========================================================================

    def _infer_naming_convention_edges(
        self,
        items: list[dict[str, Any]],
        rules: list[NamingInferenceRule],
        tc: TenantContext,
    ) -> list[DependencyEdge]:
        """Infers application dependencies based on explicit naming convention rules.

        Rules Enforced:
        - Do not infer application dependencies from naming conventions without an explicit configured rule.
        - Do not present an inferred edge with the same confidence as a structural one (strictly LOW or MEDIUM).
        """
        edges: list[DependencyEdge] = []
        now = dt.datetime.now(dt.UTC)
        name_to_item: dict[str, dict[str, Any]] = {
            item.get("name", ""): item for item in items if item.get("name")
        }

        active_rules = [r for r in rules if r.enabled]
        for rule in active_rules:
            # Enforce non-structural confidence rule
            confidence = (
                EdgeConfidenceLevel.LOW
                if rule.confidence == EdgeConfidenceLevel.HIGH
                else rule.confidence
            )

            try:
                pattern = re.compile(rule.source_pattern)
            except re.error as e:
                logger.error(f"Invalid naming pattern in rule '{rule.name}': {e}")
                continue

            for name, source_item in name_to_item.items():
                if pattern.search(name):
                    target_name = pattern.sub(rule.target_pattern, name)
                    target_item = name_to_item.get(target_name)

                    if target_item:
                        source_id = source_item.get("id") or source_item.get("resource_id")
                        target_id = target_item.get("id") or target_item.get("resource_id")
                        if not source_id or not target_id or source_id == target_id:
                            continue

                        edge = DependencyEdge(
                            id=f"dep-inf-name-{tc.tenant_id[:6]}-{uuid.uuid4().hex[:8]}",
                            tenant_id=tc.tenant_id,
                            source_ref=TypedEntityRef(
                                entity_type=EntityReferenceType.RESOURCE,
                                entity_id=str(source_id),
                                name=name,
                            ),
                            target_ref=TypedEntityRef(
                                entity_type=EntityReferenceType.RESOURCE,
                                entity_id=str(target_id),
                                name=target_name,
                            ),
                            relationship_type=rule.relationship_type,
                            direction=DependencyDirection.OUTBOUND,
                            provenance=EdgeProvenance(
                                provenance_type=EdgeProvenanceType.INFERRED,
                                rule_id=f"RULE-NAMING-{rule.name}",
                                layer=DiscoveryLayer.INFERRED_NAMING,
                            ),
                            # STRICT: Inferred edges are NEVER high confidence!
                            confidence=confidence,
                            criticality=EdgeCriticality.MEDIUM,
                            status=EdgeStatus.ACTIVE,
                            notes=f"Inferred via explicit naming rule '{rule.name}'.",
                            first_seen=now,
                            last_seen=now,
                            effective_from=now,
                        )
                        edges.append(edge)

        return edges

    # ==========================================================================
    # Stale-Edge Marking
    # ==========================================================================

    def _mark_stale_edges(
        self,
        scan_time: dt.datetime,
        threshold_seconds: int,
        observed_candidates: list[DependencyEdge],
        tenant_context: TenantContext,
    ) -> int:
        """Marks active discovered edges that were not re-observed as STALE.

        Manual edges are never automatically marked stale by discovery cycles.
        """
        stale_threshold = scan_time - dt.timedelta(seconds=threshold_seconds)
        observed_pairs = {
            (c.source_ref.entity_id, c.target_ref.entity_id, c.relationship_type)
            for c in observed_candidates
        }

        active_edges = self.repository.list_edges(
            status=EdgeStatus.ACTIVE, tenant_context=tenant_context
        )
        stale_count = 0

        for edge in active_edges:
            # Manual edges are protected from automated stale marking
            if edge.is_manual:
                continue

            pair = (edge.source_ref.entity_id, edge.target_ref.entity_id, edge.relationship_type)
            if pair not in observed_pairs and edge.last_seen < stale_threshold:
                edge.status = EdgeStatus.STALE
                edge.add_history(
                    action="MARKED_STALE",
                    actor_id="discovery-engine",
                    from_status=EdgeStatus.ACTIVE.value,
                    to_status=EdgeStatus.STALE.value,
                    note=f"Edge no longer observed as of {scan_time.isoformat()}.",
                )
                self.repository.save_edge(edge, tenant_context=tenant_context)
                stale_count += 1
                logger.info(f"Marked edge '{edge.id}' as STALE [Last seen: {edge.last_seen}].")

        return stale_count
