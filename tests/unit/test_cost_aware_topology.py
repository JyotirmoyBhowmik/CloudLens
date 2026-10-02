"""Comprehensive Unit and Integration Tests for Cost-Aware Topology Service (Prompt 33).

Enforces:
- Master brief Sections 21-22; BBP Section 25 (views, encoding, interaction).
- Eight Canonical Views:
  - SERVICE_DEPENDENCY (root: SERVICE, default depth: 3)
  - APPLICATION_DEPENDENCY (root: APPLICATION, default depth: 4)
  - ACCOUNT_TOPOLOGY (root: SCOPE, default depth: 2)
  - SUBSCRIPTION_TOPOLOGY (root: SCOPE, default depth: 2)
  - PROJECT_TOPOLOGY (root: SCOPE, default depth: 2)
  - COMPARTMENT_TOPOLOGY (root: SCOPE, default depth: 2)
  - RESOURCE_RELATIONSHIP (root: RESOURCE, default depth: 2)
  - COST_AWARE_DEPENDENCY (root: any, default depth: 3, with visual spend overlay)
- Full Node Enrichment:
  - status, period cost, budget utilisation, runtime state, usage metrics,
    threshold badge, cost trend, forecast, pricing classification, owner, provider.
- Chain Cost Decomposition:
  - Root spend decomposed across load balancer, compute, database, backup.
  - Per-node share visible and verifiable.
- Shared Service Apportionment:
  - Shared service consumed by 3 applications is NOT double/triple counted in portfolio aggregation.
  - Formula strictly follows BILLING_RELATIONSHIP attributes and FinOps allocation rules.
- Restricted Node Rule:
  - Unentitled nodes render as Restricted placeholders rather than being omitted.
  - Graph topology and edge connectivity preserved.
- Graph Clustering & Sub-2.0s Performance:
  - 500-node graph projects and clusters in < 2.0 seconds.
- Multi-format Graph Export:
  - JSON, CSV, GraphML, DOT, and SVG vector graphics with visual cost encoding.
- Multi-Tenant Isolation & REST API contract validation.
"""

from __future__ import annotations

import datetime as dt
import time
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from api.cloudlens_api.main import app
from domain.dependency.models import (
    BillingAttributes,
    DependencyEdge,
    EdgeProvenance,
    TypedEntityRef,
)
from domain.dependency.repository import (
    DependencyRepository,
    reset_dependency_repository,
)
from domain.models.enums import (
    DependencyDirection,
    DiscoveryLayer,
    EdgeConfidenceLevel,
    EdgeCriticality,
    EdgeProvenanceType,
    EdgeStatus,
    EntityReferenceType,
    FinancialSensitivity,
    GranteeType,
    GrantEffect,
    GraphExportFormat,
    NodeCostTrend,
    NodeScheduleState,
    RelationshipType,
    ThresholdBadge,
    TopologyBudgetStatus,
    TopologyPricingClassification,
    TopologyViewType,
)
from domain.rbac.models import ScopeGrant
from domain.tenant.context import TenantContext
from domain.topology.models import (
    GraphExportRequest,
    MultiChainAggregationRequest,
    TopologyProjectionRequest,
)
from domain.topology.projection import VIEW_DEFAULT_DEPTHS
from domain.topology.service import (
    TopologyService,
    reset_topology_service,
)

# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture(autouse=True)
def cleanup_topology_state():
    """Ensures clean state between tests."""
    reset_dependency_repository()
    reset_topology_service()
    yield
    reset_dependency_repository()
    reset_topology_service()


@pytest.fixture
def tenant_ctx() -> TenantContext:
    """Standard primary tenant context."""
    return TenantContext(
        tenant_id="tenant-acme",
        user_id="user-architect",
        correlation_id=str(uuid.uuid4()),
        roles=["ENGINEER"],
    )


@pytest.fixture
def other_tenant_ctx() -> TenantContext:
    """Secondary tenant context for isolation verification."""
    return TenantContext(
        tenant_id="tenant-competitor",
        user_id="user-rogue",
        correlation_id=str(uuid.uuid4()),
        roles=["ENGINEER"],
    )


@pytest.fixture
def topology_service() -> TopologyService:
    """Returns a fresh TopologyService."""
    return TopologyService()


@pytest.fixture
def client() -> TestClient:
    """FastAPI TestClient fixture."""
    return TestClient(app)


