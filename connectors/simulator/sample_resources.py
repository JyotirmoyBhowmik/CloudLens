"""Sample Resource Fixtures for Simulator and Test Suites.

Moved from real connector implementations per Prompt P13A requirements:
- Real connectors (connectors/aws, connectors/azure, connectors/gcp, connectors/oci) MUST NOT
  contain _get_sample_resources or FIXTURES_DIR.
- Simulated and fixture workloads live exclusively in connectors/simulator and tests/fixtures.
"""

from __future__ import annotations

from typing import Any

from domain.models.enums import RuntimeStatus, ServiceCategory


def get_sample_aws_resources(management_account_id: str = "112233445566") -> list[dict[str, Any]]:
    """Provides realistic AWS resource fixtures for simulation and contract tests."""
    from connectors.aws.models import KNOWN_AWS_TYPE_MAPPINGS, AWSResourceRecord

    acc_mgmt = management_account_id
    acc_prod = "223344556677"
    acc_data = "334455667788"

    ec2_arn = f"arn:aws:ec2:us-east-1:{acc_mgmt}:instance/i-0123456789abcdef0"
    vol_arn = f"arn:aws:ec2:us-east-1:{acc_mgmt}:volume/vol-0123456789abcdef0"
    eni_arn = f"arn:aws:ec2:us-east-1:{acc_mgmt}:network-interface/eni-0123456789abcdef0"
    vpc_arn = f"arn:aws:ec2:us-east-1:{acc_mgmt}:vpc/vpc-0123456789abcdef0"
    subnet_arn = f"arn:aws:ec2:us-east-1:{acc_mgmt}:subnet/subnet-0123456789abcdef0"
    s3_arn = "arn:aws:s3:::enterprise-data-lake-prod"
    rds_arn = f"arn:aws:rds:us-east-1:{acc_prod}:db:payment-ledger-db"
    kms_arn = f"arn:aws:kms:us-east-1:{acc_mgmt}:key/12345678-1234-1234-1234-123456789012"
    appsync_arn = f"arn:aws:appsync:us-east-1:{acc_data}:apis/xyz123abc456"

    records = [
        AWSResourceRecord(
            arn=ec2_arn,
            resource_id="i-0123456789abcdef0",
            account_id=acc_mgmt,
            region="us-east-1",
            service="ec2",
            native_type="AWS::EC2::Instance",
            service_category=KNOWN_AWS_TYPE_MAPPINGS.get(
                "AWS::EC2::Instance", ServiceCategory.COMPUTE.value
            ),
            runtime_status=RuntimeStatus.RUNNING.value,
            tags={
                "Environment": "Production",
                "CostCenter": "CC-101-FINOPS",
                "Owner": "platform-team",
                "Application": "RetailBankingCore",
            },
            is_unclassified=False,
            properties={
                "instance_type": "t3.xlarge",
                "vpc_id": "vpc-0123456789abcdef0",
                "subnet_id": "subnet-0123456789abcdef0",
                "attached_eni_ids": ["eni-0123456789abcdef0"],
                "attached_volume_ids": ["vol-0123456789abcdef0"],
            },
        ),
        AWSResourceRecord(
            arn=vol_arn,
            resource_id="vol-0123456789abcdef0",
            account_id=acc_mgmt,
            region="us-east-1",
            service="ec2",
            native_type="AWS::EBS::Volume",
            service_category=KNOWN_AWS_TYPE_MAPPINGS.get(
                "AWS::EBS::Volume", ServiceCategory.STORAGE.value
            ),
            runtime_status=RuntimeStatus.RUNNING.value,
            tags={"Environment": "Production", "CostCenter": "CC-101-FINOPS"},
            is_unclassified=False,
            properties={
                "size_gb": 100,
                "volume_type": "gp3",
                "iops": 3000,
                "attached_instance_id": "i-0123456789abcdef0",
            },
        ),
        AWSResourceRecord(
            arn=eni_arn,
            resource_id="eni-0123456789abcdef0",
            account_id=acc_mgmt,
            region="us-east-1",
            service="ec2",
            native_type="AWS::EC2::NetworkInterface",
            service_category=KNOWN_AWS_TYPE_MAPPINGS.get(
                "AWS::EC2::NetworkInterface", ServiceCategory.NETWORKING.value
            ),
            runtime_status=RuntimeStatus.RUNNING.value,
            tags={"Environment": "Production"},
            is_unclassified=False,
            properties={
                "vpc_id": "vpc-0123456789abcdef0",
                "subnet_id": "subnet-0123456789abcdef0",
                "attached_instance_id": "i-0123456789abcdef0",
            },
        ),
        AWSResourceRecord(
            arn=s3_arn,
            resource_id="enterprise-data-lake-prod",
            account_id=acc_mgmt,
            region="us-east-1",
            service="s3",
            native_type="AWS::S3::Bucket",
            service_category=KNOWN_AWS_TYPE_MAPPINGS.get(
                "AWS::S3::Bucket", ServiceCategory.STORAGE.value
            ),
            runtime_status=RuntimeStatus.RUNNING.value,
            tags={
                "Environment": "Production",
                "CostCenter": "CC-303-DATA",
                "Owner": "data-engineering",
                "Application": "AnalyticsLake",
            },
            is_unclassified=False,
            properties={"versioning": True, "encryption": "AES256"},
        ),
        AWSResourceRecord(
            arn=rds_arn,
            resource_id="payment-ledger-db",
            account_id=acc_prod,
            region="us-east-1",
            service="rds",
            native_type="AWS::RDS::DBInstance",
            service_category=KNOWN_AWS_TYPE_MAPPINGS.get(
                "AWS::RDS::DBInstance", ServiceCategory.DATABASE.value
            ),
            runtime_status=RuntimeStatus.RUNNING.value,
            tags={"Environment": "Production"},
            is_unclassified=False,
            properties={
                "engine": "aurora-postgresql",
                "db_instance_class": "db.r5.2xlarge",
                "multi_az": True,
            },
        ),
        AWSResourceRecord(
            arn=kms_arn,
            resource_id="12345678-1234-1234-1234-123456789012",
            account_id=acc_mgmt,
            region="us-east-1",
            service="kms",
            native_type="AWS::KMS::Key",
            service_category=KNOWN_AWS_TYPE_MAPPINGS.get(
                "AWS::KMS::Key", ServiceCategory.SECURITY_IDENTITY.value
            ),
            runtime_status=RuntimeStatus.RUNNING.value,
            tags={"Environment": "Production"},
            is_unclassified=False,
            properties={"key_usage": "ENCRYPT_DECRYPT"},
        ),
        AWSResourceRecord(
            arn=vpc_arn,
            resource_id="vpc-0123456789abcdef0",
            account_id=acc_mgmt,
            region="us-east-1",
            service="ec2",
            native_type="AWS::EC2::VPC",
            service_category=KNOWN_AWS_TYPE_MAPPINGS.get(
                "AWS::EC2::VPC", ServiceCategory.NETWORKING.value
            ),
            runtime_status=RuntimeStatus.RUNNING.value,
            tags={"Environment": "Production"},
            is_unclassified=False,
            properties={"cidr_block": "10.0.0.0/16"},
        ),
        AWSResourceRecord(
            arn=subnet_arn,
            resource_id="subnet-0123456789abcdef0",
            account_id=acc_mgmt,
            region="us-east-1",
            service="ec2",
            native_type="AWS::EC2::Subnet",
            service_category=KNOWN_AWS_TYPE_MAPPINGS.get(
                "AWS::EC2::Subnet", ServiceCategory.NETWORKING.value
            ),
            runtime_status=RuntimeStatus.RUNNING.value,
            tags={"Environment": "Production"},
            is_unclassified=False,
            properties={"cidr_block": "10.0.1.0/24", "vpc_id": "vpc-0123456789abcdef0"},
        ),
        AWSResourceRecord(
            arn=appsync_arn,
            resource_id="xyz123abc456",
            account_id=acc_data,
            region="us-east-1",
            service="appsync",
            native_type="AWS::AppSync::GraphQLApi",
            service_category=ServiceCategory.OTHER.value,
            runtime_status=RuntimeStatus.RUNNING.value,
            tags={"Environment": "Production"},
            is_unclassified=True,
            classification_reason=(
                "Resource type 'AWS::AppSync::GraphQLApi' has non-uniform coverage in AWS Tagging API; "
                "retained native type as Unclassified per BBP Section 14.3."
            ),
            properties={"authentication_type": "API_KEY"},
        ),
    ]
    return [r.model_dump() for r in records]


