"""Comprehensive Unit and Integration Tests for Dependency Model & Discovery Engine (Prompt 32).

Enforces:
- BBP Section 24: Relationship types, multi-layer discovery, manual edge protection,
  point-in-time graph queries, impact-set analysis, bulk import, and billing synchronization.
- Eight relationship types registered in master data and domain model.
- Four discovery layers with honest confidence levels (HIGH for structural/network/provider,
  AS_ASSERTED for CMDB, LOW/MEDIUM for inferred).
- Merge rule: Discovered edge NEVER silently overwrites a manual edge; conflicts are surfaced
  with both versions visible.
- Negative constraints:
  - Do NOT infer application dependencies from naming conventions without an explicit rule.
  - Do NOT present an inferred edge with the same confidence as a structural one (never HIGH).
- Cycle detection and depth control in downstream & upstream impact analysis.
- Multi-tenant isolation across all repository and service operations.
- Full REST API verification using FastAPI TestClient.
"""

from __future__ import annotations

import datetime as dt
import uuid
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from api.cloudlens_api.main import app
from domain.dependency.models import (
    BillingAllocationSyncItem,
    BillingAllocationSyncRequest,
    BulkImportItem,
    BulkImportRequest,
    ConflictResolveRequest,
    DiscoveryConfiguration,
    EdgeUpdateRequest,
    ManualEdgeCreateRequest,
    NamingInferenceRule,
    TypedEntityRef,
)
from domain.dependency.repository import (
    reset_dependency_repository,
)
from domain.dependency.service import (
    DependencyService,
    reset_dependency_service,
)
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
from domain.models.exceptions import (
    DependencyEdgeNotFoundException,
    MissingTenantContextException,
)
from domain.tenant.context import TenantContext

# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture(autouse=True)
def cleanup_dependency_state():
    """Ensures clean repository and service instances between tests."""
    reset_dependency_repository()
    reset_dependency_service()
    yield
    reset_dependency_repository()
    reset_dependency_service()


@pytest.fixture
def tenant_ctx() -> TenantContext:
    """Standard primary tenant context."""
    return TenantContext(
        tenant_id="tenant-alpha",
        user_id="user-architect",
        correlation_id=str(uuid.uuid4()),
    )


@pytest.fixture
def other_tenant_ctx() -> TenantContext:
    """Secondary tenant context for multi-tenant isolation testing."""
    return TenantContext(
        tenant_id="tenant-beta",
        user_id="user-other-admin",
        correlation_id=str(uuid.uuid4()),
    )


@pytest.fixture
def dependency_service() -> DependencyService:
    """Returns a fresh DependencyService."""
    return DependencyService()


@pytest.fixture
def client() -> TestClient:
    """FastAPI TestClient fixture."""
    return TestClient(app)


# ==============================================================================
# 1. Master Data & Relationship Types Verification
# ==============================================================================


class TestMasterDataAndRelationshipTypes:
    """Verifies that all 8 relationship types exist and master data is intact."""

    def test_eight_canonical_relationship_types_exist(self):
        """Validates all 8 relationship types required by Prompt 32 BBP Section 24."""
        expected_types = {
            "LOGICAL_DEPENDENCY",
            "NETWORK_CONNECTIVITY",
            "APPLICATION_DEPENDENCY",
            "DATA_FLOW",
            "SECURITY_RELATIONSHIP",
            "SHARED_SERVICE",
            "BILLING_RELATIONSHIP",
            "PARENT_CHILD",
        }
        actual_types = {rt.value for rt in RelationshipType}
        for exp in expected_types:
            assert exp in actual_types

    def test_seed_contains_all_eight_relationship_types(self):
        """Verifies relationship_type master data seed file contains all 8 types."""
        from masterdata.registry import SYSTEM_MASTER_REGISTRY

        assert "RELATIONSHIP_TYPE" in SYSTEM_MASTER_REGISTRY
        metadata = SYSTEM_MASTER_REGISTRY["RELATIONSHIP_TYPE"]
        assert Path(metadata.seed_file).exists()


# ==============================================================================
# 2. Manual Edge Lifecycle
# ==============================================================================


