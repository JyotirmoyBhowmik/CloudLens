"""Unit Tests for Multi-Cloud Scope Hierarchy Fixtures.

Acceptance Criteria:
- All four provider hierarchies (AWS, Azure, GCP, OCI) can be represented with
  no loss of native type, native identifier or parentage, demonstrated by fixtures for each provider.
- SUB_GROUP is legitimately absent for AWS and GCP — modeled as a valid state, not as an error.
- Single self-referencing tree; no parallel hierarchy tables.
"""

from domain.models.enums import ProviderType, ScopeAbsenceReason, ScopeRole
from domain.models.scope import Scope, ScopeTree


def test_azure_management_group_hierarchy_fixture():
    """Verify Azure hierarchy: Tenant -> Root MG -> MG -> Sub-MG -> Subscription -> Billing Account.

    Verifies native type 'ManagementGroup' mapped to canonical role 'GROUP' without loss.
    """
    tree = ScopeTree()

    # 1. Tenant
    tenant = tree.add_scope(
        Scope(
            id="az-scope-tenant",
            tenant_id="tenant-corp-01",
            name="Contoso Tenant",
            canonical_role=ScopeRole.TENANT,
            provider=ProviderType.AZURE,
            native_type="AzureTenant",
            native_id="72f988bf-86f1-41af-91ab-2d7cd011db47",
            provider_native={
                "displayName": "Contoso Corp",
                "tenantId": "72f988bf-86f1-41af-91ab-2d7cd011db47",
            },
        )
    )

    # 2. Root Group
    root_mg = tree.add_scope(
        Scope(
            id="az-scope-root-mg",
            tenant_id="tenant-corp-01",
            parent_id=tenant.id,
            name="Tenant Root Group",
            canonical_role=ScopeRole.ROOT_GROUP,
            provider=ProviderType.AZURE,
            native_type="TenantRootGroup",
            native_id="/providers/Microsoft.Management/managementGroups/72f988bf-86f1-41af-91ab-2d7cd011db47",
            provider_native={"type": "/providers/Microsoft.Management/managementGroups"},
        )
    )

    # 3. Management Group mapped to GROUP
    core_mg = tree.add_scope(
        Scope(
            id="az-scope-core-mg",
            tenant_id="tenant-corp-01",
            parent_id=root_mg.id,
            name="Core Platform MG",
            canonical_role=ScopeRole.GROUP,
            provider=ProviderType.AZURE,
            native_type="ManagementGroup",  # Native type preserved verbatim
            native_id="/providers/Microsoft.Management/managementGroups/core-platform-mg",
            provider_native={"details": {"parent": {"id": root_mg.native_id}}},
        )
    )

    # 4. Sub-Group (Management Group)
    finops_mg = tree.add_scope(
        Scope(
            id="az-scope-finops-mg",
            tenant_id="tenant-corp-01",
            parent_id=core_mg.id,
            name="FinOps Shared Services MG",
            canonical_role=ScopeRole.SUB_GROUP,
            provider=ProviderType.AZURE,
            native_type="ManagementGroup",
            native_id="/providers/Microsoft.Management/managementGroups/finops-shared-mg",
        )
    )

    # 5. Billing Boundary (Subscription)
    sub = tree.add_scope(
        Scope(
            id="az-scope-sub-prod",
            tenant_id="tenant-corp-01",
            parent_id=finops_mg.id,
            name="Production Services Subscription",
            canonical_role=ScopeRole.BILLING_BOUNDARY,
            provider=ProviderType.AZURE,
            native_type="Subscription",
            native_id="/subscriptions/a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            provider_native={"state": "Enabled", "subscriptionPolicies": {"spendingLimit": "Off"}},
        )
    )

    # Verify native attributes, parentage, and materialized path
    assert core_mg.native_type == "ManagementGroup"
    assert core_mg.canonical_role == ScopeRole.GROUP
    assert finops_mg.is_sub_group_applicable is True
    assert sub.native_type == "Subscription"
    assert (
        sub.materialized_path == f"/{tenant.id}/{root_mg.id}/{core_mg.id}/{finops_mg.id}/{sub.id}"
    )
    assert sub.depth == 4


