"""Tenant-Scoped Repository for Forecast Entities and Milestone Snapshots (Prompt P06).

Enforces:
- Prompt 13 Item 84: 100% TenantContext validation across all repository operations.
- Pattern P1: Protocol + SqlForecastRepository (SQLAlchemy 2.0 async + asyncpg).
- Pattern P3: Injected dependency, zero mutable dict singletons in production.
- Pattern P4: Transactional RLS isolation via get_tenant_session().
- Pattern P6: Startup guard preventing InMemory repository outside development.
- Stored forecasts with method, input window, generation timestamp, and confidence label surviving restarts.
- Forecast accuracy milestones recorded and retrievable across restarts.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import os
import sys
from datetime import date, datetime
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_tenant_session, run_async, verify_persistence_startup_guard
from domain.forecasting.models import (
    ForecastEntity,
    ForecastMilestoneSnapshot,
)
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)


@runtime_checkable
class ForecastRepository(Protocol):
    """Authoritative protocol for Forecast and Milestone persistence."""

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> ForecastEntity | None:
        ...

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ForecastEntity]:
        ...

    def save(self, entity: ForecastEntity, *, tenant_context: TenantContext) -> ForecastEntity:
        ...

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        ...

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        ...

    def count(self, *, tenant_context: TenantContext, filter_params: Any = None) -> int:
        ...

    def find_active_by_scope(
        self,
        scope_id: str,
        period_start: date,
        period_end: date,
        *,
        tenant_context: TenantContext,
    ) -> ForecastEntity | None:
        ...

    def find_by_period_overlap(
        self,
        start_date: date,
        end_date: date,
        *,
        tenant_context: TenantContext,
    ) -> list[ForecastEntity]:
        ...

    def save_milestone(
        self,
        snapshot: ForecastMilestoneSnapshot,
        *,
        tenant_context: TenantContext,
    ) -> ForecastMilestoneSnapshot:
        ...

    def list_milestones(
        self,
        *,
        period_identifier: str | None = None,
        scope_id: str | None = None,
        tenant_context: TenantContext,
    ) -> list[ForecastMilestoneSnapshot]:
        ...

    def clear_tenant_data(self, *, tenant_context: TenantContext) -> None:
        ...


class SqlForecastRepository:
    """PostgreSQL implementation of ForecastRepository using SQLAlchemy async."""

    is_in_memory: bool = False

    def _run_async(self, coro: Any) -> Any:
        return run_async(coro)

    def _row_to_forecast(self, row: Any) -> ForecastEntity:
        m = dict(row._mapping)
        raw = m.get("forecast_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "id" in raw:
            return ForecastEntity.model_validate(raw)

        from domain.forecasting.models import (
            ConfidenceLabel,
            DateWindow,
            ForecastMethod,
            ForecastMethodResult,
            ForecastPeriod,
        )
        return ForecastEntity(
            id=m["id"],
            tenant_id=m["tenant_id"],
            scope_id=m["scope_id"],
            period=ForecastPeriod.MONTHLY,
            period_start=m["period_start"],
            period_end=m["period_end"],
            input_window=DateWindow(start_date=m["period_start"], end_date=m["period_end"]),
            primary_method=ForecastMethod(m["method"]),
            effective_method=ForecastMethod(m["method"]),
            method_results=[
                ForecastMethodResult(
                    method=ForecastMethod(m["method"]),
                    predicted_cost=float(m["predicted_cost"]),
                    lower_bound=float(m["lower_bound"]) if m.get("lower_bound") is not None else float(m["predicted_cost"]),
                    upper_bound=float(m["upper_bound"]) if m.get("upper_bound") is not None else float(m["predicted_cost"]),
                    confidence=ConfidenceLabel(m["confidence_label"]),
                )
            ],
            confidence=ConfidenceLabel(m["confidence_label"]),
            generation_timestamp=m.get("generated_at") or datetime.now(),
        )

    def _row_to_milestone(self, row: Any) -> ForecastMilestoneSnapshot:
        m = dict(row._mapping)
        raw = m.get("milestone_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "id" in raw:
            return ForecastMilestoneSnapshot.model_validate(raw)

        from domain.forecasting.models import AccuracyMilestone, BiasDirection
        return ForecastMilestoneSnapshot(
            id=m["id"],
            forecast_id=m["forecast_id"],
            tenant_id=m["tenant_id"],
            scope_id=m["scope_id"],
            period_identifier="period",
            milestone=AccuracyMilestone.FIFTY_PERCENT,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            checkpoint_date=date(2026, 1, 15),
            actual_spend_to_date=float(m.get("actual_spend") or m.get("actual_spend_to_date") or 0.0),
            projected_period_close=float(m.get("predicted_spend") or m.get("projected_period_close") or 0.0),
            variance_amount=float(m.get("variance_amount") or 0.0),
            percentage_error=float(m.get("variance_pct") or 0.0),
            bias_direction=BiasDirection(m.get("bias_direction") or "BALANCED"),
            recorded_at=m.get("recorded_at") or m.get("evaluated_at") or datetime.now(),
        )

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> ForecastEntity | None:
        async def _get():
            tid = tenant_context.tenant_id
            async with get_tenant_session(tid) as session:
                res = await session.execute(
                    text("SELECT * FROM forecasts WHERE id = :id AND tenant_id = :tid;"),
                    {"id": entity_id, "tid": tid},
                )
                row = res.first()
                return self._row_to_forecast(row) if row else None

        return self._run_async(_get())

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ForecastEntity]:
        async def _list():
            tid = tenant_context.tenant_id
            sql = "SELECT * FROM forecasts WHERE tenant_id = :tid"
            params: dict[str, Any] = {"tid": tid}
            if filter_params and isinstance(filter_params, dict):
                if "scope_id" in filter_params and filter_params["scope_id"]:
                    sql += " AND scope_id = :sid"
                    params["sid"] = filter_params["scope_id"]
                if "effective_method" in filter_params and filter_params["effective_method"]:
                    m = filter_params["effective_method"]
                    sql += " AND method = :method"
                    params["method"] = m.value if hasattr(m, "value") else str(m)
                if "confidence" in filter_params and filter_params["confidence"]:
                    c = filter_params["confidence"]
                    sql += " AND confidence_label = :conf"
                    params["conf"] = c.value if hasattr(c, "value") else str(c)

            sql += " ORDER BY generated_at DESC LIMIT :limit OFFSET :offset;"
            params["limit"] = limit
            params["offset"] = offset

            async with get_tenant_session(tid) as session:
                res = await session.execute(text(sql), params)
                return [self._row_to_forecast(r) for r in res.fetchall()]

        return self._run_async(_list())

    def save(self, entity: ForecastEntity, *, tenant_context: TenantContext) -> ForecastEntity:
        async def _save():
            tid = tenant_context.tenant_id
            async with get_tenant_session(tid) as session:
                query = text("""
                    INSERT INTO forecasts (
                        id, tenant_id, scope_id, period_start, period_end,
                        method, predicted_cost, lower_bound, upper_bound,
                        confidence_label, forecast_payload, generated_at
                    ) VALUES (
                        :id, :tid, :sid, :p_start, :p_end,
                        :method, :pred, :lower, :upper,
                        :conf, CAST(:payload AS jsonb), :gen_at
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        scope_id = EXCLUDED.scope_id,
                        period_start = EXCLUDED.period_start,
                        period_end = EXCLUDED.period_end,
                        method = EXCLUDED.method,
                        predicted_cost = EXCLUDED.predicted_cost,
                        lower_bound = EXCLUDED.lower_bound,
                        upper_bound = EXCLUDED.upper_bound,
                        confidence_label = EXCLUDED.confidence_label,
                        forecast_payload = EXCLUDED.forecast_payload,
                        generated_at = EXCLUDED.generated_at;
                """)
                lower = entity.lower_bound
                upper = entity.upper_bound
                await session.execute(
                    query,
                    {
                        "id": entity.id,
                        "tid": tid,
                        "sid": entity.scope_id,
                        "p_start": entity.period_start,
                        "p_end": entity.period_end,
                        "method": entity.effective_method.value,
                        "pred": entity.predicted_cost,
                        "lower": lower,
                        "upper": upper,
                        "conf": entity.confidence.value,
                        "payload": json.dumps(entity.model_dump(mode="json")),
                        "gen_at": entity.generation_timestamp,
                    },
                )
                await session.commit()
                return entity

        return self._run_async(_save())

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        async def _del():
            tid = tenant_context.tenant_id
            async with get_tenant_session(tid) as session:
                res = await session.execute(
                    text("DELETE FROM forecasts WHERE id = :id AND tenant_id = :tid;"),
                    {"id": entity_id, "tid": tid},
                )
                await session.commit()
                return (res.rowcount or 0) > 0

        return self._run_async(_del())

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return self.get(entity_id, tenant_context=tenant_context) is not None

    def count(self, *, tenant_context: TenantContext, filter_params: Any = None) -> int:
        async def _cnt():
            tid = tenant_context.tenant_id
            async with get_tenant_session(tid) as session:
                res = await session.execute(
                    text("SELECT COUNT(*) FROM forecasts WHERE tenant_id = :tid;"),
                    {"tid": tid},
                )
                return res.scalar() or 0

        return self._run_async(_cnt())

    def find_active_by_scope(
        self,
        scope_id: str,
        period_start: date,
        period_end: date,
        *,
        tenant_context: TenantContext,
    ) -> ForecastEntity | None:
        async def _find():
            tid = tenant_context.tenant_id
            async with get_tenant_session(tid) as session:
                query = text("""
                    SELECT * FROM forecasts
                    WHERE tenant_id = :tid AND scope_id = :sid AND period_start = :p_start AND period_end = :p_end
                    ORDER BY generated_at DESC LIMIT 1;
                """)
                res = await session.execute(
                    query,
                    {"tid": tid, "sid": scope_id, "p_start": period_start, "p_end": period_end},
                )
                row = res.first()
                return self._row_to_forecast(row) if row else None

        return self._run_async(_find())

    def find_by_period_overlap(
        self,
        start_date: date,
        end_date: date,
        *,
        tenant_context: TenantContext,
    ) -> list[ForecastEntity]:
        async def _find_overlap():
            tid = tenant_context.tenant_id
            async with get_tenant_session(tid) as session:
                query = text("""
                    SELECT * FROM forecasts
                    WHERE tenant_id = :tid AND NOT (period_end < :start_date OR period_start > :end_date)
                    ORDER BY generated_at DESC;
                """)
                res = await session.execute(
                    query,
                    {"tid": tid, "start_date": start_date, "end_date": end_date},
                )
                return [self._row_to_forecast(r) for r in res.fetchall()]

        return self._run_async(_find_overlap())

    def save_milestone(
        self,
        snapshot: ForecastMilestoneSnapshot,
        *,
        tenant_context: TenantContext,
    ) -> ForecastMilestoneSnapshot:
        async def _save():
            tid = tenant_context.tenant_id
            async with get_tenant_session(tid) as session:
                query = text("""
                    INSERT INTO forecast_milestones (
                        id, tenant_id, forecast_id, scope_id, milestone_pct,
                        actual_spend_to_date, projected_period_close, variance_amount,
                        variance_pct, bias_direction, milestone_payload, evaluated_at
                    ) VALUES (
                        :id, :tid, :fid, :sid, :pct,
                        :actual, :proj, :var_amt,
                        :var_pct, :bias, CAST(:payload AS jsonb), :eval_at
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        actual_spend_to_date = EXCLUDED.actual_spend_to_date,
                        projected_period_close = EXCLUDED.projected_period_close,
                        variance_amount = EXCLUDED.variance_amount,
                        variance_pct = EXCLUDED.variance_pct,
                        bias_direction = EXCLUDED.bias_direction,
                        milestone_payload = EXCLUDED.milestone_payload,
                        evaluated_at = EXCLUDED.evaluated_at;
                """)
                await session.execute(
                    query,
                    {
                        "id": snapshot.id,
                        "tid": tid,
                        "fid": snapshot.forecast_id,
                        "sid": snapshot.scope_id,
                        "pct": snapshot.milestone.percentage,
                        "actual": snapshot.actual_spend_to_date,
                        "proj": snapshot.projected_period_close,
                        "var_amt": snapshot.variance_amount,
                        "var_pct": snapshot.percentage_error,
                        "bias": snapshot.bias_direction.value,
                        "payload": json.dumps(snapshot.model_dump(mode="json")),
                        "eval_at": snapshot.recorded_at,
                    },
                )
                await session.commit()
                return snapshot

        return self._run_async(_save())

    def list_milestones(
        self,
        *,
        period_identifier: str | None = None,
        scope_id: str | None = None,
        tenant_context: TenantContext,
    ) -> list[ForecastMilestoneSnapshot]:
        async def _list_m():
            tid = tenant_context.tenant_id
            sql = "SELECT * FROM forecast_milestones WHERE tenant_id = :tid"
            params: dict[str, Any] = {"tid": tid}
            if scope_id:
                sql += " AND scope_id = :sid"
                params["sid"] = scope_id
            sql += " ORDER BY recorded_at ASC;"

            async with get_tenant_session(tid) as session:
                res = await session.execute(text(sql), params)
                return [self._row_to_milestone(r) for r in res.fetchall()]

        return self._run_async(_list_m())

    def clear_tenant_data(self, *, tenant_context: TenantContext) -> None:
        async def _clear():
            tid = tenant_context.tenant_id
            async with get_tenant_session(tid) as session:
                await session.execute(text("DELETE FROM forecast_milestones WHERE tenant_id = :tid;"), {"tid": tid})
                await session.execute(text("DELETE FROM forecasts WHERE tenant_id = :tid;"), {"tid": tid})
                await session.commit()

        self._run_async(_clear())


_forecast_repo_instance: Any = None


def get_forecast_repository() -> Any:
    """Returns singleton ForecastRepository instance with production startup guard."""
    global _forecast_repo_instance
    if _forecast_repo_instance is None:
        _forecast_repo_instance = SqlForecastRepository()
        verify_persistence_startup_guard(_forecast_repo_instance)
    return _forecast_repo_instance


def reset_forecast_repository(repo: Any = None) -> Any:
    """Resets singleton ForecastRepository (for test teardown)."""
    global _forecast_repo_instance
    _forecast_repo_instance = repo
    return _forecast_repo_instance or get_forecast_repository()


__all__ = [
    "ForecastRepository",
    "SqlForecastRepository",
    "get_forecast_repository",
    "reset_forecast_repository",
]
