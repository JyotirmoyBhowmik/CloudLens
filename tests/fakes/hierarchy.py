"""In-memory test fake for HierarchyRepository (Prompt P07 / Prompt 38)."""

from __future__ import annotations

import builtins
import threading

from domain.hierarchy.models import InventoryResource35, SavedInventoryView
from domain.tenant.context import TenantContext


class InMemoryHierarchyRepository:
    """In-memory repository fake for hierarchy resources and saved views."""

    is_in_memory: bool = True

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._resources: dict[tuple[str, str], InventoryResource35] = {}
        self._views: dict[tuple[str, str], SavedInventoryView] = {}

    def _validate_tenant_context(self, tenant_context: TenantContext) -> None:
        if not tenant_context or not tenant_context.tenant_id:
            raise ValueError("Operation requires valid TenantContext with non-empty tenant_id.")

    def save_resource(
        self, resource: InventoryResource35, *, tenant_context: TenantContext
    ) -> InventoryResource35:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            self._resources[(tenant_context.tenant_id, resource.id)] = resource.model_copy()
            return resource

    def get_resource(
        self, resource_id: str, *, tenant_context: TenantContext | None = None
    ) -> InventoryResource35 | None:
        with self._lock:
            if tenant_context:
                res = self._resources.get((tenant_context.tenant_id, resource_id))
            else:
                res = next((r for (_, rid), r in self._resources.items() if rid == resource_id), None)
            return res.model_copy() if res else None

    def list_resources(
        self, *, tenant_context: TenantContext | None = None, limit: int = 1000
    ) -> builtins.list[InventoryResource35]:
        with self._lock:
            if tenant_context:
                items = [
                    r.model_copy()
                    for (tid, _), r in self._resources.items()
                    if tid == tenant_context.tenant_id
                ]
            else:
                items = [r.model_copy() for r in self._resources.values()]
            return items[:limit]

    def delete_resource(self, resource_id: str, *, tenant_context: TenantContext) -> bool:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            key = (tenant_context.tenant_id, resource_id)
            if key in self._resources:
                del self._resources[key]
                return True
            return False

    def save_saved_view(
        self, view: SavedInventoryView, *, tenant_context: TenantContext
    ) -> SavedInventoryView:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            self._views[(tenant_context.tenant_id, view.id)] = view.model_copy()
            return view

    def get_saved_view(
        self, view_id: str, *, tenant_context: TenantContext
    ) -> SavedInventoryView | None:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            v = self._views.get((tenant_context.tenant_id, view_id))
            return v.model_copy() if v else None

    def list_saved_views(
        self, *, tenant_context: TenantContext
    ) -> builtins.list[SavedInventoryView]:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            return [
                v.model_copy()
                for (tid, _), v in self._views.items()
                if tid == tenant_context.tenant_id
            ]

    def delete_saved_view(self, view_id: str, *, tenant_context: TenantContext) -> bool:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            key = (tenant_context.tenant_id, view_id)
            if key in self._views:
                del self._views[key]
                return True
            return False


from datetime import datetime, UTC
from decimal import Decimal


def _corp_email(username: str) -> str:
    return f"{username}@cloudlens.corp"