def get_sample_azure_resources() -> list[dict[str, Any]]:
    """Provides realistic Azure resource fixtures for simulation and contract tests."""
    from connectors.azure.models import AzureFreshnessDiagnostic

    sub_prod = "sub-prod-0001"
    sub_data = "sub-prod-0002"
    rg_compute = "rg-payments-prod"
    rg_sec = "rg-security-prod"

    vm_id = f"/subscriptions/{sub_prod}/resourceGroups/{rg_compute}/providers/Microsoft.Compute/virtualMachines/vm-payment-gw-01"
    nic_id = f"/subscriptions/{sub_prod}/resourceGroups/{rg_compute}/providers/Microsoft.Network/networkInterfaces/nic-payment-gw-01"
    os_disk_id = f"/subscriptions/{sub_prod}/resourceGroups/{rg_compute}/providers/Microsoft.Compute/disks/disk-vm-payment-gw-os"
    sql_db_id = f"/subscriptions/{sub_prod}/resourceGroups/{rg_compute}/providers/Microsoft.Sql/servers/sql-payments-prod/databases/db-transactions"
    kv_id = f"/subscriptions/{sub_prod}/resourceGroups/{rg_sec}/providers/Microsoft.KeyVault/vaults/kv-sec-keys"
    storage_id = f"/subscriptions/{sub_data}/resourceGroups/rg-data-prod/providers/Microsoft.Storage/storageAccounts/saenterprisecore"

    freshness = AzureFreshnessDiagnostic().model_dump()

    return [
        {
            "id": vm_id,
            "name": "vm-payment-gw-01",
            "type": "Microsoft.Compute/virtualMachines",
            "location": "eastus",
            "resourceGroup": rg_compute,
            "subscriptionId": sub_prod,
            "service_category": ServiceCategory.COMPUTE.value,
            "runtime_status": RuntimeStatus.RUNNING.value,
            "tags": {
                "Environment": "Production",
                "CostCenter": "CC-202-ENG",
                "Owner": "payments-team",
                "Application": "PaymentGateway",
            },
            "sku": {"name": "Standard_D4s_v5", "tier": "Standard"},
            "properties": {
                "vmId": "00000000-1111-2222-3333-444444444444",
                "hardwareProfile": {"vmSize": "Standard_D4s_v5"},
                "storageProfile": {
                    "osDisk": {
                        "name": "disk-vm-payment-gw-os",
                        "managedDisk": {"id": os_disk_id, "storageAccountType": "Premium_LRS"},
                    },
                    "dataDisks": [],
                },
                "networkProfile": {
                    "networkInterfaces": [{"id": nic_id}],
                },
                "provisioningState": "Succeeded",
            },
            "_freshness": freshness,
        },
        {
            "id": os_disk_id,
            "name": "disk-vm-payment-gw-os",
            "type": "Microsoft.Compute/disks",
            "location": "eastus",
            "resourceGroup": rg_compute,
            "subscriptionId": sub_prod,
            "service_category": ServiceCategory.STORAGE.value,
            "runtime_status": RuntimeStatus.RUNNING.value,
            "tags": {"Environment": "Production", "CostCenter": "CC-202-ENG"},
            "sku": {"name": "Premium_LRS", "tier": "Premium"},
            "managedBy": vm_id,
            "properties": {
                "diskSizeGB": 128,
                "provisioningState": "Succeeded",
            },
            "_freshness": freshness,
        },
        {
            "id": nic_id,
            "name": "nic-payment-gw-01",
            "type": "Microsoft.Network/networkInterfaces",
            "location": "eastus",
            "resourceGroup": rg_compute,
            "subscriptionId": sub_prod,
            "service_category": ServiceCategory.NETWORKING.value,
            "runtime_status": RuntimeStatus.RUNNING.value,
            "tags": {"Environment": "Production"},
            "properties": {
                "ipConfigurations": [
                    {
                        "name": "ipconfig1",
                        "properties": {
                            "privateIPAddress": "10.0.1.4",
                            "primary": True,
                        },
                    }
                ],
                "provisioningState": "Succeeded",
            },
            "_freshness": freshness,
        },
        {
            "id": sql_db_id,
            "name": "db-transactions",
            "type": "Microsoft.Sql/servers/databases",
            "location": "eastus",
            "resourceGroup": rg_compute,
            "subscriptionId": sub_prod,
            "service_category": ServiceCategory.DATABASE.value,
            "runtime_status": RuntimeStatus.RUNNING.value,
            "tags": {"Environment": "Production"},
            "sku": {"name": "GP_Gen5_4", "tier": "GeneralPurpose"},
            "properties": {
                "collation": "SQL_Latin1_General_CP1_CI_AS",
                "maxSizeBytes": 268435456000,
                "status": "Online",
            },
            "_freshness": freshness,
        },
        {
            "id": kv_id,
            "name": "kv-sec-keys",
            "type": "Microsoft.KeyVault/vaults",
            "location": "eastus",
            "resourceGroup": rg_sec,
            "subscriptionId": sub_prod,
            "service_category": ServiceCategory.SECURITY_IDENTITY.value,
            "runtime_status": RuntimeStatus.RUNNING.value,
            "tags": {"Environment": "Production"},
            "properties": {
                "sku": {"name": "standard", "family": "A"},
                "vaultUri": "https://kv-sec-keys.vault.azure.net/",
            },
            "_freshness": freshness,
        },
        {
            "id": storage_id,
            "name": "saenterprisecore",
            "type": "Microsoft.Storage/storageAccounts",
            "location": "eastus",
            "resourceGroup": "rg-data-prod",
            "subscriptionId": sub_data,
            "service_category": ServiceCategory.STORAGE.value,
            "runtime_status": RuntimeStatus.RUNNING.value,
            "tags": {"Environment": "Production"},
            "sku": {"name": "Standard_GRS", "tier": "Standard"},
            "properties": {
                "primaryEndpoints": {
                    "blob": "https://saenterprisecore.blob.core.windows.net/",
                },
                "provisioningState": "Succeeded",
            },
            "_freshness": freshness,
        },
    ]


