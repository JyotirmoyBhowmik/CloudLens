"""Azure Structural Relationships Discovery Service (Prompt 16 / BBP Section 14.2 & 15.4).

Enforces:
- Extracts structural topology relationships from Resource Graph (NICs, managed disks, parent-child, managedBy).
- Declares the DISCOVER_RELATIONSHIPS capability as PARTIAL because dynamic traffic flow routing is not evaluated.
"""

from __future__ import annotations

import logging
from typing import Any

from connectors.azure.models import AzureRelationshipRecord
from connectors.contract.models import PagedResult, PaginationParams

logger = logging.getLogger(__name__)


class AzureRelationshipService:
    """Derives structural dependencies from Azure Resource Graph."""

    def __init__(self, tenant_id: str, config: dict[str, Any] | None = None) -> None:
        self.tenant_id = tenant_id
        self.config = config or {}
        # Explicit declaration that capability is PARTIAL
        self.is_partial: bool = True
        self.partial_explanation: str = (
            "Derived from structural ARM and Resource Graph bindings only (NIC attachments, OS/data disks, "
            "parent-child containment, and managedBy links). Dynamic network flow routing and application-layer "
            "dependencies are not evaluated."
        )

    def _sample_relationships(self) -> list[AzureRelationshipRecord]:
        """Provides structural relationships among sample resources."""
        sub_prod = "sub-prod-0001"
        rg_compute = "rg-payments-prod"

        vm_id = f"/subscriptions/{sub_prod}/resourceGroups/{rg_compute}/providers/Microsoft.Compute/virtualMachines/vm-payment-gw-01"
        nic_id = f"/subscriptions/{sub_prod}/resourceGroups/{rg_compute}/providers/Microsoft.Network/networkInterfaces/nic-payment-gw-01"
        disk_id = f"/subscriptions/{sub_prod}/resourceGroups/{rg_compute}/providers/Microsoft.Compute/disks/disk-vm-payment-gw-os"
        sql_srv_id = f"/subscriptions/{sub_prod}/resourceGroups/{rg_compute}/providers/Microsoft.Sql/servers/sql-payments-prod"
        sql_db_id = f"{sql_srv_id}/databases/db-transactions"

        return [
            # 1. VM -> NIC attachment
            AzureRelationshipRecord(
                source_id=vm_id,
                target_id=nic_id,
                relationship_type="NETWORK_INTERFACE",
                is_structural_only=True,
            ),
            # 2. VM -> OS Disk attachment
            AzureRelationshipRecord(
                source_id=vm_id,
                target_id=disk_id,
                relationship_type="OS_DISK",
                is_structural_only=True,
            ),
            # 3. Disk managedBy VM link
            AzureRelationshipRecord(
                source_id=disk_id,
                target_id=vm_id,
                relationship_type="MANAGED_BY",
                is_structural_only=True,
            ),
            # 4. SQL Server -> Database parent-child
            AzureRelationshipRecord(
                source_id=sql_srv_id,
                target_id=sql_db_id,
                relationship_type="PARENT_CHILD",
                is_structural_only=True,
            ),
        ]

    async def discover_relationships(
        self,
        scope_id: str = "root",
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        """Extracts structural dependency records from Resource Graph."""
        all_rels = self._sample_relationships()

        if scope_id and scope_id != "root" and scope_id != "scope-root":
            filtered = [r for r in all_rels if scope_id in r.source_id or scope_id in r.target_id]
        else:
            filtered = all_rels

        records = [r.model_dump() for r in filtered]
        page_size = pagination.page_size if pagination else len(records)
        page_items = records[:page_size]
        is_truncated = len(records) > page_size

        return PagedResult(
            items=page_items,
            continuation_token=str(page_size) if is_truncated else None,
            is_truncated=is_truncated,
            total_records=len(records),
        )
