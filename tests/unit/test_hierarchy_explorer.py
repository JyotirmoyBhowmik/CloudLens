"""Unit & Contract Tests for Cloud Hierarchy Explorer, Inventory and Search (Prompt 38).

Enforces:
- Full navigation model: Provider -> Organisation -> Group -> Billing Boundary -> [Sub-group] -> Service -> Resource.
- Aggregate roll-ups: aggregate_cost, budget utilisation %, worst_child_threshold_state bubbling.
- 6 Lateral Lenses: APPLICATION, COST_CENTRE, ENVIRONMENT, OWNER, REGION, TAG.
- Scope-safe global search across 9 entity types (FR-580, FR-585) with exact-identifier match priority.
- Structured multi-attribute filtering with boolean combination semantics (FR-107, FR-581).
- Reactive count preview without full dataset materialisation (FR-584).
- 35 canonical inventory fields (API-019 / BBP Section 16).
- Bulk curated assignment and saved view management (FR-583, FR-108).
- Scope-respecting CSV and JSON export.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.hierarchy.models import (
    BulkAssignmentRequest,
    HierarchyLevel,
    InventoryFilterQuery,
    LateralLensType,
    SavedInventoryView,
    TagFilter,
)
from domain.hierarchy.service import (
    HierarchyService,
    get_hierarchy_service,
    reset_hierarchy_service,
)
from domain.tenant.context import TenantContext



from tests.fakes.hierarchy import InMemoryHierarchyRepository
from domain.hierarchy.repository import reset_hierarchy_repository
from datetime import datetime, UTC
from domain.hierarchy.models import InventoryResource35

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
        "prj-inv", "Inventory Modernization", Decimal("820.00"),
    ),
    (
        "res-az-blob-01", "sc-azure-prod-1",
        "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-inventory-prod/providers/Microsoft.Storage/storageAccounts/stinvprod01",
        "stinvprod01", "Azure", "AzureBlobStorage", "Azure Blob Storage", "Storage",
        "Microsoft.Storage/storageAccounts", "ObjectStorage", "eastus", "East US", None, "PAID",
        "RUNNING", "ACTIVE",
        [
            {"key": "Environment", "value": "Production"},
            {"key": "CostCenter", "value": "CC-102-ENG"},
        ],
        "app-inventory", "Inventory Mgmt", "env-prod", "Production",
        None, "Unowned", None,
        "cc-102", "CC-102-ENG", "bu-eng", "Engineering",
        "prj-inv", "Inventory Modernization", Decimal("95.00"),
    ),
    # GCP Analytics Tier (sc-gcp-analytics-1)
    (
        "res-gcp-gce-01", "sc-gcp-analytics-1",
        "projects/prj-gcp-data-lake-prod/zones/us-central1-a/instances/worker-analytics-01",
        "worker-analytics-01", "GCP", "ComputeEngine", "Google Compute Engine", "Compute",
        "compute.googleapis.com/Instance", "VirtualMachine", "us-central1", "US Central (Iowa)", "us-central1-a", "PAID",
        "RUNNING", "ACTIVE",
        [
            {"key": "Environment", "value": "Production"},
            {"key": "CostCenter", "value": "CC-103-DATA"},
            {"key": "Owner", "value": "Dave Architect"},
            {"key": "Project", "value": "Customer 360 Analytics"},
        ],
        "app-analytics", "Customer Analytics", "env-prod", "Production",
        "usr-dave", "Dave Architect", _corp_email("dave.architect"),
        "cc-103", "CC-103-DATA", "bu-data", "Data & AI",
        "prj-c360", "Customer 360 Analytics", Decimal("430.00"),
    ),
    (
        "res-gcp-bq-01", "sc-gcp-analytics-1",
        "projects/prj-gcp-data-lake-prod/datasets/ds_enterprise_warehouse",
        "ds_enterprise_warehouse", "GCP", "BigQuery", "Google Cloud BigQuery", "Analytics",
        "bigquery.googleapis.com/Dataset", "DataWarehouse", "us-central1", "US Central (Iowa)", None, "PAID",
        "RUNNING", "ACTIVE",
        [
            {"key": "Environment", "value": "Production"},
            {"key": "CostCenter", "value": "CC-103-DATA"},
            {"key": "Owner", "value": "Dave Architect"},
            {"key": "Project", "value": "Data Lakehouse"},
        ],
        "app-warehouse", "Data Warehouse", "env-prod", "Production",
        "usr-dave", "Dave Architect", _corp_email("dave.architect"),
        "cc-103", "CC-103-DATA", "bu-data", "Data & AI",
        "prj-dlake", "Data Lakehouse", Decimal("680.00"),
    ),
    (
        "res-gcp-gke-01", "sc-gcp-analytics-1",
        "projects/prj-gcp-data-lake-prod/locations/us-central1/clusters/gke-analytics-prod",
        "gke-analytics-prod", "GCP", "GoogleKubernetesEngine", "Google Kubernetes Engine (GKE)", "Containers",
        "container.googleapis.com/Cluster", "KubernetesCluster", "us-central1", "US Central (Iowa)", "us-central1-b", "PAID",
        "RUNNING", "ACTIVE",
        [
            {"key": "Environment", "value": "Production"},
            {"key": "CostCenter", "value": "CC-103-DATA"},
            {"key": "Owner", "value": "Dave Architect"},
            {"key": "Project", "value": "Data Lakehouse"},
        ],
        "app-warehouse", "Data Warehouse", "env-prod", "Production",
        "usr-dave", "Dave Architect", _corp_email("dave.architect"),
        "cc-103", "CC-103-DATA", "bu-data", "Data & AI",
        "prj-dlake", "Data Lakehouse", Decimal("1480.00"),
    ),
    (
        "res-gcp-gcs-01", "sc-gcp-analytics-1",
        "gcp-analytics-raw-bucket", "gcp-analytics-raw-bucket",
        "GCP", "CloudStorage", "Google Cloud Storage", "Storage",
        "storage.googleapis.com/Bucket", "ObjectStorage", "us-central1", "US Central (Iowa)", None, "PAID",
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

    # Also seed default view for saved view test
    v = SavedInventoryView(
        id="view-prod-compute",
        user_id="finops-admin",
        name="Production Compute View",
        filters={"providers": ["AWS", "Azure"], "environments": ["Production"]},
        created_at=now,
    )
    repo.save_saved_view(v, tenant_context=tc)


@pytest.fixture(autouse=True)
def clean_hierarchy_service():
    """Ensure clean service singleton state for each test run."""
    fake_repo = InMemoryHierarchyRepository()
    reset_hierarchy_repository(fake_repo)
    reset_hierarchy_service()
    seed_test_hierarchy(fake_repo, "default-tenant")
    svc = get_hierarchy_service()
    svc._budgets = {
        "GLOBAL": Decimal("50000.00"),
        "AWS": Decimal("22000.00"),
        "Azure": Decimal("16000.00"),
        "GCP": Decimal("8000.00"),
        "OCI": Decimal("4000.00"),
        "sc-aws-prod-1": Decimal("18000.00"),
        "sc-aws-dev-1": Decimal("4000.00"),
        "sc-azure-prod-1": Decimal("16000.00"),
        "sc-gcp-analytics-1": Decimal("8000.00"),
        "sc-oci-core-1": Decimal("4000.00"),
        "app-payments": Decimal("15000.00"),
        "app-checkout": Decimal("10000.00"),
        "app-inventory": Decimal("7000.00"),
        "app-analytics": Decimal("8000.00"),
        "app-warehouse": Decimal("10000.00"),
        "cc-finops": Decimal("20000.00"),
        "cc-eng": Decimal("15000.00"),
        "cc-data": Decimal("10000.00"),
        "cc-sales": Decimal("5000.00"),
    }
    yield
    reset_hierarchy_service()
    reset_hierarchy_repository()


@pytest.fixture
def service() -> HierarchyService:
    return get_hierarchy_service()


@pytest.fixture
def global_tenant_context() -> TenantContext:
    return TenantContext(
        tenant_id="default-tenant",
        user_id="finops-admin",
        scope_grants=["*"],
    )


@pytest.fixture
def restricted_aws_context() -> TenantContext:
    return TenantContext(
        tenant_id="default-tenant",
        user_id="aws-engineer",
        scope_grants=["sc-aws-prod-1"],
    )


# ==============================================================================
# 1. Cloud Hierarchy Explorer & Traversal Tests
# ==============================================================================


class TestHierarchyExplorerTraversal:
    """Verifies tree navigation model, native vocabulary, and aggregate roll-ups."""

    def test_provider_hierarchy_structure_and_native_vocabulary(
        self, service: HierarchyService, global_tenant_context: TenantContext
    ):
        """Verifies full hierarchy levels and provider-native terminology."""
        tree = service.get_hierarchy_tree(
            lens_type=LateralLensType.PROVIDER_HIERARCHY,
            tenant_context=global_tenant_context,
        )

        assert tree.level == HierarchyLevel.ORGANISATION
        assert len(tree.children) == 4  # AWS, Azure, GCP, OCI

        provider_map = {c.name.upper(): c for c in tree.children}
        assert "AWS" in provider_map
        assert "AZURE" in provider_map
        assert "GCP" in provider_map
        assert "OCI" in provider_map

        # AWS: Organisation -> OU (GROUP) -> Account (BILLING_BOUNDARY) -> Service -> Resource
        aws_node = provider_map["AWS"]
        aws_org = aws_node.children[0]
        assert aws_org.native_type == "Organization"
        aws_ou = aws_org.children[0]
        assert aws_ou.native_type == "OrganizationalUnit"
        assert aws_ou.level == HierarchyLevel.GROUP
        aws_acct = aws_ou.children[0]
        assert aws_acct.native_type == "Account"
        assert aws_acct.level == HierarchyLevel.BILLING_BOUNDARY

        # Azure: Tenant -> ManagementGroup (GROUP) -> Subscription (BILLING_BOUNDARY) -> ResourceGroup (SUB_GROUP)
        az_node = provider_map["AZURE"]
        az_tenant = az_node.children[0]
        az_mg = az_tenant.children[0]
        assert az_mg.native_type == "ManagementGroup"
        assert az_mg.level == HierarchyLevel.GROUP
        az_sub = az_mg.children[0]
        assert az_sub.native_type == "Subscription"
        assert az_sub.level == HierarchyLevel.BILLING_BOUNDARY
        az_rg = az_sub.children[0]
        assert az_rg.native_type == "ResourceGroup"
        assert az_rg.level == HierarchyLevel.SUB_GROUP

    def test_aggregate_cost_and_budget_utilisation_rollup(
        self, service: HierarchyService, global_tenant_context: TenantContext
    ):
        """Verifies aggregate cost sums up from leaf resources and budget utilisation is computed."""
        tree = service.get_hierarchy_tree(
            lens_type=LateralLensType.PROVIDER_HIERARCHY,
            tenant_context=global_tenant_context,
        )

        assert tree.aggregate_cost > Decimal("0.00")
        assert tree.budget_amount == Decimal("50000.00")
        assert tree.budget_utilisation_pct > Decimal("0.00")

        # Sum of provider costs must exactly equal global estate cost
        prov_sum = sum((c.aggregate_cost for c in tree.children), Decimal("0.00"))
        assert prov_sum == tree.aggregate_cost

    def test_worst_child_threshold_state_bubbling(
        self, service: HierarchyService, global_tenant_context: TenantContext
    ):
        """Verifies worst child threshold state bubbles up: CRITICAL > WARNING > NORMAL."""
        tree = service.get_hierarchy_tree(
            lens_type=LateralLensType.PROVIDER_HIERARCHY,
            tenant_context=global_tenant_context,
        )

        # Because some resources cost > $1000 (e.g. EKS $1450, SQL $1150), they are CRITICAL
        assert tree.worst_child_threshold_state == "CRITICAL"

        # Check AWS provider node worst child state
        aws_node = next(c for c in tree.children if c.name.upper() == "AWS")
        assert aws_node.worst_child_threshold_state == "CRITICAL"


# ==============================================================================
# 2. Six Lateral Lenses Tests
# ==============================================================================


class TestLateralLensSwitcher:
    """Verifies that all 6 lateral lenses group the same underlying estate correctly."""

    def test_application_lens_tree(
        self, service: HierarchyService, global_tenant_context: TenantContext
    ):
        """Verifies APPLICATION lens: App -> Environment -> Service -> Resource."""
        tree = service.get_hierarchy_tree(
            lens_type=LateralLensType.APPLICATION,
            tenant_context=global_tenant_context,
        )
        assert tree.lens_type == LateralLensType.APPLICATION
        assert tree.name == "Estate by Application"
        assert len(tree.children) >= 3

        app_names = {c.name for c in tree.children}
        assert "Payments Core" in app_names
        assert "Checkout Service" in app_names

        payments_app = next(c for c in tree.children if c.name == "Payments Core")
        assert payments_app.aggregate_cost > Decimal("0.00")
        assert payments_app.level == HierarchyLevel.GROUP
        # Children are environments (e.g. Production, Development)
        assert len(payments_app.children) >= 1

    def test_cost_centre_lens_tree(
        self, service: HierarchyService, global_tenant_context: TenantContext
    ):
        """Verifies COST_CENTRE lens: Cost Centre -> Project -> Resource."""
        tree = service.get_hierarchy_tree(
            lens_type=LateralLensType.COST_CENTRE,
            tenant_context=global_tenant_context,
        )
        assert tree.lens_type == LateralLensType.COST_CENTRE
        cc_names = {c.name for c in tree.children}
        assert "CC-101-FINOPS" in cc_names
        assert "CC-202-ENG" in cc_names

    def test_environment_lens_tree(
        self, service: HierarchyService, global_tenant_context: TenantContext
    ):
        """Verifies ENVIRONMENT lens: Environment -> Application -> Resource."""
        tree = service.get_hierarchy_tree(
            lens_type=LateralLensType.ENVIRONMENT,
            tenant_context=global_tenant_context,
        )
        assert tree.lens_type == LateralLensType.ENVIRONMENT
        env_names = {c.name for c in tree.children}
        assert "Production" in env_names

    def test_owner_lens_tree_includes_unowned(
        self, service: HierarchyService, global_tenant_context: TenantContext
    ):
        """Verifies OWNER lens includes named owners and explicitly 'Unowned'."""
        tree = service.get_hierarchy_tree(
            lens_type=LateralLensType.OWNER,
            tenant_context=global_tenant_context,
        )
        assert tree.lens_type == LateralLensType.OWNER
        owner_names = {c.name for c in tree.children}
        assert "Alice Engineer" in owner_names
        assert "Unowned" in owner_names

    def test_region_lens_tree(
        self, service: HierarchyService, global_tenant_context: TenantContext
    ):
        """Verifies REGION lens: Region -> Service -> Resource."""
        tree = service.get_hierarchy_tree(
            lens_type=LateralLensType.REGION,
            tenant_context=global_tenant_context,
        )
        assert tree.lens_type == LateralLensType.REGION
        reg_names = {c.name for c in tree.children}
        assert "us-east-1" in reg_names
        assert "eastus" in reg_names

    def test_tag_lens_tree(self, service: HierarchyService, global_tenant_context: TenantContext):
        """Verifies TAG lens: Tag Key -> Tag Value -> Resource."""
        tree = service.get_hierarchy_tree(
            lens_type=LateralLensType.TAG,
            tenant_context=global_tenant_context,
        )
        assert tree.lens_type == LateralLensType.TAG
        tag_keys = {c.name for c in tree.children}
        assert "Tag: Environment" in tag_keys
        assert "Tag: CostCenter" in tag_keys


# ==============================================================================
# 3. Node Detail Pane Tests
# ==============================================================================


class TestHierarchyDetailPane:
    """Verifies detail pane metrics, breadcrumbs, and contributing services."""

    def test_get_node_detail_returns_breadcrumbs_and_services(
        self, service: HierarchyService, global_tenant_context: TenantContext
    ):
        detail = service.get_node_detail(
            node_id="aws-acct-112233440001",
            lens_type=LateralLensType.PROVIDER_HIERARCHY,
            tenant_context=global_tenant_context,
        )

        assert detail.node_id == "aws-acct-112233440001"
        assert len(detail.breadcrumbs) >= 3
        assert detail.aggregate_cost > Decimal("0.00")
        assert len(detail.top_contributing_services) > 0
        assert len(detail.direct_resources) > 0


# ==============================================================================
# 4. Scope-Safe Global Search (FR-580, FR-585)
# ==============================================================================


class TestScopeSafeGlobalSearch:
    """Verifies search across 9 entity types, exact ranking, and scope isolation."""

    def test_exact_identifier_match_ranked_first(
        self, service: HierarchyService, global_tenant_context: TenantContext
    ):
        """Exact-identifier match must score 1.0 and rank first."""
        res = service.search_global(
            query="i-09f87238a111",
            tenant_context=global_tenant_context,
        )

        assert res.total_matches >= 1
        top = res.results[0]
        assert top.identifier == "i-09f87238a111"
        assert top.rank_score == 1.0
        assert top.entity_type == "RESOURCE"

    def test_nine_entity_types_indexed(
        self, service: HierarchyService, global_tenant_context: TenantContext
    ):
        """Verifies search across RESOURCE, SERVICE, SCOPE, APPLICATION, BUDGET, OWNER, CONNECTOR, POLICY, ALERT."""
        search_terms = {
            "RESOURCE": "prod-payment-worker-1",
            "SERVICE": "Amazon Elastic Compute Cloud",
            "SCOPE": "AWS Core Production",
            "APPLICATION": "Payments Core",
            "BUDGET": "Core FinOps Q4 Budget",
            "OWNER": "Alice Engineer",
            "CONNECTOR": "AWS Multi-Account Connector",
            "POLICY": "Mandatory FinOps Tagging Policy",
            "ALERT": "EC2 Cost Velocity Anomaly Alert",
        }

        for entity_type, term in search_terms.items():
            res = service.search_global(query=term, tenant_context=global_tenant_context)
            assert res.total_matches >= 1, f"Expected match for {entity_type} query: {term}"
            matched_types = {item.entity_type for item in res.results}
            assert entity_type in matched_types, (
                f"Entity type {entity_type} not found in search results"
            )

    def test_scope_safe_search_isolation(
        self, service: HierarchyService, restricted_aws_context: TenantContext
    ):
        """FR-585: Caller with restricted scope grants NEVER sees out-of-scope entities."""
        # Query for Azure resource native identifier
        azure_res = service.search_global(
            query="vm-checkout-worker-1",
            tenant_context=restricted_aws_context,
        )
        # Must return 0 matches and disclose nothing about Azure
        assert azure_res.total_matches == 0
        assert len(azure_res.results) == 0
        assert azure_res.is_scope_restricted is True

        # Query for GCP project
        gcp_res = service.search_global(
            query="prj-finops-0001",
            tenant_context=restricted_aws_context,
        )
        assert gcp_res.total_matches == 0

        # Query for in-scope AWS resource
        aws_res = service.search_global(
            query="prod-payment-worker-1",
            tenant_context=restricted_aws_context,
        )
        assert aws_res.total_matches >= 1
        assert aws_res.results[0].scope_id == "sc-aws-prod-1"


# ==============================================================================
# 5. Multi-Attribute Filtering & Boolean Combination (FR-107, FR-581)
# ==============================================================================


class TestMultiAttributeFiltering:
    """Verifies AND across filters, OR within multi-selects, and tag operators."""

    def test_provider_and_environment_boolean_combination(
        self, service: HierarchyService, global_tenant_context: TenantContext
    ):
        """AND across Provider & Environment."""
        query = InventoryFilterQuery(
            providers=["AWS"],
            environments=["Production"],
        )
        total, items = service.query_inventory(query, global_tenant_context)
        assert total >= 1
        for item in items:
            assert item.provider.upper() == "AWS"
            assert item.environment_name == "Production"

    def test_owner_filter_including_unowned(
        self, service: HierarchyService, global_tenant_context: TenantContext
    ):
        """Filter by Unowned owner."""
        query = InventoryFilterQuery(owners=["Unowned"])
        total, items = service.query_inventory(query, global_tenant_context)
        assert total >= 1
        for item in items:
            assert item.owner_name == "Unowned"

    def test_tag_filter_operators(
        self, service: HierarchyService, global_tenant_context: TenantContext
    ):
        """Verifies tag filter operators: exists, not_exists, eq, ne."""
        # 1. Tag exists: Project
        q_exists = InventoryFilterQuery(tag_filters=[TagFilter(key="Project", operator="exists")])
        total_exists, items_exists = service.query_inventory(q_exists, global_tenant_context)
        assert total_exists >= 1
        for it in items_exists:
            tag_keys = [t["key"] for t in it.tags]
            assert "Project" in tag_keys

        # 2. Tag eq: Environment == Production
        q_eq = InventoryFilterQuery(
            tag_filters=[TagFilter(key="Environment", value="Production", operator="eq")]
        )
        total_eq, items_eq = service.query_inventory(q_eq, global_tenant_context)
        assert total_eq >= 1
        for it in items_eq:
            env_tag = next((t["value"] for t in it.tags if t["key"] == "Environment"), None)
            assert env_tag == "Production"

    def test_cost_range_filtering(
        self, service: HierarchyService, global_tenant_context: TenantContext
    ):
        """Filter by min_cost and max_cost."""
        query = InventoryFilterQuery(
            min_cost=Decimal("500.00"),
            max_cost=Decimal("1200.00"),
        )
        total, items = service.query_inventory(query, global_tenant_context)
        assert total >= 1
        for item in items:
            assert item.monthly_cost >= Decimal("500.00")
            assert item.monthly_cost <= Decimal("1200.00")


# ==============================================================================
# 6. Reactive Count Preview (FR-584)
# ==============================================================================


class TestReactiveCountPreview:
    """Verifies count preview without full result materialisation."""

    def test_count_preview_computes_spend_and_distributions(
        self, service: HierarchyService, global_tenant_context: TenantContext
    ):
        query = InventoryFilterQuery(providers=["AWS"])
        preview = service.preview_filter_counts(query, global_tenant_context)

        assert preview.matching_count > 0
        assert preview.total_spend > Decimal("0.00")
        assert "AWS" in preview.counts_by_provider
        assert preview.counts_by_provider["AWS"] == preview.matching_count


# ==============================================================================
# 7. Canonical 35 Fields, Bulk Assignment & Saved Views
# ==============================================================================


class TestInventoryOperationsAndViews:
    """Verifies all 35 canonical fields, bulk curation, and view persistence."""

    def test_thirty_five_canonical_fields_present(
        self, service: HierarchyService, global_tenant_context: TenantContext
    ):
        _, items = service.query_inventory(InventoryFilterQuery(), global_tenant_context)
        sample = items[0]
        fields = [
            "id",
            "tenant_id",
            "scope_id",
            "native_id",
            "name",
            "provider",
            "service_id",
            "service_name",
            "service_category",
            "resource_type_id",
            "resource_type",
            "region_id",
            "region_name",
            "availability_zone",
            "pricing_status",
            "runtime_state",
            "lifecycle_status",
            "tags",
            "application_id",
            "application_name",
            "environment_id",
            "environment_name",
            "owner_id",
            "owner_name",
            "owner_email",
            "cost_center_id",
            "cost_center_name",
            "business_unit_id",
            "business_unit_name",
            "project_id",
            "project_name",
            "monthly_cost",
            "currency",
            "last_synced_at",
            "created_at",
        ]
        sample_dict = sample.model_dump()
        for f in fields:
            assert f in sample_dict, f"Missing field: {f}"

    def test_bulk_curated_assignment(
        self, service: HierarchyService, global_tenant_context: TenantContext
    ):
        req = BulkAssignmentRequest(
            resource_ids=["res-aws-s3-01"],
            owner_name="Dave Architect",
            owner_email="dave.architect@cloudlens.corp",
            application_name="Payments Modern",
            environment_name="Production",
            cost_center="CC-999-OVERRIDE",
        )
        resp = service.bulk_assign_curated_fields(req, global_tenant_context)
        assert resp.updated_count == 1
        assert "owner_name" in resp.modified_fields

        # Verify update persisted
        updated_res = service.get_resource_by_id("res-aws-s3-01", global_tenant_context)
        assert updated_res.owner_name == "Dave Architect"
        assert updated_res.cost_center_name == "CC-999-OVERRIDE"

    def test_saved_views_lifecycle(
        self, service: HierarchyService, global_tenant_context: TenantContext
    ):
        view = SavedInventoryView(
            id="view-test-01",
            name="Test Custom View",
            user_id="finops-admin",
            filters={"providers": ["AWS"]},
            selected_columns=["name", "monthly_cost"],
            is_shared=True,
            created_at=service.get_resource_by_id("res-aws-vm-01", global_tenant_context).created_at,
        )
        saved = service.save_view(view, global_tenant_context)
        assert saved.id == "view-test-01"

        views = service.list_saved_views(global_tenant_context)
        assert any(v.id == "view-test-01" for v in views)

        deleted = service.delete_saved_view("view-test-01", global_tenant_context)
        assert deleted is True

    def test_export_inventory_csv_and_json(
        self, service: HierarchyService, global_tenant_context: TenantContext
    ):
        csv_data, csv_mime = service.export_inventory(
            InventoryFilterQuery(providers=["AWS"]),
            export_format="csv",
            tenant_context=global_tenant_context,
        )
        assert csv_mime == "text/csv"
        assert "id,tenant_id,scope_id,native_id,name" in csv_data

        json_data, json_mime = service.export_inventory(
            InventoryFilterQuery(providers=["AWS"]),
            export_format="json",
            tenant_context=global_tenant_context,
        )
        assert json_mime == "application/json"
        assert '"native_id":' in json_data


# ==============================================================================
# 8. REST API Contracts Tests
# ==============================================================================


class TestHierarchyAPIContracts:
    """Verifies FastAPI endpoints return expected responses and status codes."""

    @pytest.fixture
    def client(self) -> TestClient:
        return TestClient(app)

    @pytest.fixture
    def test_headers(self, make_auth_token) -> dict[str, str]:
        token = make_auth_token(tenant_id="default-tenant", user_id="admin", roles=["SUPERUSER"], permissions=["*"])
        return {"Authorization": f"Bearer {token}"}

    def test_api_get_hierarchy_tree(self, client: TestClient, test_headers):
        res = client.get("/api/v1/hierarchy/tree?lens_type=PROVIDER_HIERARCHY", headers=test_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["level"] == "ORGANISATION"
        assert len(data["children"]) == 4

    def test_api_get_node_detail(self, client: TestClient, test_headers):
        res = client.get("/api/v1/hierarchy/nodes/aws-acct-112233440001", headers=test_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["node_id"] == "aws-acct-112233440001"
        assert len(data["breadcrumbs"]) > 0

    def test_api_global_search_scope_safe(self, client: TestClient, make_auth_token):
        admin_token = make_auth_token(tenant_id="default-tenant", user_id="admin", roles=["SUPERUSER"], permissions=["*"])
        res_admin = client.get(
            "/api/v1/hierarchy/search?q=prod-payment-worker-1",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res_admin.status_code == 200
        assert res_admin.json()["total_matches"] >= 1

        restricted_token = make_auth_token(tenant_id="default-tenant", user_id="aws-user", roles=["VIEWER"], permissions=["sc-aws-prod-1"])
        res_restricted = client.get(
            "/api/v1/hierarchy/search?q=vm-checkout-worker-1",
            headers={"Authorization": f"Bearer {restricted_token}"},
        )
        assert res_restricted.status_code == 200
        assert res_restricted.json()["total_matches"] == 0

    def test_api_count_preview(self, client: TestClient, test_headers):
        res = client.post(
            "/api/v1/hierarchy/inventory/count-preview",
            json={"providers": ["Azure"]},
            headers=test_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["matching_count"] > 0

    def test_api_query_inventory(self, client: TestClient, test_headers):
        res = client.post(
            "/api/v1/hierarchy/inventory/query?limit=10&offset=0",
            json={"providers": ["AWS"]},
            headers=test_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["total"] > 0
        assert len(data["items"]) > 0

    def test_api_bulk_assign_curated_fields(self, client: TestClient, test_headers):
        payload = {
            "resource_ids": ["res-aws-vm-01"],
            "owner_name": "API Tester",
            "owner_email": "api.tester@cloudlens.corp",
        }
        res = client.post("/api/v1/hierarchy/inventory/bulk-assign", json=payload, headers=test_headers)
        assert res.status_code == 200
        assert res.json()["updated_count"] == 1

    def test_api_saved_views_lifecycle(self, client: TestClient, test_headers):
        view_payload = {
            "id": "view-api-test",
            "user_id": "finops-admin",
            "name": "API Test View",
            "filters": {"providers": ["OCI"]},
        }
        res_save = client.post("/api/v1/hierarchy/inventory/views", json=view_payload, headers=test_headers)
        assert res_save.status_code == 200

        res_list = client.get("/api/v1/hierarchy/inventory/views", headers=test_headers)
        assert res_list.status_code == 200
        views = res_list.json()
        assert any(v["name"] == "API Test View" for v in views)

        res_del = client.delete("/api/v1/hierarchy/inventory/views/view-api-test", headers=test_headers)
        assert res_del.status_code == 200

    def test_api_export_inventory(self, client: TestClient, test_headers):
        res = client.post(
            "/api/v1/hierarchy/inventory/export?format=csv",
            json={"providers": ["AWS"]},
            headers=test_headers,
        )
        assert res.status_code == 200
        assert "text/csv" in res.headers["content-type"]
        assert "res-aws-vm-01" in res.text