# Helper function to seed an enterprise application topology
def seed_ecommerce_topology(
    dep_repo: DependencyRepository,
    tc: TenantContext,
) -> dict[str, TypedEntityRef]:
    """Sets up e-commerce application dependency graph with shared services."""
    now = dt.datetime.now(dt.UTC)

    refs = {
        "app_checkout": TypedEntityRef(
            entity_type=EntityReferenceType.APPLICATION,
            entity_id="app-checkout",
            name="Checkout Application",
        ),
        "svc_web": TypedEntityRef(
            entity_type=EntityReferenceType.SERVICE,
            entity_id="svc-web-gateway",
            name="Web Gateway",
        ),
        "res_ec2": TypedEntityRef(
            entity_type=EntityReferenceType.RESOURCE,
            entity_id="res-compute-01",
            name="App Servers ASG",
        ),
        "res_rds": TypedEntityRef(
            entity_type=EntityReferenceType.RESOURCE,
            entity_id="res-rds-postgres",
            name="Checkout Database",
        ),
        "res_s3_backup": TypedEntityRef(
            entity_type=EntityReferenceType.RESOURCE,
            entity_id="res-s3-backup",
            name="Nightly Backup Bucket",
        ),
        # Shared platform services
        "svc_shared_auth": TypedEntityRef(
            entity_type=EntityReferenceType.SERVICE,
            entity_id="svc-shared-auth",
            name="Enterprise SSO/Auth Service",
        ),
        "svc_shared_logging": TypedEntityRef(
            entity_type=EntityReferenceType.SERVICE,
            entity_id="svc-shared-logging",
            name="Centralized OpenSearch Logging",
        ),
    }

    edges_data = [
        # Checkout App -> Web Gateway
        (
            "app_checkout",
            "svc_web",
            RelationshipType.APPLICATION_DEPENDENCY,
            DependencyDirection.OUTBOUND,
            None,
        ),
        # Web Gateway -> Compute
        (
            "svc_web",
            "res_ec2",
            RelationshipType.LOGICAL_DEPENDENCY,
            DependencyDirection.OUTBOUND,
            None,
        ),
        # Compute -> Database
        ("res_ec2", "res_rds", RelationshipType.DATA_FLOW, DependencyDirection.OUTBOUND, None),
        # Database -> S3 Backup
        (
            "res_rds",
            "res_s3_backup",
            RelationshipType.DATA_FLOW,
            DependencyDirection.OUTBOUND,
            None,
        ),
        # App -> Shared SSO (50% share)
        (
            "app_checkout",
            "svc_shared_auth",
            RelationshipType.SHARED_SERVICE,
            DependencyDirection.OUTBOUND,
            BillingAttributes(allocation_rule="SHARED_SERVICE_RATIO", allocation_percentage=50.0),
        ),
        # App -> Shared Logging (40% share)
        (
            "app_checkout",
            "svc_shared_logging",
            RelationshipType.SHARED_SERVICE,
            DependencyDirection.OUTBOUND,
            BillingAttributes(allocation_rule="SHARED_SERVICE_RATIO", allocation_percentage=40.0),
        ),
    ]

    for s_key, t_key, rel_type, direction, billing in edges_data:
        edge = DependencyEdge(
            id=f"edge-{s_key}-{t_key}",
            tenant_id=tc.tenant_id,
            source_ref=refs[s_key],
            target_ref=refs[t_key],
            relationship_type=rel_type,
            direction=direction,
            provenance=EdgeProvenance(
                provenance_type=EdgeProvenanceType.MANUAL,
                actor_id=tc.user_id,
                layer=DiscoveryLayer.CURATED_APPLICATION,
                created_at=now,
            ),
            confidence=EdgeConfidenceLevel.HIGH,
            criticality=EdgeCriticality.CRITICAL,
            status=EdgeStatus.ACTIVE,
            billing_attributes=billing,
            first_seen=now,
            last_seen=now,
        )
        dep_repo.save_edge(edge, tenant_context=tc)

    return refs


# ==============================================================================
# 1. Master Data & Canonical Views Verification
# ==============================================================================


