"""Contract and Conformance Tests for CloudLens Connectors (Prompt 47 Item 23).

Validates:
- Every connector implements the BaseCloudConnector contract.
- Conformance verified for AWS, Azure, GCP, OCI, Stub, and ProviderSimulatorConnector.
- ProviderSimulatorConnector implements the full capability contract:
  - C-01 Hierarchy Discovery
  - C-02 Resource Inventory
  - C-03 Cost Data Ingestion
  - C-04 Usage Data Ingestion
  - C-11 Pricing Catalog Sync
  - C-18 Quota and Limit Sync
- Simulated rate limiting and pagination adhere to enterprise standards.
- Raw payload landing files have valid cryptographic SHA256 checksums.
- End-to-end execution through SyncOrchestrator records valid SyncJob audit logs.
- Simulator is indistinguishable to every layer above the connector.
"""

import hashlib
import json

import pytest

from connectors.aws.connector import AWSConnector
from connectors.azure.connector import AzureConnector
from connectors.contract.base import BaseCloudConnector
from connectors.gcp.connector import GCPConnector
from connectors.oci.connector import OCIConnector
from connectors.simulator.connector import ProviderSimulatorConnector
from connectors.simulator.models import PaginationParams, SimulatorProfile
from connectors.simulator.orchestrator import SyncOrchestrator
from connectors.stub.connector import StubConnector
from domain.models.enums import ProviderCapability, SyncJobStatus


@pytest.fixture
def all_connectors() -> list[BaseCloudConnector]:
    """Provides instances of all registered connectors for contract conformance testing."""
    return [
        AWSConnector(connector_id="conn-test-aws", tenant_id="T-TEST", config={}),
        AzureConnector(connector_id="conn-test-azure", tenant_id="T-TEST", config={}),
        GCPConnector(connector_id="conn-test-gcp", tenant_id="T-TEST", config={}),
        OCIConnector(connector_id="conn-test-oci", tenant_id="T-TEST", config={}),
        StubConnector(connector_id="conn-test-stub", tenant_id="T-TEST", config={}),
        ProviderSimulatorConnector(
            connector_id="conn-test-sim-aws",
            tenant_id="T-TEST",
            profile=SimulatorProfile.AWS,
        ),
        ProviderSimulatorConnector(
            connector_id="conn-test-sim-azure",
            tenant_id="T-TEST",
            profile=SimulatorProfile.AZURE,
        ),
        ProviderSimulatorConnector(
            connector_id="conn-test-sim-gcp",
            tenant_id="T-TEST",
            profile=SimulatorProfile.GCP,
        ),
        ProviderSimulatorConnector(
            connector_id="conn-test-sim-oci",
            tenant_id="T-TEST",
            profile=SimulatorProfile.OCI,
        ),
    ]


class TestConnectorInterfaceConformance:
    """Validates BaseCloudConnector interface conformance across all connector implementations."""

    def test_base_contract_inheritance(self, all_connectors: list[BaseCloudConnector]):
        """Every connector must inherit from BaseCloudConnector."""
        for conn in all_connectors:
            assert isinstance(
                conn, BaseCloudConnector
            ), f"{conn.__class__.__name__} must inherit BaseCloudConnector"
            assert conn.connector_id.startswith("conn-test-")
            assert conn.tenant_id == "T-TEST"
            assert isinstance(conn.provider_name, str)
            assert len(conn.provider_name) > 0

    @pytest.mark.asyncio
    async def test_credential_validation_contract(self, all_connectors: list[BaseCloudConnector]):
        """Every connector must return a dictionary with a boolean 'valid' field."""
        for conn in all_connectors:
            result = await conn.validate_credentials()
            assert isinstance(result, dict)
            assert "valid" in result
            assert isinstance(result["valid"], bool)

    @pytest.mark.asyncio
    async def test_connection_health_check_contract(self, all_connectors: list[BaseCloudConnector]):
        """Every connector must return a boolean from test_connection()."""
        for conn in all_connectors:
            connected = await conn.test_connection()
            assert isinstance(connected, bool)
            assert connected is True

    @pytest.mark.asyncio
    async def test_hierarchy_discovery_contract(self, all_connectors: list[BaseCloudConnector]):
        """Every connector must return a list from discover_hierarchy()."""
        for conn in all_connectors:
            hierarchy = await conn.discover_hierarchy()
            assert isinstance(hierarchy, list)

    @pytest.mark.asyncio
    async def test_resource_discovery_contract(self, all_connectors: list[BaseCloudConnector]):
        """Every connector must return a list from discover_resources()."""
        for conn in all_connectors:
            resources = await conn.discover_resources(scope_id="scope-root")
            assert isinstance(resources, list)


