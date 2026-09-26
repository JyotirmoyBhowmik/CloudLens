"""CloudLens Synthetic Multi-Provider Estate Generator.

Generates a realistic enterprise cloud estate of configurable size (default: 100,000 resources)
with:
- Realistic hierarchy depth across AWS, Azure, GCP, and OCI
- Deliberate tagging debt & gaps (default ~20% missing required tags)
- Pareto spend distribution: 5-8 dominant services account for ~80% of spend,
  with a long tail of small-cost resources
- Strict mathematical reconciliation manifest (Prompt 04 Item 30 / Acceptance)
"""

import hashlib
import json
import random
from collections.abc import Generator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic import Field as PydanticField

from domain.models.enums import (
    ChargeCategory,
    DependencyDirection,
    DependencyType,
    PricingStatus,
    ProviderType,
    RuntimeStatus,
    ScopeRole,
    SyncJobStatus,
)
from domain.models.facts import CostFact, RuntimeState, UsageFact
from domain.models.governance import Dependency, SyncJob
from domain.models.inventory import Resource, Tag
from domain.models.measures import FinancialMeasure, QuantityMeasure
from domain.models.scope import Scope
from domain.rules.monetary import round_currency, to_decimal

PROVIDERS = ("aws", "azure", "gcp", "oci")

REGIONS = {
    "aws": ("us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"),
    "azure": ("eastus", "westeurope", "southeastasia", "ukwest"),
    "gcp": ("us-central1", "europe-west1", "asia-east1", "australia-southeast1"),
    "oci": ("us-ashburn-1", "eu-frankfurt-1", "ap-tokyo-1", "uk-london-1"),
}

# Dominant core services (~80% cost weight)
DOMINANT_SERVICES = {
    "aws": [
        ("Compute", "AmazonEC2", "VirtualMachine", Decimal("150.00"), Decimal("850.00")),
        ("Database", "AmazonRDS", "RelationalDatabase", Decimal("200.00"), Decimal("1200.00")),
        ("Containers", "AmazonEKS", "KubernetesCluster", Decimal("300.00"), Decimal("1500.00")),
        ("Storage", "AmazonS3", "ObjectStorage", Decimal("80.00"), Decimal("600.00")),
    ],
    "azure": [
        ("Compute", "VirtualMachines", "VirtualMachine", Decimal("140.00"), Decimal("820.00")),
        ("Database", "SQLDatabase", "RelationalDatabase", Decimal("190.00"), Decimal("1150.00")),
        (
            "Containers",
            "AzureKubernetesService",
            "KubernetesCluster",
            Decimal("290.00"),
            Decimal("1450.00"),
        ),
        ("Storage", "BlobStorage", "ObjectStorage", Decimal("75.00"), Decimal("580.00")),
    ],
    "gcp": [
        ("Compute", "ComputeEngine", "VirtualMachine", Decimal("145.00"), Decimal("830.00")),
        ("Database", "CloudSQL", "RelationalDatabase", Decimal("195.00"), Decimal("1180.00")),
        (
            "Containers",
            "GoogleKubernetesEngine",
            "KubernetesCluster",
            Decimal("310.00"),
            Decimal("1480.00"),
        ),
        ("Storage", "CloudStorage", "ObjectStorage", Decimal("78.00"), Decimal("590.00")),
    ],
    "oci": [
        ("Compute", "ComputeService", "VirtualMachine", Decimal("130.00"), Decimal("780.00")),
        (
            "Database",
            "AutonomousDatabase",
            "RelationalDatabase",
            Decimal("220.00"),
            Decimal("1250.00"),
        ),
        (
            "Containers",
            "ContainerEngine",
            "KubernetesCluster",
            Decimal("270.00"),
            Decimal("1350.00"),
        ),
        ("Storage", "ObjectStorage", "ObjectStorage", Decimal("70.00"), Decimal("520.00")),
    ],
}