class TestMasterDataAndCanonicalViews:
    """Verifies all eight canonical topology views in master data and default settings."""

    def test_eight_canonical_views_exist_in_masterdata(self):
        """Verifies TOPOLOGY_VIEW seed file contains all eight views with root types & depths."""
        from masterdata.registry import SYSTEM_MASTER_REGISTRY

        assert "TOPOLOGY_VIEW" in SYSTEM_MASTER_REGISTRY
        metadata = SYSTEM_MASTER_REGISTRY["TOPOLOGY_VIEW"]
        assert Path(metadata.seed_file).exists()

        expected_views = {
            "SERVICE_DEPENDENCY",
            "APPLICATION_DEPENDENCY",
            "ACCOUNT_TOPOLOGY",
            "SUBSCRIPTION_TOPOLOGY",
            "PROJECT_TOPOLOGY",
            "COMPARTMENT_TOPOLOGY",
            "RESOURCE_RELATIONSHIP",
            "COST_AWARE_DEPENDENCY",
        }
        enum_views = {v.value for v in TopologyViewType}
        assert expected_views.issubset(enum_views)

    def test_default_depths_match_specification(self):
        """Verifies canonical default traversal depths match BBP Section 25."""
        assert VIEW_DEFAULT_DEPTHS[TopologyViewType.SERVICE_DEPENDENCY] == (
            EntityReferenceType.SERVICE,
            3,
        )
        assert VIEW_DEFAULT_DEPTHS[TopologyViewType.APPLICATION_DEPENDENCY] == (
            EntityReferenceType.APPLICATION,
            4,
        )
        assert VIEW_DEFAULT_DEPTHS[TopologyViewType.ACCOUNT_TOPOLOGY] == (
            EntityReferenceType.SCOPE,
            2,
        )
        assert VIEW_DEFAULT_DEPTHS[TopologyViewType.SUBSCRIPTION_TOPOLOGY] == (
            EntityReferenceType.SCOPE,
            2,
        )
        assert VIEW_DEFAULT_DEPTHS[TopologyViewType.PROJECT_TOPOLOGY] == (
            EntityReferenceType.SCOPE,
            2,
        )
        assert VIEW_DEFAULT_DEPTHS[TopologyViewType.COMPARTMENT_TOPOLOGY] == (
            EntityReferenceType.SCOPE,
            2,
        )
        assert VIEW_DEFAULT_DEPTHS[TopologyViewType.RESOURCE_RELATIONSHIP] == (
            EntityReferenceType.RESOURCE,
            2,
        )
        assert VIEW_DEFAULT_DEPTHS[TopologyViewType.COST_AWARE_DEPENDENCY] == (None, 3)


# ==============================================================================
# 2. Node Enrichment Verification
# ==============================================================================


class TestNodeEnrichment:
    """Tests operational, threshold, and FinOps telemetry population on graph nodes."""

    def test_enrichment_carries_all_telemetry_dimensions(
        self, topology_service: TopologyService, tenant_ctx: TenantContext
    ):
        """Node carries status, cost, budget utilisation, runtime state, usage, and badges."""
        ref = TypedEntityRef(
            entity_type=EntityReferenceType.RESOURCE,
            entity_id="res-rds-postgres",
            name="Checkout DB",
        )

        custom_telemetry = {
            "cost": Decimal("2450.75"),
            "status": "RUNNING",
            "budget_utilisation_pct": 92.5,
            "runtime_state": NodeScheduleState.RUNNING_ON_SCHEDULE,
            "usage": {"cpu_utilization": 68.4, "memory_utilization": 82.1},
            "threshold_state": ThresholdBadge.AMBER,
            "cost_trend": NodeCostTrend.UP,
            "cost_trend_pct": 14.2,
            "pricing_classification": TopologyPricingClassification.RESERVED,
            "owner": "Data Platform Team",
            "provider": "aws",
        }

        enrichment = topology_service.enrichment_service.enrich_node(
            ref,
            custom_telemetry=custom_telemetry,
            tenant_context=tenant_ctx,
        )

        assert enrichment.status == "RUNNING"
        assert enrichment.cost == Decimal("2450.75")
        assert enrichment.budget_utilisation_pct == 92.5
        assert enrichment.budget_status == TopologyBudgetStatus.WARN
        assert enrichment.threshold_state == ThresholdBadge.AMBER
        assert enrichment.cost_trend == NodeCostTrend.UP
        assert enrichment.cost_trend_pct == 14.2
        assert enrichment.pricing_classification == TopologyPricingClassification.RESERVED
        assert enrichment.owner == "Data Platform Team"
        assert enrichment.provider == "aws"
        assert enrichment.usage["cpu_utilization"] == 68.4

    def test_threshold_badge_auto_derivation_from_budget(
        self, topology_service: TopologyService, tenant_ctx: TenantContext
    ):
        """Threshold badge automatically triggers RED if budget utilisation >= 100%."""
        ref = TypedEntityRef(
            entity_type=EntityReferenceType.SERVICE,
            entity_id="svc-ai-inference",
            name="LLM Inference Gateway",
        )

        enrichment = topology_service.enrichment_service.enrich_node(
            ref,
            custom_telemetry={"cost": Decimal("10000.00"), "budget_utilisation_pct": 125.0},
            tenant_context=tenant_ctx,
        )
        assert enrichment.budget_status == TopologyBudgetStatus.BREACH
        assert enrichment.threshold_state == ThresholdBadge.RED


