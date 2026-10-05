"""Level 5 Cloud-Provider Compatibility & Contract Suite (BBP Section 47).

Validates provider-specific hierarchy models and native billing schema adapters for:
- AWS (Organizations, AWS Account, CUR 2.0 / aws_focus_1_0)
- Azure (Management Groups, Subscriptions, EA/MCA / azure_cost_details_focus_1_0)
- GCP (Folders, Projects, BigQuery FOCUS / gcp_billing_focus_1_0)
- OCI (Tenancy, Compartments, Cost Reports / oci_focus_1_0)
"""

from __future__ import annotations

import pytest

from connectors.simulator import ProviderSimulatorConnector, SimulatorProfile
from domain.cost.schema_guard import SUPPORTED_PROVIDER_SCHEMAS, SchemaVersionGuard
from domain.models.enums import ProviderType
from domain.models.exceptions import UnknownSchemaVersionException


class TestCloudProviderSuite:
    """Verifies each cloud provider's structural hierarchy and billing schema contract."""

    @pytest.mark.parametrize(
        "profile,expected_provider,schema_version",
        [
            (SimulatorProfile.AWS, ProviderType.AWS, "aws_focus_1_0"),
            (SimulatorProfile.AZURE, ProviderType.AZURE, "azure_cost_details_focus_1_0"),
            (SimulatorProfile.GCP, ProviderType.GCP, "gcp_billing_focus_1_0"),
            (SimulatorProfile.OCI, ProviderType.OCI, "oci_focus_1_0"),
        ],
    )
    def test_provider_schema_support_and_guard(
        self, profile: SimulatorProfile, expected_provider: ProviderType, schema_version: str
    ) -> None:
        """Every supported provider registers an authoritative FOCUS 1.0 schema without guessing."""
        # Provider is recognized
        assert expected_provider.value in SUPPORTED_PROVIDER_SCHEMAS
        assert schema_version in SUPPORTED_PROVIDER_SCHEMAS[expected_provider.value]

        # Guard validates successfully
        SchemaVersionGuard.validate_schema(expected_provider.value, schema_version)
        assert SchemaVersionGuard.is_focus_native(schema_version) is True

    def test_unsupported_provider_schema_strictly_fails(self) -> None:
        """Unknown or hallucinated billing schemas must raise UnknownSchemaVersionException immediately."""
        with pytest.raises(UnknownSchemaVersionException):
            SchemaVersionGuard.validate_schema("aws", "aws_unsupported_csv_v9")

        with pytest.raises(UnknownSchemaVersionException):
            SchemaVersionGuard.validate_schema("unknown_cloud", "generic_schema_v1")

    @pytest.mark.asyncio
    async def test_aws_hierarchy_and_inventory_contract(self) -> None:
        """AWS connector returns valid organizational hierarchy with AWS accounts."""
        conn = ProviderSimulatorConnector(
            connector_id="conn-aws-prov-test",
            tenant_id="tenant-prov-test",
            profile=SimulatorProfile.AWS,
        )
        assert conn.profile.value == "aws"
        hierarchy = await conn.discover_hierarchy()
        assert len(hierarchy) > 0
        root_node = hierarchy[0]
        assert root_node["type"] == "Root"
        assert root_node["id"] == "r-root-01"

        resources = await conn.discover_resources(scope_id=root_node["id"])
        assert len(resources) > 0
        assert "ResourceArn" in resources[0]
        assert "arn:aws:" in resources[0]["ResourceArn"]

    @pytest.mark.asyncio
    async def test_azure_hierarchy_and_inventory_contract(self) -> None:
        """Azure connector returns valid management groups and subscriptions."""
        conn = ProviderSimulatorConnector(
            connector_id="conn-azure-prov-test",
            tenant_id="tenant-prov-test",
            profile=SimulatorProfile.AZURE,
        )
        assert conn.profile.value == "azure"
        hierarchy = await conn.discover_hierarchy()
        assert len(hierarchy) > 0
        root_node = hierarchy[0]
        assert root_node["type"] == "ManagementGroup"
        assert "Microsoft.Management" in root_node["id"]

        resources = await conn.discover_resources(scope_id=root_node["id"])
        assert len(resources) > 0
        assert "Microsoft.Compute/virtualMachines" in resources[0]["type"]

    @pytest.mark.asyncio
    async def test_gcp_hierarchy_and_inventory_contract(self) -> None:
        """GCP connector returns valid organization, folders, and projects."""
        conn = ProviderSimulatorConnector(
            connector_id="conn-gcp-prov-test",
            tenant_id="tenant-prov-test",
            profile=SimulatorProfile.GCP,
        )
        assert conn.profile.value == "gcp"
        hierarchy = await conn.discover_hierarchy()
        assert len(hierarchy) > 0
        root_node = hierarchy[0]
        assert root_node["type"] == "Organization"
        assert "organizations/" in root_node["id"]

        resources = await conn.discover_resources(scope_id=root_node["id"])
        assert len(resources) > 0
        assert "compute.googleapis.com" in resources[0]["id"]

    @pytest.mark.asyncio
    async def test_oci_hierarchy_and_inventory_contract(self) -> None:
        """OCI connector returns valid tenancy and compartments."""
        conn = ProviderSimulatorConnector(
            connector_id="conn-oci-prov-test",
            tenant_id="tenant-prov-test",
            profile=SimulatorProfile.OCI,
        )
        assert conn.profile.value == "oci"
        hierarchy = await conn.discover_hierarchy()
        assert len(hierarchy) > 0
        root_node = hierarchy[0]
        assert root_node["type"] == "Tenancy"
        assert "ocid1.tenancy." in root_node["id"]

        resources = await conn.discover_resources(scope_id=root_node["id"])
        assert len(resources) > 0
        assert "ocid1.instance." in resources[0]["id"]