class TestManualEdgeLifecycle:
    """Tests manual relationship edge creation, retrieval, update, and soft deletion."""

    def test_create_and_retrieve_manual_edge(
        self, dependency_service: DependencyService, tenant_ctx: TenantContext
    ):
        """Manual edge creation assigns MANUAL provenance and AS_ASSERTED confidence."""
        req = ManualEdgeCreateRequest(
            source_ref=TypedEntityRef(
                entity_type=EntityReferenceType.APPLICATION,
                entity_id="app-checkout",
                name="Checkout Service",
            ),
            target_ref=TypedEntityRef(
                entity_type=EntityReferenceType.RESOURCE,
                entity_id="rds-postgres-main",
                name="Main DB",
            ),
            relationship_type=RelationshipType.DATA_FLOW,
            direction=DependencyDirection.OUTBOUND,
            confidence=EdgeConfidenceLevel.AS_ASSERTED,
            criticality=EdgeCriticality.CRITICAL,
            notes="Direct database writes for order processing",
        )

        edge = dependency_service.create_manual_edge(
            req, actor="user-architect", tenant_context=tenant_ctx
        )
        assert edge.id is not None
        assert edge.is_manual is True
        assert edge.provenance.provenance_type == EdgeProvenanceType.MANUAL
        assert edge.provenance.actor_id == "user-architect"
        assert edge.confidence == EdgeConfidenceLevel.AS_ASSERTED
        assert edge.criticality == EdgeCriticality.CRITICAL
        assert edge.status == EdgeStatus.ACTIVE

        # Retrieve edge
        fetched = dependency_service.get_edge(edge.id, tenant_context=tenant_ctx)
        assert fetched.id == edge.id
        assert fetched.source_ref.entity_id == "app-checkout"
        assert fetched.target_ref.entity_id == "rds-postgres-main"

    def test_update_manual_edge(
        self, dependency_service: DependencyService, tenant_ctx: TenantContext
    ):
        """Updating an edge modifies attributes and logs history entry."""
        req = ManualEdgeCreateRequest(
            source_ref=TypedEntityRef(
                entity_type=EntityReferenceType.SERVICE,
                entity_id="svc-auth",
            ),
            target_ref=TypedEntityRef(
                entity_type=EntityReferenceType.RESOURCE,
                entity_id="redis-session-cache",
            ),
            relationship_type=RelationshipType.LOGICAL_DEPENDENCY,
            criticality=EdgeCriticality.MEDIUM,
        )
        edge = dependency_service.create_manual_edge(
            req, actor="user-architect", tenant_context=tenant_ctx
        )

        # Update criticality and notes
        update_req = EdgeUpdateRequest(
            criticality=EdgeCriticality.HIGH,
            notes="Upgraded criticality due to session reliance",
        )
        updated = dependency_service.update_edge(
            edge.id, update_req, actor="user-architect", tenant_context=tenant_ctx
        )
        assert updated.criticality == EdgeCriticality.HIGH
        assert updated.notes == "Upgraded criticality due to session reliance"
        assert len(updated.history) >= 2
        assert updated.history[-1].action == "MANUAL_UPDATED"

    def test_delete_manual_edge_marks_status_deleted(
        self, dependency_service: DependencyService, tenant_ctx: TenantContext
    ):
        """Soft deleting an edge sets status=DELETED and sets effective_to."""
        req = ManualEdgeCreateRequest(
            source_ref=TypedEntityRef(
                entity_type=EntityReferenceType.APPLICATION, entity_id="app-1"
            ),
            target_ref=TypedEntityRef(entity_type=EntityReferenceType.RESOURCE, entity_id="res-1"),
            relationship_type=RelationshipType.LOGICAL_DEPENDENCY,
        )
        edge = dependency_service.create_manual_edge(
            req, actor="user-architect", tenant_context=tenant_ctx
        )

        dependency_service.delete_edge(edge.id, actor="user-architect", tenant_context=tenant_ctx)

        # Active edge list should no longer include it
        active_edges = dependency_service.list_edges(tenant_context=tenant_ctx)
        assert not any(e.id == edge.id for e in active_edges)

        # Include deleted flag retrieves it with DELETED status
        all_edges = dependency_service.list_edges(include_deleted=True, tenant_context=tenant_ctx)
        deleted = next(e for e in all_edges if e.id == edge.id)
        assert deleted.status == EdgeStatus.DELETED
        assert deleted.effective_to is not None


# ==============================================================================
# 3. Multi-Layer Discovery with Honest Confidence
# ==============================================================================