# ==============================================================================
# 3. Chain Cost Decomposition & Aggregation
# ==============================================================================


class TestChainCostDecomposition:
    """Verifies that dependency chain spend is accurately decomposed across nodes."""

    def test_application_chain_cost_decomposed_across_nodes(
        self, topology_service: TopologyService, tenant_ctx: TenantContext
    ):
        """Checkout application decomposed across web gateway, compute, db, and storage."""
        seed_ecommerce_topology(topology_service.dep_repo, tenant_ctx)

        custom_costs = {
            "app-checkout": Decimal("50.00"),
            "svc-web-gateway": Decimal("200.00"),
            "res-compute-01": Decimal("1500.00"),
            "res-rds-postgres": Decimal("2400.00"),
            "res-s3-backup": Decimal("100.00"),
            "svc-shared-auth": Decimal("1000.00"),  # 50% = 500.00
            "svc-shared-logging": Decimal("800.00"),  # 40% = 320.00
        }

        decomp = topology_service.calculate_chain_cost(
            "app-checkout",
            root_entity_type=EntityReferenceType.APPLICATION,
            custom_node_costs=custom_costs,
            tenant_context=tenant_ctx,
        )

        # Expected:
        # Direct root: 50.00
        # Downstream:
        # svc-web: 200.00
        # res-compute-01: 1500.00
        # res-rds-postgres: 2400.00
        # res-s3-backup: 100.00
        # svc-shared-auth (50%): 500.00
        # svc-shared-logging (40%): 320.00
        # Total Downstream = 200 + 1500 + 2400 + 100 + 500 + 320 = 5020.00
        # Total Chain Cost = 50.00 + 5020.00 = 5070.00
        assert decomp.direct_root_cost == Decimal("50.00")
        assert decomp.attributed_downstream_cost == Decimal("5020.00")
        assert decomp.total_chain_cost == Decimal("5070.00")

        # Contributing nodes checks
        nodes_by_id = {n.entity_id: n for n in decomp.contributing_nodes}
        assert "svc-web-gateway" in nodes_by_id
        assert nodes_by_id["svc-web-gateway"].effective_contributed_cost == Decimal("200.00")

        assert "res-rds-postgres" in nodes_by_id
        assert nodes_by_id["res-rds-postgres"].effective_contributed_cost == Decimal("2400.00")
        assert nodes_by_id["res-rds-postgres"].cost_share_percentage == pytest.approx(
            47.34, rel=1e-2
        )

        # Shared services breakdown
        assert len(decomp.shared_services_included) == 2
        shared_by_id = {s.service_id: s for s in decomp.shared_services_included}
        assert shared_by_id["svc-shared-auth"].apportioned_cost_to_this_chain == Decimal("500.00")
        assert shared_by_id["svc-shared-logging"].apportioned_cost_to_this_chain == Decimal(
            "320.00"
        )

    def test_cycle_detection_prevents_infinite_recursion(
        self, topology_service: TopologyService, tenant_ctx: TenantContext
    ):
        """Circular dependencies between nodes do not cause infinite recursion."""
        now = dt.datetime.now(dt.UTC)
        app_ref = TypedEntityRef(
            entity_type=EntityReferenceType.APPLICATION, entity_id="app-a", name="App A"
        )
        svc_b = TypedEntityRef(
            entity_type=EntityReferenceType.SERVICE, entity_id="svc-b", name="Service B"
        )
        svc_c = TypedEntityRef(
            entity_type=EntityReferenceType.SERVICE, entity_id="svc-c", name="Service C"
        )

        edges = [
            (app_ref, svc_b),
            (svc_b, svc_c),
            (svc_c, svc_b),  # Cycle: B -> C -> B
        ]
        for s, t in edges:
            edge = DependencyEdge(
                id=f"edge-{s.entity_id}-{t.entity_id}",
                tenant_id=tenant_ctx.tenant_id,
                source_ref=s,
                target_ref=t,
                relationship_type=RelationshipType.APPLICATION_DEPENDENCY,
                direction=DependencyDirection.OUTBOUND,
                provenance=EdgeProvenance(
                    provenance_type=EdgeProvenanceType.MANUAL,
                    actor_id=tenant_ctx.user_id,
                    layer=DiscoveryLayer.CURATED_APPLICATION,
                    created_at=now,
                ),
                confidence=EdgeConfidenceLevel.HIGH,
                criticality=EdgeCriticality.HIGH,
                status=EdgeStatus.ACTIVE,
                first_seen=now,
                last_seen=now,
            )
            topology_service.dep_repo.save_edge(edge, tenant_context=tenant_ctx)

        decomp = topology_service.calculate_chain_cost(
            "app-a",
            custom_node_costs={
                "app-a": Decimal("10"),
                "svc-b": Decimal("20"),
                "svc-c": Decimal("30"),
            },
            tenant_context=tenant_ctx,
        )
        # Should complete successfully and visit each node once
        assert decomp.total_chain_cost == Decimal("60.00")
        assert len(decomp.contributing_nodes) == 2