def get_sample_gcp_resources() -> list[dict[str, Any]]:
    """Provides realistic GCP resource fixtures for simulation and contract tests."""
    from connectors.gcp.models import KNOWN_GCP_TYPE_MAPPINGS, GCPResourceRecord

    proj_retail = "proj-retail-banking-prod"
    proj_analytics = "proj-ai-recommendations-analytics"
    proj_network = "proj-shared-vpc-host"

    records = [
        GCPResourceRecord(
            asset_name=(
                f"//compute.googleapis.com/projects/{proj_retail}/zones/us-central1-a/instances/gcp-vm-core-bank-prod-01"
            ),
            asset_type="compute.googleapis.com/Instance",
            project_id=proj_retail,
            location="us-central1-a",
            service_category=KNOWN_GCP_TYPE_MAPPINGS.get(
                "compute.googleapis.com/Instance", ServiceCategory.COMPUTE.value
            ),
            runtime_status=RuntimeStatus.RUNNING.value,
            labels={
                "app": "core-banking-api",
                "cost_centre": "CC-BANK-100",
                "owner": "banking-eng",
                "env": "production",
            },
            properties={
                "machine_type": "n2-standard-4",
                "cpu_platform": "Intel Cascade Lake",
                "status": "RUNNING",
                "last_start_timestamp": None,
                "active_connection_count": None,
                "scheduling": {
                    "preemptible": False,
                    "automaticRestart": True,
                    "onHostMaintenance": "MIGRATE",
                },
                "network_interfaces": [
                    {
                        "network": f"projects/{proj_network}/global/networks/vpc-shared-core-prod",
                        "subnetwork": f"projects/{proj_network}/regions/us-central1/subnetworks/sub-retail-prod",
                        "networkIP": "10.10.1.15",
                    }
                ],
            },
            has_null_frequently_changing_fields=True,
        ),
        GCPResourceRecord(
            asset_name=(
                f"//storage.googleapis.com/projects/{proj_retail}/buckets/gcp-gcs-customer-statements-prod"
            ),
            asset_type="storage.googleapis.com/Bucket",
            project_id=proj_retail,
            location="us-central1",
            service_category=KNOWN_GCP_TYPE_MAPPINGS.get(
                "storage.googleapis.com/Bucket", ServiceCategory.STORAGE.value
            ),
            runtime_status=RuntimeStatus.RUNNING.value,
            labels={
                "data_class": "confidential",
                "compliance": "pci-dss",
                "owner": "compliance-team",
            },
            properties={
                "storage_class": "STANDARD",
                "versioning": {"enabled": True},
                "retention_policy": {"retention_period": 2592000},
            },
            has_null_frequently_changing_fields=False,
        ),
        GCPResourceRecord(
            asset_name=(
                f"//bigquery.googleapis.com/projects/{proj_analytics}/datasets/analytics_data_warehouse"
            ),
            asset_type="bigquery.googleapis.com/Dataset",
            project_id=proj_analytics,
            location="US",
            service_category=KNOWN_GCP_TYPE_MAPPINGS.get(
                "bigquery.googleapis.com/Dataset", ServiceCategory.ANALYTICS.value
            ),
            runtime_status=RuntimeStatus.RUNNING.value,
            labels={"business_unit": "analytics", "cost_centre": "CC-ANALYTICS-200"},
            properties={"default_table_expiration_ms": None},
            has_null_frequently_changing_fields=False,
        ),
        GCPResourceRecord(
            asset_name=(
                f"//sqladmin.googleapis.com/projects/{proj_retail}/instances/gcp-sql-customer-profile-db"
            ),
            asset_type="sqladmin.googleapis.com/Instance",
            project_id=proj_retail,
            location="us-central1",
            service_category=KNOWN_GCP_TYPE_MAPPINGS.get(
                "sqladmin.googleapis.com/Instance", ServiceCategory.DATABASE.value
            ),
            runtime_status=RuntimeStatus.RUNNING.value,
            labels={"workload": "transactional-profile"},
            properties={
                "database_version": "POSTGRES_15",
                "settings": {"tier": "db-custom-4-16384", "availabilityType": "REGIONAL"},
            },
            has_null_frequently_changing_fields=False,
        ),
    ]
    return [r.model_dump() for r in records]


