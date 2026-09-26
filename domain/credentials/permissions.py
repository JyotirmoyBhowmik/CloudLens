"""Documented Least-Privilege Permission Reference Service (Prompt 12 Item 81).

Enforces:
- SEC-012 & SEC-016: Explicit per-provider mapping connecting each connector capability
  to minimum required permissions, required scope, and consequence if not granted.
- Prompt 15 Onboarding Wizard Integration: Delivers structured, renderable reference data
  and authoritative markdown documentation for AWS, Azure, GCP, and OCI estates.
- Strictly read-only: Zero write or mutate permissions across all providers.
"""

from pathlib import Path

from pydantic import BaseModel, Field

from domain.models.enums import ProviderCapability, ProviderType


class LeastPrivilegeRequirement(BaseModel):
    """Explicit mapping between a connector capability and its least-privilege requirements."""

    capability_code: ProviderCapability = Field(
        ..., description="Canonical capability flag (e.g. C-01)"
    )
    capability_name: str = Field(..., description="Human-readable capability name")
    minimum_permissions: list[str] = Field(
        ..., description="Specific API actions or roles required"
    )
    required_scope: str = Field(..., description="Hierarchy boundary required for evaluation")
    consequence_if_not_granted: str = Field(
        ...,
        description="Explicit business and technical consequence if permission is absent",
    )
    is_mandatory: bool = Field(
        default=True, description="Whether core FinOps analytics depend on this capability"
    )


class ProviderPermissionReference(BaseModel):
    """Complete least-privilege specification for a single cloud provider."""

    provider: ProviderType = Field(..., description="Provider identifier")
    provider_name: str = Field(..., description="Provider display name")
    primary_auth_mechanism: str = Field(
        ..., description="Recommended enterprise authentication approach"
    )
    supported_auth_mechanisms: list[str] = Field(
        default_factory=list, description="Allowed secondary methods"
    )
    forbidden_auth_mechanisms: list[str] = Field(
        default_factory=list, description="Strictly prohibited methods"
    )
    capabilities: list[LeastPrivilegeRequirement] = Field(
        default_factory=list, description="Capability mappings"
    )
    markdown_path: str = Field(..., description="Path to authoritative documentation artifact")


# ==============================================================================
# Authoritative Least-Privilege Catalogues by Provider
# ==============================================================================

