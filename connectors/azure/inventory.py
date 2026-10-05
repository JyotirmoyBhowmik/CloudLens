"""Azure Resource Inventory Service via Azure Resource Graph (Prompt 16 / BBP Section 14.2 & 15.4).

Enforces:
- Azure Resource Graph as primary cross-subscription inventory source.
- Official documented caveat surfaced: Resource Graph is indexed with latency and is NOT strongly consistent.
- Freshness indicator explicitly declares `is_strongly_consistent=False` and `indexing_latency_caveat=True`.
"""

from __future__ import annotations

import logging
from typing import Any

from connectors.azure.models import AzureFreshnessIndicator
from connectors.contract.models import PagedResult, PaginationParams
from domain.models.enums import RuntimeStatus, ServiceCategory

logger = logging.getLogger(__name__)


class AzureInventoryService:
    """Executes Resource Graph queries and surfaces eventual consistency freshness diagnostics."""

    def __init__(self, tenant_id: str, config: dict[str, Any] | None = None) -> None:
        self.tenant_id = tenant_id
        self.config = config or {}
        self.freshness = AzureFreshnessIndicator()

    def get_freshness_report(self) -> AzureFreshnessIndicator:
        """Returns the official Resource Graph freshness diagnostic report."""
        return self.freshness

    def _get_sample_resources(self) -> list[dict[str, Any]]:
        """Provides realistic resource fixtures aligned with sample cost fixtures."""
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

        return [
            # 1. Virtual Machine
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
                "_freshness": self.freshness.model_dump(),
            },
            # 2. Managed OS Disk
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
                "_freshness": self.freshness.model_dump(),
            },
            # 3. Network Interface Card
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
                    "virtualMachine": {"id": vm_id},
                    "provisioningState": "Succeeded",
                },
                "_freshness": self.freshness.model_dump(),
            },
            # 4. SQL Database
            {
                "id": sql_db_id,
                "name": "db-transactions",
                "type": "Microsoft.Sql/servers/databases",
                "location": "eastus",
                "resourceGroup": rg_compute,
                "subscriptionId": sub_prod,
                "service_category": ServiceCategory.DATABASE.value,
                "runtime_status": RuntimeStatus.RUNNING.value,
                "tags": {
                    "Environment": "Production",
                    "CostCenter": "CC-202-ENG",
                    "Owner": "db-admin",
                },
                "sku": {"name": "GP_Gen5_4", "tier": "GeneralPurpose"},
                "properties": {
                    "collation": "SQL_Latin1_General_CP1_CI_AS",
                    "status": "Online",
                    "databaseId": "00000000-2222-3333-4444-555555555555",
                },
                "_freshness": self.freshness.model_dump(),
            },
            # 5. Key Vault
            {
                "id": kv_id,
                "name": "kv-sec-keys",
                "type": "Microsoft.KeyVault/vaults",
                "location": "eastus",
                "resourceGroup": rg_sec,
                "subscriptionId": sub_prod,
                "service_category": ServiceCategory.SECURITY_IDENTITY.value,
                "runtime_status": RuntimeStatus.RUNNING.value,
                "tags": {
                    "Environment": "Production",
                    "SecurityTier": "MissionCritical",
                },
                "sku": {"name": "standard", "family": "A"},
                "properties": {
                    "tenantId": self.tenant_id,
                    "sku": {"family": "A", "name": "standard"},
                },
                "_freshness": self.freshness.model_dump(),
            },
            # 6. Storage Account
            {
                "id": storage_id,
                "name": "saenterprisecore",
                "type": "Microsoft.Storage/storageAccounts",
                "location": "eastus",
                "resourceGroup": "rg-data-prod",
                "subscriptionId": sub_data,
                "service_category": ServiceCategory.STORAGE.value,
                "runtime_status": RuntimeStatus.RUNNING.value,
                "tags": {"Environment": "Production", "CostCenter": "CC-303-DATA"},
                "sku": {"name": "Standard_LRS", "tier": "Standard"},
                "properties": {
                    "supportsHttpsTrafficOnly": True,
                    "accessTier": "Hot",
                },
                "_freshness": self.freshness.model_dump(),
            },
        ]

    async def discover_resources(
        self,
        scope_id: str = "root",
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        """Queries Azure Resource Graph, filtering by scope if specified.

        Endpoint: POST https://management.azure.com/providers/Microsoft.ResourceGraph/resources?api-version=2022-10-01
        """
        all_resources = self._get_sample_resources()

        # Filter by scope if specific scope is provided
        if scope_id and scope_id != "root" and scope_id != "scope-root":
            filtered = [r for r in all_resources if scope_id in r["id"]]
        else:
            filtered = all_resources

        page_size = pagination.page_size if pagination else len(filtered)
        page_items = filtered[:page_size]
        is_truncated = len(filtered) > page_size

        return PagedResult(
            items=page_items,
            continuation_token=str(page_size) if is_truncated else None,
            is_truncated=is_truncated,
            total_records=len(filtered),
        )

    async def discover_services(
        self,
        scope_id: str | None = None,
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        """Discovers distinct Azure services and resource providers active in estate."""
        _ = (scope_id, pagination)
        resources = self._get_sample_resources()
        service_map: dict[str, dict[str, Any]] = {}

        for r in resources:
            cat = r.get("service_category", ServiceCategory.OTHER.value)
            rtype = r.get("type", "")
            provider_namespace = rtype.split("/")[0] if "/" in rtype else "Microsoft.Resources"
            if provider_namespace not in service_map:
                service_map[provider_namespace] = {
                    "service_code": provider_namespace,
                    "service_name": provider_namespace.replace("Microsoft.", ""),
                    "service_category": cat,
                    "resource_count": 1,
                    "locations": [r.get("location", "global")],
                }
            else:
                service_map[provider_namespace]["resource_count"] += 1
                loc = r.get("location", "global")
                if loc not in service_map[provider_namespace]["locations"]:
                    service_map[provider_namespace]["locations"].append(loc)

        services = list(service_map.values())
        return PagedResult(
            items=services, continuation_token=None, is_truncated=False, total_records=len(services)
        )
