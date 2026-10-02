"""Tenant-Scoped Repository for Forecast Entities and Milestone Snapshots (Prompt 29).

Enforces:
- Prompt 13 Item 84: 100% TenantContext validation across all repository operations.
- Tenant isolation per BBP Section 41 and SEC-015.
- Prompt 29: Stored forecasts with method, input window, generation timestamp, and confidence label.
- Prompt 29: Forecast accuracy milestones recorded at 25%, 50%, 75%, and period close.
"""

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


class ForecastRepository(TenantAwareRepository[ForecastEntity]):
    """In-memory tenant-isolated repository for forecast records and milestone evaluations."""

    def __init__(self) -> None:
        # Key: (tenant_id, forecast_id) -> ForecastEntity
        self._forecasts: dict[tuple[str, str], ForecastEntity] = {}
        # Key: (tenant_id, snapshot_id) -> ForecastMilestoneSnapshot
        self._milestones: dict[tuple[str, str], ForecastMilestoneSnapshot] = {}

    # ==========================================================================
    # 1. Base TenantAwareRepository Implementation
    # ==========================================================================

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> ForecastEntity | None:
        """Retrieves a single forecast by ID within tenant boundary."""
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
        """Lists forecasts belonging strictly to the tenant with optional pagination."""
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

        # Sort descending by generation timestamp
        results.sort(key=lambda x: x.generation_timestamp, reverse=True)
        return results[offset : offset + limit]

    def save(self, entity: ForecastEntity, *, tenant_context: TenantContext) -> ForecastEntity:
        """Persists or updates a forecast within tenant boundary."""
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, entity.id)
        self._forecasts[key] = entity
        return entity

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        """Deletes a forecast within tenant boundary."""
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, entity_id)
        if key in self._forecasts:
            del self._forecasts[key]
            return True
        return False

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        """Checks if a forecast exists within tenant boundary."""
        self._validate_tenant_context(tenant_context)
        return (tenant_context.tenant_id, entity_id) in self._forecasts

    def count(self, *, tenant_context: TenantContext, filter_params: Any = None) -> int:
        """Returns total forecast count matching filter within tenant boundary."""
        self._validate_tenant_context(tenant_context)
        return len(
            self.list(tenant_context=tenant_context, filter_params=filter_params, limit=10000)
        )

    # ==========================================================================
    # 2. Specialized Forecast Domain Queries
    # ==========================================================================

    def find_active_by_scope(
        self,
        scope_id: str,
        period_start: date,
        period_end: date,
        *,
        tenant_context: TenantContext,
    ) -> ForecastEntity | None:
        """Retrieves active forecast matching scope and period boundaries."""
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
        """Finds all active forecasts whose input window or target period overlaps specified range."""
        self._validate_tenant_context(tenant_context)
        tenant_id = tenant_context.tenant_id

        results: builtins.list[ForecastEntity] = []
        for (t_id, _), f in self._forecasts.items():
            if t_id == tenant_id and f.is_active:
                # Check period overlap or input window overlap
                period_overlaps = not (f.period_end < start_date or f.period_start > end_date)
                window_overlaps = not (
                    f.input_window.end_date < start_date or f.input_window.start_date > end_date
                )
                if period_overlaps or window_overlaps:
                    results.append(f)
        return results

    # ==========================================================================
    # 3. Milestone Snapshot Persistence
    # ==========================================================================

    def save_milestone(
        self,
        snapshot: ForecastMilestoneSnapshot,
        *,
        tenant_context: TenantContext,
    ) -> ForecastMilestoneSnapshot:
        """Persists a milestone evaluation snapshot."""
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
        """Lists milestone snapshots matching filters within tenant boundary."""
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
        """Clears all stored forecasts and milestones for the authenticated tenant."""
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id
        for k in [k for k in self._forecasts if k[0] == t_id]:
            del self._forecasts[k]
        for k in [k for k in self._milestones if k[0] == t_id]:
            del self._milestones[k]

    def _clear_all_for_testing(self) -> None:
        """Clears all stored data across tenants (internal test isolation only)."""
        self._forecasts.clear()
        self._milestones.clear()


# ==============================================================================
# Repository Singleton Factory
# ==============================================================================

_forecast_repo_instance: ForecastRepository | None = None


def get_forecast_repository() -> ForecastRepository:
    """Returns singleton ForecastRepository instance."""
    global _forecast_repo_instance
    if _forecast_repo_instance is None:
        _forecast_repo_instance = ForecastRepository()
    return _forecast_repo_instance


def reset_forecast_repository() -> None:
    """Resets singleton ForecastRepository (for test teardown)."""
    global _forecast_repo_instance
    if _forecast_repo_instance is not None:
        _forecast_repo_instance._clear_all_for_testing()
    _forecast_repo_instance = None