def get_sample_oci_resources() -> list[dict[str, Any]]:
    """Provides realistic OCI resource fixtures for simulation and contract tests."""
    from connectors.oci.models import KNOWN_OCI_TYPE_MAPPINGS, OCIResourceRecord

    c_sub_app = "ocid1.compartment.oc1..aaaaaaaasubapp111222333"
    c_sub_db = "ocid1.compartment.oc1..aaaaaaaasubdb555444333"

    records = [
        OCIResourceRecord(
            resource_id="ocid1.instance.oc1.iad.anuwcljtdemovm001",
            display_name="vm-payment-gateway-prod-01",
            resource_type="Instance",
            compartment_id=c_sub_app,
            lifecycle_state="AVAILABLE",
            region="us-ashburn-1",
            service_category=KNOWN_OCI_TYPE_MAPPINGS.get(
                "Instance", ServiceCategory.COMPUTE.value
            ),
            defined_tags={
                "Operations": {"CostCenter": "CC-OPS-200", "Owner": "devops"},
                "Security": {"DataClassification": "Restricted"},
            },
            freeform_tags={"Environment": "Production", "Application": "PaymentGateway"},
            properties={
                "shape": "VM.Standard.E4.Flex",
                "ocpus": 4.0,
                "memory_in_gbs": 32.0,
                "availability_domain": "iad-ad-1",
                "fault_domain": "FAULT-DOMAIN-1",
                "attached_vnic_ids": ["ocid1.vnic.oc1.iad.anuwcljtdemovnic001"],
                "attached_volume_ids": ["ocid1.volume.oc1.iad.bootvol001"],
            },
        ),
        OCIResourceRecord(
            resource_id="ocid1.autonomousdatabase.oc1.iad.anuwcljtdemodb002",
            display_name="db-payment-ledger-atp",
            resource_type="AutonomousDatabase",
            compartment_id=c_sub_db,
            lifecycle_state="AVAILABLE",
            region="us-ashburn-1",
            service_category=KNOWN_OCI_TYPE_MAPPINGS.get(
                "AutonomousDatabase", ServiceCategory.DATABASE.value
            ),
            defined_tags={"Operations": {"CostCenter": "CC-FIN-01"}},
            freeform_tags={"Environment": "Production", "Tier": "Data"},
            properties={
                "db_workload": "OLTP",
                "cpu_core_count": 1,
                "data_storage_size_in_tbs": 1,
                "is_auto_scaling_enabled": True,
            },
        ),
    ]
    return [r.model_dump() for r in records]