# ==============================================================================
# 4. Shared Service Apportionment & Multi-Chain Portfolio Aggregation
# ==============================================================================


class TestSharedServiceApportionment:
    """Verifies that a shared service consumed across multiple chains is NEVER double-counted."""

    def test_shared_service_consumed_by_three_apps_not_triple_counted(
        self, topology_service: TopologyService, tenant_ctx: TenantContext
    ):
        """Shared Elasticsearch cluster (spend $10,000) consumed by 3 apps (50%, 30%, 20%).

        Sum of portfolio equals exactly the sum of dedicated resources plus $10,000,
        never $30,000!
        """
        now = dt.datetime.now(dt.UTC)
        shared_es = TypedEntityRef(
            entity_type=EntityReferenceType.SERVICE,
            entity_id="svc-shared-es",
            name="Shared Elasticsearch Cluster",
        )

        app1 = TypedEntityRef(
            entity_type=EntityReferenceType.APPLICATION, entity_id="app-1", name="App 1"
        )
        app2 = TypedEntityRef(
            entity_type=EntityReferenceType.APPLICATION, entity_id="app-2", name="App 2"
        )
        app3 = TypedEntityRef(
            entity_type=EntityReferenceType.APPLICATION, entity_id="app-3", name="App 3"
        )

        apps_and_shares = [
            (app1, Decimal("50.0")),
            (app2, Decimal("30.0")),
            (app3, Decimal("20.0")),
        ]

        for app_ref, share_pct in apps_and_shares:
            edge = DependencyEdge(
                id=f"edge-{app_ref.entity_id}-shared-es",
                tenant_id=tenant_ctx.tenant_id,
                source_ref=app_ref,
                target_ref=shared_es,
                relationship_type=RelationshipType.SHARED_SERVICE,
                direction=DependencyDirection.OUTBOUND,
                provenance=EdgeProvenance(
                    provenance_type=EdgeProvenanceType.MANUAL,
                    actor_id=tenant_ctx.user_id,
                    layer=DiscoveryLayer.CURATED_APPLICATION,
                    created_at=now,
                ),
                confidence=EdgeConfidenceLevel.HIGH,
                criticality=EdgeCriticality.CRITICAL,
                status=EdgeStatus.ACTIVE,
                billing_attributes=BillingAttributes(
                    allocation_rule="SHARED_SERVICE_RATIO",
                    allocation_percentage=float(share_pct),
                ),
                first_seen=now,
                last_seen=now,
            )
            topology_service.dep_repo.save_edge(edge, tenant_context=tenant_ctx)

        custom_costs = {
            "app-1": Decimal("1000.00"),
            "app-2": Decimal("2000.00"),
            "app-3": Decimal("3000.00"),
            "svc-shared-es": Decimal("10000.00"),
        }

        # Multi-chain aggregation request
        req = MultiChainAggregationRequest(root_entity_ids=["app-1", "app-2", "app-3"])
        res = topology_service.aggregate_multi_chain(
            req,
            custom_node_costs=custom_costs,
            tenant_context=tenant_ctx,
        )

        # Expected chain totals:
        # App 1: 1000 + 5000 = 6000
        # App 2: 2000 + 3000 = 5000
        # App 3: 3000 + 2000 = 5000
        assert res.chain_totals["app-1"] == Decimal("6000.00")
        assert res.chain_totals["app-2"] == Decimal("5000.00")
        assert res.chain_totals["app-3"] == Decimal("5000.00")

        # Portfolio Total = 1000 + 2000 + 3000 + 10000 (shared ES once) = 16000.00
        assert res.total_portfolio_cost == Decimal("16000.00")
        assert res.sum_of_chains_matches_portfolio is True
        assert len(res.shared_services_deduplicated) == 1
        assert res.shared_services_deduplicated[0].total_service_cost == Decimal("10000.00")
        assert res.shared_services_deduplicated[0].consumers_count == 3