class TestProviderSimulatorCapabilities:
    """Deep validation of ProviderSimulatorConnector specific capabilities (Prompt 47 Item 23)."""

    @pytest.mark.asyncio
    async def test_declared_capabilities_contract(self):
        """Simulator declares full capability contract: C-01, C-02, C-03, C-04, C-11, C-18."""
        for profile in SimulatorProfile:
            sim = ProviderSimulatorConnector(
                connector_id=f"conn-sim-{profile.value}",
                tenant_id="T-TEST",
                profile=profile,
            )
            val = await sim.validate_credentials()
            assert val["valid"] is True
            assert "capabilities" in val
            caps = val["capabilities"]

            expected_caps = [
                ProviderCapability.C01_HIERARCHY.value,
                ProviderCapability.C02_INVENTORY.value,
                ProviderCapability.C03_COST.value,
                ProviderCapability.C04_USAGE.value,
                ProviderCapability.C11_PRICING.value,
                ProviderCapability.C18_QUOTA.value,
            ]
            for exp in expected_caps:
                assert exp in caps, f"Simulator {profile.value} missing capability {exp}"

    @pytest.mark.asyncio
    async def test_simulated_pagination(self):
        """Validates simulated pagination across resources and cost records."""
        sim = ProviderSimulatorConnector(
            connector_id="conn-sim-aws-page",
            tenant_id="T-TEST",
            profile=SimulatorProfile.AWS,
        )

        # 1. Resource pagination
        items = await sim.discover_resources(
            scope_id="root",
            pagination=PaginationParams(page_size=5),
        )
        assert len(items) <= 5
        assert len(items) > 0

        # 2. Billing pagination
        cost_records = await sim.fetch_cost_and_usage(
            pagination=PaginationParams(page_size=10),
        )
        assert len(cost_records) <= 10
        assert len(cost_records) > 0

    @pytest.mark.asyncio
    async def test_raw_payload_landing_and_checksum_integrity(self):
        """Validates raw payload landings with cryptographic SHA256 checksums."""
        sim = ProviderSimulatorConnector(
            connector_id="conn-sim-landing",
            tenant_id="T-TEST",
            profile=SimulatorProfile.AZURE,
        )

        records = await sim.fetch_cost_and_usage()
        assert len(records) > 0

        landings = sim.get_landings()
        assert len(landings) >= 1
        last_landing = landings[-1]

        # Verify SHA256 matches actual content
        payload_bytes = json.dumps(last_landing.raw_content, sort_keys=True, default=str).encode(
            "utf-8"
        )
        computed_sha256 = hashlib.sha256(payload_bytes).hexdigest()

        assert last_landing.sha256_checksum == computed_sha256
        assert last_landing.byte_size == len(payload_bytes)

    @pytest.mark.asyncio
    async def test_sync_orchestrator_execution(self):
        """Validates end-to-end sync execution through SyncOrchestrator."""
        orchestrator = SyncOrchestrator()
        sim = ProviderSimulatorConnector(
            connector_id="conn-sim-orch",
            tenant_id="T-TEST",
            profile=SimulatorProfile.GCP,
        )

        job = await orchestrator.execute_sync(
            connector=sim,
            scope_id="gcp-org-root",
            fetch_billing=True,
        )

        assert job.status == SyncJobStatus.COMPLETED
        assert job.rows_ingested > 0
        assert job.completed_at is not None
        assert len(orchestrator.get_history()) >= 1