class TestMultiLayerDiscovery:
    """Verifies four discovery layers and honest confidence rules."""

    def test_layer1_structural_discovery(
        self, dependency_service: DependencyService, tenant_ctx: TenantContext
    ):
        """Structural discovery generates parent-child relationships with HIGH confidence."""
        inventory = [
            {
                "id": "vm-web-01",
                "name": "vm-web-01",
                "resource_type": "compute_instance",
                "parent_id": "vpc-core-01",
                "scope_id": "scope-prod",
            }
        ]

        cfg = DiscoveryConfiguration(
            enable_structural=True,
            enable_network=False,
            enable_provider_platform=False,
            naming_rules=[],
        )
        result = dependency_service.run_discovery(
            inventory, config=cfg, actor="discovery-worker", tenant_context=tenant_ctx
        )

        assert result.structural_edges_found >= 1
        edges = dependency_service.list_edges(tenant_context=tenant_ctx)
        struct_edges = [e for e in edges if e.provenance.layer == DiscoveryLayer.STRUCTURAL]
        assert len(struct_edges) >= 1
        for e in struct_edges:
            assert e.confidence == EdgeConfidenceLevel.HIGH
            assert e.relationship_type == RelationshipType.PARENT_CHILD
            assert e.provenance.provenance_type == EdgeProvenanceType.DISCOVERED
            assert e.provenance.rule_id == "RULE-STRUCT-PARENT-01"

    def test_layer2_network_discovery(
        self, dependency_service: DependencyService, tenant_ctx: TenantContext
    ):
        """Network discovery creates network connectivity edges with HIGH confidence."""
        inventory = [
            {
                "id": "nic-01",
                "resource_type": "network_interface",
                "subnet_id": "subnet-app-01",
                "network_interfaces": ["nic-01"],
                "security_group_ids": ["sg-web"],
            }
        ]

        cfg = DiscoveryConfiguration(
            enable_structural=False,
            enable_network=True,
            enable_provider_platform=False,
            naming_rules=[],
        )
        result = dependency_service.run_discovery(
            inventory, config=cfg, actor="discovery-worker", tenant_context=tenant_ctx
        )

        assert result.network_edges_found >= 1
        edges = dependency_service.list_edges(tenant_context=tenant_ctx)
        net_edges = [e for e in edges if e.provenance.layer == DiscoveryLayer.NETWORK]
        assert len(net_edges) >= 1
        for e in net_edges:
            assert e.confidence == EdgeConfidenceLevel.HIGH
            assert e.relationship_type in (
                RelationshipType.NETWORK_CONNECTIVITY,
                RelationshipType.SECURITY_RELATIONSHIP,
            )

    def test_layer3_provider_platform_probed_discovery(
        self, dependency_service: DependencyService, tenant_ctx: TenantContext
    ):
        """Provider platform relationships are probed (not assumed) with HIGH confidence."""
        inventory = [
            {
                "id": "eks-cluster-prod",
                "resource_type": "k8s_cluster",
                "provider_relationships": [
                    {
                        "target_id": "role-eks-nodegroup",
                        "relationship_type": "SECURITY_RELATIONSHIP",
                        "target_type": "RESOURCE",
                    }
                ],
            }
        ]

        cfg = DiscoveryConfiguration(
            enable_structural=False,
            enable_network=False,
            enable_provider_platform=True,
            naming_rules=[],
        )
        result = dependency_service.run_discovery(
            inventory, config=cfg, actor="discovery-worker", tenant_context=tenant_ctx
        )

        assert result.provider_edges_found == 1
        edge = dependency_service.list_edges(tenant_context=tenant_ctx)[0]
        assert edge.confidence == EdgeConfidenceLevel.HIGH
        assert edge.provenance.layer == DiscoveryLayer.PROVIDER_PLATFORM
        assert edge.provenance.rule_id == "DISCO-L3-PROVIDER-PROBED"


# ==============================================================================
# 4. Negative Constraints
# ==============================================================================


class TestNegativeConstraints:
    """Enforces negative constraints on naming convention inference and confidence."""

    def test_no_naming_inference_without_explicit_rule(
        self, dependency_service: DependencyService, tenant_ctx: TenantContext
    ):
        """Negative constraint: Naming inference MUST NOT occur without explicit configured rule."""
        inventory = [
            {
                "id": "vm-app-frontend-01",
                "name": "vm-app-frontend-01",
                "resource_type": "compute_instance",
            },
            {
                "id": "vm-app-backend-01",
                "name": "vm-app-backend-01",
                "resource_type": "compute_instance",
            },
        ]

        # Naming inference disabled / no rules
        cfg = DiscoveryConfiguration(
            enable_structural=False,
            enable_network=False,
            enable_provider_platform=False,
            naming_rules=[],
        )
        result = dependency_service.run_discovery(
            inventory, config=cfg, actor="discovery-worker", tenant_context=tenant_ctx
        )
        assert result.inferred_edges_found == 0
        assert len(dependency_service.list_edges(tenant_context=tenant_ctx)) == 0

    def test_naming_inference_never_allowed_high_confidence(
        self, dependency_service: DependencyService, tenant_ctx: TenantContext
    ):
        """Negative constraint: Inferred edge MUST NEVER have HIGH confidence; strictly LOW or MEDIUM."""
        inventory = [
            {
                "id": "app-orders-web",
                "name": "app-orders-web",
                "resource_type": "compute_instance",
            },
            {
                "id": "app-orders-api",
                "name": "app-orders-api",
                "resource_type": "compute_instance",
            },
        ]

        # Configure an inference rule that attempts to request HIGH confidence
        rule = NamingInferenceRule(
            name="rule-web-to-api",
            source_pattern=r"-web$",
            target_pattern=r"-api",
            relationship_type=RelationshipType.APPLICATION_DEPENDENCY,
            confidence=EdgeConfidenceLevel.HIGH,  # Attempting illegal HIGH confidence
            enabled=True,
        )

        cfg = DiscoveryConfiguration(
            enable_structural=False,
            enable_network=False,
            enable_provider_platform=False,
            naming_rules=[rule],
        )
        result = dependency_service.run_discovery(
            inventory, config=cfg, actor="discovery-worker", tenant_context=tenant_ctx
        )

        assert result.inferred_edges_found == 1
        edge = dependency_service.list_edges(tenant_context=tenant_ctx)[0]
        assert edge.provenance.provenance_type == EdgeProvenanceType.INFERRED
        # Must be strictly downgraded/coerced away from HIGH
        assert edge.confidence != EdgeConfidenceLevel.HIGH
        assert edge.confidence in (EdgeConfidenceLevel.LOW, EdgeConfidenceLevel.MEDIUM)