# Long-tail minor services (~20% cost weight, small pennies $0.05 - $25.00)
LONG_TAIL_SERVICES = {
    "aws": [
        ("Management", "CloudWatch", "MetricAlarm", Decimal("0.10"), Decimal("1.50")),
        ("Security", "KMS", "Key", Decimal("1.00"), Decimal("5.00")),
        ("Networking", "Route53", "HostedZone", Decimal("0.50"), Decimal("2.00")),
        ("Security", "SecretsManager", "Secret", Decimal("0.40"), Decimal("1.20")),
        ("Integration", "SNS", "Topic", Decimal("0.05"), Decimal("0.80")),
        ("Integration", "SQS", "Queue", Decimal("0.05"), Decimal("1.10")),
    ],
    "azure": [
        ("Management", "AzureMonitor", "MetricAlert", Decimal("0.10"), Decimal("1.50")),
        ("Security", "KeyVault", "Key", Decimal("1.00"), Decimal("5.00")),
        ("Networking", "DNS", "DnsZone", Decimal("0.50"), Decimal("2.00")),
        ("Integration", "ServiceBus", "Queue", Decimal("0.05"), Decimal("1.10")),
    ],
    "gcp": [
        ("Management", "CloudMonitoring", "AlertPolicy", Decimal("0.10"), Decimal("1.50")),
        ("Security", "CloudKMS", "CryptoKey", Decimal("1.00"), Decimal("5.00")),
        ("Networking", "CloudDNS", "ManagedZone", Decimal("0.50"), Decimal("2.00")),
        ("Integration", "PubSub", "Topic", Decimal("0.05"), Decimal("1.00")),
    ],
    "oci": [
        ("Management", "MonitoringService", "Alarm", Decimal("0.10"), Decimal("1.50")),
        ("Security", "VaultService", "Key", Decimal("1.00"), Decimal("5.00")),
        ("Networking", "DnsService", "Zone", Decimal("0.50"), Decimal("2.00")),
        ("Integration", "QueueService", "Queue", Decimal("0.05"), Decimal("1.00")),
    ],
}

ENVIRONMENTS = ("production", "staging", "development", "sandbox")
COST_CENTERS = ("CC-101-FINOPS", "CC-202-ENG", "CC-303-DATA", "CC-404-SEC", "CC-505-CORE")
OWNERS = ("platform-team", "billing-ops", "data-engineering", "infra-core", "app-services")