TEST_SPECS = [
    # AWS Production (sc-aws-prod-1)
    (
        "res-aws-vm-01", "sc-aws-prod-1", "i-09f87238a111", "prod-payment-worker-1",
        "AWS", "AmazonEC2", "Amazon Elastic Compute Cloud", "Compute", "ec2:instance",
        "VirtualMachine", "us-east-1", "US East (N. Virginia)", "us-east-1a", "PAID",
        "RUNNING", "ACTIVE",
        [
            {"key": "Environment", "value": "Production"},
            {"key": "CostCenter", "value": "CC-101-FINOPS"},
            {"key": "Owner", "value": "Alice Engineer"},
            {"key": "Project", "value": "Payments Modernization"},
        ],
        "app-payments", "Payments Core", "env-prod", "Production",
        "usr-alice", "Alice Engineer", _corp_email("alice.engineer"),
        "cc-101", "CC-101-FINOPS", "bu-finops", "FinOps",
        "prj-pay", "Payments Modernization", Decimal("142.50"),
    ),
    (
        "res-aws-vm-02", "sc-aws-prod-1", "i-08a71239b222", "prod-payment-worker-2",
        "AWS", "AmazonEC2", "Amazon Elastic Compute Cloud", "Compute", "ec2:instance",
        "VirtualMachine", "us-east-1", "US East (N. Virginia)", "us-east-1b", "PAID",
        "RUNNING", "ACTIVE",
        [
            {"key": "Environment", "value": "Production"},
            {"key": "CostCenter", "value": "CC-101-FINOPS"},
            {"key": "Owner", "value": "Alice Engineer"},
            {"key": "Project", "value": "Payments Modernization"},
        ],
        "app-payments", "Payments Core", "env-prod", "Production",
        "usr-alice", "Alice Engineer", _corp_email("alice.engineer"),
        "cc-101", "CC-101-FINOPS", "bu-finops", "FinOps",
        "prj-pay", "Payments Modernization", Decimal("142.50"),
    ),
    (
        "res-aws-rds-01", "sc-aws-prod-1", "db-98234abcc1", "prod-payments-db",
        "AWS", "AmazonRDS", "Amazon Relational Database Service", "Database", "rds:db",
        "RelationalDatabase", "us-east-1", "US East (N. Virginia)", "us-east-1a", "PAID",
        "RUNNING", "ACTIVE",
        [
            {"key": "Environment", "value": "Production"},
            {"key": "CostCenter", "value": "CC-101-FINOPS"},
            {"key": "Owner", "value": "Bob DBA"},
            {"key": "Project", "value": "Payments Modernization"},
        ],
        "app-payments", "Payments Core", "env-prod", "Production",
        "usr-bob", "Bob DBA", _corp_email("bob.dba"),
        "cc-101", "CC-101-FINOPS", "bu-finops", "FinOps",
        "prj-pay", "Payments Modernization", Decimal("920.00"),
    ),
    (
        "res-aws-eks-01", "sc-aws-prod-1", "arn:aws:eks:us-east-1:112233440001:cluster/prod-core-eks", "prod-core-eks",
        "AWS", "AmazonEKS", "Amazon Elastic Kubernetes Service", "Containers", "eks:cluster",
        "KubernetesCluster", "us-east-1", "US East (N. Virginia)", "us-east-1a", "PAID",
        "RUNNING", "ACTIVE",
        [
            {"key": "Environment", "value": "Production"},
            {"key": "CostCenter", "value": "CC-102-ENG"},
            {"key": "Owner", "value": "Alice Engineer"},
            {"key": "Project", "value": "Payments Modernization"},
        ],
        "app-payments", "Payments Core", "env-prod", "Production",
        "usr-alice", "Alice Engineer", _corp_email("alice.engineer"),
        "cc-202", "CC-202-ENG", "bu-eng", "Engineering",
        "prj-pay", "Payments Modernization", Decimal("1450.00"),
    ),
    # AWS Dev Sandbox (sc-aws-dev-1)
    (
        "res-aws-vm-dev", "sc-aws-dev-1", "i-dev0192384a", "dev-payment-sandbox",
        "AWS", "AmazonEC2", "Amazon Elastic Compute Cloud", "Compute", "ec2:instance",
        "VirtualMachine", "us-east-1", "US East (N. Virginia)", "us-east-1a", "PAID",
        "STOPPED", "ACTIVE",
        [
            {"key": "Environment", "value": "Development"},
            {"key": "CostCenter", "value": "CC-102-ENG"},
            {"key": "Owner", "value": "Alice Engineer"},
        ],
        "app-payments", "Payments Core", "env-dev", "Development",
        "usr-alice", "Alice Engineer", _corp_email("alice.engineer"),
        "cc-102", "CC-102-ENG", "bu-eng", "Engineering",
        "prj-pay", "Payments Modernization", Decimal("230.00"),
    ),
    (
        "res-aws-s3-01", "sc-aws-dev-1", "cloudlens-dev-artifacts-bucket", "dev-artifacts-bucket",
        "AWS", "AmazonS3", "Amazon Simple Storage Service", "Storage", "s3:bucket",
        "ObjectStorage", "us-east-1", "US East (N. Virginia)", None, "FREE_TIER",
        "RUNNING", "ACTIVE",
        [
            {"key": "Environment", "value": "Development"},
            {"key": "CostCenter", "value": "CC-102-ENG"},
        ],
        "app-payments", "Payments Core", "env-dev", "Development",
        "usr-alice", "Alice Engineer", _corp_email("alice.engineer"),
        "cc-102", "CC-102-ENG", "bu-eng", "Engineering",
        "prj-pay", "Payments Modernization", Decimal("35.00"),
    ),
    # Azure Corporate Production (sc-azure-prod-1)
    (
        "res-az-vm-01", "sc-azure-prod-1",
        "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-checkout-prod/providers/Microsoft.Compute/virtualMachines/vm-checkout-worker-1",
        "vm-checkout-worker-1", "Azure", "VirtualMachines", "Azure Virtual Machines", "Compute",
        "Microsoft.Compute/virtualMachines", "VirtualMachine", "eastus", "East US", "1", "PAID",
        "RUNNING", "ACTIVE",
        [
            {"key": "Environment", "value": "Production"},
            {"key": "CostCenter", "value": "CC-101-FINOPS"},
            {"key": "Owner", "value": "Carol Ops"},
            {"key": "Project", "value": "Checkout Replatform"},
        ],
        "app-checkout", "Checkout Service", "env-prod", "Production",
        "usr-carol", "Carol Ops", _corp_email("carol.ops"),
        "cc-101", "CC-101-FINOPS", "bu-finops", "FinOps",
        "prj-chk", "Checkout Replatform", Decimal("320.00"),
    ),
    (
        "res-az-sql-01", "sc-azure-prod-1",
        "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-checkout-prod/providers/Microsoft.Sql/servers/sql-chk-srv/databases/db-checkout",
        "db-checkout-primary", "Azure", "AzureSQLDatabase", "Azure SQL Database", "Database",
        "Microsoft.Sql/servers/databases", "RelationalDatabase", "eastus", "East US", "1", "PAID",
        "RUNNING", "ACTIVE",
        [
            {"key": "Environment", "value": "Production"},
            {"key": "CostCenter", "value": "CC-101-FINOPS"},
            {"key": "Owner", "value": "Carol Ops"},
            {"key": "Project", "value": "Checkout Replatform"},
        ],
        "app-checkout", "Checkout Service", "env-prod", "Production",
        "usr-carol", "Carol Ops", _corp_email("carol.ops"),
        "cc-101", "CC-101-FINOPS", "bu-finops", "FinOps",
        "prj-chk", "Checkout Replatform", Decimal("1150.00"),
    ),
    (
        "res-az-aks-01", "sc-azure-prod-1",
        "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-inventory-prod/providers/Microsoft.ContainerService/managedClusters/aks-inventory-cluster",
        "aks-inventory-cluster", "Azure", "AzureKubernetesService", "Azure Kubernetes Service (AKS)", "Containers",
        "Microsoft.ContainerService/managedClusters", "KubernetesCluster", "eastus", "East US", "2", "PAID",
        "RUNNING", "ACTIVE",
        [
            {"key": "Environment", "value": "Production"},
            {"key": "CostCenter", "value": "CC-102-ENG"},
            {"key": "Owner", "value": "Carol Ops"},
            {"key": "Project", "value": "Inventory Sync"},
        ],
        "app-inventory", "Inventory Mgmt", "env-prod", "Production",
        "usr-carol", "Carol Ops", _corp_email("carol.ops"),
        "cc-102", "CC-102-ENG", "bu-eng", "Engineering",
        "prj-inv", "Inventory Sync", Decimal("980.00"),
    ),
    # GCP BigData Analytics (sc-gcp-analytics-1)
    (
        "res-gcp-bq-01", "sc-gcp-analytics-1",
        "projects/gcp-bigdata-prod/datasets/edw_customer_analytics", "edw-customer-analytics-ds",
        "GCP", "BigQuery", "Google Cloud BigQuery", "Analytics",
        "bigquery:dataset", "AnalyticsDataset", "us-central1", "Iowa", None, "PAID",
        "RUNNING", "ACTIVE",
        [
            {"key": "Environment", "value": "Production"},
            {"key": "CostCenter", "value": "CC-103-DATA"},
            {"key": "Owner", "value": "Dave Architect"},
            {"key": "Project", "value": "Customer 360 EDW"},
        ],
        "app-analytics", "Customer Analytics", "env-prod", "Production",
        "usr-dave", "Dave Architect", _corp_email("dave.architect"),
        "cc-103", "CC-103-DATA", "bu-data", "Data & AI",
        "prj-c360", "Customer 360", Decimal("840.00"),
    ),
    (
        "res-gcp-gke-01", "sc-gcp-analytics-1",
        "projects/gcp-bigdata-prod/zones/us-central1-a/clusters/gke-data-ingest", "gke-data-ingest-cluster",
        "GCP", "GoogleKubernetesEngine", "Google Kubernetes Engine (GKE)", "Containers",
        "container:cluster", "KubernetesCluster", "us-central1", "Iowa", "us-central1-a", "PAID",
        "RUNNING", "ACTIVE",
        [
            {"key": "Environment", "value": "Production"},
            {"key": "CostCenter", "value": "CC-103-DATA"},
            {"key": "Owner", "value": "Dave Architect"},
            {"key": "Project", "value": "Customer 360 EDW"},
        ],
        "app-analytics", "Customer Analytics", "env-prod", "Production",
        "usr-dave", "Dave Architect", _corp_email("dave.architect"),
        "cc-103", "CC-103-DATA", "bu-data", "Data & AI",
        "prj-c360", "Customer 360", Decimal("1320.00"),
    ),
    (
        "res-gcp-gcs-01", "sc-gcp-analytics-1",
        "gcp-raw-lake-landing-us", "gcp-raw-lake-landing-us",
        "GCP", "CloudStorage", "Google Cloud Storage", "Storage",
        "storage:bucket", "ObjectStorage", "us-central1", "Iowa", None, "PAID",
        "RUNNING", "ACTIVE",
        [
            {"key": "Environment", "value": "Production"},
            {"key": "CostCenter", "value": "CC-103-DATA"},
        ],
        "app-warehouse", "Data Warehouse", "env-prod", "Production",
        None, "Unowned", None,
        "cc-103", "CC-103-DATA", "bu-data", "Data & AI",
        "prj-dlake", "Data Lakehouse", Decimal("310.00"),
    ),
    # OCI Core Infrastructure (sc-oci-core-1)
    (
        "res-oci-vm-01", "sc-oci-core-1",
        "ocid1.instance.oc1.iad.anuwcljra111", "oci-core-compute-01",
        "OCI", "OracleCompute", "Oracle Cloud Infrastructure Compute", "Compute",
        "oci:core:instance", "VirtualMachine", "us-ashburn-1", "US East (Ashburn)", "AD-1", "PAID",
        "RUNNING", "ACTIVE",
        [
            {"key": "Environment", "value": "Production"},
            {"key": "CostCenter", "value": "CC-101-FINOPS"},
            {"key": "Owner", "value": "Alice Engineer"},
            {"key": "Project", "value": "Disaster Recovery"},
        ],
        "app-payments", "Payments Core", "env-prod", "Production",
        "usr-alice", "Alice Engineer", _corp_email("alice.engineer"),
        "cc-101", "CC-101-FINOPS", "bu-finops", "FinOps",
        "prj-dr", "Disaster Recovery Sync", Decimal("280.00"),
    ),
    (
        "res-oci-adb-01", "sc-oci-core-1",
        "ocid1.autonomousdatabase.oc1.iad.anuwcljrb222", "oci-autonomous-db-core",
        "OCI", "OracleAutonomousDatabase", "Oracle Autonomous Database", "Database",
        "oci:database:autonomousdatabase", "AutonomousDatabase", "us-ashburn-1", "US East (Ashburn)", "AD-1", "PAID",
        "RUNNING", "ACTIVE",
        [
            {"key": "Environment", "value": "Production"},
            {"key": "CostCenter", "value": "CC-101-FINOPS"},
            {"key": "Owner", "value": "Bob DBA"},
            {"key": "Project", "value": "Disaster Recovery"},
        ],
        "app-payments", "Payments Core", "env-prod", "Production",
        "usr-bob", "Bob DBA", _corp_email("bob.dba"),
        "cc-101", "CC-101-FINOPS", "bu-finops", "FinOps",
        "prj-dr", "Disaster Recovery Sync", Decimal("1250.00"),
    ),
    (
        "res-aws-kms-01", "sc-aws-prod-1",
        "arn:aws:kms:us-east-1:112233440001:key/12345678", "prod-master-key",
        "AWS", "KeyManagementService", "AWS Key Management Service", "Security",
        "kms:key", "KeyManagementService", "us-east-1", "US East (N. Virginia)", None, "PAID",
        "RUNNING", "ACTIVE",
        [
            {"key": "Environment", "value": "Production"},
            {"key": "CostCenter", "value": "CC-104-SEC"},
            {"key": "Owner", "value": "Sam Security"},
            {"key": "Project", "value": "Security Hardening"},
        ],
        "app-security", "Security Core", "env-prod", "Production",
        "usr-sam", "Sam Security", _corp_email("sam.security"),
        "cc-104", "CC-104-SEC", "bu-sec", "Security",
        "prj-sec", "Security Hardening", Decimal("45.00"),
    ),
]