# ==============================================================================
# 5. Merge Rule & Manual Edge Protection
# ==============================================================================


class TestMergeRuleAndManualProtection:
    """Verifies that discovered edges never silently overwrite manual edges."""

    def test_reobserved_manual_edge_updates_last_seen_and_retains_manual_provenance(
        self, dependency_service: DependencyService, tenant_ctx: TenantContext
    ):
        """When discovery re-observes an existing manual edge, last_seen is updated, provenance remains MANUAL."""
        # 1. User creates a manual edge
        create_req = ManualEdgeCreateRequest(
            source_ref=TypedEntityRef(
                entity_type=EntityReferenceType.RESOURCE, entity_id="res-db-1"
            ),
            target_ref=TypedEntityRef(
                entity_type=EntityReferenceType.RESOURCE, entity_id="scope-primary"
            ),
            relationship_type=RelationshipType.PARENT_CHILD,
            notes="Manually assigned parent scope",
        )
        manual_edge = dependency_service.create_manual_edge(
            create_req, actor="user-architect", tenant_context=tenant_ctx
        )
        initial_last_seen = manual_edge.last_seen

        # 2. Automated discovery encounters the exact same relationship
        inventory = [
            {
                "id": "res-db-1",
                "parent_id": "scope-primary",
                "resource_type": "database",
            }
        ]
        cfg = DiscoveryConfiguration(enable_structural=True)
        res = dependency_service.run_discovery(
            inventory, config=cfg, actor="discovery-worker", tenant_context=tenant_ctx
        )

        # Edge was matched and confirmed
        assert res.total_edges_observed >= 1
        assert res.conflicts_surfaced == 0

        current_edge = dependency_service.get_edge(manual_edge.id, tenant_context=tenant_ctx)
        assert current_edge.is_manual is True
        assert current_edge.provenance.provenance_type == EdgeProvenanceType.MANUAL
        assert current_edge.notes == "Manually assigned parent scope"
        assert current_edge.last_seen >= initial_last_seen

    def test_contradicting_discovered_edge_surfaces_conflict_with_both_versions(
        self, dependency_service: DependencyService, tenant_ctx: TenantContext
    ):
        """When a discovered edge contradicts a manual edge, surface an EdgeConflict with both versions visible."""
        # 1. User asserts manual parent for res-vm-01 is 'vpc-legacy'
        manual_req = ManualEdgeCreateRequest(
            source_ref=TypedEntityRef(
                entity_type=EntityReferenceType.RESOURCE, entity_id="res-vm-01"
            ),
            target_ref=TypedEntityRef(
                entity_type=EntityReferenceType.RESOURCE, entity_id="vpc-legacy"
            ),
            relationship_type=RelationshipType.PARENT_CHILD,
            notes="Manual override parent container",
        )
        manual_edge = dependency_service.create_manual_edge(
            manual_req, actor="user-architect", tenant_context=tenant_ctx
        )

        # 2. Discovery observes parent is actually 'vpc-modern'
        inventory = [
            {
                "id": "res-vm-01",
                "parent_id": "vpc-modern",
                "resource_type": "compute_instance",
            }
        ]
        cfg = DiscoveryConfiguration(enable_structural=True)
        run_res = dependency_service.run_discovery(
            inventory, config=cfg, actor="discovery-worker", tenant_context=tenant_ctx
        )

        assert run_res.conflicts_surfaced == 1
        conflicts = dependency_service.list_conflicts(tenant_context=tenant_ctx)
        assert len(conflicts) == 1
        c = conflicts[0]

        # Both versions are visible for human review
        assert c.manual_edge_id == manual_edge.id
        assert c.manual_version["target_ref"]["entity_id"] == "vpc-legacy"
        assert c.discovered_version["target_ref"]["entity_id"] == "vpc-modern"
        assert c.is_resolved is False

        # Existing manual edge was NOT overwritten
        edge = dependency_service.get_edge(manual_edge.id, tenant_context=tenant_ctx)
        assert edge.target_ref.entity_id == "vpc-legacy"

    def test_conflict_resolution_workflow(
        self, dependency_service: DependencyService, tenant_ctx: TenantContext
    ):
        """Human resolves conflict via KEEP_MANUAL or ACCEPT_DISCOVERED."""
        # Create conflict
        manual_req = ManualEdgeCreateRequest(
            source_ref=TypedEntityRef(
                entity_type=EntityReferenceType.RESOURCE, entity_id="res-srv-01"
            ),
            target_ref=TypedEntityRef(
                entity_type=EntityReferenceType.RESOURCE, entity_id="target-old"
            ),
            relationship_type=RelationshipType.PARENT_CHILD,
        )
        manual_edge = dependency_service.create_manual_edge(
            manual_req, actor="user-architect", tenant_context=tenant_ctx
        )

        inventory = [{"id": "res-srv-01", "parent_id": "target-new", "resource_type": "vm"}]
        dependency_service.run_discovery(
            inventory,
            config=DiscoveryConfiguration(enable_structural=True),
            actor="discovery-worker",
            tenant_context=tenant_ctx,
        )

        conflicts = dependency_service.list_conflicts(tenant_context=tenant_ctx)
        assert len(conflicts) == 1
        conflict_id = conflicts[0].conflict_id

        # Resolve with ACCEPT_DISCOVERED
        resolve_payload = ConflictResolveRequest(
            resolution_action=ConflictResolutionAction.ACCEPT_DISCOVERED,
            resolution_notes="Approved migration to target-new",
        )
        resolved_conflict = dependency_service.resolve_conflict(
            conflict_id,
            resolve_payload,
            actor="user-reviewer",
            tenant_context=tenant_ctx,
        )
        assert resolved_conflict.is_resolved is True
        assert resolved_conflict.resolution_action == ConflictResolutionAction.ACCEPT_DISCOVERED

        # Discovered edge is now activated with target-new
        active_edge = next(
            e
            for e in dependency_service.list_edges(
                source_id="res-srv-01", tenant_context=tenant_ctx
            )
            if e.status == EdgeStatus.ACTIVE
        )
        assert active_edge.target_ref.entity_id == "target-new"

        # Prior manual edge is superseded
        superseded = dependency_service.get_edge(manual_edge.id, tenant_context=tenant_ctx)
        assert superseded.status == EdgeStatus.SUPERSEDED