# ==============================================================================
# 5. Restricted Node Rule (Privacy & Masking)
# ==============================================================================


class TestRestrictedNodeEvaluation:
    """Verifies that unentitled nodes render as Restricted placeholders and are NEVER omitted."""

    def test_restricted_node_renders_placeholder_retaining_edges(
        self, topology_service: TopologyService, tenant_ctx: TenantContext
    ):
        """Database node is restricted under RBAC; must render as [Restricted Resource] with masked cost."""
        seed_ecommerce_topology(topology_service.dep_repo, tenant_ctx)

        # Create scope grants: allow access to everything EXCEPT the database resource
        deny_grant = ScopeGrant(
            id="grant-deny-db",
            tenant_id=tenant_ctx.tenant_id,
            grantee_type=GranteeType.USER,
            grantee_id=tenant_ctx.user_id,
            effect=GrantEffect.DENY,
            resource_exceptions=["res-rds-postgres"],
            financial_sensitivity=FinancialSensitivity.NON_FINANCIAL,
        )
        allow_all_grant = ScopeGrant(
            id="grant-allow-all",
            tenant_id=tenant_ctx.tenant_id,
            grantee_type=GranteeType.USER,
            grantee_id=tenant_ctx.user_id,
            effect=GrantEffect.ALLOW,
            providers=["*"],
            financial_sensitivity=FinancialSensitivity.FULL_FINANCIAL_DETAIL,
        )

        req = TopologyProjectionRequest(
            view_type=TopologyViewType.APPLICATION_DEPENDENCY,
            root_entity_id="app-checkout",
            max_depth=4,
        )

        custom_costs = {
            "app-checkout": Decimal("50.00"),
            "svc-web-gateway": Decimal("200.00"),
            "res-compute-01": Decimal("1500.00"),
            "res-rds-postgres": Decimal("2400.00"),
            "res-s3-backup": Decimal("100.00"),
            "svc-shared-auth": Decimal("1000.00"),
            "svc-shared-logging": Decimal("800.00"),
        }

        # Project view with caller grants
        view = topology_service.project_view(
            req,
            grants=[deny_grant, allow_all_grant],
            custom_node_costs=custom_costs,
            tenant_context=tenant_ctx,
        )

        assert view.restricted_nodes_count >= 1

        # The restricted node must still exist in the graph!
        nodes_by_id = {n.id: n for n in view.nodes}
        assert "res-rds-postgres" in nodes_by_id
        db_node = nodes_by_id["res-rds-postgres"]

        assert db_node.is_restricted is True
        assert db_node.display_name == "[Restricted Resource]"
        assert db_node.direct_cost == Decimal("0.0")  # Masked spend
        assert db_node.enrichment is not None
        assert db_node.enrichment.status == "RESTRICTED"

        # Edges connected to the restricted node must still exist, marked as is_restricted
        edges_to_db = [
            e
            for e in view.edges
            if e.target_id == "res-rds-postgres" or e.source_id == "res-rds-postgres"
        ]
        assert len(edges_to_db) > 0
        assert all(e.is_restricted for e in edges_to_db)


# ==============================================================================
# 6. Graph Clustering & Performance Limit (< 2.0s for 500+ nodes)
# ==============================================================================