AWS_PERMISSIONS = ProviderPermissionReference(
    provider=ProviderType.AWS,
    provider_name="Amazon Web Services (AWS)",
    primary_auth_mechanism="Cross-Account IAM Role + External ID (sts:AssumeRole)",
    supported_auth_mechanisms=[
        "OIDC Web Identity Federation (EKS / Workload)",
        "AWS IAM Identity Center Federation",
        "Audited IAM User Access Keys (Mandatory 90-day rotation)",
    ],
    forbidden_auth_mechanisms=[
        "AWS Root User Credentials",
        "Shared Static Long-Lived Passwords",
    ],
    markdown_path="docs/permissions/aws.md",
    capabilities=[
        LeastPrivilegeRequirement(
            capability_code=ProviderCapability.C01_HIERARCHY,
            capability_name="Hierarchy Discovery",
            minimum_permissions=[
                "organizations:DescribeOrganization",
                "organizations:ListAccounts",
                "organizations:ListRoots",
                "organizations:ListOrganizationalUnitsForParent",
                "organizations:ListAccountsForParent",
            ],
            required_scope="AWS Organizations Management Account or Delegated Administrator",
            consequence_if_not_granted=(
                "CloudLens cannot discover multi-account hierarchy; accounts must be added individually. "
                "Scope inheritance, OU-based cost allocation, and parent tag inheritance cannot function."
            ),
            is_mandatory=True,
        ),
        LeastPrivilegeRequirement(
            capability_code=ProviderCapability.C02_INVENTORY,
            capability_name="Resource Inventory",
            minimum_permissions=[
                "resource-explorer-2:Search",
                "tag:GetResources",
                "tag:GetTagKeys",
                "tag:GetTagValues",
            ],
            required_scope="AWS Account or Multi-Region Resource Explorer Aggregator",
            consequence_if_not_granted=(
                "Inventory discovery disabled. CloudLens cannot identify orphan resources, unallocated workloads, "
                "or evaluate resource-level tag hygiene policies."
            ),
            is_mandatory=True,
        ),
        LeastPrivilegeRequirement(
            capability_code=ProviderCapability.C03_COST,
            capability_name="Cost & Billing Ingestion",
            minimum_permissions=[
                "ce:GetCostAndUsage",
                "ce:GetCostAndUsageWithResources",
                "s3:GetObject on CUR/Cost & Usage Report S3 Bucket",
                "s3:ListBucket on CUR S3 Bucket",
            ],
            required_scope="Billing / Management Account with CUR export target bucket",
            consequence_if_not_granted=(
                "Billed cost ingestion fails completely. Spend analytics, FOCUS 1.0 normalization, "
                "and financial reconciliation cannot operate."
            ),
            is_mandatory=True,
        ),
        LeastPrivilegeRequirement(
            capability_code=ProviderCapability.C04_USAGE,
            capability_name="Usage Metrics & Right-Sizing",
            minimum_permissions=[
                "cloudwatch:GetMetricData",
                "cloudwatch:ListMetrics",
            ],
            required_scope="Target AWS Account",
            consequence_if_not_granted=(
                "Utilization telemetry unavailable. Idle compute detection, right-sizing recommendations, "
                "and anomaly correlation with utilization curves are disabled."
            ),
            is_mandatory=False,
        ),
        LeastPrivilegeRequirement(
            capability_code=ProviderCapability.C11_PRICING,
            capability_name="Pricing Discovery",
            minimum_permissions=[
                "pricing:GetProducts",
                "pricing:DescribeServices",
            ],
            required_scope="Global endpoint ('us-east-1')",
            consequence_if_not_granted=(
                "Public rate card lookup disabled. CloudLens falls back to cached baseline prices; "
                "on-demand rate comparison and spot pricing analytics may become stale."
            ),
            is_mandatory=False,
        ),
        LeastPrivilegeRequirement(
            capability_code=ProviderCapability.C18_QUOTA,
            capability_name="Quota & Service Limits",
            minimum_permissions=[
                "servicequotas:GetServiceQuota",
                "servicequotas:ListServiceQuotas",
            ],
            required_scope="Target AWS Account",
            consequence_if_not_granted=(
                "Service quota tracking disabled. Platform cannot alert when resource provisioning approaches "
                "account limits or hard API throttles."
            ),
            is_mandatory=False,
        ),
    ],
)