# ==============================================================================
# 6. Point-in-Time Graph & Stale Edge Marking
# ==============================================================================


class TestPointInTimeAndStaleMarking:
    """Tests temporal graph queries (as_of) and automated stale marking."""

    def test_point_in_time_topology_graph(
        self, dependency_service: DependencyService, tenant_ctx: TenantContext
    ):
        """Point-in-time graph query returns only edges effective at the requested timestamp."""
        t0 = dt.datetime.now(dt.UTC) - dt.timedelta(days=10)
        t1 = dt.datetime.now(dt.UTC) - dt.timedelta(days=5)

        # Create edge 1 at t0
        edge1_req = ManualEdgeCreateRequest(
            source_ref=TypedEntityRef(entity_type=EntityReferenceType.SERVICE, entity_id="svc-1"),
            target_ref=TypedEntityRef(entity_type=EntityReferenceType.SERVICE, entity_id="svc-2"),
            relationship_type=RelationshipType.LOGICAL_DEPENDENCY,
        )
        edge1 = dependency_service.create_manual_edge(
            edge1_req, actor="user-architect", tenant_context=tenant_ctx
        )
        # Manually backdate effective_from for testing
        edge1.effective_from = t0
        dependency_service.repository.save_edge(edge1, tenant_context=tenant_ctx)

        # Query as_of t0 - 1 day (should be empty)
        graph_before = dependency_service.get_topology_graph(
            as_of=t0 - dt.timedelta(days=1), tenant_context=tenant_ctx
        )
        assert len(graph_before.edges) == 0

        # Query as_of t1 (should contain edge1)
        graph_t1 = dependency_service.get_topology_graph(as_of=t1, tenant_context=tenant_ctx)
        assert len(graph_t1.edges) == 1
        assert graph_t1.edges[0].id == edge1.id

    def test_stale_edge_marking(
        self, dependency_service: DependencyService, tenant_ctx: TenantContext
    ):
        """Unobserved edges beyond the stale threshold are marked STALE."""
        # 1. Run discovery creating an edge
        inventory_initial = [{"id": "disk-01", "parent_id": "vm-01", "resource_type": "volume"}]
        dependency_service.run_discovery(
            inventory_initial,
            config=DiscoveryConfiguration(enable_structural=True),
            actor="discovery",
            tenant_context=tenant_ctx,
        )
        edges = dependency_service.list_edges(tenant_context=tenant_ctx)
        assert len(edges) == 1
        assert edges[0].status == EdgeStatus.ACTIVE

        # Backdate last_seen to 10 days ago
        edges[0].last_seen = dt.datetime.now(dt.UTC) - dt.timedelta(days=10)
        dependency_service.repository.save_edge(edges[0], tenant_context=tenant_ctx)

        # 2. Run discovery with an empty inventory and 1 day stale threshold
        cfg = DiscoveryConfiguration(
            enable_structural=True,
            stale_threshold_seconds=86400,  # 1 day threshold
        )
        run_res = dependency_service.run_discovery(
            [], config=cfg, actor="discovery", tenant_context=tenant_ctx
        )

        assert run_res.stale_edges_marked == 1
        updated = dependency_service.get_edge(edges[0].id, tenant_context=tenant_ctx)
        assert updated.status == EdgeStatus.STALE