class TestGraphClusteringAndPerformance:
    """Verifies sub-2.0s projection on 500-node topology and automatic leaf clustering."""

    def test_500_nodes_project_and_cluster_under_two_seconds(
        self, topology_service: TopologyService, tenant_ctx: TenantContext
    ):
        """Generates 500 nodes and validates that projection and clustering complete in < 2.0s."""
        now = dt.datetime.now(dt.UTC)
        root = TypedEntityRef(
            entity_type=EntityReferenceType.APPLICATION,
            entity_id="app-mega",
            name="Mega Application",
        )

        # Generate 10 middle-tier microservices, each with 50 storage volumes
        num_services = 10
        volumes_per_svc = 50
        custom_costs: dict[str, Decimal] = {"app-mega": Decimal("100.0")}

        for s_idx in range(num_services):
            svc_id = f"svc-cluster-{s_idx}"
            svc_ref = TypedEntityRef(
                entity_type=EntityReferenceType.SERVICE, entity_id=svc_id, name=f"Service {s_idx}"
            )
            custom_costs[svc_id] = Decimal("50.0")

            # Root -> Service
            topology_service.dep_repo.save_edge(
                DependencyEdge(
                    id=f"edge-root-{svc_id}",
                    tenant_id=tenant_ctx.tenant_id,
                    source_ref=root,
                    target_ref=svc_ref,
                    relationship_type=RelationshipType.APPLICATION_DEPENDENCY,
                    direction=DependencyDirection.OUTBOUND,
                    provenance=EdgeProvenance(
                        provenance_type=EdgeProvenanceType.DISCOVERED,
                        actor_id="system",
                        layer=DiscoveryLayer.STRUCTURAL,
                        created_at=now,
                    ),
                    confidence=EdgeConfidenceLevel.HIGH,
                    criticality=EdgeCriticality.MEDIUM,
                    status=EdgeStatus.ACTIVE,
                    first_seen=now,
                    last_seen=now,
                ),
                tenant_context=tenant_ctx,
            )

            # Service -> 50 Storage Volumes
            for v_idx in range(volumes_per_svc):
                vol_id = f"vol-{s_idx}-{v_idx}"
                vol_ref = TypedEntityRef(
                    entity_type=EntityReferenceType.RESOURCE,
                    entity_id=vol_id,
                    name=f"EBS Vol {s_idx}-{v_idx}",
                )
                custom_costs[vol_id] = Decimal("10.0")
                topology_service.dep_repo.save_edge(
                    DependencyEdge(
                        id=f"edge-{svc_id}-{vol_id}",
                        tenant_id=tenant_ctx.tenant_id,
                        source_ref=svc_ref,
                        target_ref=vol_ref,
                        relationship_type=RelationshipType.LOGICAL_DEPENDENCY,
                        direction=DependencyDirection.OUTBOUND,
                        provenance=EdgeProvenance(
                            provenance_type=EdgeProvenanceType.DISCOVERED,
                            actor_id="system",
                            layer=DiscoveryLayer.STRUCTURAL,
                            created_at=now,
                        ),
                        confidence=EdgeConfidenceLevel.HIGH,
                        criticality=EdgeCriticality.LOW,
                        status=EdgeStatus.ACTIVE,
                        first_seen=now,
                        last_seen=now,
                    ),
                    tenant_context=tenant_ctx,
                )

        # Now we have 1 + 10 + 500 = 511 nodes total
        req = TopologyProjectionRequest(
            view_type=TopologyViewType.APPLICATION_DEPENDENCY,
            root_entity_id="app-mega",
            max_depth=4,
            interactive_node_limit=50,  # Force clustering of the 500 leaves
            enable_clustering=True,
        )

        start_time = time.perf_counter()
        view = topology_service.project_view(
            req,
            custom_node_costs=custom_costs,
            tenant_context=tenant_ctx,
        )
        elapsed_sec = time.perf_counter() - start_time

        # BBP Section 25 Target: < 2.0s
        assert elapsed_sec < 2.0, f"Projection took {elapsed_sec:.2f}s, exceeding 2.0s limit!"
        assert view.clustered_nodes_count > 0
        assert view.total_nodes <= 50

        # Clustered nodes must aggregate spend accurately
        clustered_nodes = [n for n in view.nodes if n.is_clustered]
        assert len(clustered_nodes) == 10  # 1 cluster per service
        for cn in clustered_nodes:
            assert cn.cluster_count == 50
            assert cn.direct_cost == Decimal("500.00")  # 50 * 10.00

    def test_node_collapse_hides_descendants(
        self, topology_service: TopologyService, tenant_ctx: TenantContext
    ):
        """Collapsing a node hides its descendants from the projection."""
        seed_ecommerce_topology(topology_service.dep_repo, tenant_ctx)

        # Collapse Web Gateway: res-compute-01, res-rds-postgres, res-s3-backup should be hidden
        req = TopologyProjectionRequest(
            view_type=TopologyViewType.APPLICATION_DEPENDENCY,
            root_entity_id="app-checkout",
            collapsed_node_ids=["svc-web-gateway"],
        )

        view = topology_service.project_view(req, tenant_context=tenant_ctx)
        node_ids = {n.id for n in view.nodes}

        assert "app-checkout" in node_ids
        assert "svc-web-gateway" in node_ids
        # Descendants hidden
        assert "res-compute-01" not in node_ids
        assert "res-rds-postgres" not in node_ids

        # Node itself marked collapsed
        web_node = next(n for n in view.nodes if n.id == "svc-web-gateway")
        assert web_node.collapsed is True


# ==============================================================================
# 7. Multi-Format Graph Export
# ==============================================================================