def test_aws_organization_unit_hierarchy_fixture():
    """Verify AWS hierarchy: Org -> Root OU -> OU (GROUP) -> Member Account (BILLING_BOUNDARY).

    Verifies native type 'OrganizationalUnit' mapped to 'GROUP' and SUB_GROUP absence modeled as valid state.
    """
    tree = ScopeTree()

    # 1. AWS Org Tenant
    org = tree.add_scope(
        Scope(
            id="aws-scope-org",
            tenant_id="tenant-corp-01",
            name="AWS Organization Master",
            canonical_role=ScopeRole.TENANT,
            provider=ProviderType.AWS,
            native_type="AWSOrganization",
            native_id="o-awsenterprise01",
            provider_native={
                "Arn": "arn:aws:organizations::111122223333:organization/o-awsenterprise01"
            },
        )
    )

    # 2. Root OU
    root_ou = tree.add_scope(
        Scope(
            id="aws-scope-root",
            tenant_id="tenant-corp-01",
            parent_id=org.id,
            name="Root",
            canonical_role=ScopeRole.ROOT_GROUP,
            provider=ProviderType.AWS,
            native_type="RootOU",
            native_id="r-root01",
            provider_native={
                "Id": "r-root01",
                "Arn": "arn:aws:organizations::111122223333:root/o-awsenterprise01/r-root01",
            },
        )
    )

    # 3. OrganizationalUnit mapped to GROUP
    workload_ou = tree.add_scope(
        Scope(
            id="aws-scope-workloads-ou",
            tenant_id="tenant-corp-01",
            parent_id=root_ou.id,
            name="Production Workloads OU",
            canonical_role=ScopeRole.GROUP,
            provider=ProviderType.AWS,
            native_type="OrganizationalUnit",  # Native type preserved verbatim
            native_id="ou-root01-workloads",
            provider_native={"Id": "ou-root01-workloads", "ParentId": "r-root01"},
        )
    )

    # 4. Member Account as BILLING_BOUNDARY
    account = tree.add_scope(
        Scope(
            id="aws-scope-acc-prod",
            tenant_id="tenant-corp-01",
            parent_id=workload_ou.id,
            name="Core Banking Production Account",
            canonical_role=ScopeRole.BILLING_BOUNDARY,
            provider=ProviderType.AWS,
            native_type="Account",
            native_id="111122223333",
            provider_native={"Status": "ACTIVE", "JoinedMethod": "CREATED"},
        )
    )

    # Assert SUB_GROUP absence is modeled as a valid state (not bare null or error)
    assert workload_ou.is_sub_group_applicable is False
    assert workload_ou.sub_group_absence_reason == ScopeAbsenceReason.NOT_APPLICABLE_TO_PROVIDER
    assert account.is_sub_group_applicable is False
    assert account.sub_group_absence_reason == ScopeAbsenceReason.NOT_APPLICABLE_TO_PROVIDER

    # Assert hierarchy path and parentage
    assert workload_ou.canonical_role == ScopeRole.GROUP
    assert workload_ou.native_type == "OrganizationalUnit"
    assert account.materialized_path == f"/{org.id}/{root_ou.id}/{workload_ou.id}/{account.id}"
    assert account.depth == 3