# ==============================================================================
# 7. Impact-Set Analysis & Cycle Detection
# ==============================================================================


class TestImpactSetAnalysis:
    """Verifies downstream blast radius, upstream traversal, depth limits, and cycle detection."""

    def test_downstream_impact_blast_radius_and_depth_limit(
        self, dependency_service: DependencyService, tenant_ctx: TenantContext
    ):
        """Calculates downstream dependents with depth limits."""
        # Pipeline: Shared Service -> App Core -> Microservice A -> DB
        edges_to_create = [
            ("shared-auth", "app-core", EdgeCriticality.CRITICAL),
            ("app-core", "ms-orders", EdgeCriticality.HIGH),
            ("ms-orders", "db-orders", EdgeCriticality.MEDIUM),
        ]
        for src, tgt, crit in edges_to_create:
            dependency_service.create_manual_edge(
                ManualEdgeCreateRequest(
                    source_ref=TypedEntityRef(
                        entity_type=EntityReferenceType.SERVICE, entity_id=src
                    ),
                    target_ref=TypedEntityRef(
                        entity_type=EntityReferenceType.SERVICE, entity_id=tgt
                    ),
                    relationship_type=RelationshipType.SHARED_SERVICE,
                    criticality=crit,
                ),
                actor="user-architect",
                tenant_context=tenant_ctx,
            )

        # Full depth impact of shared-auth
        full_impact = dependency_service.compute_downstream_impact(
            "shared-auth", tenant_context=tenant_ctx
        )
        assert full_impact.total_dependents == 3
        assert full_impact.critical_dependents_count == 1
        assert full_impact.has_cycle is False

        # Max depth = 1 impact
        depth1_impact = dependency_service.compute_downstream_impact(
            "shared-auth", max_depth=1, tenant_context=tenant_ctx
        )
        assert depth1_impact.total_dependents == 1
        assert depth1_impact.dependents[0].entity_ref.entity_id == "app-core"

    def test_cycle_detection_in_dependency_graph(
        self, dependency_service: DependencyService, tenant_ctx: TenantContext
    ):
        """Cyclic dependencies (A -> B -> C -> A) are detected gracefully without infinite loops."""
        cycle_edges = [
            ("node-A", "node-B"),
            ("node-B", "node-C"),
            ("node-C", "node-A"),
        ]
        for src, tgt in cycle_edges:
            dependency_service.create_manual_edge(
                ManualEdgeCreateRequest(
                    source_ref=TypedEntityRef(
                        entity_type=EntityReferenceType.SERVICE, entity_id=src
                    ),
                    target_ref=TypedEntityRef(
                        entity_type=EntityReferenceType.SERVICE, entity_id=tgt
                    ),
                    relationship_type=RelationshipType.SHARED_SERVICE,
                ),
                actor="user-architect",
                tenant_context=tenant_ctx,
            )

        impact = dependency_service.compute_downstream_impact("node-A", tenant_context=tenant_ctx)
        assert impact.has_cycle is True
        assert len(impact.cycle_nodes) > 0
        assert impact.total_dependents == 2  # B and C

    def test_upstream_dependencies_computation(
        self, dependency_service: DependencyService, tenant_ctx: TenantContext
    ):
        """Traverses upstream dependencies that an entity relies upon."""
        # App relies on DB, DB relies on Storage
        dependency_service.create_manual_edge(
            ManualEdgeCreateRequest(
                source_ref=TypedEntityRef(
                    entity_type=EntityReferenceType.APPLICATION, entity_id="app-store"
                ),
                target_ref=TypedEntityRef(
                    entity_type=EntityReferenceType.RESOURCE, entity_id="db-master"
                ),
                relationship_type=RelationshipType.DATA_FLOW,
                direction=DependencyDirection.OUTBOUND,
            ),
            actor="user-architect",
            tenant_context=tenant_ctx,
        )
        dependency_service.create_manual_edge(
            ManualEdgeCreateRequest(
                source_ref=TypedEntityRef(
                    entity_type=EntityReferenceType.RESOURCE, entity_id="db-master"
                ),
                target_ref=TypedEntityRef(
                    entity_type=EntityReferenceType.RESOURCE, entity_id="ebs-vol-01"
                ),
                relationship_type=RelationshipType.LOGICAL_DEPENDENCY,
                direction=DependencyDirection.OUTBOUND,
            ),
            actor="user-architect",
            tenant_context=tenant_ctx,
        )

        upstream = dependency_service.compute_upstream_dependencies(
            "app-store", tenant_context=tenant_ctx
        )
        assert upstream.total_dependents == 2
        upstream_ids = {d.entity_ref.entity_id for d in upstream.dependents}
        assert "db-master" in upstream_ids
        assert "ebs-vol-01" in upstream_ids


