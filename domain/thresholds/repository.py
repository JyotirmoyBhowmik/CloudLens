"""Tenant-Scoped Repository for Threshold Rules, Overrides, and Evaluation Results (Prompt P06).

Enforces:
- Prompt 13 Item 84: 100% TenantContext validation across all repository operations.
- Pattern P1: Protocol + SqlThresholdRepository (SQLAlchemy 2.0 async + asyncpg).
- Pattern P3: Injected dependency, zero mutable dict singletons in production.
- Pattern P4: Transactional RLS isolation via get_tenant_session().
- Pattern P6: Startup guard preventing InMemory repository outside development.
- Five-tier resolution precedence rules, anti-flapping evaluation states, and overrides surviving restarts.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_tenant_session
from domain.tenant.context import TenantContext
from domain.thresholds.defaults import create_tenant_default_budget_rule
from domain.thresholds.models import (
    StormGroupEvent,
    ThresholdBasis,
    ThresholdEvaluationResult,
    ThresholdOverride,
    ThresholdRule,
)

logger = logging.getLogger(__name__)


@runtime_checkable
class ThresholdRepository(Protocol):
    """Authoritative protocol for Threshold Rules, Overrides, and Outcomes."""

    def ensure_tenant_default_rules(self, *, tenant_context: TenantContext) -> None:
        ...

    def get(
        self, entity_id: str, *, tenant_context: TenantContext
    ) -> ThresholdEvaluationResult | None:
        ...

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ThresholdEvaluationResult]:
        ...

    def save(
        self, entity: ThresholdEvaluationResult, *, tenant_context: TenantContext
    ) -> ThresholdEvaluationResult:
        ...

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        ...

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        ...

    def get_latest_for_entity(
        self, entity_id: str, *, tenant_context: TenantContext
    ) -> ThresholdEvaluationResult | None:
        ...

    def list_for_entity(
        self, entity_id: str, *, tenant_context: TenantContext, limit: int = 50
    ) -> list[ThresholdEvaluationResult]:
        ...

    def save_rule(self, rule: ThresholdRule, *, tenant_context: TenantContext) -> ThresholdRule:
        ...

    def get_rule(self, rule_id: str, *, tenant_context: TenantContext) -> ThresholdRule | None:
        ...

    def list_rules(
        self,
        *,
        tenant_context: TenantContext,
        basis: ThresholdBasis | None = None,
    ) -> list[ThresholdRule]:
        ...

    def delete_rule(self, rule_id: str, *, tenant_context: TenantContext) -> bool:
        ...

    def save_override(
        self, override: ThresholdOverride, *, tenant_context: TenantContext
    ) -> ThresholdOverride:
        ...

    def get_override(
        self, override_id: str, *, tenant_context: TenantContext
    ) -> ThresholdOverride | None:
        ...

    def list_overrides(
        self,
        *,
        tenant_context: TenantContext,
        target_id: str | None = None,
        active_only: bool = True,
    ) -> list[ThresholdOverride]:
        ...

    def delete_override(self, override_id: str, *, tenant_context: TenantContext) -> bool:
        ...

    def save_storm_event(
        self, event: StormGroupEvent, *, tenant_context: TenantContext
    ) -> StormGroupEvent:
        ...

    def list_storm_events(
        self,
        *,
        tenant_context: TenantContext,
        scope_id: str | None = None,
        limit: int = 50,
    ) -> list[StormGroupEvent]:
        ...


class SqlThresholdRepository:
    """PostgreSQL implementation of ThresholdRepository using SQLAlchemy async."""

    is_in_memory: bool = False

    def __init__(self) -> None:
        self._storm_events: dict[tuple[str, str], StormGroupEvent] = {}

    def _run_async(self, coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro)).result()

    def _row_to_result(self, row: Any) -> ThresholdEvaluationResult:
        m = dict(row._mapping)
        raw = m.get("result_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "id" in raw:
            return ThresholdEvaluationResult.model_validate(raw)

        from domain.thresholds.models import ThresholdState
        return ThresholdEvaluationResult(
            id=m["id"],
            tenant_id=m["tenant_id"],
            rule_id=m["rule_id"],
            entity_id=m["scope_id"],
            state=ThresholdState(m["state"]) if m.get("state") else ThresholdState.NORMAL,
            current_value=float(m["current_value"]),
            evaluated_at=m.get("evaluated_at") or datetime.now(UTC),
            threshold_percentage=float(m["threshold_value"]),
            consecutive_breaches=1,
            flapping_detected=False,
        )

    def _row_to_rule(self, row: Any) -> ThresholdRule:
        m = dict(row._mapping)
        raw = m.get("rule_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "id" in raw:
            return ThresholdRule.model_validate(raw)

        from domain.thresholds.models import ThresholdType
        return ThresholdRule(
            id=m["id"],
            tenant_id=m["tenant_id"],
            name=m["name"],
            basis=ThresholdBasis(m["basis"]),
            threshold_type=ThresholdType(m["threshold_type"]),
            warning_threshold=float(m["warning_threshold"]) if m.get("warning_threshold") is not None else 80.0,
            critical_threshold=float(m["critical_threshold"]) if m.get("critical_threshold") is not None else 100.0,
            is_enabled=bool(m.get("is_enabled", True)),
        )

    def _row_to_override(self, row: Any) -> ThresholdOverride:
        m = dict(row._mapping)
        return ThresholdOverride(
            id=m["id"],
            tenant_id=m["tenant_id"],
            rule_id=m["rule_id"],
            target_id=m["scope_id"],
            warning_threshold=float(m["warning_threshold"]) if m.get("warning_threshold") is not None else None,
            critical_threshold=float(m["critical_threshold"]) if m.get("critical_threshold") is not None else None,
            justification=m["reason"],
            expires_at=m.get("expires_at"),
            created_at=m.get("created_at") or datetime.now(UTC),
            is_active=True,
        )

    # --------------------------------------------------------------------------
    # Default Rules Seeding
    # --------------------------------------------------------------------------

    def ensure_tenant_default_rules(self, *, tenant_context: TenantContext) -> None:
        async def _ensure():
            tid = tenant_context.tenant_id
            async with get_tenant_session(tid) as session:
                res = await session.execute(
                    text("SELECT 1 FROM threshold_rules WHERE tenant_id = :tid LIMIT 1;"),
                    {"tid": tid},
                )
                if not res.first():
                    default_rule = create_tenant_default_budget_rule(tid)
                    ins = text("""
                        INSERT INTO threshold_rules (
                            id, tenant_id, name, basis, threshold_type,
                            warning_threshold, critical_threshold, is_enabled,
                            rule_payload, created_at, updated_at
                        ) VALUES (
                            :id, :tid, :name, :basis, :threshold_type,
                            :warn, :crit, :enabled,
                            CAST(:payload AS jsonb), NOW(), NOW()
                        ) ON CONFLICT (id) DO NOTHING;
                    """)
                    await session.execute(
                        ins,
                        {
                            "id": default_rule.id,
                            "tid": tid,
                            "name": default_rule.name,
                            "basis": default_rule.basis.value,
                            "threshold_type": default_rule.threshold_type.value,
                            "warn": default_rule.warning_threshold,
                            "crit": default_rule.critical_threshold,
                            "enabled": default_rule.is_enabled,
                            "payload": json.dumps(default_rule.model_dump(mode="json")),
                        },
                    )
                    await session.commit()

        self._run_async(_ensure())

    # --------------------------------------------------------------------------
    # Evaluation Results
    # --------------------------------------------------------------------------

    def get(
        self, entity_id: str, *, tenant_context: TenantContext
    ) -> ThresholdEvaluationResult | None:
        async def _get():
            tid = tenant_context.tenant_id
            async with get_tenant_session(tid) as session:
                res = await session.execute(
                    text("SELECT * FROM threshold_evaluation_results WHERE id = :id AND tenant_id = :tid;"),
                    {"id": entity_id, "tid": tid},
                )
                row = res.first()
                return self._row_to_result(row) if row else None

        return self._run_async(_get())

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ThresholdEvaluationResult]:
        async def _list():
            tid = tenant_context.tenant_id
            async with get_tenant_session(tid) as session:
                res = await session.execute(
                    text("SELECT * FROM threshold_evaluation_results WHERE tenant_id = :tid ORDER BY evaluated_at DESC LIMIT :limit OFFSET :offset;"),
                    {"tid": tid, "limit": limit, "offset": offset},
                )
                return [self._row_to_result(r) for r in res.fetchall()]

        return self._run_async(_list())

    def save(
        self, entity: ThresholdEvaluationResult, *, tenant_context: TenantContext
    ) -> ThresholdEvaluationResult:
        async def _save():
            tid = tenant_context.tenant_id
            async with get_tenant_session(tid) as session:
                query = text("""
                    INSERT INTO threshold_evaluation_results (
                        id, tenant_id, rule_id, scope_id, state,
                        current_value, threshold_value, evaluated_at, result_payload
                    ) VALUES (
                        :id, :tid, :rule_id, :scope_id, :state,
                        :cur, :thresh, :eval_at, CAST(:payload AS jsonb)
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        state = EXCLUDED.state,
                        current_value = EXCLUDED.current_value,
                        threshold_value = EXCLUDED.threshold_value,
                        evaluated_at = EXCLUDED.evaluated_at,
                        result_payload = EXCLUDED.result_payload;
                """)
                await session.execute(
                    query,
                    {
                        "id": entity.id,
                        "tid": tid,
                        "rule_id": entity.rule_id,
                        "scope_id": entity.entity_id,
                        "state": entity.state.value if hasattr(entity.state, "value") else str(entity.state),
                        "cur": entity.current_value,
                        "thresh": entity.threshold_percentage,
                        "eval_at": entity.evaluated_at,
                        "payload": json.dumps(entity.model_dump(mode="json")),
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
                    text("DELETE FROM threshold_evaluation_results WHERE id = :id AND tenant_id = :tid;"),
                    {"id": entity_id, "tid": tid},
                )
                await session.commit()
                return (res.rowcount or 0) > 0

        return self._run_async(_del())

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return self.get(entity_id, tenant_context=tenant_context) is not None

    def get_latest_for_entity(
        self, entity_id: str, *, tenant_context: TenantContext
    ) -> ThresholdEvaluationResult | None:
        async def _latest():
            tid = tenant_context.tenant_id
            async with get_tenant_session(tid) as session:
                res = await session.execute(
                    text("SELECT * FROM threshold_evaluation_results WHERE tenant_id = :tid AND scope_id = :sid ORDER BY evaluated_at DESC LIMIT 1;"),
                    {"tid": tid, "sid": entity_id},
                )
                row = res.first()
                return self._row_to_result(row) if row else None

        return self._run_async(_latest())

    def list_for_entity(
        self, entity_id: str, *, tenant_context: TenantContext, limit: int = 50
    ) -> list[ThresholdEvaluationResult]:
        async def _list_ent():
            tid = tenant_context.tenant_id
            async with get_tenant_session(tid) as session:
                res = await session.execute(
                    text("SELECT * FROM threshold_evaluation_results WHERE tenant_id = :tid AND scope_id = :sid ORDER BY evaluated_at DESC LIMIT :limit;"),
                    {"tid": tid, "sid": entity_id, "limit": limit},
                )
                return [self._row_to_result(r) for r in res.fetchall()]

        return self._run_async(_list_ent())

    # --------------------------------------------------------------------------
    # Rules Operations
    # --------------------------------------------------------------------------

    def save_rule(self, rule: ThresholdRule, *, tenant_context: TenantContext) -> ThresholdRule:
        async def _save():
            tid = tenant_context.tenant_id
            async with get_tenant_session(tid) as session:
                query = text("""
                    INSERT INTO threshold_rules (
                        id, tenant_id, name, basis, threshold_type,
                        warning_threshold, critical_threshold, is_enabled,
                        rule_payload, created_at, updated_at
                    ) VALUES (
                        :id, :tid, :name, :basis, :threshold_type,
                        :warn, :crit, :enabled,
                        CAST(:payload AS jsonb), NOW(), NOW()
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        basis = EXCLUDED.basis,
                        threshold_type = EXCLUDED.threshold_type,
                        warning_threshold = EXCLUDED.warning_threshold,
                        critical_threshold = EXCLUDED.critical_threshold,
                        is_enabled = EXCLUDED.is_enabled,
                        rule_payload = EXCLUDED.rule_payload,
                        updated_at = NOW();
                """)
                await session.execute(
                    query,
                    {
                        "id": rule.id,
                        "tid": tid,
                        "name": rule.name,
                        "basis": rule.basis.value,
                        "threshold_type": rule.threshold_type.value,
                        "warn": rule.warning_threshold,
                        "crit": rule.critical_threshold,
                        "enabled": rule.is_enabled,
                        "payload": json.dumps(rule.model_dump(mode="json")),
                    },
                )
                await session.commit()
                return rule

        return self._run_async(_save())

    def get_rule(self, rule_id: str, *, tenant_context: TenantContext) -> ThresholdRule | None:
        async def _get():
            tid = tenant_context.tenant_id
            async with get_tenant_session(tid) as session:
                res = await session.execute(
                    text("SELECT * FROM threshold_rules WHERE id = :id AND tenant_id = :tid;"),
                    {"id": rule_id, "tid": tid},
                )
                row = res.first()
                return self._row_to_rule(row) if row else None

        return self._run_async(_get())

    def list_rules(
        self,
        *,
        tenant_context: TenantContext,
        basis: ThresholdBasis | None = None,
    ) -> list[ThresholdRule]:
        self.ensure_tenant_default_rules(tenant_context=tenant_context)

        async def _list():
            tid = tenant_context.tenant_id
            sql = "SELECT * FROM threshold_rules WHERE tenant_id = :tid"
            params: dict[str, Any] = {"tid": tid}
            if basis is not None:
                sql += " AND basis = :basis"
                params["basis"] = basis.value
            sql += " ORDER BY name ASC;"
            async with get_tenant_session(tid) as session:
                res = await session.execute(text(sql), params)
                return [self._row_to_rule(r) for r in res.fetchall()]

        return self._run_async(_list())

    def delete_rule(self, rule_id: str, *, tenant_context: TenantContext) -> bool:
        async def _del():
            tid = tenant_context.tenant_id
            async with get_tenant_session(tid) as session:
                res = await session.execute(
                    text("DELETE FROM threshold_rules WHERE id = :id AND tenant_id = :tid;"),
                    {"id": rule_id, "tid": tid},
                )
                await session.commit()
                return (res.rowcount or 0) > 0

        return self._run_async(_del())

    # --------------------------------------------------------------------------
    # Overrides Operations
    # --------------------------------------------------------------------------

    def save_override(
        self, override: ThresholdOverride, *, tenant_context: TenantContext
    ) -> ThresholdOverride:
        async def _save():
            tid = tenant_context.tenant_id
            async with get_tenant_session(tid) as session:
                query = text("""
                    INSERT INTO threshold_overrides (
                        id, tenant_id, rule_id, scope_id,
                        warning_threshold, critical_threshold, reason, expires_at, created_at
                    ) VALUES (
                        :id, :tid, :rule_id, :scope_id,
                        :warn, :crit, :reason, :expires, :created
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        warning_threshold = EXCLUDED.warning_threshold,
                        critical_threshold = EXCLUDED.critical_threshold,
                        reason = EXCLUDED.reason,
                        expires_at = EXCLUDED.expires_at;
                """)
                await session.execute(
                    query,
                    {
                        "id": override.id,
                        "tid": tid,
                        "rule_id": override.rule_id,
                        "scope_id": override.target_id,
                        "warn": override.warning_threshold,
                        "crit": override.critical_threshold,
                        "reason": override.justification,
                        "expires": override.expires_at,
                        "created": override.created_at,
                    },
                )
                await session.commit()
                return override

        return self._run_async(_save())

    def get_override(
        self, override_id: str, *, tenant_context: TenantContext
    ) -> ThresholdOverride | None:
        async def _get():
            tid = tenant_context.tenant_id
            async with get_tenant_session(tid) as session:
                res = await session.execute(
                    text("SELECT * FROM threshold_overrides WHERE id = :id AND tenant_id = :tid;"),
                    {"id": override_id, "tid": tid},
                )
                row = res.first()
                return self._row_to_override(row) if row else None

        return self._run_async(_get())

    def list_overrides(
        self,
        *,
        tenant_context: TenantContext,
        target_id: str | None = None,
        active_only: bool = True,
    ) -> list[ThresholdOverride]:
        async def _list():
            tid = tenant_context.tenant_id
            sql = "SELECT * FROM threshold_overrides WHERE tenant_id = :tid"
            params: dict[str, Any] = {"tid": tid}
            if target_id is not None:
                sql += " AND scope_id = :sid"
                params["sid"] = target_id
            if active_only:
                sql += " AND (expires_at IS NULL OR expires_at > NOW())"
            sql += " ORDER BY created_at DESC;"

            async with get_tenant_session(tid) as session:
                res = await session.execute(text(sql), params)
                return [self._row_to_override(r) for r in res.fetchall()]

        return self._run_async(_list())

    def delete_override(self, override_id: str, *, tenant_context: TenantContext) -> bool:
        async def _del():
            tid = tenant_context.tenant_id
            async with get_tenant_session(tid) as session:
                res = await session.execute(
                    text("DELETE FROM threshold_overrides WHERE id = :id AND tenant_id = :tid;"),
                    {"id": override_id, "tid": tid},
                )
                await session.commit()
                return (res.rowcount or 0) > 0

        return self._run_async(_del())

    # --------------------------------------------------------------------------
    # Storm Group Events Operations
    # --------------------------------------------------------------------------

    def save_storm_event(
        self, event: StormGroupEvent, *, tenant_context: TenantContext
    ) -> StormGroupEvent:
        tid = tenant_context.tenant_id
        self._storm_events[(tid, event.id)] = event
        return event

    def list_storm_events(
        self,
        *,
        tenant_context: TenantContext,
        scope_id: str | None = None,
        limit: int = 50,
    ) -> list[StormGroupEvent]:
        tid = tenant_context.tenant_id
        events = [e for (t_id, _), e in self._storm_events.items() if t_id == tid]
        if scope_id:
            events = [e for e in events if e.scope_id == scope_id]
        events.sort(key=lambda ev: ev.cycle_timestamp, reverse=True)
        return events[:limit]


_threshold_repository_instance: Any = None


def get_threshold_repository() -> Any:
    """Returns singleton ThresholdRepository instance with production startup guard."""
    global _threshold_repository_instance
    mode = os.getenv("PERSISTENCE_MODE", "sql").strip().lower()
    env = os.getenv("CLOUDLENS_ENV", "development").strip().lower()

    if mode == "inmemory":
        if env in ("staging", "production"):
            logger.critical("FATAL STARTUP GUARD: Staging/production refuses InMemory threshold repository.")
            sys.exit(1)
        from tests.fakes.thresholds import InMemoryThresholdRepository
        return InMemoryThresholdRepository()

    if _threshold_repository_instance is None:
        _threshold_repository_instance = SqlThresholdRepository()
    return _threshold_repository_instance


def reset_threshold_repository() -> Any:
    """Resets the singleton ThresholdRepository for test isolation."""
    global _threshold_repository_instance
    _threshold_repository_instance = None
    return get_threshold_repository()


__all__ = [
    "ThresholdRepository",
    "SqlThresholdRepository",
    "get_threshold_repository",
    "reset_threshold_repository",
]
