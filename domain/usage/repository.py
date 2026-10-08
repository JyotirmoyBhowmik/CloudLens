"""Tenant-Isolated Repository for Usage Telemetry, Overrides, and Expectations (Prompt 25, Prompt P07).

Enforces:
- Prompt 13 Item 84: Mandatory TenantContext on every public repository method.
- Prompt 25: Storage of pre-aggregated usage facts, explicit gaps, and labeled interpolations via PostgreSQL.
- Protocol + SqlUsageRepository per docs/persistence-pattern.md.
- Production startup guard verifying no in-memory repositories in staging/production.
"""

from __future__ import annotations

import builtins
import json
import logging
import threading
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_tenant_session, run_async, verify_persistence_startup_guard
from domain.tenant.context import TenantContext
from domain.usage.models import (
    ExpectationLevel,
    MonitoringTypeOverride,
    PreAggregatedUsageRecord,
    UsageExpectation,
    UsageQueryFilter,
)

logger = logging.getLogger(__name__)


@runtime_checkable
class UsageRepository(Protocol):
    """Authoritative repository protocol for usage facts, overrides, expectations."""

    def save_usage_record(
        self, record: PreAggregatedUsageRecord, *, tenant_context: TenantContext
    ) -> None: ...
    def save(
        self, entity: PreAggregatedUsageRecord, *, tenant_context: TenantContext
    ) -> PreAggregatedUsageRecord: ...
    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool: ...
    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool: ...
    def save_usage_records(
        self, records: builtins.list[PreAggregatedUsageRecord], *, tenant_context: TenantContext
    ) -> int: ...
    def get(
        self, entity_id: str, *, tenant_context: TenantContext
    ) -> PreAggregatedUsageRecord | None: ...
    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[PreAggregatedUsageRecord]: ...
    def query_metrics(
        self, filter_params: UsageQueryFilter, *, tenant_context: TenantContext
    ) -> builtins.list[PreAggregatedUsageRecord]: ...
    def save_override(
        self, override: MonitoringTypeOverride, *, tenant_context: TenantContext
    ) -> None: ...
    def get_override(
        self, resource_id: str, *, tenant_context: TenantContext
    ) -> MonitoringTypeOverride | None: ...
    def list_overrides(
        self, *, tenant_context: TenantContext
    ) -> builtins.list[MonitoringTypeOverride]: ...
    def save_expectation(
        self, expectation: UsageExpectation, *, tenant_context: TenantContext
    ) -> None: ...
    def get_expectation(
        self, expectation_id: str, *, tenant_context: TenantContext
    ) -> UsageExpectation | None: ...
    def list_expectations(
        self,
        *,
        tenant_context: TenantContext,
        level: ExpectationLevel | None = None,
        target_id: str | None = None,
    ) -> builtins.list[UsageExpectation]: ...
    def delete_expectation(self, expectation_id: str, *, tenant_context: TenantContext) -> bool: ...