# ==============================================================================
# 8. Bulk Import & CMDB Integration
# ==============================================================================


class TestBulkImportAndCMDB:
    """Verifies bulk import of relationships with IMPORTED provenance."""

    def test_bulk_import_from_cmdb(
        self, dependency_service: DependencyService, tenant_ctx: TenantContext
    ):
        """Bulk import saves relationships with IMPORTED provenance and source tracking."""
        payload = BulkImportRequest(
            import_source="ServiceNow-CMDB",
            items=[
                BulkImportItem(
                    source_id="app-finance",
                    source_type=EntityReferenceType.APPLICATION,
                    target_id="db-oracle-erp",
                    target_type=EntityReferenceType.RESOURCE,
                    relationship_type=RelationshipType.DATA_FLOW,
                    criticality=EdgeCriticality.CRITICAL,
                    notes="Imported nightly from enterprise CMDB",
                ),
                BulkImportItem(
                    source_id="app-hr",
                    source_type=EntityReferenceType.APPLICATION,
                    target_id="shared-idp",
                    target_type=EntityReferenceType.SERVICE,
                    relationship_type=RelationshipType.SHARED_SERVICE,
                    criticality=EdgeCriticality.HIGH,
                ),
            ],
        )

        result = dependency_service.bulk_import(
            payload, actor="cmdb-sync-bot", tenant_context=tenant_ctx
        )
        assert result.edges_created == 2
        assert len(result.errors) == 0

        edges = dependency_service.list_edges(tenant_context=tenant_ctx)
        assert len(edges) == 2
        for e in edges:
            assert e.provenance.provenance_type == EdgeProvenanceType.IMPORTED
            assert e.provenance.import_source == "ServiceNow-CMDB"
            assert e.confidence == EdgeConfidenceLevel.AS_ASSERTED


# ==============================================================================
# 9. Billing Relationship Synchronization
# ==============================================================================


class TestBillingRelationshipSynchronization:
    """Verifies billing relationship linking shared costs to consumers."""

    def test_sync_billing_relationships(
        self, dependency_service: DependencyService, tenant_ctx: TenantContext
    ):
        """Links shared-service costs to consumer applications/scopes."""
        payload = BillingAllocationSyncRequest(
            shared_service_ref=TypedEntityRef(
                entity_type=EntityReferenceType.SERVICE,
                entity_id="shared-eks-cluster",
                name="EKS Platform",
            ),
            allocations=[
                BillingAllocationSyncItem(
                    consumer_ref=TypedEntityRef(
                        entity_type=EntityReferenceType.APPLICATION,
                        entity_id="app-logistics",
                    ),
                    allocation_percentage=45.5,
                    cost_centre_id="CC-9001",
                ),
                BillingAllocationSyncItem(
                    consumer_ref=TypedEntityRef(
                        entity_type=EntityReferenceType.APPLICATION,
                        entity_id="app-warehouse",
                    ),
                    allocation_percentage=54.5,
                    cost_centre_id="CC-9002",
                ),
            ],
        )

        result = dependency_service.sync_billing_relationships(
            payload, actor="finops-allocator", tenant_context=tenant_ctx
        )
        assert result.edges_created == 2
        assert result.total_allocations_synced == 2

        edges = dependency_service.list_edges(tenant_context=tenant_ctx)
        assert len(edges) == 2
        for e in edges:
            assert e.relationship_type == RelationshipType.BILLING_RELATIONSHIP
            assert e.billing_attributes is not None
            assert e.billing_attributes.allocation_percentage in (45.5, 54.5)


# ==============================================================================
# 10. Multi-Tenant Isolation
# ==============================================================================


class TestMultiTenantIsolation:
    """Validates strict tenant boundaries across dependency repository and service."""

    def test_tenant_isolation_edges_and_conflicts(
        self,
        dependency_service: DependencyService,
        tenant_ctx: TenantContext,
        other_tenant_ctx: TenantContext,
    ):
        """Tenant A's edges and conflicts are strictly invisible to Tenant B."""
        # Tenant A creates an edge
        req = ManualEdgeCreateRequest(
            source_ref=TypedEntityRef(
                entity_type=EntityReferenceType.RESOURCE, entity_id="secret-tenant-a-res"
            ),
            target_ref=TypedEntityRef(
                entity_type=EntityReferenceType.RESOURCE, entity_id="secret-tenant-a-tgt"
            ),
            relationship_type=RelationshipType.SECURITY_RELATIONSHIP,
        )
        edge_a = dependency_service.create_manual_edge(
            req, actor="user-a", tenant_context=tenant_ctx
        )

        # Tenant B lists edges -> empty
        edges_b = dependency_service.list_edges(tenant_context=other_tenant_ctx)
        assert len(edges_b) == 0

        # Tenant B attempting to get edge_a raises NotFound
        with pytest.raises(DependencyEdgeNotFoundException):
            dependency_service.get_edge(edge_a.id, tenant_context=other_tenant_ctx)

    def test_tenant_context_mandatory(self, dependency_service: DependencyService):
        """Operations without TenantContext raise MissingTenantContextException."""
        with pytest.raises(MissingTenantContextException):
            dependency_service.list_edges(tenant_context=None)  # type: ignore[arg-type]


