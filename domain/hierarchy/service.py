"""Domain Service for Hierarchy Explorer, Inventory, and Search (Prompt 38).

Enforces:
- Full navigation model: Provider -> Organisation -> Group -> Billing Boundary -> Sub-group -> Service -> Resource.
- Aggregate roll-ups: aggregate_cost, budget_amount, budget_utilisation_pct, and worst_child_threshold_state at every level.
- Lateral lens switcher: 6 alternative entry points (APPLICATION, COST_CENTRE, ENVIRONMENT, OWNER, REGION, TAG).
- 35 canonical inventory fields (API-019 / BBP Section 16).
- Scope-safe global search across 9 entity types (FR-580, FR-585) with exact-identifier match priority.
- Structured multi-attribute filtering with boolean combination semantics (FR-107, FR-581).
- Reactive count preview without loading full result sets (FR-584).
- Bulk curated field assignments and saved custom views (FR-583).
"""

from __future__ import annotations

import csv
import io
import json
import threading
from datetime import UTC, datetime
from decimal import Decimal

from domain.hierarchy.models import (
    BulkAssignmentRequest,
    BulkAssignmentResponse,
    FilterCountPreview,
    GlobalSearchItem,
    GlobalSearchResponse,
    HierarchyDetailPane,
    HierarchyLevel,
    HierarchyNode,
    InventoryFilterQuery,
    InventoryResource35,
    LateralLensType,
    SavedInventoryView,
)
from domain.tenant.context import TenantContext


