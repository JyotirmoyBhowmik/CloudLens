"""GCP Labels and Source Tier Collection Service (Prompt 18 / BBP Section 14.4 & 15.4).

Enforces:
- Collection of GCP labels with source tier recorded:
  * LABEL_SOURCE_PROJECT: Inherited from project metadata
  * LABEL_SOURCE_RESOURCE: Directly attached to the resource
- Preserves label provenance for FinOps allocation and cost reporting.
"""

from __future__ import annotations

import logging
from typing import Any

from connectors.contract.models import PagedResult, PaginationParams
from connectors.gcp.models import GCPLabelRecord

logger = logging.getLogger(__name__)


class GCPTagService:
    """Collects GCP labels with strict source tier level attribution."""

    def __init__(
        self,
        primary_project_id: str = "proj-cloudlens-core",
        config: dict[str, Any] | None = None,
    ) -> None:
        self.primary_project_id = primary_project_id
        self.config = config or {}

    def _sample_labels(self) -> list[GCPLabelRecord]:
        """Provides representative labels with explicit project vs resource source tiers."""
        proj_retail = "proj-retail-banking-prod"
        proj_analytics = "proj-ai-recommendations-analytics"

        vm_id = f"//compute.googleapis.com/projects/{proj_retail}/zones/us-central1-a/instances/gcp-vm-core-bank-prod-01"
        bucket_id = f"//storage.googleapis.com/projects/{proj_retail}/buckets/gcp-gcs-customer-statements-prod"
        bq_table_id = f"//bigquery.googleapis.com/projects/{proj_analytics}/datasets/analytics/tables/bq-daily-customer-features"

        return [
            # 1. Project-level labels (LABEL_SOURCE_PROJECT)
            GCPLabelRecord(
                scope_id=f"projects/{proj_retail}",
                source_tier="LABEL_SOURCE_PROJECT",
                key="business_unit",
                value="Retail-Banking",
            ),
            GCPLabelRecord(
                scope_id=f"projects/{proj_retail}",
                source_tier="LABEL_SOURCE_PROJECT",
                key="env",
                value="production",
            ),
            GCPLabelRecord(
                scope_id=f"projects/{proj_analytics}",
                source_tier="LABEL_SOURCE_PROJECT",
                key="business_unit",
                value="Data-Analytics",
            ),
            GCPLabelRecord(
                scope_id=f"projects/{proj_analytics}",
                source_tier="LABEL_SOURCE_PROJECT",
                key="data-classification",
                value="confidential",
            ),
            # 2. Resource-level labels (LABEL_SOURCE_RESOURCE)
            GCPLabelRecord(
                scope_id=vm_id,
                source_tier="LABEL_SOURCE_RESOURCE",
                key="app",
                value="core-banking-api",
            ),
            GCPLabelRecord(
                scope_id=vm_id,
                source_tier="LABEL_SOURCE_RESOURCE",
                key="cost_centre",
                value="CC-BANK-100",
            ),
            GCPLabelRecord(
                scope_id=vm_id,
                source_tier="LABEL_SOURCE_RESOURCE",
                key="owner",
                value="banking-eng",
            ),
            GCPLabelRecord(
                scope_id=bucket_id,
                source_tier="LABEL_SOURCE_RESOURCE",
                key="app",
                value="statement-storage",
            ),
            GCPLabelRecord(
                scope_id=bucket_id,
                source_tier="LABEL_SOURCE_RESOURCE",
                key="cost_centre",
                value="CC-BANK-100",
            ),
            GCPLabelRecord(
                scope_id=bq_table_id,
                source_tier="LABEL_SOURCE_RESOURCE",
                key="project-lead",
                value="ml-platform",
            ),
        ]

    async def collect_tags(
        self,
        scope_id: str = "root",
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        """Collects labels filtered by scope_id with source tier metadata preserved."""
        all_labels = self._sample_labels()
        filtered: list[GCPLabelRecord] = []

        for lbl in all_labels:
            if (
                scope_id in ("root", "global", "")
                or lbl.scope_id == scope_id
                or scope_id in lbl.scope_id
            ):
                filtered.append(lbl)

        raw_dicts = [lbl_item.model_dump() for lbl_item in filtered]
        page_size = pagination.page_size if pagination else len(raw_dicts)
        page_items = raw_dicts[:page_size]
        is_truncated = len(raw_dicts) > page_size

        return PagedResult(
            items=page_items,
            continuation_token=str(page_size) if is_truncated else None,
            is_truncated=is_truncated,
            total_records=len(raw_dicts),
        )
