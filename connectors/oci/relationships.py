"""OCI Structural Relationships Discovery Service (Prompt 19 / BBP Section 14.5 & 15.4).

Enforces:
- Extracts structural topology relationships (VNIC attachments, Volume attachments, Subnet/VCN containment).
- Declares DISCOVER_RELATIONSHIPS capability as MINIMAL / PARTIAL:
  OCI does not expose an application-level dependency graph or packet-level traffic flow graph.
"""

from __future__ import annotations

import logging
from typing import Any

from connectors.contract.models import PagedResult, PaginationParams
from connectors.oci.models import OCIRelationshipRecord

logger = logging.getLogger(__name__)


class OCIRelationshipService:
    """Derives structural dependencies from OCI Compute, Storage, and Virtual Networking."""

    def __init__(
        self,
        tenancy_id: str = "ocid1.tenancy.oc1..aaaaaaaademo123456789",
        config: dict[str, Any] | None = None,
    ) -> None:
        self.tenancy_id = tenancy_id
        self.config = config or {}
        self.is_partial: bool = True
        self.partial_explanation: str = (
            "Derived from structural properties only (VNIC attachments, block volume attachments, "
            "and Subnet/VCN membership). OCI does not maintain an application-level dependency graph, "
            "and runtime packet flows (VCN Flow Logs) are not evaluated."
        )

    def _sample_relationships(self) -> list[OCIRelationshipRecord]:
        """Provides structural relationships among sample OCI resources."""
        vm_id = "ocid1.instance.oc1.iad.anuwcljtdemovm001"
        vnic_id = "ocid1.vnic.oc1.iad.anuwcljtdemovnic001"
        vol_id = "ocid1.volume.oc1.iad.bootvol001"
        subnet_id = "ocid1.subnet.oc1.iad.demosubnet001"
        vcn_id = "ocid1.vcn.oc1.iad.demovcn001"
        c_prod = "ocid1.compartment.oc1..aaaaaaaaprod987654321"

        return [
            # 1. Instance -> VNIC Attachment
            OCIRelationshipRecord(
                source_id=vm_id,
                target_id=vnic_id,
                relationship_type="VNIC_ATTACHMENT",
                is_structural_only=True,
            ),
            # 2. Instance -> Boot/Block Volume Attachment
            OCIRelationshipRecord(
                source_id=vm_id,
                target_id=vol_id,
                relationship_type="VOLUME_ATTACHMENT",
                is_structural_only=True,
            ),
            # 3. VNIC -> Subnet Membership
            OCIRelationshipRecord(
                source_id=vnic_id,
                target_id=subnet_id,
                relationship_type="SUBNET_MEMBER",
                is_structural_only=True,
            ),
            # 4. Subnet -> VCN Containment
            OCIRelationshipRecord(
                source_id=subnet_id,
                target_id=vcn_id,
                relationship_type="VCN_CONTAINMENT",
                is_structural_only=True,
            ),
            # 5. Resource -> Compartment Ownership Boundary
            OCIRelationshipRecord(
                source_id=vm_id,
                target_id=c_prod,
                relationship_type="COMPARTMENT_CONTAINMENT",
                is_structural_only=True,
            ),
        ]

    async def discover_relationships(
        self,
        scope_id: str = "root",
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        """Extracts structural dependency records from OCI infrastructure."""
        all_rels = self._sample_relationships()

        if scope_id and scope_id not in ("root", "global", "", self.tenancy_id):
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