@dataclass
class EstateManifest:
    """Mathematical reconciliation manifest for generated estate."""

    resource_count: int = 0
    total_cost: Decimal = Decimal("0.00")
    dominant_spend: Decimal = Decimal("0.00")
    long_tail_spend: Decimal = Decimal("0.00")
    spend_by_provider: dict[str, Decimal] = field(default_factory=dict)
    count_by_provider: dict[str, int] = field(default_factory=dict)
    compliant_tags_count: int = 0
    tagging_gaps_count: int = 0
    tagging_compliance_percentage: Decimal = Decimal("0.00")
    reconciliation_hash: str = ""

    def compute_hash(self) -> str:
        payload = f"{self.resource_count}:{self.total_cost}:{self.compliant_tags_count}:{self.tagging_gaps_count}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class SyntheticEstateGenerator:
    """High-throughput generator for synthetic multi-cloud enterprise estates."""

    def __init__(
        self,
        total_resources: int = 100000,
        tagging_gap_ratio: float = 0.20,
        dominant_ratio: float = 0.25,  # 25% of resources generate dominant 80% spend
        seed: int = 42,
    ) -> None:
        self.total_resources = total_resources
        self.tagging_gap_ratio = tagging_gap_ratio
        self.dominant_ratio = dominant_ratio
        self.seed = seed
        self.rng = random.Random(seed)

    def _generate_hierarchy(self, provider: str, account_idx: int) -> dict[str, str]:
        """Generates realistic organizational hierarchy metadata."""
        if provider == "aws":
            return {
                "organization_id": "o-enterprise-root",
                "organizational_unit": f"ou-core-workloads-{account_idx % 4}",
                "account_id": f"11223344{account_idx:04d}",
            }
        elif provider == "azure":
            return {
                "tenant_id": "t-azure-enterprise",
                "management_group": f"mg-finops-tier-{account_idx % 4}",
                "subscription_id": f"sub-prod-{account_idx:04d}",
                "resource_group": f"rg-workload-{account_idx:03d}",
            }
        elif provider == "gcp":
            return {
                "organization_id": "org-gcp-enterprise",
                "folder_id": f"folder-business-unit-{account_idx % 4}",
                "project_id": f"prj-finops-{account_idx:04d}",
            }
        else:  # oci
            return {
                "tenancy_id": "ocid1.tenancy.oc1..enterprise",
                "compartment_id": f"ocid1.compartment.oc1..tier{account_idx % 4}",
                "subcompartment_id": f"ocid1.compartment.oc1..sub{account_idx:04d}",
            }

    def _generate_tags(self, resource_idx: int) -> dict[str, str]:
        """Generates tags with deliberate realistic gaps and inconsistencies."""
        # Check if this resource falls into the deliberate tagging debt gap
        if self.rng.random() < self.tagging_gap_ratio:
            # Tagging gap: missing mandatory tags or empty
            choice = resource_idx % 3
            if choice == 0:
                return {}  # Completely untagged
            elif choice == 1:
                return {
                    "Environment": self.rng.choice(ENVIRONMENTS)
                }  # Missing Owner and CostCenter
            else:
                return {
                    "owner": self.rng.choice(OWNERS)
                }  # Inconsistent lowercase key, missing CostCenter

        # Compliant tags
        return {
            "Environment": self.rng.choice(ENVIRONMENTS),
            "CostCenter": self.rng.choice(COST_CENTERS),
            "Owner": self.rng.choice(OWNERS),
            "Project": f"project-cloudlens-{(resource_idx % 20) + 1}",
        }

    def stream_resources(self) -> Generator[tuple[dict[str, Any], bool, Decimal, str], None, None]:
        """Yields synthetic resources one by one: (resource_dict, is_dominant, cost, provider)."""
        provider_count = len(PROVIDERS)
        dominant_quota = int(self.total_resources * self.dominant_ratio)

        for idx in range(self.total_resources):
            provider = PROVIDERS[idx % provider_count]
            is_dominant = idx < dominant_quota
            region = self.rng.choice(REGIONS[provider])
            account_idx = (idx // provider_count) % 25

            hierarchy = self._generate_hierarchy(provider, account_idx)
            tags = self._generate_tags(idx)

            if is_dominant:
                svc_category, svc_name, r_type, min_c, max_c = self.rng.choice(
                    DOMINANT_SERVICES[provider]
                )
            else:
                svc_category, svc_name, r_type, min_c, max_c = self.rng.choice(
                    LONG_TAIL_SERVICES[provider]
                )

            # Random exact cost between bounds
            raw_float = self.rng.uniform(float(min_c), float(max_c))
            cost = round_currency(to_decimal(raw_float), decimal_places=2)

            resource_id = f"{provider}-{r_type.lower()}-{idx:06d}"
            record = {
                "resource_id": resource_id,
                "provider": provider,
                "service_category": svc_category,
                "service_name": svc_name,
                "resource_type": r_type,
                "region": region,
                "hierarchy": hierarchy,
                "tags": tags,
                "monthly_cost": str(cost),
            }

            yield record, is_dominant, cost, provider

    def generate_and_reconcile(self, output_file: Path | None = None) -> EstateManifest:
        """Generates all resources, streams to optional file, and builds reconciliation manifest."""
        manifest = EstateManifest(
            resource_count=0,
            total_cost=Decimal("0.00"),
            dominant_spend=Decimal("0.00"),
            long_tail_spend=Decimal("0.00"),
            spend_by_provider={p: Decimal("0.00") for p in PROVIDERS},
            count_by_provider=dict.fromkeys(PROVIDERS, 0),
        )

        f_out = None
        if output_file is not None:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            f_out = output_file.open("w", encoding="utf-8")

        try:
            for record, is_dominant, cost, provider in self.stream_resources():
                manifest.resource_count += 1
                manifest.total_cost += cost
                manifest.spend_by_provider[provider] += cost
                manifest.count_by_provider[provider] += 1

                if is_dominant:
                    manifest.dominant_spend += cost
                else:
                    manifest.long_tail_spend += cost

                # Check tagging compliance (requires Environment, CostCenter, Owner)
                tags = record["tags"]
                if "Environment" in tags and "CostCenter" in tags and "Owner" in tags:
                    manifest.compliant_tags_count += 1
                else:
                    manifest.tagging_gaps_count += 1

                if f_out is not None:
                    f_out.write(json.dumps(record) + "\n")

        finally:
            if f_out is not None:
                f_out.close()

        if manifest.resource_count > 0:
            pct = (
                Decimal(manifest.compliant_tags_count) / Decimal(manifest.resource_count)
            ) * Decimal("100.0")
            manifest.tagging_compliance_percentage = pct.quantize(Decimal("0.01"))

        manifest.reconciliation_hash = manifest.compute_hash()
        return manifest

    def generate_hierarchies(self, tenant_id: str = "T-DEMO") -> list[Scope]:
        """Generates realistic organizational hierarchies at varying depth across all 4 providers.

        Enforces Prompt 05 & Prompt 09 Item 61:
        - AWS: Org Root -> OU -> Accounts (SUB_GROUP legitimately absent)
        - Azure: Tenant -> Management Group -> Subscription -> Resource Groups (5 levels deep)
        - GCP: Org -> Folder -> Projects (SUB_GROUP legitimately absent)
        - OCI: Tenancy -> Compartment -> Subcompartments (SUB_GROUP present)
        """
        scopes: list[Scope] = []

        # 1. AWS Hierarchy (depth 0 to 2)
        aws_root = Scope(
            id=f"{tenant_id}-aws-root",
            tenant_id=tenant_id,
            name="AWS Organization Root",
            canonical_role=ScopeRole.ROOT_GROUP,
            provider=ProviderType.AWS,
            native_type="OrganizationRoot",
            native_id="r-aws-enterprise",
            parent_id=None,
            depth=0,
            materialized_path=f"/{tenant_id}-aws-root",
        )
        aws_ou_prod = Scope(
            id=f"{tenant_id}-aws-ou-prod",
            tenant_id=tenant_id,
            name="Core Workloads OU",
            canonical_role=ScopeRole.GROUP,
            provider=ProviderType.AWS,
            native_type="OrganizationalUnit",
            native_id="ou-core-workloads",
            parent_id=aws_root.id,
            depth=1,
            materialized_path=f"{aws_root.materialized_path}/{tenant_id}-aws-ou-prod",
        )
        aws_acc_bank = Scope(
            id=f"{tenant_id}-aws-acc-banking",
            tenant_id=tenant_id,
            name="Production Banking Account",
            canonical_role=ScopeRole.BILLING_ACCOUNT,
            provider=ProviderType.AWS,
            native_type="Account",
            native_id="112233445566",
            parent_id=aws_ou_prod.id,
            depth=2,
            materialized_path=f"{aws_ou_prod.materialized_path}/{tenant_id}-aws-acc-banking",
        )
        aws_acc_data = Scope(
            id=f"{tenant_id}-aws-acc-analytics",
            tenant_id=tenant_id,
            name="BigData Analytics Account",
            canonical_role=ScopeRole.BILLING_ACCOUNT,
            provider=ProviderType.AWS,
            native_type="Account",
            native_id="223344556677",
            parent_id=aws_ou_prod.id,
            depth=2,
            materialized_path=f"{aws_ou_prod.materialized_path}/{tenant_id}-aws-acc-analytics",
        )
        aws_ou_dev = Scope(
            id=f"{tenant_id}-aws-ou-dev",
            tenant_id=tenant_id,
            name="Engineering Sandbox OU",
            canonical_role=ScopeRole.GROUP,
            provider=ProviderType.AWS,
            native_type="OrganizationalUnit",
            native_id="ou-eng-sandbox",
            parent_id=aws_root.id,
            depth=1,
            materialized_path=f"{aws_root.materialized_path}/{tenant_id}-aws-ou-dev",
        )
        aws_acc_dev = Scope(
            id=f"{tenant_id}-aws-acc-dev",
            tenant_id=tenant_id,
            name="Development Sandbox Account",
            canonical_role=ScopeRole.BILLING_ACCOUNT,
            provider=ProviderType.AWS,
            native_type="Account",
            native_id="334455667788",
            parent_id=aws_ou_dev.id,
            depth=2,
            materialized_path=f"{aws_ou_dev.materialized_path}/{tenant_id}-aws-acc-dev",
        )
        scopes.extend([aws_root, aws_ou_prod, aws_acc_bank, aws_acc_data, aws_ou_dev, aws_acc_dev])

        # 2. Azure Hierarchy (depth 0 to 3)
        az_root = Scope(
            id=f"{tenant_id}-az-root",
            tenant_id=tenant_id,
            name="Azure Tenant Root",
            canonical_role=ScopeRole.ROOT_GROUP,
            provider=ProviderType.AZURE,
            native_type="TenantRootGroup",
            native_id="t-azure-root",
            parent_id=None,
            depth=0,
            materialized_path=f"/{tenant_id}-az-root",
        )
        az_mg = Scope(
            id=f"{tenant_id}-az-mg",
            tenant_id=tenant_id,
            name="Production MG",
            canonical_role=ScopeRole.GROUP,
            provider=ProviderType.AZURE,
            native_type="ManagementGroup",
            native_id="mg-finops-tier-1",
            parent_id=az_root.id,
            depth=1,
            materialized_path=f"{az_root.materialized_path}/{tenant_id}-az-mg",
        )
        az_sub = Scope(
            id=f"{tenant_id}-az-sub",
            tenant_id=tenant_id,
            name="Enterprise Core Subscription",
            canonical_role=ScopeRole.BILLING_BOUNDARY,
            provider=ProviderType.AZURE,
            native_type="Subscription",
            native_id="sub-prod-0001",
            parent_id=az_mg.id,
            depth=2,
            materialized_path=f"{az_mg.materialized_path}/{tenant_id}-az-sub",
        )
        az_rg_pay = Scope(
            id=f"{tenant_id}-az-rg-pay",
            tenant_id=tenant_id,
            name="Payments RG",
            canonical_role=ScopeRole.SUB_GROUP,
            provider=ProviderType.AZURE,
            native_type="ResourceGroup",
            native_id="rg-payments-prod",
            parent_id=az_sub.id,
            depth=3,
            materialized_path=f"{az_sub.materialized_path}/{tenant_id}-az-rg-pay",
        )
        az_rg_sec = Scope(
            id=f"{tenant_id}-az-rg-sec",
            tenant_id=tenant_id,
            name="Security RG",
            canonical_role=ScopeRole.SUB_GROUP,
            provider=ProviderType.AZURE,
            native_type="ResourceGroup",
            native_id="rg-security-prod",
            parent_id=az_sub.id,
            depth=3,
            materialized_path=f"{az_sub.materialized_path}/{tenant_id}-az-rg-sec",
        )
        scopes.extend([az_root, az_mg, az_sub, az_rg_pay, az_rg_sec])

        # 3. GCP Hierarchy (depth 0 to 2)
        gcp_org = Scope(
            id=f"{tenant_id}-gcp-org",
            tenant_id=tenant_id,
            name="Google Cloud Organization",
            canonical_role=ScopeRole.ROOT_GROUP,
            provider=ProviderType.GCP,
            native_type="Organization",
            native_id="organizations/123456789",
            parent_id=None,
            depth=0,
            materialized_path=f"/{tenant_id}-gcp-org",
        )
        gcp_fld_fin = Scope(
            id=f"{tenant_id}-gcp-fld-fin",
            tenant_id=tenant_id,
            name="Financial Services Folder",
            canonical_role=ScopeRole.GROUP,
            provider=ProviderType.GCP,
            native_type="Folder",
            native_id="folders/234567890",
            parent_id=gcp_org.id,
            depth=1,
            materialized_path=f"{gcp_org.materialized_path}/{tenant_id}-gcp-fld-fin",
        )
        gcp_prj_bank = Scope(
            id=f"{tenant_id}-gcp-prj-retail",
            tenant_id=tenant_id,
            name="Retail Banking Project",
            canonical_role=ScopeRole.BILLING_ACCOUNT,
            provider=ProviderType.GCP,
            native_type="Project",
            native_id="prj-retail-banking-01",
            parent_id=gcp_fld_fin.id,
            depth=2,
            materialized_path=f"{gcp_fld_fin.materialized_path}/{tenant_id}-gcp-prj-retail",
        )
        gcp_prj_ai = Scope(
            id=f"{tenant_id}-gcp-prj-ai",
            tenant_id=tenant_id,
            name="AI Recommendations Project",
            canonical_role=ScopeRole.BILLING_ACCOUNT,
            provider=ProviderType.GCP,
            native_type="Project",
            native_id="prj-ai-recs-02",
            parent_id=gcp_fld_fin.id,
            depth=2,
            materialized_path=f"{gcp_fld_fin.materialized_path}/{tenant_id}-gcp-prj-ai",
        )
        scopes.extend([gcp_org, gcp_fld_fin, gcp_prj_bank, gcp_prj_ai])

        # 4. OCI Hierarchy (depth 0 to 2)
        oci_tenancy = Scope(
            id=f"{tenant_id}-oci-tenancy",
            tenant_id=tenant_id,
            name="Enterprise Tenancy",
            canonical_role=ScopeRole.ROOT_GROUP,
            provider=ProviderType.OCI,
            native_type="Tenancy",
            native_id="ocid1.tenancy.oc1..demo",
            parent_id=None,
            depth=0,
            materialized_path=f"/{tenant_id}-oci-tenancy",
        )
        oci_cmp_prod = Scope(
            id=f"{tenant_id}-oci-cmp-prod",
            tenant_id=tenant_id,
            name="Production Compartment",
            canonical_role=ScopeRole.GROUP,
            provider=ProviderType.OCI,
            native_type="Compartment",
            native_id="ocid1.compartment.oc1..prod",
            parent_id=oci_tenancy.id,
            depth=1,
            materialized_path=f"{oci_tenancy.materialized_path}/{tenant_id}-oci-cmp-prod",
        )
        oci_subcmp_db = Scope(
            id=f"{tenant_id}-oci-cmp-db",
            tenant_id=tenant_id,
            name="Autonomous DB Subcompartment",
            canonical_role=ScopeRole.SUB_GROUP,
            provider=ProviderType.OCI,
            native_type="Subcompartment",
            native_id="ocid1.compartment.oc1..db",
            parent_id=oci_cmp_prod.id,
            depth=2,
            materialized_path=f"{oci_cmp_prod.materialized_path}/{tenant_id}-oci-cmp-db",
        )
        scopes.extend([oci_tenancy, oci_cmp_prod, oci_subcmp_db])

        return scopes

    def generate_complete_estate(
        self,
        tenant_id: str = "T-DEMO",
        sample_size: int = 120,
    ) -> "CompleteEstateResult":
        """Generates an interconnected synthetic estate with all 4 providers and injected anomalies.

        Enforces Prompt 09 Item 61:
        - Hierarchies at varying depth
        - Resources with realistic type distribution
        - Deliberate tagging gaps
        - Cost facts with realistic long-tail distribution
        - Usage facts appropriate to monitoring types
        - Runtime patterns including out-of-schedule running
        - Dependency edges
        - Deliberate anomalies: cost spike, restatement, stale connector, unowned cluster
        """
        scopes = self.generate_hierarchies(tenant_id)
        scopes_by_provider = {
            ProviderType.AWS: [
                s
                for s in scopes
                if s.provider == ProviderType.AWS and s.canonical_role == ScopeRole.BILLING_ACCOUNT
            ],
            ProviderType.AZURE: [
                s
                for s in scopes
                if s.provider == ProviderType.AZURE and s.canonical_role == ScopeRole.SUB_GROUP
            ],
            ProviderType.GCP: [
                s
                for s in scopes
                if s.provider == ProviderType.GCP and s.canonical_role == ScopeRole.BILLING_ACCOUNT
            ],
            ProviderType.OCI: [
                s
                for s in scopes
                if s.provider == ProviderType.OCI
                and s.canonical_role in (ScopeRole.GROUP, ScopeRole.SUB_GROUP)
            ],
        }

        resources: list[Resource] = []
        cost_facts: list[CostFact] = []
        usage_facts: list[UsageFact] = []
        runtime_states: list[RuntimeState] = []
        dependencies: list[Dependency] = []
        sync_jobs: list[SyncJob] = []
        anomalies: list[SyntheticAnomaly] = []

        now = datetime.now(UTC)
        period_start = now - timedelta(days=30)
        period_end = now

        provider_list = [ProviderType.AWS, ProviderType.AZURE, ProviderType.GCP, ProviderType.OCI]

        for i in range(sample_size):
            p = provider_list[i % 4]
            p_str = p.value
            target_scope = self.rng.choice(scopes_by_provider[p])
            region = self.rng.choice(REGIONS[p_str])
            is_dom = i % 4 == 0

            if is_dom:
                category, svc_name, r_type, min_c, max_c = self.rng.choice(DOMINANT_SERVICES[p_str])
            else:
                category, svc_name, r_type, min_c, max_c = self.rng.choice(
                    LONG_TAIL_SERVICES[p_str]
                )

            # Deliberate tagging gaps
            has_tag_gap = self.rng.random() < self.tagging_gap_ratio
            tags: list[Tag] = []
            owner_val: str | None = None
            cc_val: str | None = None
            env_val = self.rng.choice(ENVIRONMENTS)

            if not has_tag_gap:
                owner_val = self.rng.choice(OWNERS)
                cc_val = self.rng.choice(COST_CENTERS)
                tags = [
                    Tag(key="Environment", value=env_val),
                    Tag(key="CostCenter", value=cc_val),
                    Tag(key="Owner", value=owner_val),
                    Tag(key="Application", value=f"App-{svc_name[:6]}"),
                ]
            else:
                # Gap: missing Owner or CostCenter
                tags = [Tag(key="Environment", value=env_val)]

            res_id = f"res-{p_str}-{r_type.lower()}-{i:04d}"
            res = Resource(
                id=res_id,
                tenant_id=tenant_id,
                scope_id=target_scope.id,
                native_id=f"native-{p_str}-{res_id}",
                name=f"{svc_name.lower()}-{i:03d}",
                provider=p,
                service_id=f"svc-{svc_name.lower()}",
                resource_type_id=f"rt-{r_type.lower()}",
                region_id=region,
                pricing_status=PricingStatus.PAID,
                tags=tags,
                owner_id=owner_val,
                cost_center_id=cc_val,
                environment_id=f"env-{env_val}",
            )
            resources.append(res)

            # Cost Fact
            cost_amt = round_currency(to_decimal(self.rng.uniform(float(min_c), float(max_c))))
            cf = CostFact(
                id=f"cf-{p_str}-{i:04d}",
                tenant_id=tenant_id,
                scope_id=target_scope.id,
                resource_id=res.id,
                charge_period_start=period_start,
                charge_period_end=period_end,
                charge_category=ChargeCategory.USAGE,
                billed_cost=FinancialMeasure(cost_amt),
                effective_cost=FinancialMeasure(cost_amt),
                billing_currency="USD",
            )
            cost_facts.append(cf)

            # Usage Fact appropriate to monitoring type
            if r_type in ("VirtualMachine", "KubernetesCluster"):
                usage_facts.append(
                    UsageFact(
                        id=f"uf-cpu-{i:04d}",
                        tenant_id=tenant_id,
                        scope_id=target_scope.id,
                        resource_id=res.id,
                        period_start=period_start,
                        period_end=period_end,
                        metric_name="cpu_utilization_percentage",
                        usage_quantity=QuantityMeasure(Decimal(str(self.rng.randint(15, 85)))),
                        usage_unit="percentage",
                    )
                )
            elif r_type in ("ObjectStorage", "RelationalDatabase"):
                usage_facts.append(
                    UsageFact(
                        id=f"uf-storage-{i:04d}",
                        tenant_id=tenant_id,
                        scope_id=target_scope.id,
                        resource_id=res.id,
                        period_start=period_start,
                        period_end=period_end,
                        metric_name="storage_allocated_bytes",
                        usage_quantity=QuantityMeasure(
                            Decimal(str(self.rng.randint(100000000, 50000000000)))
                        ),
                        usage_unit="bytes",
                    )
                )

            # Runtime state & out-of-schedule running pattern
            is_out_of_schedule = env_val in ("development", "staging") and (i % 7 == 0)
            cpu_avg = (
                Decimal("1.5") if is_out_of_schedule else Decimal(str(self.rng.randint(20, 75)))
            )
            rs = RuntimeState(
                id=f"rs-{i:04d}",
                resource_id=res.id,
                status=RuntimeStatus.RUNNING,
                cpu_utilization_avg=QuantityMeasure(cpu_avg),
                memory_utilization_avg=QuantityMeasure(Decimal("45.0")),
                observed_at=now,
                is_idle=is_out_of_schedule,
            )
            runtime_states.append(rs)

        # Build cross-resource dependencies
        for idx in range(len(resources) - 1):
            if idx % 5 == 0:
                dependencies.append(
                    Dependency(
                        id=f"dep-{idx:03d}",
                        source_resource_id=resources[idx].id,
                        target_resource_id=resources[idx + 1].id,
                        dependency_type=DependencyType.DATABASE_CLIENT,
                        direction=DependencyDirection.OUTBOUND,
                    )
                )

        # ------------------------------------------------------------------
        # INJECT DELIBERATE ANOMALY 1: Cost Spike
        # ------------------------------------------------------------------
        spike_res = resources[0]
        spike_cost = Decimal("850.00")
        spike_cf = CostFact(
            id=f"cf-anomaly-spike-{spike_res.id}",
            tenant_id=tenant_id,
            scope_id=spike_res.scope_id,
            resource_id=spike_res.id,
            charge_period_start=now - timedelta(days=2),
            charge_period_end=now - timedelta(days=1),
            charge_category=ChargeCategory.USAGE,
            billed_cost=FinancialMeasure(spike_cost),
            effective_cost=FinancialMeasure(spike_cost),
            billing_currency="USD",
        )
        cost_facts.append(spike_cf)
        anomalies.append(
            SyntheticAnomaly(
                anomaly_type=SyntheticAnomalyType.COST_SPIKE,
                target_id=spike_res.id,
                description=f"Sudden 15x cost spike on resource '{spike_res.name}' (${spike_cost}/day vs $25 baseline).",
                detected_value=str(spike_cost),
                expected_baseline="25.00",
                timestamp=now - timedelta(days=1),
            )
        )

        # ------------------------------------------------------------------
        # INJECT DELIBERATE ANOMALY 2: Restatement / Retroactive Adjustment
        # ------------------------------------------------------------------
        restatement_cost = Decimal("-450.00")
        restatement_cf = CostFact(
            id="cf-anomaly-restatement-001",
            tenant_id=tenant_id,
            scope_id=scopes[0].id,
            resource_id=None,
            charge_period_start=now - timedelta(days=60),
            charge_period_end=now - timedelta(days=30),
            charge_category=ChargeCategory.ADJUSTMENT,
            billed_cost=FinancialMeasure(restatement_cost),
            effective_cost=FinancialMeasure(restatement_cost),
            billing_currency="USD",
        )
        cost_facts.append(restatement_cf)
        anomalies.append(
            SyntheticAnomaly(
                anomaly_type=SyntheticAnomalyType.RESTATEMENT,
                target_id=restatement_cf.id,
                description="Prior billing period retroactive adjustment credit of -$450.00 applied by provider.",
                detected_value=str(restatement_cost),
                expected_baseline="0.00",
                timestamp=now - timedelta(days=5),
            )
        )

        # ------------------------------------------------------------------
        # INJECT DELIBERATE ANOMALY 3: Stale Connector
        # ------------------------------------------------------------------
        sync_aws = SyncJob(
            id="sync-aws-ok",
            connector_type=ProviderType.AWS,
            scope_id=scopes[0].id,
            status=SyncJobStatus.COMPLETED,
            started_at=now - timedelta(hours=2),
            completed_at=now - timedelta(hours=1, minutes=45),
            rows_ingested=1250,
        )
        sync_az = SyncJob(
            id="sync-azure-ok",
            connector_type=ProviderType.AZURE,
            scope_id=scopes[6].id,
            status=SyncJobStatus.COMPLETED,
            started_at=now - timedelta(hours=3),
            completed_at=now - timedelta(hours=2, minutes=40),
            rows_ingested=980,
        )
        sync_gcp_stale = SyncJob(
            id="sync-gcp-stale",
            connector_type=ProviderType.GCP,
            scope_id=scopes[11].id,
            status=SyncJobStatus.FAILED,
            started_at=now - timedelta(days=4),
            completed_at=now - timedelta(days=4) + timedelta(minutes=30),
            rows_ingested=0,
            error_message="Connection timed out after 30000ms. Ingestion stalled; connector freshness exceeded SLA.",
        )
        sync_jobs.extend([sync_aws, sync_az, sync_gcp_stale])
        anomalies.append(
            SyntheticAnomaly(
                anomaly_type=SyntheticAnomalyType.STALE_CONNECTOR,
                target_id=sync_gcp_stale.id,
                description="GCP connector ingestion job failed 96 hours ago; connector freshness exceeds SLA.",
                detected_value="FAILED (stale 96h)",
                expected_baseline="COMPLETED (<6h)",
                timestamp=now - timedelta(days=4),
            )
        )

        # ------------------------------------------------------------------
        # INJECT DELIBERATE ANOMALY 4: Unowned Resource Cluster
        # ------------------------------------------------------------------
        unowned_scope = Scope(
            id=f"{tenant_id}-scope-orphan-lab",
            tenant_id=tenant_id,
            name="Legacy Orphan Testing Lab",
            canonical_role=ScopeRole.GROUP,
            provider=ProviderType.AWS,
            native_type="OrganizationalUnit",
            native_id="ou-orphan-lab",
            parent_id=scopes[0].id,
            depth=1,
            materialized_path=f"{scopes[0].materialized_path}/{tenant_id}-scope-orphan-lab",
        )
        scopes.append(unowned_scope)

        unowned_ids: list[str] = []
        for u in range(8):
            u_id = f"res-unowned-cluster-{u + 1:02d}"
            unowned_ids.append(u_id)
            unowned_res = Resource(
                id=u_id,
                tenant_id=tenant_id,
                scope_id=unowned_scope.id,
                native_id=f"native-unowned-{u_id}",
                name=f"orphan-worker-{u + 1:02d}",
                provider=ProviderType.AWS,
                service_id="svc-virtualmachines",
                resource_type_id="rt-instance",
                region_id="us-east-1",
                pricing_status=PricingStatus.PAID,
                tags=[],  # Zero tags
                owner_id=None,  # Zero owner
                cost_center_id=None,
            )
            resources.append(unowned_res)
            cost_facts.append(
                CostFact(
                    id=f"cf-unowned-{u + 1:02d}",
                    tenant_id=tenant_id,
                    scope_id=unowned_scope.id,
                    resource_id=unowned_res.id,
                    charge_period_start=period_start,
                    charge_period_end=period_end,
                    charge_category=ChargeCategory.USAGE,
                    billed_cost=FinancialMeasure(Decimal("120.00")),
                    effective_cost=FinancialMeasure(Decimal("120.00")),
                    billing_currency="USD",
                )
            )

        anomalies.append(
            SyntheticAnomaly(
                anomaly_type=SyntheticAnomalyType.UNOWNED_CLUSTER,
                target_id=unowned_scope.id,
                description=f"Cluster of 8 interrelated unowned resources in '{unowned_scope.name}' with zero owner tags and unmapped scope.",
                detected_value={"count": 8, "resource_ids": unowned_ids},
                expected_baseline="100% accountable ownership",
                timestamp=now,
            )
        )

        return CompleteEstateResult(
            scopes=scopes,
            resources=resources,
            cost_facts=cost_facts,
            usage_facts=usage_facts,
            runtime_states=runtime_states,
            dependencies=dependencies,
            sync_jobs=sync_jobs,
            anomalies=anomalies,
        )


class SyntheticAnomalyType(StrEnum):
    """Classifies the deliberate anomaly types required by Prompt 09 Item 61."""

    COST_SPIKE = "COST_SPIKE"
    RESTATEMENT = "RESTATEMENT"
    STALE_CONNECTOR = "STALE_CONNECTOR"
    UNOWNED_CLUSTER = "UNOWNED_CLUSTER"


class SyntheticAnomaly(BaseModel):
    """Deliberately injected realistic anomaly record for analytics and governance verification."""

    anomaly_type: SyntheticAnomalyType = PydanticField(..., description="Classification of anomaly")
    target_id: str = PydanticField(..., description="Target resource, cost fact, or connector ID")
    description: str = PydanticField(..., description="Detailed description of the anomaly")
    detected_value: Any = PydanticField(..., description="Observed anomalous metric or state")
    expected_baseline: Any = PydanticField(..., description="Normal or baseline expectation")
    timestamp: datetime = PydanticField(default_factory=lambda: datetime.now(UTC))


class CompleteEstateResult(BaseModel):
    """Complete, interconnected synthetic multi-cloud enterprise estate dataset."""

    scopes: list[Scope] = PydanticField(default_factory=list)
    resources: list[Resource] = PydanticField(default_factory=list)
    cost_facts: list[CostFact] = PydanticField(default_factory=list)
    usage_facts: list[UsageFact] = PydanticField(default_factory=list)
    runtime_states: list[RuntimeState] = PydanticField(default_factory=list)
    dependencies: list[Dependency] = PydanticField(default_factory=list)
    sync_jobs: list[SyncJob] = PydanticField(default_factory=list)
    anomalies: list[SyntheticAnomaly] = PydanticField(default_factory=list)
