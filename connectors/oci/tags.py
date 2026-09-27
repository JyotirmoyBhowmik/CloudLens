"""OCI Tags Collection and Cost-Tracking Tag Service (Prompt 19 / BBP Section 14.5 & 15.4).

Enforces:
- Distinct modeling of:
  1. Free-form tags (unstructured key-value pairs).
  2. Defined tags (namespaced schema: Namespace.Key).
  3. Cost-tracking tags (designated defined tags for billing boundary allocation; max 10 per tenancy).
- Canonical key normalization: {Namespace}.{Key} while preserving namespace separately.
- Non-retroactive tag attribution disclosure:
  * Tag-based cost attribution applies strictly from the timestamp of association onward.
  * Historical costs preceding association are NOT retroactively attributed.
"""

from __future__ import annotations

import logging
from typing import Any

from connectors.contract.models import PagedResult, PaginationParams
from connectors.oci.models import OCITagRecord

logger = logging.getLogger(__name__)

OCI_TAG_NON_RETROACTIVE_POLICY = (
    "OCI tag-based cost attribution applies strictly from the time the tag was associated with the resource. "
    "Attribution is NOT retroactive. A tag applied today does not retroactively allocate last month's cost."
)


class OCITagService:
    """Collects free-form, defined, and cost-tracking tags with non-retroactive timing semantics."""

    def __init__(
        self,
        tenancy_id: str = "ocid1.tenancy.oc1..aaaaaaaademo123456789",
        config: dict[str, Any] | None = None,
    ) -> None:
        self.tenancy_id = tenancy_id
        self.config = config or {}
        self.attribution_policy_note: str = OCI_TAG_NON_RETROACTIVE_POLICY

    def _sample_tags(self) -> list[OCITagRecord]:
        """Provides representative OCI tags distinguishing free-form, defined, and cost-tracking tags."""
        vm_id = "ocid1.instance.oc1.iad.anuwcljtdemovm001"
        db_id = "ocid1.autonomousdatabase.oc1.iad.anuwcljtdemodb002"
        bucket_id = "ocid1.bucket.oc1.iad.demologsbucket01"

        return [
            # 1. Cost-tracking defined tag (Operations.CostCenter)
            OCITagRecord(
                resource_id=vm_id,
                tag_type="COST_TRACKING",
                namespace="Operations",
                key="CostCenter",
                value="CC-OPS-200",
                canonical_key="Operations.CostCenter",
                is_cost_tracking=True,  # Cost-tracking tag in tenancy
                associated_at="2026-09-01T00:00:00Z",
                is_retroactive_attribution=False,
            ),
            # 2. Standard defined tag (Operations.Owner)
            OCITagRecord(
                resource_id=vm_id,
                tag_type="DEFINED",
                namespace="Operations",
                key="Owner",
                value="devops@cloudlens.internal",
                canonical_key="Operations.Owner",
                is_cost_tracking=False,
                associated_at="2026-09-01T00:00:00Z",
                is_retroactive_attribution=False,
            ),
            # 3. Security defined tag (Security.DataClassification)
            OCITagRecord(
                resource_id=vm_id,
                tag_type="DEFINED",
                namespace="Security",
                key="DataClassification",
                value="Restricted",
                canonical_key="Security.DataClassification",
                is_cost_tracking=False,
                associated_at="2026-09-01T00:00:00Z",
                is_retroactive_attribution=False,
            ),
            # 4. Free-form tag (Environment)
            OCITagRecord(
                resource_id=vm_id,
                tag_type="FREE_FORM",
                namespace=None,
                key="Environment",
                value="Production",
                canonical_key="Environment",
                is_cost_tracking=False,
                associated_at="2026-09-01T00:00:00Z",
                is_retroactive_attribution=False,
            ),
            # 5. Cost-tracking defined tag on Autonomous Database
            OCITagRecord(
                resource_id=db_id,
                tag_type="COST_TRACKING",
                namespace="Operations",
                key="CostCenter",
                value="CC-FIN-01",
                canonical_key="Operations.CostCenter",
                is_cost_tracking=True,
                associated_at="2026-09-01T00:00:00Z",
                is_retroactive_attribution=False,
            ),
            # 6. Free-form tag on Object Storage
            OCITagRecord(
                resource_id=bucket_id,
                tag_type="FREE_FORM",
                namespace=None,
                key="LogArchive",
                value="True",
                canonical_key="LogArchive",
                is_cost_tracking=False,
                associated_at="2026-09-01T00:00:00Z",
                is_retroactive_attribution=False,
            ),
        ]

    async def collect_tags(
        self,
        scope_id: str = "root",
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        """Collects tags filtered by scope, with canonical keys and cost-tracking distinction."""
        all_tags = self._sample_tags()
        filtered: list[OCITagRecord] = []

        for tag in all_tags:
            if (
                scope_id in ("root", "global", "", self.tenancy_id)
                or tag.resource_id == scope_id
                or scope_id in tag.resource_id
            ):
                filtered.append(tag)

        raw_dicts = [t.model_dump() for t in filtered]
        page_size = pagination.page_size if pagination else len(raw_dicts)
        page_items = raw_dicts[:page_size]
        is_truncated = len(raw_dicts) > page_size

        return PagedResult(
            items=page_items,
            continuation_token=str(page_size) if is_truncated else None,
            is_truncated=is_truncated,
            total_records=len(raw_dicts),
        )

    def list_cost_tracking_tags(self) -> list[OCITagRecord]:
        """Returns all defined tags designated as cost-tracking in this tenancy (up to 10)."""
        return [t for t in self._sample_tags() if t.is_cost_tracking]

    def get_tag_attribution_metadata(self) -> dict[str, Any]:
        """Surfaces tag attribution rules and non-retroactive policy for UI display."""
        return {
            "is_retroactive": False,
            "policy_statement": self.attribution_policy_note,
            "cost_tracking_tags_limit": 10,
            "cost_tracking_tags_active": len(self.list_cost_tracking_tags()),
        }

    def register_cost_tracking_tag(self, tag_key: str) -> None:
        """Registers a defined tag as cost-tracking in this tenancy (maximum 10 allowed)."""
        if not hasattr(self, "_cost_tracking_tags"):
            self._cost_tracking_tags: set[str] = set()
        if len(self._cost_tracking_tags) >= 10:
            raise ValueError(
                f"Maximum 10 cost-tracking tags allowed per tenancy. Cannot register '{tag_key}'."
            )
        self._cost_tracking_tags.add(tag_key)