class SqlUsageRepository:
    """PostgreSQL production implementation for usage fact partitioned tables and RLS auxiliary tables."""

    is_in_memory: bool = False

    def _run_async(self, coro: Any) -> Any:
        return run_async(coro)

    def _row_to_usage(self, row: Any) -> PreAggregatedUsageRecord:
        m = dict(row._mapping)
        raw = m.get("provider_native")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "id" in raw:
            return PreAggregatedUsageRecord.model_validate(raw)
        return PreAggregatedUsageRecord.model_validate(m)

    def _row_to_override(self, row: Any) -> MonitoringTypeOverride:
        m = dict(row._mapping)
        raw = m.get("override_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "resource_id" in raw:
            return MonitoringTypeOverride.model_validate(raw)
        return MonitoringTypeOverride.model_validate(m)

    def _row_to_expectation(self, row: Any) -> UsageExpectation:
        m = dict(row._mapping)
        raw = m.get("expectation_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "id" in raw:
            return UsageExpectation.model_validate(raw)
        return UsageExpectation.model_validate(m)

    # 1. PreAggregatedUsageRecord
    async def save_usage_record_async(
        self, record: PreAggregatedUsageRecord, *, tenant_context: TenantContext
    ) -> None:
        if record.tenant_id != tenant_context.tenant_id:
            raise ValueError(
                f"Usage record tenant '{record.tenant_id}' mismatches context '{tenant_context.tenant_id}'."
            )
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            qty_val = None
            qty_state = "UNKNOWN"
            if hasattr(record.usage_quantity, "value"):
                qty_val = float(record.usage_quantity.value) if record.usage_quantity.value is not None else None
            elif isinstance(record.usage_quantity, (int, float)):
                qty_val = float(record.usage_quantity)
            if hasattr(record.usage_quantity, "state"):
                qty_state = str(record.usage_quantity.state)

            query = text("""
                INSERT INTO usage_fact (
                    interval_start, tenant_id, id, scope_id, resource_id, interval_end,
                    metric_name, usage_quantity, usage_quantity_state, usage_unit,
                    provider_native, source_provenance, created_at
                ) VALUES (
                    :start, :tid, :id, :sid, :rid, :end,
                    :metric, :qty, :qty_st, :unit,
                    CAST(:payload AS JSONB), '{}'::jsonb, NOW()
                )
                ON CONFLICT (interval_start, tenant_id, id) DO UPDATE SET
                    interval_end = EXCLUDED.interval_end,
                    usage_quantity = EXCLUDED.usage_quantity,
                    usage_quantity_state = EXCLUDED.usage_quantity_state,
                    provider_native = EXCLUDED.provider_native;
            """)
            await sess.execute(
                query,
                {
                    "start": record.interval_start,
                    "tid": tenant_context.tenant_id,
                    "id": record.id,
                    "sid": record.scope_id,
                    "rid": record.resource_id,
                    "end": record.interval_end,
                    "metric": record.metric_name,
                    "qty": qty_val,
                    "qty_st": qty_state,
                    "unit": record.usage_unit,
                    "payload": json.dumps(record.model_dump(mode="json")),
                },
            )
            await sess.commit()

    def save_usage_record(
        self, record: PreAggregatedUsageRecord, *, tenant_context: TenantContext
    ) -> None:
        self._run_async(self.save_usage_record_async(record, tenant_context=tenant_context))

    def save(
        self, entity: PreAggregatedUsageRecord, *, tenant_context: TenantContext
    ) -> PreAggregatedUsageRecord:
        self.save_usage_record(entity, tenant_context=tenant_context)
        return entity

    async def delete_async(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("DELETE FROM usage_fact WHERE id = :id AND tenant_id = :tid;"),
                {"id": entity_id, "tid": tenant_context.tenant_id},
            )
            await sess.commit()
            return (res.rowcount or 0) > 0

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return self._run_async(self.delete_async(entity_id, tenant_context=tenant_context))

    async def exists_async(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT 1 FROM usage_fact WHERE id = :id AND tenant_id = :tid LIMIT 1;"),
                {"id": entity_id, "tid": tenant_context.tenant_id},
            )
            return res.fetchone() is not None

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return self._run_async(self.exists_async(entity_id, tenant_context=tenant_context))

    def save_usage_records(
        self, records: builtins.list[PreAggregatedUsageRecord], *, tenant_context: TenantContext
    ) -> int:
        count = 0
        for rec in records:
            self.save_usage_record(rec, tenant_context=tenant_context)
            count += 1
        return count

    async def get_async(
        self, entity_id: str, *, tenant_context: TenantContext
    ) -> PreAggregatedUsageRecord | None:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT * FROM usage_fact WHERE id = :id AND tenant_id = :tid LIMIT 1;"),
                {"id": entity_id, "tid": tenant_context.tenant_id},
            )
            row = res.fetchone()
            if not row:
                return None
            return self._row_to_usage(row)

    def get(
        self, entity_id: str, *, tenant_context: TenantContext
    ) -> PreAggregatedUsageRecord | None:
        return self._run_async(self.get_async(entity_id, tenant_context=tenant_context))

    async def list_async(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[PreAggregatedUsageRecord]:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            sql = ["SELECT * FROM usage_fact WHERE tenant_id = :tid"]
            params: dict[str, Any] = {"tid": tenant_context.tenant_id}
            if isinstance(filter_params, dict):
                if "resource_id" in filter_params and filter_params["resource_id"]:
                    sql.append("AND resource_id = :rid")
                    params["rid"] = filter_params["resource_id"]
                if "metric_name" in filter_params and filter_params["metric_name"]:
                    sql.append("AND metric_name = :mname")
                    params["mname"] = filter_params["metric_name"]
            sql.append("ORDER BY interval_start DESC LIMIT :limit OFFSET :offset;")
            params["limit"] = limit
            params["offset"] = offset

            res = await sess.execute(text(" ".join(sql)), params)
            rows = res.fetchall()
            return [self._row_to_usage(r) for r in rows]

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[PreAggregatedUsageRecord]:
        return self._run_async(
            self.list_async(tenant_context=tenant_context, filter_params=filter_params, limit=limit, offset=offset)
        )

    async def query_metrics_async(
        self, filter_params: UsageQueryFilter, *, tenant_context: TenantContext
    ) -> builtins.list[PreAggregatedUsageRecord]:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            sql = ["SELECT * FROM usage_fact WHERE tenant_id = :tid"]
            params: dict[str, Any] = {"tid": tenant_context.tenant_id}

            if filter_params.resource_id:
                sql.append("AND resource_id = :rid")
                params["rid"] = filter_params.resource_id
            if filter_params.scope_id:
                sql.append("AND scope_id = :sid")
                params["sid"] = filter_params.scope_id
            if filter_params.metric_name:
                sql.append("AND metric_name = :mname")
                params["mname"] = filter_params.metric_name
            if filter_params.interval_start_gte:
                sql.append("AND interval_start >= :sgte")
                params["sgte"] = filter_params.interval_start_gte
            if filter_params.interval_end_lte:
                sql.append("AND interval_end <= :elte")
                params["elte"] = filter_params.interval_end_lte

            sql.append("ORDER BY interval_start ASC LIMIT :limit OFFSET :offset;")
            params["limit"] = filter_params.limit
            params["offset"] = filter_params.offset

            res = await sess.execute(text(" ".join(sql)), params)
            rows = res.fetchall()
            items = [self._row_to_usage(r) for r in rows]
            if not filter_params.include_gaps:
                items = [r for r in items if not r.is_gap]
            return items

    def query_metrics(
        self, filter_params: UsageQueryFilter, *, tenant_context: TenantContext
    ) -> builtins.list[PreAggregatedUsageRecord]:
        return self._run_async(self.query_metrics_async(filter_params, tenant_context=tenant_context))

    # 2. Monitoring Type Overrides
    async def save_override_async(
        self, override: MonitoringTypeOverride, *, tenant_context: TenantContext
    ) -> None:
        if override.tenant_id != tenant_context.tenant_id:
            raise ValueError(
                f"Override tenant '{override.tenant_id}' mismatches context '{tenant_context.tenant_id}'."
            )
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            query = text("""
                INSERT INTO usage_overrides (id, tenant_id, resource_id, override_payload, created_at)
                VALUES (:id, :tid, :rid, CAST(:payload AS JSONB), NOW())
                ON CONFLICT (id) DO UPDATE SET
                    resource_id = EXCLUDED.resource_id,
                    override_payload = EXCLUDED.override_payload;
            """)
            await sess.execute(
                query,
                {
                    "id": getattr(override, "id", f"ovr-{override.resource_id}"),
                    "tid": tenant_context.tenant_id,
                    "rid": override.resource_id,
                    "payload": json.dumps(override.model_dump(mode="json")),
                },
            )
            await sess.commit()

    def save_override(
        self, override: MonitoringTypeOverride, *, tenant_context: TenantContext
    ) -> None:
        self._run_async(self.save_override_async(override, tenant_context=tenant_context))

    async def get_override_async(
        self, resource_id: str, *, tenant_context: TenantContext
    ) -> MonitoringTypeOverride | None:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT * FROM usage_overrides WHERE tenant_id = :tid AND resource_id = :rid LIMIT 1;"),
                {"tid": tenant_context.tenant_id, "rid": resource_id},
            )
            row = res.fetchone()
            if not row:
                return None
            return self._row_to_override(row)

    def get_override(
        self, resource_id: str, *, tenant_context: TenantContext
    ) -> MonitoringTypeOverride | None:
        return self._run_async(self.get_override_async(resource_id, tenant_context=tenant_context))

    async def list_overrides_async(
        self, *, tenant_context: TenantContext
    ) -> builtins.list[MonitoringTypeOverride]:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT * FROM usage_overrides WHERE tenant_id = :tid;"),
                {"tid": tenant_context.tenant_id},
            )
            rows = res.fetchall()
            return [self._row_to_override(r) for r in rows]

    def list_overrides(
        self, *, tenant_context: TenantContext
    ) -> builtins.list[MonitoringTypeOverride]:
        return self._run_async(self.list_overrides_async(tenant_context=tenant_context))

    # 3. Usage Expectations
    async def save_expectation_async(
        self, expectation: UsageExpectation, *, tenant_context: TenantContext
    ) -> None:
        if expectation.tenant_id != tenant_context.tenant_id:
            raise ValueError(
                f"Expectation tenant '{expectation.tenant_id}' mismatches context '{tenant_context.tenant_id}'."
            )
        lvl_val = expectation.level.value if hasattr(expectation.level, "value") else str(expectation.level)
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            query = text("""
                INSERT INTO usage_expectations (id, tenant_id, level, target_id, expectation_payload, created_at)
                VALUES (:id, :tid, :lvl, :tgt, CAST(:payload AS JSONB), NOW())
                ON CONFLICT (id) DO UPDATE SET
                    level = EXCLUDED.level,
                    target_id = EXCLUDED.target_id,
                    expectation_payload = EXCLUDED.expectation_payload;
            """)
            await sess.execute(
                query,
                {
                    "id": expectation.id,
                    "tid": tenant_context.tenant_id,
                    "lvl": lvl_val,
                    "tgt": expectation.target_id,
                    "payload": json.dumps(expectation.model_dump(mode="json")),
                },
            )
            await sess.commit()

    def save_expectation(
        self, expectation: UsageExpectation, *, tenant_context: TenantContext
    ) -> None:
        self._run_async(self.save_expectation_async(expectation, tenant_context=tenant_context))

    async def get_expectation_async(
        self, expectation_id: str, *, tenant_context: TenantContext
    ) -> UsageExpectation | None:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT * FROM usage_expectations WHERE id = :id AND tenant_id = :tid LIMIT 1;"),
                {"id": expectation_id, "tid": tenant_context.tenant_id},
            )
            row = res.fetchone()
            if not row:
                return None
            return self._row_to_expectation(row)

    def get_expectation(
        self, expectation_id: str, *, tenant_context: TenantContext
    ) -> UsageExpectation | None:
        return self._run_async(self.get_expectation_async(expectation_id, tenant_context=tenant_context))

    async def list_expectations_async(
        self,
        *,
        tenant_context: TenantContext,
        level: ExpectationLevel | None = None,
        target_id: str | None = None,
    ) -> builtins.list[UsageExpectation]:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            sql = ["SELECT * FROM usage_expectations WHERE tenant_id = :tid"]
            params: dict[str, Any] = {"tid": tenant_context.tenant_id}
            if level:
                lvl_val = level.value if hasattr(level, "value") else str(level)
                sql.append("AND level = :lvl")
                params["lvl"] = lvl_val
            if target_id:
                sql.append("AND target_id = :tgt")
                params["tgt"] = target_id
            res = await sess.execute(text(" ".join(sql)), params)
            rows = res.fetchall()
            return [self._row_to_expectation(r) for r in rows]

    def list_expectations(
        self,
        *,
        tenant_context: TenantContext,
        level: ExpectationLevel | None = None,
        target_id: str | None = None,
    ) -> builtins.list[UsageExpectation]:
        return self._run_async(self.list_expectations_async(tenant_context=tenant_context, level=level, target_id=target_id))

    async def delete_expectation_async(
        self, expectation_id: str, *, tenant_context: TenantContext
    ) -> bool:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("DELETE FROM usage_expectations WHERE id = :id AND tenant_id = :tid;"),
                {"id": expectation_id, "tid": tenant_context.tenant_id},
            )
            await sess.commit()
            return (res.rowcount or 0) > 0

    def delete_expectation(self, expectation_id: str, *, tenant_context: TenantContext) -> bool:
        return self._run_async(self.delete_expectation_async(expectation_id, tenant_context=tenant_context))


_usage_repo_instance: UsageRepository | None = None
_usage_lock = threading.Lock()


def get_usage_repository() -> UsageRepository:
    """Returns singleton UsageRepository instance (SqlUsageRepository by default)."""
    global _usage_repo_instance
    with _usage_lock:
        if _usage_repo_instance is None:
            repo = SqlUsageRepository()
            verify_persistence_startup_guard(repo)
            _usage_repo_instance = repo
        return _usage_repo_instance


def reset_usage_repository(repo: UsageRepository | None = None) -> None:
    """Resets the singleton UsageRepository for test isolation."""
    global _usage_repo_instance
    with _usage_lock:
        _usage_repo_instance = repo
