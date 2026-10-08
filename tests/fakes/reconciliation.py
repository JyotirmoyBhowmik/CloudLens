"""In-memory fake repository for Reconciliation Reports and Investigations (Prompt P06)."""

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


class InMemoryReconciliationRepository(TenantAwareRepository[ReconciliationReport]):
    """Tenant-isolated repository for reconciliation reports, investigation items, and estimate accuracy."""

    is_in_memory: bool = True

    def __init__(self) -> None:
        self._reports: dict[tuple[str, str], ReconciliationReport] = {}
        self._investigations: dict[tuple[str, str], ReconciliationInvestigationItem] = {}
        self._estimates: dict[tuple[str, str], EstimateVsActualItem] = {}

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> ReconciliationReport | None:
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

        results.sort(key=lambda r: r.reconciled_at, reverse=True)
        return results[offset : offset + limit]

    def save(
        self, entity: ReconciliationReport, *, tenant_context: TenantContext
    ) -> ReconciliationReport:
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, entity.id)
        self._reports[key] = entity
        return entity

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, entity_id)
        if key in self._reports:
            del self._reports[key]
            return True
        return False

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, entity_id)
        return key in self._reports

    def save_investigation_item(
        self,
        item: ReconciliationInvestigationItem,
        *,
        tenant_context: TenantContext,
    ) -> ReconciliationInvestigationItem:
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

    def get_history(
        self,
        *,
        tenant_context: TenantContext,
        provider: str | None = None,
        scope_id: str | None = None,
    ) -> builtins.list[ReconciliationReport]:
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

        reports.sort(key=lambda r: (r.billing_period, r.reconciled_at))
        return reports

    def save_estimate_vs_actual(
        self,
        item: EstimateVsActualItem,
        *,
        tenant_context: TenantContext,
    ) -> EstimateVsActualItem:
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
        self._validate_tenant_context(tenant_context)
        tid = tenant_context.tenant_id

        items: list[EstimateVsActualItem] = []
        for (t, _), est in self._estimates.items():
            if t == tid:
                if billing_period and est.billing_period != billing_period:
                    continue
                items.append(est)

        return items

    def prevent_cost_adjustment(
        self,
        cost_fact_id: str,
        *,
        tenant_context: TenantContext,
    ) -> None:
        self._validate_tenant_context(tenant_context)
        raise ReconciliationAdjustmentForbiddenException(cost_fact_id)
