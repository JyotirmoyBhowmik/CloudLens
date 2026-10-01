"""Tenant-Aware Reconciliation Repository (Prompt 24 Items 1-7).

Enforces:
- Prompt 13 Item 84: Mandatory TenantContext in every repository method.
- Prompt 24 Item 4: Persisting and tracking investigation items on tolerance failures.
- Prompt 24 Item 7: Retaining historical reconciliation audits per billing period.
- Prompt 24 Item 6: Persisting and querying estimate-vs-actual comparison items.
- Prompt 24 Negative Constraints:
  * Strict prohibition against adjusting ingested cost data to force a match (ReconciliationAdjustmentForbiddenException).
"""

from __future__ import annotations

import builtins
import logging
from datetime import UTC, datetime
from typing import Any

from domain.cost.reconciliation.models import (
    EstimateVsActualItem,
    InvestigationStatus,
    ReconciliationInvestigationItem,
    ReconciliationReport,
)
from domain.models.exceptions import (
    ReconciliationAdjustmentForbiddenException,
    ReconciliationInvestigationNotFoundException,
)
from domain.tenant.context import TenantContext
from domain.tenant.repository import TenantAwareRepository

logger = logging.getLogger(__name__)


class ReconciliationRepository(TenantAwareRepository[ReconciliationReport]):
    """Tenant-isolated repository for reconciliation reports, investigation items, and estimate accuracy."""

    def __init__(self) -> None:
        # Key: (tenant_id, report_id) -> ReconciliationReport
        self._reports: dict[tuple[str, str], ReconciliationReport] = {}
        # Key: (tenant_id, item_id) -> ReconciliationInvestigationItem
        self._investigations: dict[tuple[str, str], ReconciliationInvestigationItem] = {}
        # Key: (tenant_id, item_id) -> EstimateVsActualItem
        self._estimates: dict[tuple[str, str], EstimateVsActualItem] = {}

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> ReconciliationReport | None:
        """Retrieves a single reconciliation report by ID within the tenant scope."""
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, entity_id)
        return self._reports.get(key)

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[ReconciliationReport]:
        """Lists reconciliation reports belonging strictly to the tenant."""
        self._validate_tenant_context(tenant_context)
        tid = tenant_context.tenant_id

        results: list[ReconciliationReport] = []
        for (t, _), report in self._reports.items():
            if t == tid:
                if isinstance(filter_params, dict):
                    if (
                        "billing_period" in filter_params
                        and filter_params["billing_period"]
                        and report.billing_period != filter_params["billing_period"]
                    ):
                        continue
                    if (
                        "provider" in filter_params
                        and filter_params["provider"]
                        and report.provider != filter_params["provider"]
                    ):
                        continue
                    if (
                        "scope_id" in filter_params
                        and filter_params["scope_id"]
                        and report.scope_id != filter_params["scope_id"]
                    ):
                        continue
                    if (
                        "status" in filter_params
                        and filter_params["status"]
                        and report.status != filter_params["status"]
                    ):
                        continue
                results.append(report)

        # Sort descending by reconciled_at
        results.sort(key=lambda r: r.reconciled_at, reverse=True)
        return results[offset : offset + limit]

    def save(
        self, entity: ReconciliationReport, *, tenant_context: TenantContext
    ) -> ReconciliationReport:
        """Persists or updates a reconciliation report."""
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, entity.id)
        self._reports[key] = entity
        return entity

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        """Deletes a reconciliation report within tenant scope."""
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, entity_id)
        if key in self._reports:
            del self._reports[key]
            return True
        return False

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        """Checks if a reconciliation report exists within tenant scope."""
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, entity_id)
        return key in self._reports

    # --------------------------------------------------------------------------
    # Investigation Items Lifecycle
    # --------------------------------------------------------------------------

    def save_investigation_item(
        self,
        item: ReconciliationInvestigationItem,
        *,
        tenant_context: TenantContext,
    ) -> ReconciliationInvestigationItem:
        """Persists an investigation item raised on tolerance failure."""
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, item.id)
        self._investigations[key] = item
        return item

    def get_investigation_item(
        self,
        item_id: str,
        *,
        tenant_context: TenantContext,
    ) -> ReconciliationInvestigationItem | None:
        """Retrieves an investigation item by ID."""
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, item_id)
        return self._investigations.get(key)

    def list_investigation_items(
        self,
        *,
        tenant_context: TenantContext,
        status: InvestigationStatus | None = None,
        provider: str | None = None,
    ) -> builtins.list[ReconciliationInvestigationItem]:
        """Lists investigation items for tenant with optional status and provider filters."""
        self._validate_tenant_context(tenant_context)
        tid = tenant_context.tenant_id

        results: builtins.list[ReconciliationInvestigationItem] = []
        for (t, _), item in self._investigations.items():
            if t == tid:
                if status is not None and item.status != status:
                    continue
                if provider is not None and item.provider != provider:
                    continue
                results.append(item)

        results.sort(key=lambda i: i.created_at, reverse=True)
        return results

    def update_investigation_item(
        self,
        item_id: str,
        status: InvestigationStatus,
        notes: str | None = None,
        *,
        tenant_context: TenantContext,
    ) -> ReconciliationInvestigationItem:
        """Updates the status and auditor notes of an investigation item."""
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, item_id)
        existing = self._investigations.get(key)
        if not existing:
            raise ReconciliationInvestigationNotFoundException(item_id)

        update_dict: dict[str, Any] = {"status": status}
        if status in (InvestigationStatus.RESOLVED, InvestigationStatus.CLOSED):
            update_dict["resolved_at"] = datetime.now(UTC)
        if notes:
            combined_notes = f"{existing.notes}\n{notes}".strip() if existing.notes else notes
            update_dict["notes"] = combined_notes

        updated = existing.model_copy(update=update_dict)
        self._investigations[key] = updated
        return updated

    # --------------------------------------------------------------------------
    # History & Trends
    # --------------------------------------------------------------------------

    def get_history(
        self,
        *,
        tenant_context: TenantContext,
        provider: str | None = None,
        scope_id: str | None = None,
    ) -> builtins.list[ReconciliationReport]:
        """Retrieves chronological reconciliation history for variance trend analysis."""
        self._validate_tenant_context(tenant_context)
        tid = tenant_context.tenant_id

        reports: builtins.list[ReconciliationReport] = []
        for (t, _), r in self._reports.items():
            if t == tid:
                if provider and r.provider != provider:
                    continue
                if scope_id and r.scope_id != scope_id:
                    continue
                reports.append(r)

        # Chronological order (oldest to newest)
        reports.sort(key=lambda r: (r.billing_period, r.reconciled_at))
        return reports

    # --------------------------------------------------------------------------
    # Estimate vs Actual Accuracy Tracking (Prompt 24 Item 6)
    # --------------------------------------------------------------------------

    def save_estimate_vs_actual(
        self,
        item: EstimateVsActualItem,
        *,
        tenant_context: TenantContext,
    ) -> EstimateVsActualItem:
        """Persists an estimate vs actual comparison item."""
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, item.id)
        self._estimates[key] = item
        return item

    def list_estimate_vs_actual(
        self,
        *,
        tenant_context: TenantContext,
        billing_period: str | None = None,
    ) -> builtins.list[EstimateVsActualItem]:
        """Lists estimate vs actual items for tenant, optionally filtered by billing period."""
        self._validate_tenant_context(tenant_context)
        tid = tenant_context.tenant_id

        items: list[EstimateVsActualItem] = []
        for (t, _), est in self._estimates.items():
            if t == tid:
                if billing_period and est.billing_period != billing_period:
                    continue
                items.append(est)

        return items

    # --------------------------------------------------------------------------
    # Anti-Fudging Guard (Prompt 24 Strict Negative Constraint)
    # --------------------------------------------------------------------------

    def prevent_cost_adjustment(
        self,
        cost_fact_id: str,
        *,
        tenant_context: TenantContext,
    ) -> None:
        """Guarantees that cost facts cannot be adjusted to force reconciliation.

        Strictly enforces Prompt 24 rule: 'Do not adjust ingested cost data to force a match.'
        """
        self._validate_tenant_context(tenant_context)
        raise ReconciliationAdjustmentForbiddenException(cost_fact_id)


_GLOBAL_RECONCILIATION_REPO = ReconciliationRepository()


def get_reconciliation_repository() -> ReconciliationRepository:
    """Dependency injection provider for ReconciliationRepository."""
    return _GLOBAL_RECONCILIATION_REPO
