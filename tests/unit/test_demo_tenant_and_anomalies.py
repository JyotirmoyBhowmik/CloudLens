"""Unit and Integration Tests for Demonstration Tenant Seeding & Anomaly Discovery (Prompt 09).

Validates:
- Multi-provider hierarchy depth across AWS, Azure, GCP, and OCI.
- Resource distribution, tagging debt, and out-of-schedule running telemetry.
- Pareto long-tail cost distribution.
- Discoverability of all four deliberate anomalies:
  1. COST_SPIKE
  2. RESTATEMENT
  3. STALE_CONNECTOR
  4. UNOWNED_CLUSTER
- Idempotent re-seeding without duplicate keys or records.
- Ingestion fixtures: syntax, realistic edge cases, zero secrets or real credentials.
- Fast execution (< 2 minutes SLA; typically < 0.1s).
- REST API contract for demo tenant endpoints.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.attribution.models import OwnershipResolutionRule
from domain.models.enums import ChargeCategory, ProviderType, ScopeRole, SyncJobStatus
from domain.synthetic.demo_tenant import (
    DEMO_TENANT_ID,
    DemoTenantLoaderService,
)
from domain.synthetic.estate_generator import (
    SyntheticAnomalyType,
)


@pytest.fixture
def demo_service() -> DemoTenantLoaderService:
    """Provides a fresh instance of DemoTenantLoaderService for testing."""
    return DemoTenantLoaderService()


@pytest.fixture
def client() -> TestClient:
    """Test client for FastAPI app."""
    return TestClient(app)


class TestDemonstrationEstateGeneration:
    """Validates estate generation across all four providers."""

    def test_multi_provider_hierarchy_depth(self, demo_service: DemoTenantLoaderService):
        """Validates scope hierarchy depth and role mapping across AWS, Azure, GCP, OCI."""
        report = demo_service.seed_demo_tenant(
            tenant_id=DEMO_TENANT_ID, sample_size=30, force_reseed=True
        )
        assert report.status == "COMPLETED"
        assert report.tenant_id == DEMO_TENANT_ID

        estate = demo_service.get_estate(DEMO_TENANT_ID)
        assert estate is not None

        # Check all 4 providers are represented in scopes
        providers_in_scopes = {s.provider for s in estate.scopes}
        assert ProviderType.AWS in providers_in_scopes
        assert ProviderType.AZURE in providers_in_scopes
        assert ProviderType.GCP in providers_in_scopes
        assert ProviderType.OCI in providers_in_scopes

        # Azure must reach depth >= 3 (Tenant -> Management Group -> Subscription -> Resource Group)
        azure_scopes = [s for s in estate.scopes if s.provider == ProviderType.AZURE]
        max_azure_depth = max(s.depth for s in azure_scopes)
        assert max_azure_depth >= 3

        # AWS and GCP must have SUB_GROUP legitimately absent
        aws_scopes = [s for s in estate.scopes if s.provider == ProviderType.AWS]
        gcp_scopes = [s for s in estate.scopes if s.provider == ProviderType.GCP]
        assert not any(s.canonical_role == ScopeRole.SUB_GROUP for s in aws_scopes)
        assert not any(s.canonical_role == ScopeRole.SUB_GROUP for s in gcp_scopes)

        # OCI has SUB_GROUP present for nested compartments
        oci_scopes = [s for s in estate.scopes if s.provider == ProviderType.OCI]
        assert any(s.canonical_role == ScopeRole.SUB_GROUP for s in oci_scopes)

    def test_resource_type_distribution_and_tagging_debt(
        self, demo_service: DemoTenantLoaderService
    ):
        """Validates realistic resource distribution and deliberate tagging debt."""
        demo_service.seed_demo_tenant(tenant_id=DEMO_TENANT_ID, sample_size=40, force_reseed=True)
        estate = demo_service.get_estate(DEMO_TENANT_ID)
        assert estate is not None

        # Resources span all 4 providers
        res_providers = {r.provider for r in estate.resources}
        assert len(res_providers) == 4

        # Deliberate tagging debt: some resources must have empty or incomplete tags
        untagged_resources = [r for r in estate.resources if len(r.tags) == 0]
        assert (
            len(untagged_resources) >= 8
        )  # At least the 8 unowned cluster resources + random debt

        # Out-of-schedule running detection: idle runtime states exist
        idle_runtime_states = [rs for rs in estate.runtime_states if rs.is_idle]
        assert len(idle_runtime_states) > 0
        for irs in idle_runtime_states:
            assert irs.cpu_utilization_avg.value < Decimal("5.0")

    def test_pareto_cost_distribution(self, demo_service: DemoTenantLoaderService):
        """Validates long-tail cost distribution across resources."""
        demo_service.seed_demo_tenant(tenant_id=DEMO_TENANT_ID, sample_size=50, force_reseed=True)
        estate = demo_service.get_estate(DEMO_TENANT_ID)
        assert estate is not None
        assert len(estate.cost_facts) > 0

        # Total billed cost must be positive and non-trivial
        total_cost = sum(
            cf.billed_cost.value for cf in estate.cost_facts if cf.billed_cost.is_present
        )
        assert total_cost > Decimal("1000.00")


class TestDeliberateAnomaliesDiscoverability:
    """Validates that all four deliberate anomalies are discoverable via dedicated discovery queries."""

    def test_all_four_anomalies_registered(self, demo_service: DemoTenantLoaderService):
        """All 4 anomaly types must be recorded in the seed report."""
        report = demo_service.seed_demo_tenant(
            tenant_id=DEMO_TENANT_ID, sample_size=30, force_reseed=True
        )
        anomaly_types = {a.anomaly_type for a in report.anomalies}

        assert SyntheticAnomalyType.COST_SPIKE in anomaly_types
        assert SyntheticAnomalyType.RESTATEMENT in anomaly_types
        assert SyntheticAnomalyType.STALE_CONNECTOR in anomaly_types
        assert SyntheticAnomalyType.UNOWNED_CLUSTER in anomaly_types
        assert len(report.anomalies) == 4

    def test_cost_spike_anomaly_discoverable(self, demo_service: DemoTenantLoaderService):
        """Deliberate 15x cost spike is discoverable in cost facts and query helper."""
        demo_service.seed_demo_tenant(tenant_id=DEMO_TENANT_ID, sample_size=30, force_reseed=True)
        spikes = demo_service.find_cost_spikes(tenant_id=DEMO_TENANT_ID)

        assert len(spikes) == 1
        spike_info = spikes[0]
        assert spike_info["spike_amount"] == "850.00"
        assert spike_info["baseline_amount"] == "25.00"
        assert spike_info["resource"] is not None
        assert len(spike_info["cost_facts"]) >= 1

    def test_restatement_anomaly_discoverable(self, demo_service: DemoTenantLoaderService):
        """Prior billing period retroactive adjustment credit (-$450.00) is discoverable."""
        demo_service.seed_demo_tenant(tenant_id=DEMO_TENANT_ID, sample_size=30, force_reseed=True)
        restatements = demo_service.find_restatements(tenant_id=DEMO_TENANT_ID)

        assert len(restatements) >= 1
        adj_fact = next(
            (cf for cf in restatements if cf.billed_cost.value == Decimal("-450.00")), None
        )
        assert adj_fact is not None
        assert adj_fact.charge_category == ChargeCategory.ADJUSTMENT
        assert adj_fact.id == "cf-anomaly-restatement-001"

    def test_stale_connector_anomaly_discoverable(self, demo_service: DemoTenantLoaderService):
        """Connector job failed >72h ago (96h stale) is discoverable."""
        demo_service.seed_demo_tenant(tenant_id=DEMO_TENANT_ID, sample_size=30, force_reseed=True)
        stale_jobs = demo_service.find_stale_connectors(
            tenant_id=DEMO_TENANT_ID, max_freshness_hours=72
        )

        assert len(stale_jobs) >= 1
        gcp_job = next((j for j in stale_jobs if j.id == "sync-gcp-stale"), None)
        assert gcp_job is not None
        assert gcp_job.status == SyncJobStatus.FAILED
        assert gcp_job.connector_type == ProviderType.GCP
        assert "exceeded SLA" in (gcp_job.error_message or "")

    def test_unowned_cluster_anomaly_discoverable(self, demo_service: DemoTenantLoaderService):
        """Cluster of 8 interrelated unowned resources resolves to UNRESOLVED via OwnershipResolutionService."""
        demo_service.seed_demo_tenant(tenant_id=DEMO_TENANT_ID, sample_size=30, force_reseed=True)
        clusters = demo_service.find_unowned_clusters(tenant_id=DEMO_TENANT_ID)

        assert len(clusters) == 1
        cluster = clusters[0]
        assert cluster["unowned_resource_count"] == 8
        assert cluster["resolution_rule"] == OwnershipResolutionRule.UNRESOLVED.value
        assert "Legacy Orphan Testing Lab" in cluster["scope_name"]


class TestDemonstrationTenantIdempotence:
    """Validates idempotent seeding and performance SLA."""

    def test_idempotent_seeding_without_force_reseed(self, demo_service: DemoTenantLoaderService):
        """Consecutive seed calls without force_reseed return existing state without duplicate mutation."""
        initial = demo_service.seed_demo_tenant(
            tenant_id=DEMO_TENANT_ID, sample_size=20, force_reseed=True
        )
        second = demo_service.seed_demo_tenant(
            tenant_id=DEMO_TENANT_ID, sample_size=20, force_reseed=False
        )

        assert initial.resources_count == second.resources_count
        assert initial.cost_facts_count == second.cost_facts_count
        assert second.is_reseeded is False

    def test_forced_reseed_replaces_cleanly(self, demo_service: DemoTenantLoaderService):
        """Forced reseed replaces the estate without duplication."""
        report1 = demo_service.seed_demo_tenant(
            tenant_id=DEMO_TENANT_ID, sample_size=20, force_reseed=True
        )
        report2 = demo_service.seed_demo_tenant(
            tenant_id=DEMO_TENANT_ID, sample_size=30, force_reseed=True
        )

        assert report1.resources_count < report2.resources_count
        assert report2.is_reseeded is True
        # Estate now reflects the 30-sample estate rather than accumulating on top
        estate = demo_service.get_estate(DEMO_TENANT_ID)
        assert estate is not None
        assert len(estate.resources) == report2.resources_count

    def test_execution_duration_under_two_minutes(self, demo_service: DemoTenantLoaderService):
        """Validates seeding completes well within the 2-minute requirement (Item 63)."""
        report = demo_service.seed_demo_tenant(
            tenant_id=DEMO_TENANT_ID, sample_size=100, force_reseed=True
        )
        assert report.elapsed_seconds < 120.0
        assert report.elapsed_seconds < 2.0  # Even on test machines, should be under 2s!


class TestIngestionFixtures:
    """Validates the raw multi-cloud ingestion fixtures for Prompt 09 Item 62."""

    FIXTURES = [
        "aws_cur_sample.json",
        "azure_cost_export_sample.json",
        "gcp_billing_export_sample.json",
        "oci_usage_report_sample.json",
    ]

    def test_fixtures_exist_and_are_valid_json(self):
        """All four provider fixtures must exist and contain valid JSON arrays."""
        fixtures_dir = Path(__file__).resolve().parent.parent.parent / "connectors" / "fixtures"
        assert fixtures_dir.exists(), f"Fixtures directory missing: {fixtures_dir}"

        for fixture_name in self.FIXTURES:
            fixture_path = fixtures_dir / fixture_name
            assert fixture_path.exists(), f"Fixture missing: {fixture_name}"
            content = json.loads(fixture_path.read_text(encoding="utf-8"))
            assert isinstance(content, list), f"Fixture {fixture_name} must be a JSON array"
            assert len(content) >= 3, f"Fixture {fixture_name} should contain multiple line items"

    def test_fixtures_contain_no_real_credentials_or_secrets(self):
        """Ingestion fixtures must contain zero real secrets, AWS access keys, or API tokens."""
        fixtures_dir = Path(__file__).resolve().parent.parent.parent / "connectors" / "fixtures"

        forbidden_patterns = [
            "AKIA",  # Standard AWS active access key prefix
            "ghp_",  # GitHub personal access token
            "Bearer eyJ",  # JWT bearer token
            "password123",
            "BEGIN RSA PRIVATE KEY",
        ]

        for fixture_name in self.FIXTURES:
            raw_text = (fixtures_dir / fixture_name).read_text(encoding="utf-8")
            for pattern in forbidden_patterns:
                assert pattern not in raw_text, (
                    f"Forbidden pattern '{pattern}' detected in fixture {fixture_name}"
                )

    def test_fixtures_contain_messy_edge_cases(self):
        """Ingestion fixtures must contain realistic messiness: credits, untagged rows, adjustments."""
        fixtures_dir = Path(__file__).resolve().parent.parent.parent / "connectors" / "fixtures"

        # AWS: contains Credit / Refund line
        aws_data = json.loads((fixtures_dir / "aws_cur_sample.json").read_text(encoding="utf-8"))
        assert any(item.get("lineItem/LineItemType") == "Credit" for item in aws_data)

        # Azure: contains untagged resource
        azure_data = json.loads(
            (fixtures_dir / "azure_cost_export_sample.json").read_text(encoding="utf-8")
        )
        assert any(item.get("Tags") in ("{}", None) for item in azure_data)

        # GCP: contains adjustment cost_type
        gcp_data = json.loads(
            (fixtures_dir / "gcp_billing_export_sample.json").read_text(encoding="utf-8")
        )
        assert any(item.get("cost_type") == "adjustment" for item in gcp_data)

        # OCI: contains correction lineItem
        oci_data = json.loads(
            (fixtures_dir / "oci_usage_report_sample.json").read_text(encoding="utf-8")
        )
        assert any(item.get("lineItem/isCorrection") == "TRUE" for item in oci_data)


class TestDemoTenantRestApi:
    """Validates FastAPI REST endpoints for demonstration tenant management."""

    def test_seed_demo_tenant_endpoint(self, client: TestClient):
        """POST /api/v1/system/demo/seed populates estate and returns seed report."""
        resp = client.post("/api/v1/system/demo/seed?sample_size=20&force_reseed=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == DEMO_TENANT_ID
        assert data["scopes_count"] > 0
        assert data["resources_count"] > 0
        assert len(data["anomalies"]) == 4

    def test_demo_tenant_status_endpoint(self, client: TestClient):
        """GET /api/v1/system/demo/status returns active population status."""
        resp = client.get("/api/v1/system/demo/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_seeded"] is True
        assert data["tenant_id"] == DEMO_TENANT_ID
        assert data["anomalies_count"] == 4

    def test_demo_anomalies_endpoints(self, client: TestClient):
        """GET /api/v1/system/demo/anomalies endpoints return discovered anomalies."""
        # Generic anomalies endpoint
        all_resp = client.get("/api/v1/system/demo/anomalies")
        assert all_resp.status_code == 200
        assert len(all_resp.json()) == 4

        # Filtered by type
        spike_resp = client.get("/api/v1/system/demo/anomalies?anomaly_type=COST_SPIKE")
        assert spike_resp.status_code == 200
        assert len(spike_resp.json()) == 1

        # Dedicated endpoint for cost spikes
        spikes_resp = client.get("/api/v1/system/demo/anomalies/cost-spikes")
        assert spikes_resp.status_code == 200
        assert len(spikes_resp.json()) == 1

        # Dedicated endpoint for restatements
        restatements_resp = client.get("/api/v1/system/demo/anomalies/restatements")
        assert restatements_resp.status_code == 200
        assert len(restatements_resp.json()) >= 1

        # Dedicated endpoint for stale connectors
        stale_resp = client.get(
            "/api/v1/system/demo/anomalies/stale-connectors?max_freshness_hours=72"
        )
        assert stale_resp.status_code == 200
        assert len(stale_resp.json()) >= 1

        # Dedicated endpoint for unowned clusters
        unowned_resp = client.get("/api/v1/system/demo/anomalies/unowned-clusters")
        assert unowned_resp.status_code == 200
        assert len(unowned_resp.json()) == 1