AZURE_PERMISSIONS = ProviderPermissionReference(
    provider=ProviderType.AZURE,
    provider_name="Microsoft Azure",
    primary_auth_mechanism="Entra ID Service Principal + Asymmetric Certificate",
    supported_auth_mechanisms=[
        "Workload Identity Federation (OIDC via AKS / Container Runtime)",
        "System-Assigned / User-Assigned Managed Identity (Azure hosted)",
        "Audited Client Secret (Mandatory 90-day rotation exception)",
    ],
    forbidden_auth_mechanisms=[
        "Interactive User Account Passwords",
        "Subscription Owner or Contributor Full Roles",
    ],
    markdown_path="docs/permissions/azure.md",
    capabilities=[
        LeastPrivilegeRequirement(
            capability_code=ProviderCapability.C01_HIERARCHY,
            capability_name="Hierarchy Discovery",
            minimum_permissions=[
                "Microsoft.Management/managementGroups/read",
                "Microsoft.Management/managementGroups/descendants/read",
                "Microsoft.Resources/subscriptions/read",
            ],
            required_scope="Root Management Group or Target Management Group Subtree",
            consequence_if_not_granted=(
                "Azure Management Group and Subscription hierarchy discovery fails. Subscriptions must be connected "
                "as isolated islands; cross-subscription grouping and inheritance are lost."
            ),
            is_mandatory=True,
        ),
        LeastPrivilegeRequirement(
            capability_code=ProviderCapability.C02_INVENTORY,
            capability_name="Resource Inventory",
            minimum_permissions=[
                "Microsoft.Resources/subscriptions/resourceGroups/read",
                "Microsoft.Resources/resources/read",
            ],
            required_scope="Subscription or Target Resource Group",
            consequence_if_not_granted=(
                "Azure resource inventory disabled. Infrastructure assets, virtual machines, and storage accounts "
                "cannot be tracked or attributed to cost centers."
            ),
            is_mandatory=True,
        ),
        LeastPrivilegeRequirement(
            capability_code=ProviderCapability.C03_COST,
            capability_name="Cost & Billing Ingestion",
            minimum_permissions=[
                "Microsoft.CostManagement/exports/read",
                "Microsoft.Consumption/usageDetails/read",
                "Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read (on export blob)",
            ],
            required_scope="Enrollment / Billing Account / Subscription holding scheduled Cost Export",
            consequence_if_not_granted=(
                "Azure Cost Management data export cannot be read. Cost facts and amortized reservation "
                "reporting cannot be generated."
            ),
            is_mandatory=True,
        ),
        LeastPrivilegeRequirement(
            capability_code=ProviderCapability.C04_USAGE,
            capability_name="Usage Metrics",
            minimum_permissions=[
                "Microsoft.Insights/metrics/read",
                "Microsoft.Insights/metricDefinitions/read",
            ],
            required_scope="Subscription / Resource",
            consequence_if_not_granted=(
                "Azure Monitor metrics unavailable. Idle CPU detection, VM rightsizing, and memory "
                "underutilization insights cannot function."
            ),
            is_mandatory=False,
        ),
        LeastPrivilegeRequirement(
            capability_code=ProviderCapability.C11_PRICING,
            capability_name="Pricing Discovery",
            minimum_permissions=[
                "Public Retail Rates API (anonymous GET /api/v1/prices)",
            ],
            required_scope="Global",
            consequence_if_not_granted=(
                "Custom enterprise discount sheet evaluation disabled; standard retail list prices used."
            ),
            is_mandatory=False,
        ),
        LeastPrivilegeRequirement(
            capability_code=ProviderCapability.C18_QUOTA,
            capability_name="Quota & Service Limits",
            minimum_permissions=[
                "Microsoft.Quota/quotas/read",
                "Microsoft.Quota/quotaLimits/read",
            ],
            required_scope="Subscription",
            consequence_if_not_granted=(
                "Azure regional quota monitoring disabled. Quota headroom alerts cannot be raised."
            ),
            is_mandatory=False,
        ),
    ],
)

GCP_PERMISSIONS = ProviderPermissionReference(
    provider=ProviderType.GCP,
    provider_name="Google Cloud Platform (GCP)",
    primary_auth_mechanism="Workload Identity Federation (Keyless OIDC)",
    supported_auth_mechanisms=[
        "Service Account Attached to Compute / GKE Workload Identity",
        "Audited Service Account Key JSON (Mandatory 90-day rotation)",
    ],
    forbidden_auth_mechanisms=[
        "Interactive User Credentials (gcloud auth)",
        "roles/owner or roles/editor Project Privileges",
    ],
    markdown_path="docs/permissions/gcp.md",
    capabilities=[
        LeastPrivilegeRequirement(
            capability_code=ProviderCapability.C01_HIERARCHY,
            capability_name="Hierarchy Discovery",
            minimum_permissions=[
                "resourcemanager.organizations.get",
                "resourcemanager.folders.list",
                "resourcemanager.folders.get",
                "resourcemanager.projects.list",
                "resourcemanager.projects.get",
            ],
            required_scope="Organization or Target Folder Subtree ('roles/resourcemanager.organizationViewer')",
            consequence_if_not_granted=(
                "GCP Organization folder hierarchy discovery fails. Projects must be mapped manually without "
                "parent inheritance."
            ),
            is_mandatory=True,
        ),
        LeastPrivilegeRequirement(
            capability_code=ProviderCapability.C02_INVENTORY,
            capability_name="Resource Inventory",
            minimum_permissions=[
                "cloudasset.assets.searchAllResources",
                "cloudasset.assets.list",
            ],
            required_scope="Organization or Project ('roles/cloudasset.viewer')",
            consequence_if_not_granted=(
                "Cloud Asset Inventory disabled. Orphan disks, unattached external IPs, and Compute instances "
                "cannot be tracked."
            ),
            is_mandatory=True,
        ),
        LeastPrivilegeRequirement(
            capability_code=ProviderCapability.C03_COST,
            capability_name="Cost & Billing Ingestion",
            minimum_permissions=[
                "bigquery.jobs.create",
                "bigquery.tables.getData",
                "bigquery.tables.get",
            ],
            required_scope="Project holding Cloud Billing BigQuery Export Dataset ('roles/bigquery.dataViewer')",
            consequence_if_not_granted=(
                "BigQuery Cloud Billing export cannot be queried. All GCP cost attribution, CUD discount tracking, "
                "and SKU-level spend analysis fail."
            ),
            is_mandatory=True,
        ),
        LeastPrivilegeRequirement(
            capability_code=ProviderCapability.C04_USAGE,
            capability_name="Usage Metrics",
            minimum_permissions=[
                "monitoring.timeSeries.list",
                "monitoring.metricDescriptors.list",
            ],
            required_scope="Project Metrics Scope ('roles/monitoring.viewer')",
            consequence_if_not_granted=(
                "Cloud Monitoring metrics unavailable. Idle VM recommendations and GKE node pool utilization "
                "benchmarking are disabled."
            ),
            is_mandatory=False,
        ),
        LeastPrivilegeRequirement(
            capability_code=ProviderCapability.C11_PRICING,
            capability_name="Pricing Discovery",
            minimum_permissions=[
                "cloudbilling.services.list",
                "cloudbilling.skus.list",
            ],
            required_scope="Global Cloud Catalog API",
            consequence_if_not_granted=(
                "GCP SKU catalog synchronization disabled; real-time pricing dimension lookups unavailable."
            ),
            is_mandatory=False,
        ),
        LeastPrivilegeRequirement(
            capability_code=ProviderCapability.C18_QUOTA,
            capability_name="Quota & Service Limits",
            minimum_permissions=[
                "serviceusage.quotas.get",
                "serviceusage.services.get",
            ],
            required_scope="Project ('roles/servicemanagement.quotaViewer')",
            consequence_if_not_granted=(
                "GCP quota tracking disabled. Warnings for CPU, IP, or GPU exhaustion cannot be emitted."
            ),
            is_mandatory=False,
        ),
    ],
)

