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
from decimal import Decimal
from pathlib import Path
from typing import Any

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
            count_by_provider={p: 0 for p in PROVIDERS},
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