class TestGraphExport:
    """Tests export to JSON, CSV, GraphML, DOT, and SVG vector graphics."""

    def test_export_all_formats(self, topology_service: TopologyService, tenant_ctx: TenantContext):
        """Validates all five export formats produce valid structured content."""
        seed_ecommerce_topology(topology_service.dep_repo, tenant_ctx)
        proj_req = TopologyProjectionRequest(
            view_type=TopologyViewType.APPLICATION_DEPENDENCY,
            root_entity_id="app-checkout",
        )

        formats = [
            (GraphExportFormat.JSON, "application/json", "json"),
            (GraphExportFormat.CSV, "text/csv", "csv"),
            (GraphExportFormat.GRAPHML, "application/xml", "graphml"),
            (GraphExportFormat.DOT, "text/vnd.graphviz", "dot"),
            (GraphExportFormat.SVG, "image/svg+xml", "svg"),
        ]

        for fmt, expected_type, ext in formats:
            exp_req = GraphExportRequest(format=fmt, projection=proj_req)
            result = topology_service.export_graph(exp_req, tenant_context=tenant_ctx)

            assert result.format == fmt
            assert result.content_type == expected_type
            assert result.filename.endswith(f".{ext}")
            assert len(result.content) > 50

            if fmt == GraphExportFormat.SVG:
                assert "<svg" in result.content
                assert "Spend:" in result.content
            elif fmt == GraphExportFormat.DOT:
                assert "digraph" in result.content
            elif fmt == GraphExportFormat.GRAPHML:
                assert "<graphml" in result.content


# ==============================================================================
# 8. REST API & Multi-Tenant Isolation
# ==============================================================================


class TestTopologyRestApi:
    """Verifies REST API endpoints and cross-tenant isolation."""

    def test_list_canonical_views_endpoint(self, client: TestClient):
        """GET /api/v1/topology/views returns 8 canonical views with default depths."""
        resp = client.get("/api/v1/topology/views")
        assert resp.status_code == 200
        views = resp.json()
        assert len(views) == 8
        view_names = {v["view_type"] for v in views}
        assert "SERVICE_DEPENDENCY" in view_names
        assert "APPLICATION_DEPENDENCY" in view_names

    def test_project_and_chain_cost_endpoints(
        self, client: TestClient, topology_service: TopologyService, tenant_ctx: TenantContext
    ):
        """Validates projection and chain-cost endpoints with mandatory TenantContext headers."""
        seed_ecommerce_topology(topology_service.dep_repo, tenant_ctx)

        headers = {
            "X-Tenant-ID": tenant_ctx.tenant_id,
            "X-User-ID": tenant_ctx.user_id,
            "X-Correlation-ID": str(uuid.uuid4()),
        }

        # 1. Project view
        proj_payload = {
            "view_type": "APPLICATION_DEPENDENCY",
            "root_entity_id": "app-checkout",
            "max_depth": 3,
        }
        p_resp = client.post("/api/v1/topology/project", json=proj_payload, headers=headers)
        assert p_resp.status_code == 200
        data = p_resp.json()
        assert data["view_type"] == "APPLICATION_DEPENDENCY"
        assert len(data["nodes"]) >= 3

        # 2. Chain cost
        c_resp = client.get(
            "/api/v1/topology/chain-cost/app-checkout?entity_type=APPLICATION&max_depth=4",
            headers=headers,
        )
        assert c_resp.status_code == 200
        c_data = c_resp.json()
        assert c_data["root_entity"]["entity_id"] == "app-checkout"
        assert len(c_data["contributing_nodes"]) >= 3

    def test_multi_tenant_isolation_on_topology(
        self,
        client: TestClient,
        topology_service: TopologyService,
        tenant_ctx: TenantContext,
        other_tenant_ctx: TenantContext,
    ):
        """Tenant B cannot see Tenant A's projected topology nodes."""
        seed_ecommerce_topology(topology_service.dep_repo, tenant_ctx)

        other_headers = {
            "X-Tenant-ID": other_tenant_ctx.tenant_id,
            "X-User-ID": other_tenant_ctx.user_id,
            "X-Correlation-ID": str(uuid.uuid4()),
        }

        # Tenant B requests projection for app-checkout (which only exists in Tenant A)
        proj_payload = {
            "view_type": "APPLICATION_DEPENDENCY",
            "root_entity_id": "app-checkout",
        }
        resp = client.post("/api/v1/topology/project", json=proj_payload, headers=other_headers)
        assert resp.status_code == 200
        data = resp.json()
        # Tenant B should see only the root query node itself, with 0 edges and 0 other nodes
        assert len(data["edges"]) == 0
        assert data["total_edges"] == 0