OCI_PERMISSIONS = ProviderPermissionReference(
    provider=ProviderType.OCI,
    provider_name="Oracle Cloud Infrastructure (OCI)",
    primary_auth_mechanism="Instance / Resource Principals (for OCI-hosted nodes)",
    supported_auth_mechanisms=[
        "IAM User + API Signing RSA Keypair (4096-bit PEM)",
        "Federated Identity via IDCS / IAM (SAML 2.0)",
    ],
    forbidden_auth_mechanisms=[
        "Console User Account Passwords",
        "Tenancy Administrator Group Membership",
    ],
    markdown_path="docs/permissions/oci.md",
    capabilities=[
        LeastPrivilegeRequirement(
            capability_code=ProviderCapability.C01_HIERARCHY,
            capability_name="Hierarchy Discovery",
            minimum_permissions=[
                "read compartments in tenancy",
            ],
            required_scope="Tenancy Root",
            consequence_if_not_granted=(
                "OCI Compartment tree traversal fails. Compartments and sub-compartments cannot be mapped "
                "or allocated."
            ),
            is_mandatory=True,
        ),
        LeastPrivilegeRequirement(
            capability_code=ProviderCapability.C02_INVENTORY,
            capability_name="Resource Inventory",
            minimum_permissions=[
                "read all-resources in tenancy",
            ],
            required_scope="Tenancy Root / Target Compartment",
            consequence_if_not_granted=(
                "OCI Search and Resource inventory disabled. OCI Compute shapes, block volumes, and Autonomous "
                "Databases cannot be catalogued."
            ),
            is_mandatory=True,
        ),
        LeastPrivilegeRequirement(
            capability_code=ProviderCapability.C03_COST,
            capability_name="Cost & Billing Ingestion",
            minimum_permissions=[
                "read usage-reports in tenancy",
                "read cost-reports in tenancy",
            ],
            required_scope="Tenancy Root Object Storage (Usage Report Bucket)",
            consequence_if_not_granted=(
                "OCI daily cost and usage reports cannot be downloaded. FOCUS cost facts cannot be computed."
            ),
            is_mandatory=True,
        ),
        LeastPrivilegeRequirement(
            capability_code=ProviderCapability.C04_USAGE,
            capability_name="Usage Metrics",
            minimum_permissions=[
                "read metrics in tenancy",
            ],
            required_scope="Tenancy Root",
            consequence_if_not_granted=(
                "OCI Monitoring service query disabled. Compute OCPU and RAM utilization metrics unavailable."
            ),
            is_mandatory=False,
        ),
        LeastPrivilegeRequirement(
            capability_code=ProviderCapability.C11_PRICING,
            capability_name="Pricing Discovery",
            minimum_permissions=[
                "Public rate card API endpoints (anonymous GET /metering/api/v1/commercial/ratecard)",
            ],
            required_scope="Global",
            consequence_if_not_granted=(
                "Universal Credits (UCC) rate evaluation disabled; standard public rates applied."
            ),
            is_mandatory=False,
        ),
        LeastPrivilegeRequirement(
            capability_code=ProviderCapability.C18_QUOTA,
            capability_name="Quota & Service Limits",
            minimum_permissions=[
                "read limits in tenancy",
            ],
            required_scope="Tenancy Root",
            consequence_if_not_granted=("OCI Service Limit and quota tracking disabled."),
            is_mandatory=False,
        ),
    ],
)


