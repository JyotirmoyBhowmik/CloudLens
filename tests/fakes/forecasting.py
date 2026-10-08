"""In-memory fake repository for Forecast entities and Milestone snapshots (Prompt P06)."""

from __future__ import annotations

import builtins
import logging
from datetime import date
from typing import Any

from domain.forecasting.models import (
    ForecastEntity,
    ForecastMilestoneSnapshot,
)
from domain.tenant.context import TenantContext
from domain.tenant.repository import TenantAwareRepository

logger = logging.getLogger(__name__)


class InMemoryForecastRepository(TenantAwareRepository[ForecastEntity]):
    """In-memory tenant-isolated repository for forecast records and milestone evaluations."""

    is_in_memory: bool = True

    def __init__(self) -> None:
        self._forecasts: dict[tuple[str, str], ForecastEntity] = {}
        self._milestones: dict[tuple[str, str], ForecastMilestoneSnapshot] = {}

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> ForecastEntity | None:
        self._validate_tenant_context(tenant_context)
        return self._forecasts.get((tenant_context.tenant_id, entity_id))

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[ForecastEntity]:
        self._validate_tenant_context(tenant_context)
        tenant_id = tenant_context.tenant_id

        results = [f for (t_id, _), f in self._forecasts.items() if t_id == tenant_id]

        if filter_params and isinstance(filter_params, dict):
            if "scope_id" in filter_params and filter_params["scope_id"]:
                sid = filter_params["scope_id"]
                results = [f for f in results if f.scope_id == sid]
            if "budget_id" in filter_params and filter_params["budget_id"]:
                bid = filter_params["budget_id"]
                results = [f for f in results if f.budget_id == bid]
            if "period" in filter_params and filter_params["period"]:
                p = filter_params["period"]
                results = [f for f in results if f.period == p or f.period.value == str(p)]
            if "effective_method" in filter_params and filter_params["effective_method"]:
                m = filter_params["effective_method"]
                results = [
                    f
                    for f in results
                    if f.effective_method == m or f.effective_method.value == str(m)
                ]
            if "confidence" in filter_params and filter_params["confidence"]:
                c = filter_params["confidence"]
                results = [f for f in results if f.confidence == c or f.confidence.value == str(c)]
            if "is_active" in filter_params and filter_params["is_active"] is not None:
                is_act = bool(filter_params["is_active"])
                results = [f for f in results if f.is_active == is_act]

        results.sort(key=lambda x: x.generation_timestamp, reverse=True)
        return results[offset : offset + limit]

    def save(self, entity: ForecastEntity, *, tenant_context: TenantContext) -> ForecastEntity:
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, entity.id)
        self._forecasts[key] = entity
        return entity

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, entity_id)
        if key in self._forecasts:
            del self._forecasts[key]
            return True
        return False

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        self._validate_tenant_context(tenant_context)
        return (tenant_context.tenant_id, entity_id) in self._forecasts

    def count(self, *, tenant_context: TenantContext, filter_params: Any = None) -> int:
        self._validate_tenant_context(tenant_context)
        return len(
            self.list(tenant_context=tenant_context, filter_params=filter_params, limit=10000)
        )

    def find_active_by_scope(
        self,
        scope_id: str,
        period_start: date,
        period_end: date,
        *,
        tenant_context: TenantContext,
    ) -> ForecastEntity | None:
        self._validate_tenant_context(tenant_context)
        tenant_id = tenant_context.tenant_id

        for (t_id, _), f in self._forecasts.items():
            if (
                t_id == tenant_id
                and f.is_active
                and f.scope_id == scope_id
                and f.period_start == period_start
                and f.period_end == period_end
            ):
                return f
        return None

    def find_by_period_overlap(
        self,
        start_date: date,
        end_date: date,
        *,
        tenant_context: TenantContext,
    ) -> builtins.list[ForecastEntity]:
        self._validate_tenant_context(tenant_context)
        tenant_id = tenant_context.tenant_id

        results: builtins.list[ForecastEntity] = []
        for (t_id, _), f in self._forecasts.items():
            if t_id == tenant_id and f.is_active:
                period_overlaps = not (f.period_end < start_date or f.period_start > end_date)
                window_overlaps = not (
                    f.input_window.end_date < start_date or f.input_window.start_date > end_date
                )
                if period_overlaps or window_overlaps:
                    results.append(f)
        return results

    def save_milestone(
        self,
        snapshot: ForecastMilestoneSnapshot,
        *,
        tenant_context: TenantContext,
    ) -> ForecastMilestoneSnapshot:
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, snapshot.id)
        self._milestones[key] = snapshot
        return snapshot

    def list_milestones(
        self,
        *,
        period_identifier: str | None = None,
        scope_id: str | None = None,
        tenant_context: TenantContext,
    ) -> builtins.list[ForecastMilestoneSnapshot]:
        self._validate_tenant_context(tenant_context)
        tenant_id = tenant_context.tenant_id

        results = [m for (t_id, _), m in self._milestones.items() if t_id == tenant_id]
        if period_identifier:
            results = [m for m in results if m.period_identifier == period_identifier]
        if scope_id:
            results = [m for m in results if m.scope_id == scope_id]

        results.sort(key=lambda x: (x.period_start, x.checkpoint_date))
        return results

    def clear_tenant_data(self, *, tenant_context: TenantContext) -> None:
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id
        for k in [k for k in self._forecasts if k[0] == t_id]:
            del self._forecasts[k]
        for k in [k for k in self._milestones if k[0] == t_id]:
            del self._milestones[k]

    def _clear_all_for_testing(self) -> None:
        self._forecasts.clear()
        self._milestones.clear()