def seed_test_hierarchy(repo: InMemoryHierarchyRepository, tenant_id: str = "default-tenant") -> None:
    now = datetime.now(UTC)
    tc = TenantContext(tenant_id=tenant_id, user_id="test-seed", scope_grants=["*"])
    for s in TEST_SPECS:
        r = InventoryResource35(
            id=s[0],
            tenant_id=tenant_id,
            scope_id=s[1],
            native_id=s[2],
            name=s[3],
            provider=s[4],
            service_id=s[5],
            service_name=s[6],
            service_category=s[7],
            resource_type_id=s[8],
            resource_type=s[9],
            region_id=s[10],
            region_name=s[11],
            availability_zone=s[12],
            pricing_status=s[13],
            runtime_state=s[14],
            lifecycle_status=s[15],
            tags=s[16],
            application_id=s[17],
            application_name=s[18],
            environment_id=s[19],
            environment_name=s[20],
            owner_id=s[21],
            owner_name=s[22],
            owner_email=s[23],
            cost_center_id=s[24],
            cost_center_name=s[25],
            business_unit_id=s[26],
            business_unit_name=s[27],
            project_id=s[28],
            project_name=s[29],
            monthly_cost=s[30],
            currency="USD",
            last_synced_at=now,
            created_at=now,
        )
        repo.save_resource(r, tenant_context=tc)

    v = SavedInventoryView(
        id="view-prod-compute",
        user_id="finops-admin",
        name="Production Compute View",
        filters={"providers": ["AWS", "Azure"], "environments": ["Production"]},
        created_at=now,
    )
    repo.save_saved_view(v, tenant_context=tc)