PROVIDER_PERMISSION_REGISTRY: dict[ProviderType, ProviderPermissionReference] = {
    ProviderType.AWS: AWS_PERMISSIONS,
    ProviderType.AZURE: AZURE_PERMISSIONS,
    ProviderType.GCP: GCP_PERMISSIONS,
    ProviderType.OCI: OCI_PERMISSIONS,
}


class PermissionReferenceService:
    """Provides authoritative least-privilege references across all four hyperscalers."""

    @classmethod
    def get_reference(cls, provider: ProviderType) -> ProviderPermissionReference:
        ref = PROVIDER_PERMISSION_REGISTRY.get(provider)
        if not ref:
            raise ValueError(f"No permission reference registered for provider '{provider.value}'.")
        return ref

    @classmethod
    def list_all_references(cls) -> list[ProviderPermissionReference]:
        return list(PROVIDER_PERMISSION_REGISTRY.values())

    @classmethod
    def render_markdown(cls, provider: ProviderType) -> str:
        """Generates the authoritative least-privilege markdown reference document."""
        ref = cls.get_reference(provider)
        lines = [
            f"# {ref.provider_name} Permission Reference",
            "",
            f"> **Provider**: {ref.provider_name}  ",
            "> **Security Baseline**: Read-only, Least Privilege (SEC-012)  ",
            f"> **Authoritative Specification**: `{ref.markdown_path}`",
            "",
            "---",
            "",
            "## 1. Authentication Mechanisms",
            "",
            "| Mechanism | Description | Security Tier |",
            "|:---|:---|:---:|",
            f"| **{ref.primary_auth_mechanism}** | Primary recommended authentication pattern | **Primary** |",
        ]

        for method in ref.supported_auth_mechanisms:
            lines.append(
                f"| **{method}** | Supported secondary authentication pattern | **Supported** |"
            )
        for method in ref.forbidden_auth_mechanisms:
            lines.append(
                f"| **{method}** | Strictly prohibited by governance policy | **Forbidden** |"
            )

        lines.extend(
            [
                "",
                "---",
                "",
                "## 2. Required Permissions by Capability Group",
                "",
                "| Capability Flag | Capability Group | Minimum Required Permissions | Required Scope | Consequence if Not Granted |",
                "|:---:|:---|:---|:---|:---|",
            ]
        )

        for req in ref.capabilities:
            perms = "<br>".join(f"`{p}`" for p in req.minimum_permissions)
            lines.append(
                f"| `{req.capability_code.value}` | **{req.capability_name}** | {perms} | {req.required_scope} | {req.consequence_if_not_granted} |"
            )

        lines.append("")
        return "\n".join(lines)

    @classmethod
    def sync_markdown_files_to_disk(cls, base_dir: Path | None = None) -> None:
        """Synchronizes authoritative markdown files in docs/permissions/ to ensure documentation integrity."""
        root = base_dir or Path(__file__).resolve().parent.parent.parent
        for provider in [ProviderType.AWS, ProviderType.AZURE, ProviderType.GCP, ProviderType.OCI]:
            ref = cls.get_reference(provider)
            target_path = root / ref.markdown_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            content = cls.render_markdown(provider)
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(content)