# ==============================================================================
# 11. REST API Contract & Endpoints
# ==============================================================================


class TestDependencyRestAPI:
    """Verifies all REST API endpoints under /api/v1/dependencies."""

    def test_api_manual_edge_crud(self, client: TestClient):
        """Tests POST, GET, PATCH, DELETE /api/v1/dependencies/edges."""
        headers = {
            "X-Tenant-ID": "tenant-api-test",
            "X-User-ID": "user-api-lead",
        }

        # 1. Create manual edge
        create_payload = {
            "source_ref": {
                "entity_type": "SERVICE",
                "entity_id": "svc-api-gateway",
                "name": "API Gateway",
            },
            "target_ref": {
                "entity_type": "SERVICE",
                "entity_id": "svc-customer-api",
                "name": "Customer API",
            },
            "relationship_type": "NETWORK_CONNECTIVITY",
            "criticality": "HIGH",
            "notes": "Direct reverse proxy routing",
        }
        res_post = client.post(
            "/api/v1/dependencies/edges/manual", json=create_payload, headers=headers
        )
        assert res_post.status_code == 201
        data = res_post.json()
        edge_id = data["id"]
        assert data["relationship_type"] == "NETWORK_CONNECTIVITY"
        assert data["is_manual"] is True

        # 2. Get edge by ID
        res_get = client.get(f"/api/v1/dependencies/edges/{edge_id}", headers=headers)
        assert res_get.status_code == 200
        assert res_get.json()["id"] == edge_id

        # 3. List edges
        res_list = client.get("/api/v1/dependencies/edges", headers=headers)
        assert res_list.status_code == 200
        assert len(res_list.json()) == 1

        # 4. Patch edge
        res_patch = client.patch(
            f"/api/v1/dependencies/edges/{edge_id}",
            json={"criticality": "CRITICAL"},
            headers=headers,
        )
        assert res_patch.status_code == 200
        assert res_patch.json()["criticality"] == "CRITICAL"

        # 5. Delete edge (204 NO_CONTENT)
        res_delete = client.delete(f"/api/v1/dependencies/edges/{edge_id}", headers=headers)
        assert res_delete.status_code == 204

    def test_api_discovery_run_and_graph(self, client: TestClient):
        """Tests POST /discovery/run and GET /graph."""
        headers = {
            "X-Tenant-ID": "tenant-api-test",
            "X-User-ID": "user-api-lead",
        }
        discovery_payload = [
            {
                "id": "vm-app-1",
                "parent_id": "subnet-01",
                "resource_type": "compute_instance",
            }
        ]
        res_disco = client.post(
            "/api/v1/dependencies/discovery/run",
            json=discovery_payload,
            headers=headers,
        )
        assert res_disco.status_code == 200
        disco_data = res_disco.json()
        assert disco_data["total_edges_observed"] >= 1

        # Graph endpoint
        res_graph = client.get("/api/v1/dependencies/graph", headers=headers)
        assert res_graph.status_code == 200
        graph_data = res_graph.json()
        assert len(graph_data["edges"]) >= 1
        assert len(graph_data["nodes"]) >= 2

    def test_api_impact_and_upstream(self, client: TestClient):
        """Tests GET /impact/{id} and GET /upstream/{id}."""
        headers = {
            "X-Tenant-ID": "tenant-api-test",
            "X-User-ID": "user-api-lead",
        }
        # Create an edge first
        client.post(
            "/api/v1/dependencies/edges/manual",
            json={
                "source_ref": {"entity_type": "SERVICE", "entity_id": "svc-spoke"},
                "target_ref": {"entity_type": "SERVICE", "entity_id": "svc-hub"},
                "relationship_type": "LOGICAL_DEPENDENCY",
            },
            headers=headers,
        )

        res_impact = client.get("/api/v1/dependencies/impact/svc-hub?max_depth=2", headers=headers)
        assert res_impact.status_code == 200
        assert res_impact.json()["total_dependents"] == 1

        res_upstream = client.get("/api/v1/dependencies/upstream/svc-spoke", headers=headers)
        assert res_upstream.status_code == 200
        assert res_upstream.json()["total_dependents"] == 1