def test_gcp_folder_hierarchy_fixture():
    """Verify GCP hierarchy: CloudIdentity -> Org -> Folder (GROUP) -> Project (BILLING_BOUNDARY).

    Verifies native type 'Folder' mapped to 'GROUP' and SUB_GROUP absence modeled as valid state.
    """
    tree = ScopeTree()

    # 1. CloudIdentity Tenant
    identity = tree.add_scope(
        Scope(
            id="gcp-scope-identity",
            tenant_id="tenant-corp-01",
            name="GCP Cloud Identity Customer",
            canonical_role=ScopeRole.TENANT,
            provider=ProviderType.GCP,
            native_type="CloudIdentity",
            native_id="customers/C01234567",
        )
    )

    # 2. Organization
    org = tree.add_scope(
        Scope(
            id="gcp-scope-org",
            tenant_id="tenant-corp-01",
            parent_id=identity.id,
            name="example.com Organization",
            canonical_role=ScopeRole.ROOT_GROUP,
            provider=ProviderType.GCP,
            native_type="Organization",
            native_id="organizations/123456789012",
        )
    )

    # 3. Folder mapped to GROUP
    folder = tree.add_scope(
        Scope(
            id="gcp-scope-finance-folder",
            tenant_id="tenant-corp-01",
            parent_id=org.id,
            name="Finance Engineering Folder",
            canonical_role=ScopeRole.GROUP,
            provider=ProviderType.GCP,
            native_type="Folder",  # Native type preserved verbatim
            native_id="folders/987654321098",
            provider_native={"lifecycleState": "ACTIVE"},
        )
    )

    # 4. Project as BILLING_BOUNDARY
    project = tree.add_scope(
        Scope(
            id="gcp-scope-proj-prod",
            tenant_id="tenant-corp-01",
            parent_id=folder.id,
            name="FinOps Production Project",
            canonical_role=ScopeRole.BILLING_BOUNDARY,
            provider=ProviderType.GCP,
            native_type="Project",
            native_id="projects/cloudlens-prod-finance",
            provider_native={"projectNumber": "100200300400", "lifecycleState": "ACTIVE"},
        )
    )

    # Assert SUB_GROUP absence is modeled as a valid state
    assert folder.is_sub_group_applicable is False
    assert folder.sub_group_absence_reason == ScopeAbsenceReason.NOT_APPLICABLE_TO_PROVIDER
    assert project.materialized_path == f"/{identity.id}/{org.id}/{folder.id}/{project.id}"
    assert folder.canonical_role == ScopeRole.GROUP
    assert folder.native_type == "Folder"


def test_oci_compartment_hierarchy_fixture():
    """Verify OCI hierarchy: Tenancy -> Root Compartment -> Compartment (GROUP) -> Sub-Compartment.

    Verifies native type 'Compartment' mapped to 'GROUP' and SUB_GROUP support.
    """
    tree = ScopeTree()

    # 1. Tenancy
    tenancy = tree.add_scope(
        Scope(
            id="oci-scope-tenancy",
            tenant_id="tenant-corp-01",
            name="Enterprise OCI Tenancy",
            canonical_role=ScopeRole.TENANT,
            provider=ProviderType.OCI,
            native_type="Tenancy",
            native_id="ocid1.tenancy.oc1..aaaaaaaatenancy01",
        )
    )

    # 2. Root Compartment
    root_comp = tree.add_scope(
        Scope(
            id="oci-scope-root-comp",
            tenant_id="tenant-corp-01",
            parent_id=tenancy.id,
            name="Root Compartment",
            canonical_role=ScopeRole.ROOT_GROUP,
            provider=ProviderType.OCI,
            native_type="RootCompartment",
            native_id="ocid1.compartment.oc1..aaaaaaaroot01",
        )
    )

    # 3. Compartment mapped to GROUP
    app_comp = tree.add_scope(
        Scope(
            id="oci-scope-app-comp",
            tenant_id="tenant-corp-01",
            parent_id=root_comp.id,
            name="Application Workloads",
            canonical_role=ScopeRole.GROUP,
            provider=ProviderType.OCI,
            native_type="Compartment",  # Native type preserved verbatim
            native_id="ocid1.compartment.oc1..aaaaaaaaworkloads",
            provider_native={"lifecycleState": "ACTIVE"},
        )
    )

    # 4. Sub-Compartment as SUB_GROUP
    db_comp = tree.add_scope(
        Scope(
            id="oci-scope-db-comp",
            tenant_id="tenant-corp-01",
            parent_id=app_comp.id,
            name="Autonomous Databases Sub-Compartment",
            canonical_role=ScopeRole.SUB_GROUP,
            provider=ProviderType.OCI,
            native_type="Compartment",
            native_id="ocid1.compartment.oc1..aaaaaaadatabases",
            provider_native={"lifecycleState": "ACTIVE"},
        )
    )

    # Assert OCI SUB_GROUP is applicable
    assert db_comp.is_sub_group_applicable is True
    assert app_comp.canonical_role == ScopeRole.GROUP
    assert app_comp.native_type == "Compartment"
    assert db_comp.materialized_path == f"/{tenancy.id}/{root_comp.id}/{app_comp.id}/{db_comp.id}"
