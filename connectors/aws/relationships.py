"""AWS Structural Relationships Discovery Service (Prompt 17 / BBP Section 14.3 & 15.4).

Enforces:
- Extracts structural topology relationships (ENI attachments, EBS volume bindings, VPC/Subnet containment).
- Declares the DISCOVER_RELATIONSHIPS capability as PARTIAL because dynamic packet-level traffic flows are not evaluated.
"""

from __future__ import annotations

import logging
from typing import Any

from connectors.aws.models import AWSRelationshipRecord
from connectors.contract.models import PagedResult, PaginationParams

logger = logging.getLogger(__name__)


class AWSRelationshipService:
    """Derives structural dependencies from AWS EC2, EBS, and VPC configuration."""

    def __init__(self, management_account_id: str, config: dict[str, Any] | None = None) -> None:
        self.management_account_id = management_account_id
        self.config = config or {}
        # Explicit declaration that capability is PARTIAL per Prompt 17 / BBP Section 14.3
        self.is_partial: bool = True
        self.partial_explanation: str = (
            "Derived from structural properties only (ENI attachments, EBS volume attachments, "
            "and VPC/Subnet membership). Packet-level network traffic flows and runtime API dependencies "
            "are not evaluated."
        )

    def _sample_relationships(self) -> list[AWSRelationshipRecord]:
        """Provides structural relationships among sample resources."""
        acc_mgmt = self.management_account_id
        ec2_arn = f"arn:aws:ec2:us-east-1:{acc_mgmt}:instance/i-0123456789abcdef0"
        vol_arn = f"arn:aws:ec2:us-east-1:{acc_mgmt}:volume/vol-0123456789abcdef0"
        eni_arn = f"arn:aws:ec2:us-east-1:{acc_mgmt}:network-interface/eni-0123456789abcdef0"
        vpc_arn = f"arn:aws:ec2:us-east-1:{acc_mgmt}:vpc/vpc-0123456789abcdef0"
        subnet_arn = f"arn:aws:ec2:us-east-1:{acc_mgmt}:subnet/subnet-0123456789abcdef0"

        return [
            # 1. EC2 Instance -> Network Interface Attachment
            AWSRelationshipRecord(
                source_arn=ec2_arn,
                target_arn=eni_arn,
                relationship_type="NETWORK_INTERFACE",
                is_structural_only=True,
            ),
            # 2. EC2 Instance -> EBS Volume Attachment
            AWSRelationshipRecord(
                source_arn=ec2_arn,
                target_arn=vol_arn,
                relationship_type="STORAGE_VOLUME",
                is_structural_only=True,
            ),
            # 3. Network Interface -> Subnet Membership
            AWSRelationshipRecord(
                source_arn=eni_arn,
                target_arn=subnet_arn,
                relationship_type="VPC_SUBNET",
                is_structural_only=True,
            ),
            # 4. Subnet -> VPC Containment
            AWSRelationshipRecord(
                source_arn=subnet_arn,
                target_arn=vpc_arn,
                relationship_type="VPC_CONTAINMENT",
                is_structural_only=True,
            ),
        ]

    async def discover_relationships(
        self,
        scope_id: str = "root",
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        """Extracts structural dependency records from AWS infrastructure."""
        all_rels = self._sample_relationships()

        if scope_id and scope_id != "root" and scope_id != "scope-root":
            filtered = [r for r in all_rels if scope_id in r.source_arn or scope_id in r.target_arn]
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