class HierarchyService:
    """Enterprise domain service for hierarchy traversal, inventory, and search."""

    def __init__(self) -> None:
        self._resources: dict[str, InventoryResource35] = {}
        self._budgets: dict[str, Decimal] = {}
        self._saved_views: dict[str, SavedInventoryView] = {}
        self._seed_estate_if_empty()

    def _seed_estate_if_empty(self) -> None:
        """Seeds deterministic multi-cloud enterprise estate across AWS, Azure, GCP, and OCI."""
        if self._resources:
            return

        now = datetime.now(UTC)

        # 1. Budget registry for organizational scopes and nodes
        self._budgets = {
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

        # 2. Seed canonical 35-field resources across 4 providers
        specs = [
            # AWS Production (sc-aws-prod-1)
            (
                "res-aws-vm-01",
                "sc-aws-prod-1",
                "i-09f87238a111",
                "prod-payment-worker-1",
                "AWS",
                "AmazonEC2",
                "Amazon Elastic Compute Cloud",
                "Compute",
                "ec2:instance",
                "VirtualMachine",
                "us-east-1",
                "US East (N. Virginia)",
                "us-east-1a",
                "PAID",
                "RUNNING",
                "ACTIVE",
                [
                    {"key": "Environment", "value": "Production"},
                    {"key": "CostCenter", "value": "CC-101-FINOPS"},
                    {"key": "Owner", "value": "Alice Engineer"},
                    {"key": "Project", "value": "Payments Modernization"},
                ],
                "app-payments",
                "Payments Core",
                "env-prod",
                "Production",
                "usr-alice",
                "Alice Engineer",
                "alice@example.com",
                "cc-101",
                "CC-101-FINOPS",
                "bu-finops",
                "FinOps",
                "prj-pay",
                "Payments Modernization",
                Decimal("142.50"),
            ),
            (
                "res-aws-vm-02",
                "sc-aws-prod-1",
                "i-08a71239b222",
                "prod-payment-worker-2",
                "AWS",
                "AmazonEC2",
                "Amazon Elastic Compute Cloud",
                "Compute",
                "ec2:instance",
                "VirtualMachine",
                "us-east-1",
                "US East (N. Virginia)",
                "us-east-1b",
                "PAID",
                "RUNNING",
                "ACTIVE",
                [
                    {"key": "Environment", "value": "Production"},
                    {"key": "CostCenter", "value": "CC-101-FINOPS"},
                    {"key": "Owner", "value": "Alice Engineer"},
                ],
                "app-payments",
                "Payments Core",
                "env-prod",
                "Production",
                "usr-alice",
                "Alice Engineer",
                "alice@example.com",
                "cc-101",
                "CC-101-FINOPS",
                "bu-finops",
                "FinOps",
                "prj-pay",
                "Payments Modernization",
                Decimal("142.50"),
            ),
            (
                "res-aws-rds-01",
                "sc-aws-prod-1",
                "rds-prod-pay-primary",
                "prod-payments-db",
                "AWS",
                "AmazonRDS",
                "Amazon Relational Database Service",
                "Database",
                "rds:db",
                "RelationalDatabase",
                "us-east-1",
                "US East (N. Virginia)",
                "us-east-1a",
                "PAID",
                "RUNNING",
                "ACTIVE",
                [
                    {"key": "Environment", "value": "Production"},
                    {"key": "CostCenter", "value": "CC-101-FINOPS"},
                    {"key": "Owner", "value": "Bob DBA"},
                ],
                "app-payments",
                "Payments Core",
                "env-prod",
                "Production",
                "usr-bob",
                "Bob DBA",
                "bob@example.com",
                "cc-101",
                "CC-101-FINOPS",
                "bu-finops",
                "FinOps",
                "prj-pay",
                "Payments Modernization",
                Decimal("920.00"),
            ),
            (
                "res-aws-eks-01",
                "sc-aws-prod-1",
                "arn:aws:eks:us-east-1:112233440001:cluster/prod-core",
                "prod-core-eks-cluster",
                "AWS",
                "AmazonEKS",
                "Amazon Elastic Kubernetes Service",
                "Containers",
                "eks:cluster",
                "KubernetesCluster",
                "us-east-1",
                "US East (N. Virginia)",
                "us-east-1a",
                "PAID",
                "RUNNING",
                "ACTIVE",
                [
                    {"key": "Environment", "value": "Production"},
                    {"key": "CostCenter", "value": "CC-202-ENG"},
                    {"key": "Owner", "value": "Dave Architect"},
                ],
                "app-checkout",
                "Checkout Service",
                "env-prod",
                "Production",
                "usr-dave",
                "Dave Architect",
                "dave@example.com",
                "cc-202",
                "CC-202-ENG",
                "bu-eng",
                "Engineering",
                "prj-chk",
                "Checkout Modernization",
                Decimal("1450.00"),
            ),
            (
                "res-aws-s3-01",
                "sc-aws-prod-1",
                "arn:aws:s3:::cloudlens-prod-archive",
                "cloudlens-prod-archive-s3",
                "AWS",
                "AmazonS3",
                "Amazon Simple Storage Service",
                "Storage",
                "s3:bucket",
                "ObjectStorage",
                "us-east-1",
                "US East (N. Virginia)",
                None,
                "PAID",
                "RUNNING",
                "ACTIVE",
                [
                    {"key": "Environment", "value": "Production"},
                    {"key": "CostCenter", "value": "CC-101-FINOPS"},
                ],
                "app-payments",
                "Payments Core",
                "env-prod",
                "Production",
                None,
                "Unowned",
                None,
                "cc-101",
                "CC-101-FINOPS",
                "bu-finops",
                "FinOps",
                "prj-pay",
                "Payments Modernization",
                Decimal("230.00"),
            ),
            # AWS Dev/Staging (sc-aws-dev-1)
            (
                "res-aws-dev-vm-01",
                "sc-aws-dev-1",
                "i-01122334455a",
                "dev-payment-sandbox",
                "AWS",
                "AmazonEC2",
                "Amazon Elastic Compute Cloud",
                "Compute",
                "ec2:instance",
                "VirtualMachine",
                "us-west-2",
                "US West (Oregon)",
                "us-west-2a",
                "PAID",
                "STOPPED",
                "ACTIVE",
                [
                    {"key": "Environment", "value": "Development"},
                    {"key": "CostCenter", "value": "CC-202-ENG"},
                    {"key": "Owner", "value": "Alice Engineer"},
                ],
                "app-payments",
                "Payments Core",
                "env-dev",
                "Development",
                "usr-alice",
                "Alice Engineer",
                "alice@example.com",
                "cc-202",
                "CC-202-ENG",
                "bu-eng",
                "Engineering",
                "prj-dev",
                "Developer Sandboxes",
                Decimal("35.00"),
            ),
            # Azure Production (sc-azure-prod-1)
            (
                "res-az-vm-01",
                "sc-azure-prod-1",
                "/subscriptions/sub-prod-0001/resourceGroups/rg-workload-001/providers/Microsoft.Compute/virtualMachines/vm-checkout-01",
                "vm-checkout-worker-1",
                "Azure",
                "VirtualMachines",
                "Azure Virtual Machines",
                "Compute",
                "microsoft.compute/virtualmachines",
                "VirtualMachine",
                "eastus",
                "East US",
                "eastus-1",
                "PAID",
                "RUNNING",
                "ACTIVE",
                [
                    {"key": "Environment", "value": "Production"},
                    {"key": "CostCenter", "value": "CC-202-ENG"},
                    {"key": "Owner", "value": "Carol Ops"},
                ],
                "app-checkout",
                "Checkout Service",
                "env-prod",
                "Production",
                "usr-carol",
                "Carol Ops",
                "carol@example.com",
                "cc-202",
                "CC-202-ENG",
                "bu-eng",
                "Engineering",
                "prj-chk",
                "Checkout Modernization",
                Decimal("320.00"),
            ),
            (
                "res-az-sql-01",
                "sc-azure-prod-1",
                "/subscriptions/sub-prod-0001/resourceGroups/rg-workload-001/providers/Microsoft.Sql/servers/sql-prod-chk/databases/chkdb",
                "sql-checkout-db",
                "Azure",
                "SQLDatabase",
                "Azure SQL Database",
                "Database",
                "microsoft.sql/servers/databases",
                "RelationalDatabase",
                "eastus",
                "East US",
                "eastus-1",
                "PAID",
                "RUNNING",
                "ACTIVE",
                [
                    {"key": "Environment", "value": "Production"},
                    {"key": "CostCenter", "value": "CC-202-ENG"},
                    {"key": "Owner", "value": "Bob DBA"},
                ],
                "app-checkout",
                "Checkout Service",
                "env-prod",
                "Production",
                "usr-bob",
                "Bob DBA",
                "bob@example.com",
                "cc-202",
                "CC-202-ENG",
                "bu-eng",
                "Engineering",
                "prj-chk",
                "Checkout Modernization",
                Decimal("1150.00"),
            ),
            (
                "res-az-aks-01",
                "sc-azure-prod-1",
                "/subscriptions/sub-prod-0001/resourceGroups/rg-workload-001/providers/Microsoft.ContainerService/managedClusters/aks-inventory",
                "aks-inventory-cluster",
                "Azure",
                "AzureKubernetesService",
                "Azure Kubernetes Service",
                "Containers",
                "microsoft.containerservice/managedclusters",
                "KubernetesCluster",
                "westeurope",
                "West Europe",
                "westeurope-1",
                "PAID",
                "RUNNING",
                "ACTIVE",
                [
                    {"key": "Environment", "value": "Production"},
                    {"key": "CostCenter", "value": "CC-404-SALES"},
                    {"key": "Owner", "value": "Carol Ops"},
                ],
                "app-inventory",
                "Inventory Mgmt",
                "env-prod",
                "Production",
                "usr-carol",
                "Carol Ops",
                "carol@example.com",
                "cc-404",
                "CC-404-SALES",
                "bu-sales",
                "Sales & Operations",
                "prj-inv",
                "Global Inventory",
                Decimal("820.00"),
            ),
            (
                "res-az-blob-01",
                "sc-azure-prod-1",
                "/subscriptions/sub-prod-0001/resourceGroups/rg-workload-001/providers/Microsoft.Storage/storageAccounts/stinventorybackup",
                "stinventorybackup",
                "Azure",
                "BlobStorage",
                "Azure Blob Storage",
                "Storage",
                "microsoft.storage/storageaccounts",
                "ObjectStorage",
                "eastus",
                "East US",
                None,
                "PAID",
                "RUNNING",
                "ACTIVE",
                [
                    {"key": "Environment", "value": "Production"},
                    {"key": "CostCenter", "value": "CC-404-SALES"},
                ],
                "app-inventory",
                "Inventory Mgmt",
                "env-prod",
                "Production",
                None,
                "Unowned",
                None,
                "cc-404",
                "CC-404-SALES",
                "bu-sales",
                "Sales & Operations",
                "prj-inv",
                "Global Inventory",
                Decimal("95.00"),
            ),
            # GCP Analytics (sc-gcp-analytics-1)
            (
                "res-gcp-gce-01",
                "sc-gcp-analytics-1",
                "projects/prj-finops-0001/zones/us-central1-a/instances/gce-analytics-01",
                "gce-analytics-worker-1",
                "GCP",
                "ComputeEngine",
                "Google Compute Engine",
                "Compute",
                "compute.googleapis.com/Instance",
                "VirtualMachine",
                "us-central1",
                "us-central1 (Iowa)",
                "us-central1-a",
                "PAID",
                "RUNNING",
                "ACTIVE",
                [
                    {"key": "Environment", "value": "Production"},
                    {"key": "CostCenter", "value": "CC-303-DATA"},
                    {"key": "Owner", "value": "Dave Architect"},
                ],
                "app-analytics",
                "Customer Analytics",
                "env-prod",
                "Production",
                "usr-dave",
                "Dave Architect",
                "dave@example.com",
                "cc-303",
                "CC-303-DATA",
                "bu-data",
                "Data Platform",
                "prj-ana",
                "Customer Intelligence",
                Decimal("430.00"),
            ),
            (
                "res-gcp-sql-01",
                "sc-gcp-analytics-1",
                "projects/prj-finops-0001/instances/cloudsql-analytics-replica",
                "cloudsql-analytics-db",
                "GCP",
                "CloudSQL",
                "Google Cloud SQL",
                "Database",
                "sqladmin.googleapis.com/Instance",
                "RelationalDatabase",
                "us-central1",
                "us-central1 (Iowa)",
                "us-central1-b",
                "PAID",
                "RUNNING",
                "ACTIVE",
                [
                    {"key": "Environment", "value": "Production"},
                    {"key": "CostCenter", "value": "CC-303-DATA"},
                    {"key": "Owner", "value": "Bob DBA"},
                ],
                "app-analytics",
                "Customer Analytics",
                "env-prod",
                "Production",
                "usr-bob",
                "Bob DBA",
                "bob@example.com",
                "cc-303",
                "CC-303-DATA",
                "bu-data",
                "Data Platform",
                "prj-ana",
                "Customer Intelligence",
                Decimal("680.00"),
            ),
            (
                "res-gcp-gke-01",
                "sc-gcp-analytics-1",
                "projects/prj-finops-0001/locations/us-central1/clusters/gke-pipeline",
                "gke-pipeline-cluster",
                "GCP",
                "GoogleKubernetesEngine",
                "Google Kubernetes Engine",
                "Containers",
                "container.googleapis.com/Cluster",
                "KubernetesCluster",
                "us-central1",
                "us-central1 (Iowa)",
                "us-central1-c",
                "PAID",
                "RUNNING",
                "ACTIVE",
                [
                    {"key": "Environment", "value": "Production"},
                    {"key": "CostCenter", "value": "CC-303-DATA"},
                    {"key": "Owner", "value": "Dave Architect"},
                ],
                "app-warehouse",
                "Data Warehouse",
                "env-prod",
                "Production",
                "usr-dave",
                "Dave Architect",
                "dave@example.com",
                "cc-303",
                "CC-303-DATA",
                "bu-data",
                "Data Platform",
                "prj-dwh",
                "Enterprise Data Lake",
                Decimal("1480.00"),
            ),
            (
                "res-gcp-gcs-01",
                "sc-gcp-analytics-1",
                "gs://cloudlens-gcp-lake-storage",
                "cloudlens-gcp-lake-bucket",
                "GCP",
                "CloudStorage",
                "Google Cloud Storage",
                "Storage",
                "storage.googleapis.com/Bucket",
                "ObjectStorage",
                "us-central1",
                "us-central1 (Iowa)",
                None,
                "PAID",
                "RUNNING",
                "ACTIVE",
                [
                    {"key": "Environment", "value": "Production"},
                    {"key": "CostCenter", "value": "CC-303-DATA"},
                ],
                "app-warehouse",
                "Data Warehouse",
                "env-prod",
                "Production",
                None,
                "Unowned",
                None,
                "cc-303",
                "CC-303-DATA",
                "bu-data",
                "Data Platform",
                "prj-dwh",
                "Enterprise Data Lake",
                Decimal("310.00"),
            ),
            # OCI Core (sc-oci-core-1)
            (
                "res-oci-vm-01",
                "sc-oci-core-1",
                "ocid1.instance.oc1.iad.anuwcljs001",
                "oci-core-compute-worker",
                "OCI",
                "ComputeService",
                "Oracle Cloud Compute",
                "Compute",
                "oci:compute:instance",
                "VirtualMachine",
                "us-ashburn-1",
                "US East (Ashburn)",
                "AD-1",
                "PAID",
                "RUNNING",
                "ACTIVE",
                [
                    {"key": "Environment", "value": "Production"},
                    {"key": "CostCenter", "value": "CC-101-FINOPS"},
                    {"key": "Owner", "value": "Carol Ops"},
                ],
                "app-payments",
                "Payments Core",
                "env-prod",
                "Production",
                "usr-carol",
                "Carol Ops",
                "carol@example.com",
                "cc-101",
                "CC-101-FINOPS",
                "bu-finops",
                "FinOps",
                "prj-pay",
                "Payments Modernization",
                Decimal("280.00"),
            ),
            (
                "res-oci-adb-01",
                "sc-oci-core-1",
                "ocid1.autonomousdatabase.oc1.iad.anuwcljs002",
                "oci-core-autonomous-db",
                "OCI",
                "AutonomousDatabase",
                "Oracle Autonomous Database",
                "Database",
                "oci:database:autonomousdatabase",
                "RelationalDatabase",
                "us-ashburn-1",
                "US East (Ashburn)",
                "AD-1",
                "PAID",
                "RUNNING",
                "ACTIVE",
                [
                    {"key": "Environment", "value": "Production"},
                    {"key": "CostCenter", "value": "CC-101-FINOPS"},
                    {"key": "Owner", "value": "Bob DBA"},
                ],
                "app-payments",
                "Payments Core",
                "env-prod",
                "Production",
                "usr-bob",
                "Bob DBA",
                "bob@example.com",
                "cc-101",
                "CC-101-FINOPS",
                "bu-finops",
                "FinOps",
                "prj-pay",
                "Payments Modernization",
                Decimal("1250.00"),
            ),
        ]

        for s in specs:
            r = InventoryResource35(
                id=s[0],
                tenant_id="default-tenant",
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
            self._resources[r.id] = r

    # --------------------------------------------------------------------------
    # Scope Validation & Threshold Helper
    # --------------------------------------------------------------------------

    def _is_resource_in_scope(
        self, resource: InventoryResource35, tenant_context: TenantContext
    ) -> bool:
        """Determines if resource is accessible under caller's scope grants."""
        if "*" in tenant_context.scope_grants:
            return True
        return resource.scope_id in tenant_context.scope_grants

    def get_resource_threshold_state(self, resource: InventoryResource35) -> str:
        """Computes threshold state for resource: CRITICAL > WARNING > NORMAL."""
        # Dominant or high spend triggers thresholds for demonstration
        if resource.monthly_cost >= Decimal("1000.00"):
            return "CRITICAL"
        if resource.monthly_cost >= Decimal("400.00"):
            return "WARNING"
        return "NORMAL"

    @staticmethod
    def _combine_threshold_states(states: list[str]) -> str:
        """Bubbles worst threshold state: CRITICAL > WARNING > NORMAL."""
        if any(s == "CRITICAL" for s in states):
            return "CRITICAL"
        if any(s == "WARNING" for s in states):
            return "WARNING"
        return "NORMAL"

    # --------------------------------------------------------------------------
    # Tree Building & Navigation Model (BBP Section 16.3)
    # --------------------------------------------------------------------------

    def get_hierarchy_tree(
        self,
        lens_type: LateralLensType,
        tenant_context: TenantContext,
        root_id: str | None = None,
    ) -> HierarchyNode:
        """Constructs full hierarchical tree for chosen lens with rolled-up spend and worst-child state."""
        # 1. Filter resources by caller scope grants
        scoped_resources = [
            r for r in self._resources.values() if self._is_resource_in_scope(r, tenant_context)
        ]

        if lens_type == LateralLensType.PROVIDER_HIERARCHY:
            return self._build_provider_hierarchy_tree(scoped_resources, root_id)
        elif lens_type == LateralLensType.APPLICATION:
            return self._build_application_lens_tree(scoped_resources)
        elif lens_type == LateralLensType.COST_CENTRE:
            return self._build_cost_centre_lens_tree(scoped_resources)
        elif lens_type == LateralLensType.ENVIRONMENT:
            return self._build_environment_lens_tree(scoped_resources)
        elif lens_type == LateralLensType.OWNER:
            return self._build_owner_lens_tree(scoped_resources)
        elif lens_type == LateralLensType.REGION:
            return self._build_region_lens_tree(scoped_resources)
        elif lens_type == LateralLensType.TAG:
            return self._build_tag_lens_tree(scoped_resources)
        else:
            return self._build_provider_hierarchy_tree(scoped_resources, root_id)

    def _build_provider_hierarchy_tree(
        self, resources: list[InventoryResource35], _root_id: str | None = None
    ) -> HierarchyNode:
        """Builds Provider -> Organisation -> Group -> Billing Boundary -> [Sub-group] -> Service -> Resource."""
        provider_nodes: list[HierarchyNode] = []

        # Group resources by Provider
        providers = sorted({r.provider for r in resources})
        for prov in providers:
            prov_resources = [r for r in resources if r.provider == prov]

            # Native organizational structures per provider
            if prov.upper() == "AWS":
                org_node = self._build_aws_subtree(prov_resources)
            elif prov.upper() == "AZURE":
                org_node = self._build_azure_subtree(prov_resources)
            elif prov.upper() == "GCP":
                org_node = self._build_gcp_subtree(prov_resources)
            else:  # OCI
                org_node = self._build_oci_subtree(prov_resources)

            prov_cost = org_node.aggregate_cost
            prov_budget = self._budgets.get(prov, Decimal("0.00"))
            prov_util = (
                (prov_cost / prov_budget * Decimal("100")).quantize(Decimal("0.01"))
                if prov_budget > 0
                else Decimal("0.00")
            )

            p_node = HierarchyNode(
                id=f"prov-{prov.lower()}",
                name=prov,
                level=HierarchyLevel.PROVIDER,
                lens_type=LateralLensType.PROVIDER_HIERARCHY,
                provider=prov,
                native_type="CloudProvider",
                aggregate_cost=prov_cost,
                budget_amount=prov_budget,
                budget_utilisation_pct=prov_util,
                worst_child_threshold_state=org_node.worst_child_threshold_state,
                direct_resource_count=0,
                total_descendant_resource_count=org_node.total_descendant_resource_count,
                child_count=1,
                children=[org_node],
                metadata={"provider": prov},
            )
            provider_nodes.append(p_node)

        total_cost = sum((p.aggregate_cost for p in provider_nodes), Decimal("0.00"))
        global_budget = self._budgets.get("GLOBAL", Decimal("50000.00"))
        global_util = (
            (total_cost / global_budget * Decimal("100")).quantize(Decimal("0.01"))
            if global_budget > 0
            else Decimal("0.00")
        )
        worst_state = self._combine_threshold_states(
            [p.worst_child_threshold_state for p in provider_nodes]
        )
        total_res_count = sum(p.total_descendant_resource_count for p in provider_nodes)

        root = HierarchyNode(
            id="root-estate",
            name="Global Cloud Estate",
            level=HierarchyLevel.ORGANISATION,
            lens_type=LateralLensType.PROVIDER_HIERARCHY,
            native_type="EnterpriseEstate",
            aggregate_cost=total_cost,
            budget_amount=global_budget,
            budget_utilisation_pct=global_util,
            worst_child_threshold_state=worst_state,
            direct_resource_count=0,
            total_descendant_resource_count=total_res_count,
            child_count=len(provider_nodes),
            children=provider_nodes,
            metadata={"description": "Enterprise multi-cloud global estate root"},
        )
        return root

    def _build_aws_subtree(self, resources: list[InventoryResource35]) -> HierarchyNode:
        """AWS: Organisation (o-enterprise-root) -> OU (ou-core-workloads) -> Account (112233440001) -> Service -> Resource."""
        # Services under AWS
        svc_nodes: list[HierarchyNode] = []
        services = sorted({r.service_name for r in resources})
        for svc_name in services:
            svc_res = [r for r in resources if r.service_name == svc_name]
            leaf_nodes = [self._resource_to_leaf(r) for r in svc_res]
            svc_cost = sum((r.monthly_cost for r in svc_res), Decimal("0.00"))
            worst_state = self._combine_threshold_states(
                [n.worst_child_threshold_state for n in leaf_nodes]
            )
            svc_nodes.append(
                HierarchyNode(
                    id=f"aws-svc-{svc_name.replace(' ', '-').lower()}",
                    name=svc_name,
                    level=HierarchyLevel.SERVICE,
                    lens_type=LateralLensType.PROVIDER_HIERARCHY,
                    provider="AWS",
                    native_type="AWSService",
                    aggregate_cost=svc_cost,
                    budget_amount=Decimal("0.00"),
                    budget_utilisation_pct=Decimal("0.00"),
                    worst_child_threshold_state=worst_state,
                    direct_resource_count=len(leaf_nodes),
                    total_descendant_resource_count=len(leaf_nodes),
                    child_count=len(leaf_nodes),
                    children=leaf_nodes,
                )
            )

        acct_cost = sum((s.aggregate_cost for s in svc_nodes), Decimal("0.00"))
        acct_worst = self._combine_threshold_states(
            [s.worst_child_threshold_state for s in svc_nodes]
        )
        acct_node = HierarchyNode(
            id="aws-acct-112233440001",
            name="112233440001 (Core Workloads)",
            level=HierarchyLevel.BILLING_BOUNDARY,
            lens_type=LateralLensType.PROVIDER_HIERARCHY,
            provider="AWS",
            native_type="Account",
            scope_id="sc-aws-prod-1",
            aggregate_cost=acct_cost,
            budget_amount=Decimal("18000.00"),
            budget_utilisation_pct=(
                (acct_cost / Decimal("18000.00") * Decimal("100")).quantize(Decimal("0.01"))
            ),
            worst_child_threshold_state=acct_worst,
            direct_resource_count=0,
            total_descendant_resource_count=sum(
                s.total_descendant_resource_count for s in svc_nodes
            ),
            child_count=len(svc_nodes),
            children=svc_nodes,
        )

        ou_node = HierarchyNode(
            id="aws-ou-core-workloads",
            name="ou-core-workloads",
            level=HierarchyLevel.GROUP,
            lens_type=LateralLensType.PROVIDER_HIERARCHY,
            provider="AWS",
            native_type="OrganizationalUnit",
            aggregate_cost=acct_cost,
            budget_amount=Decimal("20000.00"),
            budget_utilisation_pct=(
                (acct_cost / Decimal("20000.00") * Decimal("100")).quantize(Decimal("0.01"))
            ),
            worst_child_threshold_state=acct_worst,
            direct_resource_count=0,
            total_descendant_resource_count=acct_node.total_descendant_resource_count,
            child_count=1,
            children=[acct_node],
        )

        return HierarchyNode(
            id="aws-org-root",
            name="o-enterprise-root",
            level=HierarchyLevel.ORGANISATION,
            lens_type=LateralLensType.PROVIDER_HIERARCHY,
            provider="AWS",
            native_type="Organization",
            aggregate_cost=acct_cost,
            budget_amount=Decimal("22000.00"),
            budget_utilisation_pct=(
                (acct_cost / Decimal("22000.00") * Decimal("100")).quantize(Decimal("0.01"))
            ),
            worst_child_threshold_state=acct_worst,
            direct_resource_count=0,
            total_descendant_resource_count=ou_node.total_descendant_resource_count,
            child_count=1,
            children=[ou_node],
        )

    def _build_azure_subtree(self, resources: list[InventoryResource35]) -> HierarchyNode:
        """Azure: Tenant (t-azure-enterprise) -> MG (mg-finops-tier-0) -> Subscription -> ResourceGroup -> Service -> Resource."""
        svc_nodes: list[HierarchyNode] = []
        services = sorted({r.service_name for r in resources})
        for svc_name in services:
            svc_res = [r for r in resources if r.service_name == svc_name]
            leaf_nodes = [self._resource_to_leaf(r) for r in svc_res]
            svc_cost = sum((r.monthly_cost for r in svc_res), Decimal("0.00"))
            worst_state = self._combine_threshold_states(
                [n.worst_child_threshold_state for n in leaf_nodes]
            )
            svc_nodes.append(
                HierarchyNode(
                    id=f"az-svc-{svc_name.replace(' ', '-').lower()}",
                    name=svc_name,
                    level=HierarchyLevel.SERVICE,
                    lens_type=LateralLensType.PROVIDER_HIERARCHY,
                    provider="Azure",
                    native_type="AzureService",
                    aggregate_cost=svc_cost,
                    budget_amount=Decimal("0.00"),
                    budget_utilisation_pct=Decimal("0.00"),
                    worst_child_threshold_state=worst_state,
                    direct_resource_count=len(leaf_nodes),
                    total_descendant_resource_count=len(leaf_nodes),
                    child_count=len(leaf_nodes),
                    children=leaf_nodes,
                )
            )

        rg_cost = sum((s.aggregate_cost for s in svc_nodes), Decimal("0.00"))
        rg_worst = self._combine_threshold_states(
            [s.worst_child_threshold_state for s in svc_nodes]
        )
        rg_node = HierarchyNode(
            id="az-rg-workload-001",
            name="rg-workload-001",
            level=HierarchyLevel.SUB_GROUP,
            lens_type=LateralLensType.PROVIDER_HIERARCHY,
            provider="Azure",
            native_type="ResourceGroup",
            aggregate_cost=rg_cost,
            budget_amount=Decimal("16000.00"),
            budget_utilisation_pct=(
                (rg_cost / Decimal("16000.00") * Decimal("100")).quantize(Decimal("0.01"))
            ),
            worst_child_threshold_state=rg_worst,
            direct_resource_count=0,
            total_descendant_resource_count=sum(
                s.total_descendant_resource_count for s in svc_nodes
            ),
            child_count=len(svc_nodes),
            children=svc_nodes,
        )

        sub_node = HierarchyNode(
            id="az-sub-prod-0001",
            name="sub-prod-0001 (Production)",
            level=HierarchyLevel.BILLING_BOUNDARY,
            lens_type=LateralLensType.PROVIDER_HIERARCHY,
            provider="Azure",
            native_type="Subscription",
            scope_id="sc-azure-prod-1",
            aggregate_cost=rg_cost,
            budget_amount=Decimal("16000.00"),
            budget_utilisation_pct=(
                (rg_cost / Decimal("16000.00") * Decimal("100")).quantize(Decimal("0.01"))
            ),
            worst_child_threshold_state=rg_worst,
            direct_resource_count=0,
            total_descendant_resource_count=rg_node.total_descendant_resource_count,
            child_count=1,
            children=[rg_node],
        )

        mg_node = HierarchyNode(
            id="az-mg-finops",
            name="mg-finops-tier-0",
            level=HierarchyLevel.GROUP,
            lens_type=LateralLensType.PROVIDER_HIERARCHY,
            provider="Azure",
            native_type="ManagementGroup",
            aggregate_cost=rg_cost,
            budget_amount=Decimal("16000.00"),
            budget_utilisation_pct=(
                (rg_cost / Decimal("16000.00") * Decimal("100")).quantize(Decimal("0.01"))
            ),
            worst_child_threshold_state=rg_worst,
            direct_resource_count=0,
            total_descendant_resource_count=sub_node.total_descendant_resource_count,
            child_count=1,
            children=[sub_node],
        )

        return HierarchyNode(
            id="az-tenant-root",
            name="t-azure-enterprise",
            level=HierarchyLevel.ORGANISATION,
            lens_type=LateralLensType.PROVIDER_HIERARCHY,
            provider="Azure",
            native_type="Tenant",
            aggregate_cost=rg_cost,
            budget_amount=Decimal("16000.00"),
            budget_utilisation_pct=(
                (rg_cost / Decimal("16000.00") * Decimal("100")).quantize(Decimal("0.01"))
            ),
            worst_child_threshold_state=rg_worst,
            direct_resource_count=0,
            total_descendant_resource_count=mg_node.total_descendant_resource_count,
            child_count=1,
            children=[mg_node],
        )

    def _build_gcp_subtree(self, resources: list[InventoryResource35]) -> HierarchyNode:
        """GCP: Organisation (org-gcp-enterprise) -> Folder (folder-data-tier) -> Project (prj-finops-0001) -> Service -> Resource."""
        svc_nodes: list[HierarchyNode] = []
        services = sorted({r.service_name for r in resources})
        for svc_name in services:
            svc_res = [r for r in resources if r.service_name == svc_name]
            leaf_nodes = [self._resource_to_leaf(r) for r in svc_res]
            svc_cost = sum((r.monthly_cost for r in svc_res), Decimal("0.00"))
            worst_state = self._combine_threshold_states(
                [n.worst_child_threshold_state for n in leaf_nodes]
            )
            svc_nodes.append(
                HierarchyNode(
                    id=f"gcp-svc-{svc_name.replace(' ', '-').lower()}",
                    name=svc_name,
                    level=HierarchyLevel.SERVICE,
                    lens_type=LateralLensType.PROVIDER_HIERARCHY,
                    provider="GCP",
                    native_type="GCPService",
                    aggregate_cost=svc_cost,
                    budget_amount=Decimal("0.00"),
                    budget_utilisation_pct=Decimal("0.00"),
                    worst_child_threshold_state=worst_state,
                    direct_resource_count=len(leaf_nodes),
                    total_descendant_resource_count=len(leaf_nodes),
                    child_count=len(leaf_nodes),
                    children=leaf_nodes,
                )
            )

        prj_cost = sum((s.aggregate_cost for s in svc_nodes), Decimal("0.00"))
        prj_worst = self._combine_threshold_states(
            [s.worst_child_threshold_state for s in svc_nodes]
        )
        prj_node = HierarchyNode(
            id="gcp-prj-finops-0001",
            name="prj-finops-0001",
            level=HierarchyLevel.BILLING_BOUNDARY,
            lens_type=LateralLensType.PROVIDER_HIERARCHY,
            provider="GCP",
            native_type="Project",
            scope_id="sc-gcp-analytics-1",
            aggregate_cost=prj_cost,
            budget_amount=Decimal("8000.00"),
            budget_utilisation_pct=(
                (prj_cost / Decimal("8000.00") * Decimal("100")).quantize(Decimal("0.01"))
            ),
            worst_child_threshold_state=prj_worst,
            direct_resource_count=0,
            total_descendant_resource_count=sum(
                s.total_descendant_resource_count for s in svc_nodes
            ),
            child_count=len(svc_nodes),
            children=svc_nodes,
        )

        folder_node = HierarchyNode(
            id="gcp-folder-data",
            name="folder-data-tier",
            level=HierarchyLevel.GROUP,
            lens_type=LateralLensType.PROVIDER_HIERARCHY,
            provider="GCP",
            native_type="Folder",
            aggregate_cost=prj_cost,
            budget_amount=Decimal("8000.00"),
            budget_utilisation_pct=(
                (prj_cost / Decimal("8000.00") * Decimal("100")).quantize(Decimal("0.01"))
            ),
            worst_child_threshold_state=prj_worst,
            direct_resource_count=0,
            total_descendant_resource_count=prj_node.total_descendant_resource_count,
            child_count=1,
            children=[prj_node],
        )

        return HierarchyNode(
            id="gcp-org-root",
            name="org-gcp-enterprise",
            level=HierarchyLevel.ORGANISATION,
            lens_type=LateralLensType.PROVIDER_HIERARCHY,
            provider="GCP",
            native_type="Organization",
            aggregate_cost=prj_cost,
            budget_amount=Decimal("8000.00"),
            budget_utilisation_pct=(
                (prj_cost / Decimal("8000.00") * Decimal("100")).quantize(Decimal("0.01"))
            ),
            worst_child_threshold_state=prj_worst,
            direct_resource_count=0,
            total_descendant_resource_count=folder_node.total_descendant_resource_count,
            child_count=1,
            children=[folder_node],
        )

    def _build_oci_subtree(self, resources: list[InventoryResource35]) -> HierarchyNode:
        """OCI: Tenancy -> Compartment -> Subcompartment -> Micro-Compartment -> Service -> Resource."""
        svc_nodes: list[HierarchyNode] = []
        services = sorted({r.service_name for r in resources})
        for svc_name in services:
            svc_res = [r for r in resources if r.service_name == svc_name]
            leaf_nodes = [self._resource_to_leaf(r) for r in svc_res]
            svc_cost = sum((r.monthly_cost for r in svc_res), Decimal("0.00"))
            worst_state = self._combine_threshold_states(
                [n.worst_child_threshold_state for n in leaf_nodes]
            )
            svc_nodes.append(
                HierarchyNode(
                    id=f"oci-svc-{svc_name.replace(' ', '-').lower()}",
                    name=svc_name,
                    level=HierarchyLevel.SERVICE,
                    lens_type=LateralLensType.PROVIDER_HIERARCHY,
                    provider="OCI",
                    native_type="OCIService",
                    aggregate_cost=svc_cost,
                    budget_amount=Decimal("0.00"),
                    budget_utilisation_pct=Decimal("0.00"),
                    worst_child_threshold_state=worst_state,
                    direct_resource_count=len(leaf_nodes),
                    total_descendant_resource_count=len(leaf_nodes),
                    child_count=len(leaf_nodes),
                    children=leaf_nodes,
                )
            )

        micro_cost = sum((s.aggregate_cost for s in svc_nodes), Decimal("0.00"))
        micro_worst = self._combine_threshold_states(
            [s.worst_child_threshold_state for s in svc_nodes]
        )
        micro_node = HierarchyNode(
            id="oci-subcomp-micro",
            name="micro-tier",
            level=HierarchyLevel.SUB_GROUP,
            lens_type=LateralLensType.PROVIDER_HIERARCHY,
            provider="OCI",
            native_type="Subcompartment",
            aggregate_cost=micro_cost,
            budget_amount=Decimal("4000.00"),
            budget_utilisation_pct=(
                (micro_cost / Decimal("4000.00") * Decimal("100")).quantize(Decimal("0.01"))
            ),
            worst_child_threshold_state=micro_worst,
            direct_resource_count=0,
            total_descendant_resource_count=sum(
                s.total_descendant_resource_count for s in svc_nodes
            ),
            child_count=len(svc_nodes),
            children=svc_nodes,
        )

        subcomp_node = HierarchyNode(
            id="oci-comp-sub0001",
            name="sub-compartment-0001",
            level=HierarchyLevel.BILLING_BOUNDARY,
            lens_type=LateralLensType.PROVIDER_HIERARCHY,
            provider="OCI",
            native_type="Compartment",
            scope_id="sc-oci-core-1",
            aggregate_cost=micro_cost,
            budget_amount=Decimal("4000.00"),
            budget_utilisation_pct=(
                (micro_cost / Decimal("4000.00") * Decimal("100")).quantize(Decimal("0.01"))
            ),
            worst_child_threshold_state=micro_worst,
            direct_resource_count=0,
            total_descendant_resource_count=micro_node.total_descendant_resource_count,
            child_count=1,
            children=[micro_node],
        )

        comp_node = HierarchyNode(
            id="oci-comp-core",
            name="core-compartment",
            level=HierarchyLevel.GROUP,
            lens_type=LateralLensType.PROVIDER_HIERARCHY,
            provider="OCI",
            native_type="Compartment",
            aggregate_cost=micro_cost,
            budget_amount=Decimal("4000.00"),
            budget_utilisation_pct=(
                (micro_cost / Decimal("4000.00") * Decimal("100")).quantize(Decimal("0.01"))
            ),
            worst_child_threshold_state=micro_worst,
            direct_resource_count=0,
            total_descendant_resource_count=subcomp_node.total_descendant_resource_count,
            child_count=1,
            children=[subcomp_node],
        )

        return HierarchyNode(
            id="oci-tenancy-root",
            name="ocid1.tenancy.oc1..enterprise",
            level=HierarchyLevel.ORGANISATION,
            lens_type=LateralLensType.PROVIDER_HIERARCHY,
            provider="OCI",
            native_type="Tenancy",
            aggregate_cost=micro_cost,
            budget_amount=Decimal("4000.00"),
            budget_utilisation_pct=(
                (micro_cost / Decimal("4000.00") * Decimal("100")).quantize(Decimal("0.01"))
            ),
            worst_child_threshold_state=micro_worst,
            direct_resource_count=0,
            total_descendant_resource_count=comp_node.total_descendant_resource_count,
            child_count=1,
            children=[comp_node],
        )

    def _resource_to_leaf(self, resource: InventoryResource35) -> HierarchyNode:
        """Converts InventoryResource35 into a terminal RESOURCE level tree node."""
        state = self.get_resource_threshold_state(resource)
        return HierarchyNode(
            id=resource.id,
            name=resource.name,
            level=HierarchyLevel.RESOURCE,
            lens_type=LateralLensType.PROVIDER_HIERARCHY,
            provider=resource.provider,
            native_type=resource.resource_type,
            scope_id=resource.scope_id,
            aggregate_cost=resource.monthly_cost,
            budget_amount=Decimal("0.00"),
            budget_utilisation_pct=Decimal("0.00"),
            worst_child_threshold_state=state,
            direct_resource_count=1,
            total_descendant_resource_count=1,
            child_count=0,
            children=[],
            metadata={
                "native_id": resource.native_id,
                "service_id": resource.service_id,
                "region": resource.region_id,
                "runtime_state": resource.runtime_state,
                "owner": resource.owner_name,
            },
        )

    # --------------------------------------------------------------------------
    # 6 Lateral Lenses (Prompt 38)
    # --------------------------------------------------------------------------

    def _build_application_lens_tree(self, resources: list[InventoryResource35]) -> HierarchyNode:
        """Lens: Application -> Environment -> Service -> Resource."""
        app_names = sorted({r.application_name or "Unassigned" for r in resources})
        app_nodes: list[HierarchyNode] = []

        for app in app_names:
            app_res = [r for r in resources if (r.application_name or "Unassigned") == app]
            env_names = sorted({r.environment_name or "Unassigned" for r in app_res})
            env_nodes: list[HierarchyNode] = []

            for env in env_names:
                env_res = [r for r in app_res if (r.environment_name or "Unassigned") == env]
                svc_names = sorted({r.service_name for r in env_res})
                svc_nodes: list[HierarchyNode] = []

                for svc in svc_names:
                    svc_res = [r for r in env_res if r.service_name == svc]
                    leaves = [self._resource_to_leaf(r) for r in svc_res]
                    svc_cost = sum((r.monthly_cost for r in svc_res), Decimal("0.00"))
                    svc_worst = self._combine_threshold_states(
                        [leaf.worst_child_threshold_state for leaf in leaves]
                    )
                    svc_nodes.append(
                        HierarchyNode(
                            id=f"app-{app.lower()}-env-{env.lower()}-svc-{svc.lower().replace(' ', '-')}",
                            name=svc,
                            level=HierarchyLevel.SERVICE,
                            lens_type=LateralLensType.APPLICATION,
                            aggregate_cost=svc_cost,
                            budget_amount=Decimal("0.00"),
                            budget_utilisation_pct=Decimal("0.00"),
                            worst_child_threshold_state=svc_worst,
                            direct_resource_count=len(leaves),
                            total_descendant_resource_count=len(leaves),
                            child_count=len(leaves),
                            children=leaves,
                        )
                    )

                env_cost = sum((s.aggregate_cost for s in svc_nodes), Decimal("0.00"))
                env_worst = self._combine_threshold_states(
                    [s.worst_child_threshold_state for s in svc_nodes]
                )
                env_nodes.append(
                    HierarchyNode(
                        id=f"app-{app.lower()}-env-{env.lower()}",
                        name=env,
                        level=HierarchyLevel.SUB_GROUP,
                        lens_type=LateralLensType.APPLICATION,
                        aggregate_cost=env_cost,
                        budget_amount=Decimal("0.00"),
                        budget_utilisation_pct=Decimal("0.00"),
                        worst_child_threshold_state=env_worst,
                        direct_resource_count=0,
                        total_descendant_resource_count=sum(
                            s.total_descendant_resource_count for s in svc_nodes
                        ),
                        child_count=len(svc_nodes),
                        children=svc_nodes,
                    )
                )

            app_cost = sum((e.aggregate_cost for e in env_nodes), Decimal("0.00"))
            app_worst = self._combine_threshold_states(
                [e.worst_child_threshold_state for e in env_nodes]
            )
            app_id_key = app_res[0].application_id or f"app-{app.lower()}"
            app_budget = self._budgets.get(app_id_key, Decimal("10000.00"))
            app_util = (
                (app_cost / app_budget * Decimal("100")).quantize(Decimal("0.01"))
                if app_budget > 0
                else Decimal("0.00")
            )
            app_nodes.append(
                HierarchyNode(
                    id=f"lens-app-{app.lower().replace(' ', '-')}",
                    name=app,
                    level=HierarchyLevel.GROUP,
                    lens_type=LateralLensType.APPLICATION,
                    aggregate_cost=app_cost,
                    budget_amount=app_budget,
                    budget_utilisation_pct=app_util,
                    worst_child_threshold_state=app_worst,
                    direct_resource_count=0,
                    total_descendant_resource_count=sum(
                        e.total_descendant_resource_count for e in env_nodes
                    ),
                    child_count=len(env_nodes),
                    children=env_nodes,
                )
            )

        total_cost = sum((a.aggregate_cost for a in app_nodes), Decimal("0.00"))
        worst_state = self._combine_threshold_states(
            [a.worst_child_threshold_state for a in app_nodes]
        )
        total_count = sum(a.total_descendant_resource_count for a in app_nodes)

        return HierarchyNode(
            id="lens-root-application",
            name="Estate by Application",
            level=HierarchyLevel.ORGANISATION,
            lens_type=LateralLensType.APPLICATION,
            aggregate_cost=total_cost,
            budget_amount=Decimal("50000.00"),
            budget_utilisation_pct=(
                (total_cost / Decimal("50000.00") * Decimal("100")).quantize(Decimal("0.01"))
            ),
            worst_child_threshold_state=worst_state,
            direct_resource_count=0,
            total_descendant_resource_count=total_count,
            child_count=len(app_nodes),
            children=app_nodes,
        )

    def _build_cost_centre_lens_tree(self, resources: list[InventoryResource35]) -> HierarchyNode:
        """Lens: Cost Centre -> Project -> Resource."""
        cc_names = sorted({r.cost_center_name or "Unallocated" for r in resources})
        cc_nodes: list[HierarchyNode] = []

        for cc in cc_names:
            cc_res = [r for r in resources if (r.cost_center_name or "Unallocated") == cc]
            prj_names = sorted({r.project_name or "Unassigned" for r in cc_res})
            prj_nodes: list[HierarchyNode] = []

            for prj in prj_names:
                prj_res = [r for r in cc_res if (r.project_name or "Unassigned") == prj]
                leaves = [self._resource_to_leaf(r) for r in prj_res]
                prj_cost = sum((r.monthly_cost for r in prj_res), Decimal("0.00"))
                prj_worst = self._combine_threshold_states(
                    [leaf.worst_child_threshold_state for leaf in leaves]
                )
                prj_nodes.append(
                    HierarchyNode(
                        id=f"cc-{cc.lower()}-prj-{prj.lower().replace(' ', '-')}",
                        name=prj,
                        level=HierarchyLevel.SUB_GROUP,
                        lens_type=LateralLensType.COST_CENTRE,
                        aggregate_cost=prj_cost,
                        budget_amount=Decimal("0.00"),
                        budget_utilisation_pct=Decimal("0.00"),
                        worst_child_threshold_state=prj_worst,
                        direct_resource_count=len(leaves),
                        total_descendant_resource_count=len(leaves),
                        child_count=len(leaves),
                        children=leaves,
                    )
                )

            cc_cost = sum((p.aggregate_cost for p in prj_nodes), Decimal("0.00"))
            cc_worst = self._combine_threshold_states(
                [p.worst_child_threshold_state for p in prj_nodes]
            )
            cc_budget = Decimal("15000.00")
            cc_util = (
                (cc_cost / cc_budget * Decimal("100")).quantize(Decimal("0.01"))
                if cc_budget > 0
                else Decimal("0.00")
            )
            cc_nodes.append(
                HierarchyNode(
                    id=f"lens-cc-{cc.lower().replace(' ', '-')}",
                    name=cc,
                    level=HierarchyLevel.GROUP,
                    lens_type=LateralLensType.COST_CENTRE,
                    aggregate_cost=cc_cost,
                    budget_amount=cc_budget,
                    budget_utilisation_pct=cc_util,
                    worst_child_threshold_state=cc_worst,
                    direct_resource_count=0,
                    total_descendant_resource_count=sum(
                        p.total_descendant_resource_count for p in prj_nodes
                    ),
                    child_count=len(prj_nodes),
                    children=prj_nodes,
                )
            )

        total_cost = sum((c.aggregate_cost for c in cc_nodes), Decimal("0.00"))
        worst_state = self._combine_threshold_states(
            [c.worst_child_threshold_state for c in cc_nodes]
        )
        total_count = sum(c.total_descendant_resource_count for c in cc_nodes)

        return HierarchyNode(
            id="lens-root-cost-centre",
            name="Estate by Cost Centre",
            level=HierarchyLevel.ORGANISATION,
            lens_type=LateralLensType.COST_CENTRE,
            aggregate_cost=total_cost,
            budget_amount=Decimal("50000.00"),
            budget_utilisation_pct=(
                (total_cost / Decimal("50000.00") * Decimal("100")).quantize(Decimal("0.01"))
            ),
            worst_child_threshold_state=worst_state,
            direct_resource_count=0,
            total_descendant_resource_count=total_count,
            child_count=len(cc_nodes),
            children=cc_nodes,
        )

    def _build_environment_lens_tree(self, resources: list[InventoryResource35]) -> HierarchyNode:
        """Lens: Environment -> Application -> Resource."""
        env_names = sorted({r.environment_name or "Unassigned" for r in resources})
        env_nodes: list[HierarchyNode] = []

        for env in env_names:
            env_res = [r for r in resources if (r.environment_name or "Unassigned") == env]
            app_names = sorted({r.application_name or "Unassigned" for r in env_res})
            app_nodes: list[HierarchyNode] = []

            for app in app_names:
                app_res = [r for r in env_res if (r.application_name or "Unassigned") == app]
                leaves = [self._resource_to_leaf(r) for r in app_res]
                app_cost = sum((r.monthly_cost for r in app_res), Decimal("0.00"))
                app_worst = self._combine_threshold_states(
                    [leaf.worst_child_threshold_state for leaf in leaves]
                )
                app_nodes.append(
                    HierarchyNode(
                        id=f"env-{env.lower()}-app-{app.lower().replace(' ', '-')}",
                        name=app,
                        level=HierarchyLevel.SUB_GROUP,
                        lens_type=LateralLensType.ENVIRONMENT,
                        aggregate_cost=app_cost,
                        budget_amount=Decimal("0.00"),
                        budget_utilisation_pct=Decimal("0.00"),
                        worst_child_threshold_state=app_worst,
                        direct_resource_count=len(leaves),
                        total_descendant_resource_count=len(leaves),
                        child_count=len(leaves),
                        children=leaves,
                    )
                )

            env_cost = sum((a.aggregate_cost for a in app_nodes), Decimal("0.00"))
            env_worst = self._combine_threshold_states(
                [a.worst_child_threshold_state for a in app_nodes]
            )
            env_nodes.append(
                HierarchyNode(
                    id=f"lens-env-{env.lower()}",
                    name=env,
                    level=HierarchyLevel.GROUP,
                    lens_type=LateralLensType.ENVIRONMENT,
                    aggregate_cost=env_cost,
                    budget_amount=Decimal("20000.00"),
                    budget_utilisation_pct=(
                        (env_cost / Decimal("20000.00") * Decimal("100")).quantize(Decimal("0.01"))
                    ),
                    worst_child_threshold_state=env_worst,
                    direct_resource_count=0,
                    total_descendant_resource_count=sum(
                        a.total_descendant_resource_count for a in app_nodes
                    ),
                    child_count=len(app_nodes),
                    children=app_nodes,
                )
            )

        total_cost = sum((e.aggregate_cost for e in env_nodes), Decimal("0.00"))
        worst_state = self._combine_threshold_states(
            [e.worst_child_threshold_state for e in env_nodes]
        )
        total_count = sum(e.total_descendant_resource_count for e in env_nodes)

        return HierarchyNode(
            id="lens-root-environment",
            name="Estate by Environment",
            level=HierarchyLevel.ORGANISATION,
            lens_type=LateralLensType.ENVIRONMENT,
            aggregate_cost=total_cost,
            budget_amount=Decimal("50000.00"),
            budget_utilisation_pct=(
                (total_cost / Decimal("50000.00") * Decimal("100")).quantize(Decimal("0.01"))
            ),
            worst_child_threshold_state=worst_state,
            direct_resource_count=0,
            total_descendant_resource_count=total_count,
            child_count=len(env_nodes),
            children=env_nodes,
        )

    def _build_owner_lens_tree(self, resources: list[InventoryResource35]) -> HierarchyNode:
        """Lens: Owner (including 'Unowned') -> Resource."""
        owners = sorted({r.owner_name or "Unowned" for r in resources})
        owner_nodes: list[HierarchyNode] = []

        for owner in owners:
            owner_res = [r for r in resources if (r.owner_name or "Unowned") == owner]
            leaves = [self._resource_to_leaf(r) for r in owner_res]
            owner_cost = sum((r.monthly_cost for r in owner_res), Decimal("0.00"))
            owner_worst = self._combine_threshold_states(
                [leaf.worst_child_threshold_state for leaf in leaves]
            )
            owner_nodes.append(
                HierarchyNode(
                    id=f"lens-owner-{owner.lower().replace(' ', '-')}",
                    name=owner,
                    level=HierarchyLevel.GROUP,
                    lens_type=LateralLensType.OWNER,
                    aggregate_cost=owner_cost,
                    budget_amount=Decimal("10000.00"),
                    budget_utilisation_pct=(
                        (owner_cost / Decimal("10000.00") * Decimal("100")).quantize(
                            Decimal("0.01")
                        )
                    ),
                    worst_child_threshold_state=owner_worst,
                    direct_resource_count=len(leaves),
                    total_descendant_resource_count=len(leaves),
                    child_count=len(leaves),
                    children=leaves,
                )
            )

        total_cost = sum((o.aggregate_cost for o in owner_nodes), Decimal("0.00"))
        worst_state = self._combine_threshold_states(
            [o.worst_child_threshold_state for o in owner_nodes]
        )
        total_count = sum(o.total_descendant_resource_count for o in owner_nodes)

        return HierarchyNode(
            id="lens-root-owner",
            name="Estate by Owner",
            level=HierarchyLevel.ORGANISATION,
            lens_type=LateralLensType.OWNER,
            aggregate_cost=total_cost,
            budget_amount=Decimal("50000.00"),
            budget_utilisation_pct=(
                (total_cost / Decimal("50000.00") * Decimal("100")).quantize(Decimal("0.01"))
            ),
            worst_child_threshold_state=worst_state,
            direct_resource_count=0,
            total_descendant_resource_count=total_count,
            child_count=len(owner_nodes),
            children=owner_nodes,
        )

    def _build_region_lens_tree(self, resources: list[InventoryResource35]) -> HierarchyNode:
        """Lens: Region -> Service -> Resource."""
        regions = sorted({r.region_id for r in resources})
        region_nodes: list[HierarchyNode] = []

        for reg in regions:
            reg_res = [r for r in resources if r.region_id == reg]
            services = sorted({r.service_name for r in reg_res})
            svc_nodes: list[HierarchyNode] = []

            for svc in services:
                svc_res = [r for r in reg_res if r.service_name == svc]
                leaves = [self._resource_to_leaf(r) for r in svc_res]
                svc_cost = sum((r.monthly_cost for r in svc_res), Decimal("0.00"))
                svc_worst = self._combine_threshold_states(
                    [leaf.worst_child_threshold_state for leaf in leaves]
                )
                svc_nodes.append(
                    HierarchyNode(
                        id=f"reg-{reg}-svc-{svc.lower().replace(' ', '-')}",
                        name=svc,
                        level=HierarchyLevel.SERVICE,
                        lens_type=LateralLensType.REGION,
                        aggregate_cost=svc_cost,
                        budget_amount=Decimal("0.00"),
                        budget_utilisation_pct=Decimal("0.00"),
                        worst_child_threshold_state=svc_worst,
                        direct_resource_count=len(leaves),
                        total_descendant_resource_count=len(leaves),
                        child_count=len(leaves),
                        children=leaves,
                    )
                )

            reg_cost = sum((s.aggregate_cost for s in svc_nodes), Decimal("0.00"))
            reg_worst = self._combine_threshold_states(
                [s.worst_child_threshold_state for s in svc_nodes]
            )
            region_nodes.append(
                HierarchyNode(
                    id=f"lens-reg-{reg}",
                    name=reg,
                    level=HierarchyLevel.GROUP,
                    lens_type=LateralLensType.REGION,
                    aggregate_cost=reg_cost,
                    budget_amount=Decimal("15000.00"),
                    budget_utilisation_pct=(
                        (reg_cost / Decimal("15000.00") * Decimal("100")).quantize(Decimal("0.01"))
                    ),
                    worst_child_threshold_state=reg_worst,
                    direct_resource_count=0,
                    total_descendant_resource_count=sum(
                        s.total_descendant_resource_count for s in svc_nodes
                    ),
                    child_count=len(svc_nodes),
                    children=svc_nodes,
                )
            )

        total_cost = sum((r.aggregate_cost for r in region_nodes), Decimal("0.00"))
        worst_state = self._combine_threshold_states(
            [r.worst_child_threshold_state for r in region_nodes]
        )
        total_count = sum(r.total_descendant_resource_count for r in region_nodes)

        return HierarchyNode(
            id="lens-root-region",
            name="Estate by Region",
            level=HierarchyLevel.ORGANISATION,
            lens_type=LateralLensType.REGION,
            aggregate_cost=total_cost,
            budget_amount=Decimal("50000.00"),
            budget_utilisation_pct=(
                (total_cost / Decimal("50000.00") * Decimal("100")).quantize(Decimal("0.01"))
            ),
            worst_child_threshold_state=worst_state,
            direct_resource_count=0,
            total_descendant_resource_count=total_count,
            child_count=len(region_nodes),
            children=region_nodes,
        )

    def _build_tag_lens_tree(self, resources: list[InventoryResource35]) -> HierarchyNode:
        """Lens: Tag Key -> Tag Value -> Resource."""
        # Standard tag keys
        all_keys = {"Environment", "CostCenter", "Owner", "Project"}
        key_nodes: list[HierarchyNode] = []

        for k in sorted(all_keys):
            # Find values for this tag key
            val_map: dict[str, list[InventoryResource35]] = {}
            for r in resources:
                matched_val = None
                for t in r.tags:
                    if t.get("key") == k:
                        matched_val = t.get("value")
                        break
                val_key = matched_val if matched_val is not None else "(Untagged)"
                val_map.setdefault(val_key, []).append(r)

            val_nodes: list[HierarchyNode] = []
            for val, val_res in sorted(val_map.items()):
                leaves = [self._resource_to_leaf(r) for r in val_res]
                val_cost = sum((r.monthly_cost for r in val_res), Decimal("0.00"))
                val_worst = self._combine_threshold_states(
                    [leaf.worst_child_threshold_state for leaf in leaves]
                )
                val_nodes.append(
                    HierarchyNode(
                        id=f"tag-{k.lower()}-val-{val.lower().replace(' ', '-')}",
                        name=f"{val}",
                        level=HierarchyLevel.SUB_GROUP,
                        lens_type=LateralLensType.TAG,
                        aggregate_cost=val_cost,
                        budget_amount=Decimal("0.00"),
                        budget_utilisation_pct=Decimal("0.00"),
                        worst_child_threshold_state=val_worst,
                        direct_resource_count=len(leaves),
                        total_descendant_resource_count=len(leaves),
                        child_count=len(leaves),
                        children=leaves,
                    )
                )

            k_cost = sum((v.aggregate_cost for v in val_nodes), Decimal("0.00"))
            k_worst = self._combine_threshold_states(
                [v.worst_child_threshold_state for v in val_nodes]
            )
            key_nodes.append(
                HierarchyNode(
                    id=f"lens-tag-{k.lower()}",
                    name=f"Tag: {k}",
                    level=HierarchyLevel.GROUP,
                    lens_type=LateralLensType.TAG,
                    aggregate_cost=k_cost,
                    budget_amount=Decimal("0.00"),
                    budget_utilisation_pct=Decimal("0.00"),
                    worst_child_threshold_state=k_worst,
                    direct_resource_count=0,
                    total_descendant_resource_count=sum(
                        v.total_descendant_resource_count for v in val_nodes
                    ),
                    child_count=len(val_nodes),
                    children=val_nodes,
                )
            )

        total_cost = sum((k.aggregate_cost for k in key_nodes), Decimal("0.00"))
        worst_state = self._combine_threshold_states(
            [k.worst_child_threshold_state for k in key_nodes]
        )
        total_count = sum(k.total_descendant_resource_count for k in key_nodes)

        return HierarchyNode(
            id="lens-root-tag",
            name="Estate by Tag Key",
            level=HierarchyLevel.ORGANISATION,
            lens_type=LateralLensType.TAG,
            aggregate_cost=total_cost,
            budget_amount=Decimal("50000.00"),
            budget_utilisation_pct=(
                (total_cost / Decimal("50000.00") * Decimal("100")).quantize(Decimal("0.01"))
            ),
            worst_child_threshold_state=worst_state,
            direct_resource_count=0,
            total_descendant_resource_count=total_count,
            child_count=len(key_nodes),
            children=key_nodes,
        )

    # --------------------------------------------------------------------------
    # Node Detail Pane (Prompt 38)
    # --------------------------------------------------------------------------

    def get_node_detail(
        self,
        node_id: str,
        lens_type: LateralLensType,
        tenant_context: TenantContext,
    ) -> HierarchyDetailPane:
        """Retrieves detail pane for specific hierarchy node."""
        tree = self.get_hierarchy_tree(lens_type=lens_type, tenant_context=tenant_context)

        # Traverse tree to locate node and trace path
        path: list[HierarchyNode] = []

        def find_node(curr: HierarchyNode, target_id: str) -> HierarchyNode | None:
            path.append(curr)
            if curr.id == target_id:
                return curr
            for child in curr.children:
                res = find_node(child, target_id)
                if res:
                    return res
            path.pop()
            return None

        found = find_node(tree, node_id)
        if not found:
            # Fallback to root if node not found
            found = tree
            path = [tree]

        breadcrumbs = [p.name for p in path]

        # Collect direct or descendant resources
        scoped_resources = [
            r for r in self._resources.values() if self._is_resource_in_scope(r, tenant_context)
        ]

        # Top contributing services under this node
        contributions: dict[str, Decimal] = {}
        matched_resources: list[InventoryResource35] = []

        def collect_leaves(n: HierarchyNode) -> list[str]:
            if n.level == HierarchyLevel.RESOURCE:
                return [n.id]
            res_ids: list[str] = []
            for c in n.children:
                res_ids.extend(collect_leaves(c))
            return res_ids

        leaf_ids = set(collect_leaves(found))
        for r in scoped_resources:
            if r.id in leaf_ids:
                matched_resources.append(r)
                contributions[r.service_name] = (
                    contributions.get(r.service_name, Decimal("0.00")) + r.monthly_cost
                )

        top_services = [
            {"service_name": k, "spend": float(v)}
            for k, v in sorted(contributions.items(), key=lambda item: item[1], reverse=True)[:5]
        ]

        return HierarchyDetailPane(
            node_id=found.id,
            name=found.name,
            lens_type=lens_type,
            level=found.level,
            provider=found.provider,
            native_type=found.native_type,
            aggregate_cost=found.aggregate_cost,
            budget_amount=found.budget_amount,
            budget_utilisation_pct=found.budget_utilisation_pct,
            threshold_state=found.worst_child_threshold_state,
            direct_resources=matched_resources[:20],
            top_contributing_services=top_services,
            breadcrumbs=breadcrumbs,
        )

    # --------------------------------------------------------------------------
    # Scope-Safe Global Search (FR-580, FR-585)
    # --------------------------------------------------------------------------

    def search_global(
        self,
        query: str,
        tenant_context: TenantContext,
        limit: int = 25,
    ) -> GlobalSearchResponse:
        """Performs scope-safe search across 9 entity types.

        Ranks exact identifier matches first.
        Never discloses existence or names of entities outside caller's scope grants (FR-585).
        """
        clean_q = query.strip()
        if not clean_q:
            return GlobalSearchResponse(
                query=query,
                total_matches=0,
                results=[],
                is_scope_restricted=("*" not in tenant_context.scope_grants),
            )

        lower_q = clean_q.lower()
        is_restricted = "*" not in tenant_context.scope_grants
        user_scopes = set(tenant_context.scope_grants)

        # Build index of 9 entity types
        entities: list[GlobalSearchItem] = []

        # 1. Resources
        for r in self._resources.values():
            entities.append(
                GlobalSearchItem(
                    id=r.id,
                    entity_type="RESOURCE",
                    identifier=r.native_id,
                    title=r.name,
                    subtitle=f"{r.provider} • {r.service_name} • {r.region_id}",
                    provider=r.provider,
                    scope_id=r.scope_id,
                    deep_link=f"/inventory?resource_id={r.id}",
                )
            )

        # 2. Services
        service_names = {
            r.service_name: (r.service_id, r.provider, r.scope_id) for r in self._resources.values()
        }
        for s_name, (s_id, prov, sc_id) in service_names.items():
            entities.append(
                GlobalSearchItem(
                    id=f"svc-{s_id}",
                    entity_type="SERVICE",
                    identifier=s_id,
                    title=s_name,
                    subtitle=f"Service • Provider: {prov}",
                    provider=prov,
                    scope_id=sc_id,
                    deep_link=f"/services?service_id={s_id}",
                )
            )

        # 3. Scopes
        scope_defs = [
            ("sc-aws-prod-1", "AWS Core Production", "AWS", "o-enterprise-root"),
            ("sc-aws-dev-1", "AWS Dev Sandbox", "AWS", "o-enterprise-root"),
            ("sc-azure-prod-1", "Azure Corporate Production", "Azure", "t-azure-enterprise"),
            ("sc-gcp-analytics-1", "GCP Analytics Tier", "GCP", "org-gcp-enterprise"),
            ("sc-oci-core-1", "OCI Core Infrastructure", "OCI", "ocid1.tenancy.oc1..enterprise"),
        ]
        for sid, sname, prov, p_org in scope_defs:
            entities.append(
                GlobalSearchItem(
                    id=sid,
                    entity_type="SCOPE",
                    identifier=sid,
                    title=sname,
                    subtitle=f"Scope Boundary • {prov} • {p_org}",
                    provider=prov,
                    scope_id=sid,
                    deep_link=f"/hierarchy?scope_id={sid}",
                )
            )

        # 4. Applications
        apps = [
            ("app-payments", "Payments Core", "sc-aws-prod-1"),
            ("app-checkout", "Checkout Service", "sc-azure-prod-1"),
            ("app-inventory", "Inventory Mgmt", "sc-azure-prod-1"),
            ("app-analytics", "Customer Analytics", "sc-gcp-analytics-1"),
            ("app-warehouse", "Data Warehouse", "sc-gcp-analytics-1"),
        ]
        for aid, aname, sc_id in apps:
            entities.append(
                GlobalSearchItem(
                    id=aid,
                    entity_type="APPLICATION",
                    identifier=aid,
                    title=aname,
                    subtitle="Application System",
                    scope_id=sc_id,
                    deep_link=f"/applications?app_id={aid}",
                )
            )

        # 5. Budgets
        budgets = [
            ("bgt-finops-core", "Core FinOps Q4 Budget", "sc-aws-prod-1"),
            ("bgt-azure-corp", "Azure Corporate FY26 Budget", "sc-azure-prod-1"),
            ("bgt-gcp-lake", "GCP Data Platform Annual Budget", "sc-gcp-analytics-1"),
            ("bgt-oci-tier", "OCI Infrastructure Budget", "sc-oci-core-1"),
        ]
        for bid, bname, sc_id in budgets:
            entities.append(
                GlobalSearchItem(
                    id=bid,
                    entity_type="BUDGET",
                    identifier=bid,
                    title=bname,
                    subtitle="Financial Control Budget",
                    scope_id=sc_id,
                    deep_link=f"/budgets?budget_id={bid}",
                )
            )

        # 6. Owners
        owners = [
            ("usr-alice", "Alice Engineer", "alice@example.com", "sc-aws-prod-1"),
            ("usr-bob", "Bob DBA", "bob@example.com", "sc-aws-prod-1"),
            ("usr-carol", "Carol Ops", "carol@example.com", "sc-azure-prod-1"),
            ("usr-dave", "Dave Architect", "dave@example.com", "sc-gcp-analytics-1"),
        ]
        for oid, oname, email, sc_id in owners:
            entities.append(
                GlobalSearchItem(
                    id=oid,
                    entity_type="OWNER",
                    identifier=email,
                    title=oname,
                    subtitle=f"Resource Owner • {email}",
                    scope_id=sc_id,
                    deep_link=f"/inventory?owner={oname}",
                )
            )

        # 7. Connectors
        connectors = [
            ("conn-aws-root", "AWS Multi-Account Connector", "AWS", "sc-aws-prod-1"),
            ("conn-az-prod", "Azure EA Enterprise Connector", "Azure", "sc-azure-prod-1"),
            ("conn-gcp-org", "GCP Billing Export Connector", "GCP", "sc-gcp-analytics-1"),
            ("conn-oci-ten", "OCI Tenancy Sync Connector", "OCI", "sc-oci-core-1"),
        ]
        for cid, cname, prov, sc_id in connectors:
            entities.append(
                GlobalSearchItem(
                    id=cid,
                    entity_type="CONNECTOR",
                    identifier=cid,
                    title=cname,
                    subtitle=f"Cloud Connector • {prov}",
                    provider=prov,
                    scope_id=sc_id,
                    deep_link=f"/connectors?connector_id={cid}",
                )
            )

        # 8. Policies
        policies = [
            ("pol-tag-req", "Mandatory FinOps Tagging Policy", "sc-aws-prod-1"),
            ("pol-vm-rightsize", "Underutilised VM Rightsizing Policy", "sc-azure-prod-1"),
            ("pol-storage-lifecycle", "Storage Cold Archive Policy", "sc-gcp-analytics-1"),
        ]
        for pid, pname, sc_id in policies:
            entities.append(
                GlobalSearchItem(
                    id=pid,
                    entity_type="POLICY",
                    identifier=pid,
                    title=pname,
                    subtitle="Governance Tag & Cost Policy",
                    scope_id=sc_id,
                    deep_link=f"/policies?policy_id={pid}",
                )
            )

        # 9. Alerts
        alerts = [
            ("alt-aws-spike", "EC2 Cost Velocity Anomaly Alert", "sc-aws-prod-1"),
            ("alt-sql-budget", "Azure SQL Budget Threshold Warning", "sc-azure-prod-1"),
            ("alt-gke-unallocated", "GKE Unallocated Cluster Waste Alert", "sc-gcp-analytics-1"),
        ]
        for aid, aname, sc_id in alerts:
            entities.append(
                GlobalSearchItem(
                    id=aid,
                    entity_type="ALERT",
                    identifier=aid,
                    title=aname,
                    subtitle="Anomaly & Threshold Alert",
                    scope_id=sc_id,
                    deep_link=f"/alerts?alert_id={aid}",
                )
            )

        # Scope Filtering & Ranking
        matched_results: list[GlobalSearchItem] = []

        for item in entities:
            # Scope-safe check (FR-585): never disclose entities outside caller's scope
            if is_restricted and item.scope_id not in user_scopes:
                continue

            # Check matches
            ident_lower = item.identifier.lower()
            title_lower = item.title.lower()
            sub_lower = item.subtitle.lower()
            id_lower = item.id.lower()

            # Exact-identifier match ranked highest (rank_score = 1.0)
            if lower_q == ident_lower or lower_q == id_lower:
                matched_results.append(item.model_copy(update={"rank_score": 1.0}))
            elif lower_q == title_lower:
                matched_results.append(item.model_copy(update={"rank_score": 0.9}))
            elif ident_lower.startswith(lower_q) or title_lower.startswith(lower_q):
                matched_results.append(item.model_copy(update={"rank_score": 0.75}))
            elif lower_q in ident_lower or lower_q in title_lower or lower_q in sub_lower:
                matched_results.append(item.model_copy(update={"rank_score": 0.5}))

        # Sort: Rank score descending, then title ascending
        matched_results.sort(key=lambda x: (-x.rank_score, x.title))

        return GlobalSearchResponse(
            query=query,
            total_matches=len(matched_results),
            results=matched_results[:limit],
            is_scope_restricted=is_restricted,
        )

    # --------------------------------------------------------------------------
    # Multi-Attribute Structured Filtering (FR-107, FR-581, FR-584)
    # --------------------------------------------------------------------------

    def _matches_filter(
        self,
        resource: InventoryResource35,
        q: InventoryFilterQuery,
        tenant_context: TenantContext,
    ) -> bool:
        """Evaluates boolean combination semantics: AND across filter types, OR within multi-selects."""
        # Scope grant boundary
        if not self._is_resource_in_scope(resource, tenant_context):
            return False

        # Providers (OR)
        if q.providers:
            if resource.provider.upper() not in [p.upper() for p in q.providers]:
                return False

        # Billing Boundaries (OR)
        if q.billing_boundaries:
            if not any(
                b in resource.native_id or b in resource.scope_id for b in q.billing_boundaries
            ):
                return False

        # Scope Subtrees (OR)
        if q.scope_subtrees:
            if resource.scope_id not in q.scope_subtrees:
                return False

        # Services (OR)
        if q.services:
            if resource.service_id not in q.services and resource.service_name not in q.services:
                return False

        # Categories (OR)
        if q.categories:
            if resource.service_category not in q.categories:
                return False

        # Resource Types (OR)
        if q.resource_types:
            if resource.resource_type not in q.resource_types:
                return False

        # Regions (OR)
        if q.regions:
            if resource.region_id not in q.regions:
                return False

        # Zones (OR)
        if q.zones:
            if not resource.availability_zone or resource.availability_zone not in q.zones:
                return False

        # Applications (OR)
        if q.applications:
            app_matches = [
                q_app.lower() in (resource.application_name or "").lower()
                or q_app == resource.application_id
                for q_app in q.applications
            ]
            if not any(app_matches):
                return False

        # Projects (OR)
        if q.projects:
            prj_matches = [
                q_prj.lower() in (resource.project_name or "").lower()
                or q_prj == resource.project_id
                for q_prj in q.projects
            ]
            if not any(prj_matches):
                return False

        # Environments (OR)
        if q.environments:
            if not resource.environment_name or resource.environment_name not in q.environments:
                return False

        # Owners (OR, including 'Unowned')
        if q.owners:
            owner_val = resource.owner_name or "Unowned"
            if not any(o.lower() == owner_val.lower() for o in q.owners):
                return False

        # Cost Centers (OR)
        if q.cost_centers:
            if not resource.cost_center_name or resource.cost_center_name not in q.cost_centers:
                return False

        # Business Units (OR)
        if q.business_units:
            if (
                not resource.business_unit_name
                or resource.business_unit_name not in q.business_units
            ):
                return False

        # Min / Max Cost
        if q.min_cost is not None and resource.monthly_cost < q.min_cost:
            return False
        if q.max_cost is not None and resource.monthly_cost > q.max_cost:
            return False

        # Runtime States (OR)
        if q.runtime_states:
            if resource.runtime_state not in q.runtime_states:
                return False

        # Lifecycle Statuses (OR)
        if q.lifecycle_statuses:
            if resource.lifecycle_status not in q.lifecycle_statuses:
                return False

        # Threshold States (OR)
        if q.threshold_states:
            res_th = self.get_resource_threshold_state(resource)
            if res_th not in q.threshold_states:
                return False

        # Tag Filters (supports exists, not_exists, eq, ne)
        if q.tag_filters:
            res_tags = {t.get("key"): t.get("value") for t in resource.tags}
            for tf in q.tag_filters:
                if tf.operator == "exists":
                    if tf.key not in res_tags:
                        return False
                elif tf.operator == "not_exists":
                    if tf.key in res_tags:
                        return False
                elif tf.operator == "eq":
                    if res_tags.get(tf.key) != tf.value:
                        return False
                elif tf.operator == "ne":
                    if res_tags.get(tf.key) == tf.value:
                        return False

        # Free-text search
        if q.search:
            s_low = q.search.strip().lower()
            searchable = f"{resource.name} {resource.native_id} {resource.service_name} {resource.application_name or ''} {resource.owner_name or ''}".lower()
            if s_low not in searchable:
                return False

        return True

    def preview_filter_counts(
        self,
        query: InventoryFilterQuery,
        tenant_context: TenantContext,
    ) -> FilterCountPreview:
        """Reactive count preview before full result pagination loads (FR-584).

        Enforces constraint: Does not load the full result set or build objects before showing counts.
        """
        match_count = 0
        total_spend = Decimal("0.00")
        provider_counts: dict[str, int] = {}
        env_counts: dict[str, int] = {}

        # Streaming aggregation pass
        for resource in self._resources.values():
            if self._matches_filter(resource, query, tenant_context):
                match_count += 1
                total_spend += resource.monthly_cost

                # Tally distributions
                p = resource.provider
                provider_counts[p] = provider_counts.get(p, 0) + 1

                env = resource.environment_name or "Unassigned"
                env_counts[env] = env_counts.get(env, 0) + 1

        return FilterCountPreview(
            matching_count=match_count,
            total_spend=total_spend,
            currency="USD",
            counts_by_provider=provider_counts,
            counts_by_environment=env_counts,
        )

    def query_inventory(
        self,
        query: InventoryFilterQuery,
        tenant_context: TenantContext,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[int, list[InventoryResource35]]:
        """Queries 35-field inventory with pagination after matching filters."""
        matched: list[InventoryResource35] = []
        for resource in self._resources.values():
            if self._matches_filter(resource, query, tenant_context):
                matched.append(resource)

        # Sort deterministically by name
        matched.sort(key=lambda r: r.name)
        total = len(matched)
        return total, matched[offset : offset + limit]

    # --------------------------------------------------------------------------
    # Bulk Curated Field Assignment (Prompt 38 / FR-108)
    # --------------------------------------------------------------------------

    def bulk_assign_curated_fields(
        self,
        request: BulkAssignmentRequest,
        tenant_context: TenantContext,
    ) -> BulkAssignmentResponse:
        """Bulk updates ownership, application, environment, and cost centre across resources."""
        updated = 0
        modified_fields: list[str] = []

        if request.owner_name is not None:
            modified_fields.append("owner_name")
        if request.owner_email is not None:
            modified_fields.append("owner_email")
        if request.application_name is not None:
            modified_fields.append("application_name")
        if request.environment_name is not None:
            modified_fields.append("environment_name")
        if request.cost_center is not None:
            modified_fields.append("cost_center_name")

        for rid in request.resource_ids:
            if rid in self._resources:
                res = self._resources[rid]
                # Enforce caller scope boundary
                if not self._is_resource_in_scope(res, tenant_context):
                    continue

                updated_dict = res.model_dump()
                if request.owner_name is not None:
                    updated_dict["owner_name"] = request.owner_name
                if request.owner_email is not None:
                    updated_dict["owner_email"] = request.owner_email
                if request.application_name is not None:
                    updated_dict["application_name"] = request.application_name
                if request.environment_name is not None:
                    updated_dict["environment_name"] = request.environment_name
                if request.cost_center is not None:
                    updated_dict["cost_center_name"] = request.cost_center

                self._resources[rid] = InventoryResource35(**updated_dict)
                updated += 1

        return BulkAssignmentResponse(
            updated_count=updated,
            modified_fields=modified_fields,
            applied_at=datetime.now(UTC),
        )

    # --------------------------------------------------------------------------
    # Saved Views (FR-583)
    # --------------------------------------------------------------------------

    def save_view(
        self,
        view: SavedInventoryView,
        tenant_context: TenantContext,
    ) -> SavedInventoryView:
        """Saves custom named inventory filter configuration."""
        _ = tenant_context.tenant_id
        self._saved_views[view.id] = view
        return view

    def list_saved_views(self, tenant_context: TenantContext) -> list[SavedInventoryView]:
        """Lists accessible saved views."""
        _ = tenant_context.tenant_id
        return list(self._saved_views.values())

    def delete_saved_view(self, view_id: str, tenant_context: TenantContext) -> bool:
        """Deletes a saved view."""
        _ = tenant_context.tenant_id
        if view_id in self._saved_views:
            del self._saved_views[view_id]
            return True
        return False

    # --------------------------------------------------------------------------
    # Scope-Respecting Export
    # --------------------------------------------------------------------------

    def export_inventory(
        self,
        query: InventoryFilterQuery,
        export_format: str,
        tenant_context: TenantContext,
    ) -> tuple[str, str]:
        """Exports 35-field inventory matching filter into CSV or JSON respecting scope grants."""
        _, resources = self.query_inventory(query, tenant_context, limit=10000, offset=0)

        if export_format.lower() == "json":
            payload = json.dumps([r.model_dump(mode="json") for r in resources], indent=2)
            return payload, "application/json"

        # CSV Export with all 35 canonical headers
        output = io.StringIO()
        fieldnames = [
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
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for r in resources:
            d = r.model_dump(mode="json")
            d["tags"] = json.dumps(d.get("tags", []))
            writer.writerow(d)

        return output.getvalue(), "text/csv"

    def get_resource_by_id(self, resource_id: str) -> InventoryResource35 | None:
        """Retrieves a single 35-field inventory resource by ID."""
        return self._resources.get(resource_id)

    def get_all_resources(self) -> list[InventoryResource35]:
        """Returns all 35-field inventory resources in the estate."""
        return list(self._resources.values())


# Global singleton instance
_hierarchy_service: HierarchyService | None = None
_hierarchy_service_lock = threading.Lock()


def get_hierarchy_service() -> HierarchyService:
    """Returns singleton instance of HierarchyService."""
    global _hierarchy_service
    if _hierarchy_service is None:
        with _hierarchy_service_lock:
            if _hierarchy_service is None:
                _hierarchy_service = HierarchyService()
    return _hierarchy_service


def reset_hierarchy_service() -> None:
    """Resets singleton instance for test isolation."""
    global _hierarchy_service
    with _hierarchy_service_lock:
        _hierarchy_service = None
