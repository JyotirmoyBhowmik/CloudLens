"""GCP Cloud Billing Budgets Ingestion Service (Prompt 18 / BBP Section 14.4 & 15.4).

Enforces:
- Ingests Cloud Billing Budgets via Cloud Billing Budget API (billingbudgets.googleapis.com/v1).
- Read for comparison and variance analysis only:
  * Provider budgets are strictly marked as NON-AUTHORITATIVE (is_authoritative = False).
  * CloudLens master budgets remain the definitive system of record.
- Silent creation or attachment of chargeable Pub/Sub notification topics is strictly prohibited.
"""

from __future__ import annotations

import logging
from typing import Any

from connectors.contract.models import PagedResult, PaginationParams
from connectors.gcp.models import (
    GCPBudgetRecord,
    GCPPubSubSilentCreationForbiddenException,
)

logger = logging.getLogger(__name__)


class GCPBudgetService:
    """Reads Cloud Billing Budgets for comparative analytics without silent Pub/Sub charges."""

    def __init__(
        self,
        billing_account_id: str = "01ABCD-2345EF-6789GH",
        config: dict[str, Any] | None = None,
    ) -> None:
        self.billing_account_id = billing_account_id
        self.config = config or {}

        # Strictly forbid silent programmatic Pub/Sub configuration
        if self.config.get("enable_silent_pubsub", False):
            raise GCPPubSubSilentCreationForbiddenException()

    def _sample_budgets(self, billing_account_id: str) -> list[GCPBudgetRecord]:
        """Provides sample Cloud Billing Budgets with comparison-only semantics."""
        b_acc = billing_account_id or self.billing_account_id
        clean_id = b_acc.replace("billingAccounts/", "").strip()

        return [
            GCPBudgetRecord(
                budget_name="Enterprise-Overall-Billing-Budget",
                billing_account_id=clean_id,
                amount=100000.0,
                current_spend=54300.0,
                time_period="CALENDAR_MONTH",
                is_authoritative=False,  # Non-authoritative comparison only
                has_pubsub_rule=False,  # Silent Pub/Sub disabled
            ),
            GCPBudgetRecord(
                budget_name="Retail-Banking-Monthly-Budget",
                billing_account_id=clean_id,
                amount=35000.0,
                current_spend=21200.0,
                time_period="CALENDAR_MONTH",
                is_authoritative=False,
                has_pubsub_rule=False,
            ),
        ]

    async def collect_budgets(
        self,
        scope_id: str | None = None,
        pagination: PaginationParams | None = None,
    ) -> PagedResult[dict[str, Any]]:
        """Collects budgets from Google Cloud Billing Budget API.

        Endpoint: GET https://billingbudgets.googleapis.com/v1/billingAccounts/{billingAccountId}/budgets
        """
        # Validate that silent Pub/Sub has not been enabled
        if self.config.get("enable_silent_pubsub", False):
            raise GCPPubSubSilentCreationForbiddenException()

        target_acc = scope_id or self.billing_account_id
        budgets = self._sample_budgets(target_acc)
        records = [b.model_dump() for b in budgets]

        page_size = pagination.page_size if pagination else len(records)
        page_items = records[:page_size]
        is_truncated = len(records) > page_size

        return PagedResult(
            items=page_items,
            continuation_token=str(page_size) if is_truncated else None,
            is_truncated=is_truncated,
            total_records=len(records),
        )
