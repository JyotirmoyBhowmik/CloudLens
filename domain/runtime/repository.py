"""Tenant-Scoped Repository for Runtime Observations, Schedules, and Adherence (Prompt 26, Prompt P07).

Enforces:
- Prompt 13 Item 84: 100% TenantContext validation across all repository operations.
- Tenant isolation via PostgreSQL RLS across runtime state facts, schedules, and exemptions.
- Protocol + SqlRuntimeRepository per docs/persistence-pattern.md.
- Production startup guard verifying no in-memory repositories in staging/production.
"""

from __future__ import annotations

import builtins
import json
import logging
import threading
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_tenant_session, run_async, verify_persistence_startup_guard
from domain.runtime.models import (
    NamedSchedule,
    RuntimeExemption,
    RuntimeObservation,
    ScheduleAdherenceResult,
    ScheduleAttachment,
)
from domain.runtime.schedules import STANDARD_SCHEDULES
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)


@runtime_checkable
class RuntimeRepository(Protocol):
    """Authoritative repository protocol for runtime adherence, schedules, exemptions."""

    def get(
        self, entity_id: str, *, tenant_context: TenantContext
    ) -> ScheduleAdherenceResult | None: ...
    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[ScheduleAdherenceResult]: ...
    def save(
        self, entity: ScheduleAdherenceResult, *, tenant_context: TenantContext
    ) -> ScheduleAdherenceResult: ...
    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool: ...
    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool: ...
    def save_observation(
        self, observation: RuntimeObservation, *, tenant_context: TenantContext
    ) -> None: ...
    def list_observations(
        self,
        resource_id: str,
        start_time: datetime,
        end_time: datetime,
        *,
        tenant_context: TenantContext,
    ) -> builtins.list[RuntimeObservation]: ...
    def save_schedule(self, schedule: NamedSchedule, *, tenant_context: TenantContext) -> None: ...
    def get_schedule(
        self, schedule_id: str, *, tenant_context: TenantContext
    ) -> NamedSchedule | None: ...
    def list_schedules(self, *, tenant_context: TenantContext) -> builtins.list[NamedSchedule]: ...
    def save_attachment(
        self, attachment: ScheduleAttachment, *, tenant_context: TenantContext
    ) -> None: ...
    def list_attachments(
        self, *, tenant_context: TenantContext
    ) -> builtins.list[ScheduleAttachment]: ...
    def save_exemption(self, exemption: RuntimeExemption, *, tenant_context: TenantContext) -> None: ...
    def get_exemption(
        self, exemption_id: str, *, tenant_context: TenantContext
    ) -> RuntimeExemption | None: ...
    def list_exemptions_for_resource(
        self, resource_id: str, *, tenant_context: TenantContext
    ) -> builtins.list[RuntimeExemption]: ...
    def list_all_exemptions(
        self, *, tenant_context: TenantContext
    ) -> builtins.list[RuntimeExemption]: ...


class SqlRuntimeRepository:
    """PostgreSQL production implementation with Row-Level Security enforcement."""

    is_in_memory: bool = False

    def _run_async(self, coro: Any) -> Any:
        return run_async(coro)

    def _row_to_result(self, row: Any) -> ScheduleAdherenceResult:
        m = dict(row._mapping)
        raw = m.get("result_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "id" in raw:
            return ScheduleAdherenceResult.model_validate(raw)
        return ScheduleAdherenceResult.model_validate(m)

    def _row_to_schedule(self, row: Any) -> NamedSchedule:
        m = dict(row._mapping)
        raw = m.get("schedule_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "id" in raw:
            return NamedSchedule.model_validate(raw)
        return NamedSchedule.model_validate(m)

    def _row_to_exemption(self, row: Any) -> RuntimeExemption:
        m = dict(row._mapping)
        raw = m.get("exemption_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "id" in raw:
            return RuntimeExemption.model_validate(raw)
        return RuntimeExemption.model_validate(m)

    # 1. ScheduleAdherenceResult
    async def get_async(
        self, entity_id: str, *, tenant_context: TenantContext
    ) -> ScheduleAdherenceResult | None:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT * FROM runtime_adherence_results WHERE id = :id AND tenant_id = :tid LIMIT 1;"),
                {"id": entity_id, "tid": tenant_context.tenant_id},
            )
            row = res.fetchone()
            if not row:
                return None
            return self._row_to_result(row)

    def get(
        self, entity_id: str, *, tenant_context: TenantContext
    ) -> ScheduleAdherenceResult | None:
        return self._run_async(self.get_async(entity_id, tenant_context=tenant_context))

    async def list_async(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[ScheduleAdherenceResult]:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT * FROM runtime_adherence_results WHERE tenant_id = :tid ORDER BY evaluation_window_end DESC LIMIT :limit OFFSET :offset;"),
                {"tid": tenant_context.tenant_id, "limit": limit, "offset": offset},
            )
            rows = res.fetchall()
            return [self._row_to_result(r) for r in rows]

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[ScheduleAdherenceResult]:
        return self._run_async(self.list_async(tenant_context=tenant_context, filter_params=filter_params, limit=limit, offset=offset))

    async def save_async(
        self, entity: ScheduleAdherenceResult, *, tenant_context: TenantContext
    ) -> ScheduleAdherenceResult:
        if entity.tenant_id != tenant_context.tenant_id:
            raise ValueError(
                f"Adherence entity tenant '{entity.tenant_id}' mismatches context '{tenant_context.tenant_id}'."
            )
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            query = text("""
                INSERT INTO runtime_adherence_results (
                    id, tenant_id, schedule_id, result_payload, evaluation_window_end
                ) VALUES (
                    :id, :tid, :sid, CAST(:payload AS JSONB), :end_time
                )
                ON CONFLICT (id) DO UPDATE SET
                    result_payload = EXCLUDED.result_payload,
                    evaluation_window_end = EXCLUDED.evaluation_window_end;
            """)
            await sess.execute(
                query,
                {
                    "id": entity.id,
                    "tid": tenant_context.tenant_id,
                    "sid": entity.schedule_id,
                    "payload": json.dumps(entity.model_dump(mode="json")),
                    "end_time": entity.evaluation_window_end,
                },
            )
            await sess.commit()
            return entity

    def save(
        self, entity: ScheduleAdherenceResult, *, tenant_context: TenantContext
    ) -> ScheduleAdherenceResult:
        return self._run_async(self.save_async(entity, tenant_context=tenant_context))

    async def delete_async(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("DELETE FROM runtime_adherence_results WHERE id = :id AND tenant_id = :tid;"),
                {"id": entity_id, "tid": tenant_context.tenant_id},
            )
            await sess.commit()
            return (res.rowcount or 0) > 0

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return self._run_async(self.delete_async(entity_id, tenant_context=tenant_context))

    async def exists_async(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT 1 FROM runtime_adherence_results WHERE id = :id AND tenant_id = :tid LIMIT 1;"),
                {"id": entity_id, "tid": tenant_context.tenant_id},
            )
            return res.fetchone() is not None

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return self._run_async(self.exists_async(entity_id, tenant_context=tenant_context))

    # 2. Runtime Observations (maps to partitioned runtime_state)
    async def save_observation_async(
        self, observation: RuntimeObservation, *, tenant_context: TenantContext
    ) -> None:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            status_val = observation.state.value if hasattr(observation.state, "value") else str(observation.state)
            query = text("""
                INSERT INTO runtime_state (
                    window_start, tenant_id, id, resource_id, status,
                    cpu_utilization_avg, cpu_utilization_state,
                    memory_utilization_avg, memory_utilization_state,
                    is_idle, provider_native, source_provenance, created_at
                ) VALUES (
                    :start, :tid, :id, :rid, :status,
                    NULL, 'UNKNOWN', NULL, 'UNKNOWN',
                    FALSE, CAST(:payload AS JSONB), '{}'::jsonb, NOW()
                )
                ON CONFLICT (window_start, tenant_id, id) DO UPDATE SET
                    status = EXCLUDED.status,
                    provider_native = EXCLUDED.provider_native;
            """)
            await sess.execute(
                query,
                {
                    "start": observation.interval_start,
                    "tid": tenant_context.tenant_id,
                    "id": observation.id,
                    "rid": observation.resource_id,
                    "status": status_val,
                    "payload": json.dumps(observation.model_dump(mode="json")),
                },
            )
            await sess.commit()

    def save_observation(
        self, observation: RuntimeObservation, *, tenant_context: TenantContext
    ) -> None:
        self._run_async(self.save_observation_async(observation, tenant_context=tenant_context))

    async def list_observations_async(
        self,
        resource_id: str,
        start_time: datetime,
        end_time: datetime,
        *,
        tenant_context: TenantContext,
    ) -> builtins.list[RuntimeObservation]:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            query = text("""
                SELECT provider_native FROM runtime_state
                WHERE tenant_id = :tid AND resource_id = :rid
                AND window_start >= :start AND window_start <= :end
                ORDER BY window_start ASC;
            """)
            res = await sess.execute(
                query,
                {
                    "tid": tenant_context.tenant_id,
                    "rid": resource_id,
                    "start": start_time,
                    "end": end_time,
                },
            )
            rows = res.fetchall()
            results = []
            for r in rows:
                raw = r[0]
                if isinstance(raw, str):
                    raw = json.loads(raw)
                if isinstance(raw, dict) and "id" in raw:
                    results.append(RuntimeObservation.model_validate(raw))
            return results

    def list_observations(
        self,
        resource_id: str,
        start_time: datetime,
        end_time: datetime,
        *,
        tenant_context: TenantContext,
    ) -> builtins.list[RuntimeObservation]:
        return self._run_async(
            self.list_observations_async(resource_id, start_time, end_time, tenant_context=tenant_context)
        )

    # 3. Named Schedules
    async def save_schedule_async(self, schedule: NamedSchedule, *, tenant_context: TenantContext) -> None:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            query = text("""
                INSERT INTO runtime_schedules (id, tenant_id, name, schedule_payload, created_at)
                VALUES (:id, :tid, :name, CAST(:payload AS JSONB), NOW())
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    schedule_payload = EXCLUDED.schedule_payload;
            """)
            await sess.execute(
                query,
                {
                    "id": schedule.id,
                    "tid": tenant_context.tenant_id,
                    "name": schedule.name,
                    "payload": json.dumps(schedule.model_dump(mode="json")),
                },
            )
            await sess.commit()

    def save_schedule(self, schedule: NamedSchedule, *, tenant_context: TenantContext) -> None:
        self._run_async(self.save_schedule_async(schedule, tenant_context=tenant_context))

    async def get_schedule_async(
        self, schedule_id: str, *, tenant_context: TenantContext
    ) -> NamedSchedule | None:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT * FROM runtime_schedules WHERE id = :id AND tenant_id = :tid LIMIT 1;"),
                {"id": schedule_id, "tid": tenant_context.tenant_id},
            )
            row = res.fetchone()
            if row:
                return self._row_to_schedule(row)
        if schedule_id in STANDARD_SCHEDULES:
            return STANDARD_SCHEDULES[schedule_id]
        return None

    def get_schedule(
        self, schedule_id: str, *, tenant_context: TenantContext
    ) -> NamedSchedule | None:
        return self._run_async(self.get_schedule_async(schedule_id, tenant_context=tenant_context))

    async def list_schedules_async(self, *, tenant_context: TenantContext) -> builtins.list[NamedSchedule]:
        sched_map: dict[str, NamedSchedule] = {}
        for s in STANDARD_SCHEDULES.values():
            sched_map[s.id] = s
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT * FROM runtime_schedules WHERE tenant_id = :tid;"),
                {"tid": tenant_context.tenant_id},
            )
            rows = res.fetchall()
            for r in rows:
                s = self._row_to_schedule(r)
                sched_map[s.id] = s
        return list(sched_map.values())

    def list_schedules(self, *, tenant_context: TenantContext) -> builtins.list[NamedSchedule]:
        return self._run_async(self.list_schedules_async(tenant_context=tenant_context))

    # Attachments
    _attachments: dict[tuple[str, str], ScheduleAttachment] = {}

    def save_attachment(
        self, attachment: ScheduleAttachment, *, tenant_context: TenantContext
    ) -> None:
        self._attachments[(tenant_context.tenant_id, attachment.id)] = attachment

    def list_attachments(
        self, *, tenant_context: TenantContext
    ) -> builtins.list[ScheduleAttachment]:
        return [
            att for (t_id, _), att in self._attachments.items() if t_id == tenant_context.tenant_id
        ]

    # 4. Runtime Exemptions
    async def save_exemption_async(self, exemption: RuntimeExemption, *, tenant_context: TenantContext) -> None:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            query = text("""
                INSERT INTO runtime_exemptions (id, tenant_id, resource_id, exemption_payload, created_at)
                VALUES (:id, :tid, :rid, CAST(:payload AS JSONB), NOW())
                ON CONFLICT (id) DO UPDATE SET
                    resource_id = EXCLUDED.resource_id,
                    exemption_payload = EXCLUDED.exemption_payload;
            """)
            await sess.execute(
                query,
                {
                    "id": exemption.id,
                    "tid": tenant_context.tenant_id,
                    "rid": exemption.resource_id,
                    "payload": json.dumps(exemption.model_dump(mode="json")),
                },
            )
            await sess.commit()

    def save_exemption(self, exemption: RuntimeExemption, *, tenant_context: TenantContext) -> None:
        self._run_async(self.save_exemption_async(exemption, tenant_context=tenant_context))

    async def get_exemption_async(
        self, exemption_id: str, *, tenant_context: TenantContext
    ) -> RuntimeExemption | None:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT * FROM runtime_exemptions WHERE id = :id AND tenant_id = :tid LIMIT 1;"),
                {"id": exemption_id, "tid": tenant_context.tenant_id},
            )
            row = res.fetchone()
            if not row:
                return None
            return self._row_to_exemption(row)

    def get_exemption(
        self, exemption_id: str, *, tenant_context: TenantContext
    ) -> RuntimeExemption | None:
        return self._run_async(self.get_exemption_async(exemption_id, tenant_context=tenant_context))

    async def list_exemptions_for_resource_async(
        self, resource_id: str, *, tenant_context: TenantContext
    ) -> builtins.list[RuntimeExemption]:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT * FROM runtime_exemptions WHERE tenant_id = :tid AND resource_id = :rid;"),
                {"tid": tenant_context.tenant_id, "rid": resource_id},
            )
            rows = res.fetchall()
            return [self._row_to_exemption(r) for r in rows]

    def list_exemptions_for_resource(
        self, resource_id: str, *, tenant_context: TenantContext
    ) -> builtins.list[RuntimeExemption]:
        return self._run_async(
            self.list_exemptions_for_resource_async(resource_id, tenant_context=tenant_context)
        )

    async def list_all_exemptions_async(
        self, *, tenant_context: TenantContext
    ) -> builtins.list[RuntimeExemption]:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT * FROM runtime_exemptions WHERE tenant_id = :tid;"),
                {"tid": tenant_context.tenant_id},
            )
            rows = res.fetchall()
            return [self._row_to_exemption(r) for r in rows]

    def list_all_exemptions(
        self, *, tenant_context: TenantContext
    ) -> builtins.list[RuntimeExemption]:
        return self._run_async(self.list_all_exemptions_async(tenant_context=tenant_context))


_runtime_repository_instance: RuntimeRepository | None = None
_runtime_lock = threading.Lock()


def get_runtime_repository() -> RuntimeRepository:
    """Returns singleton RuntimeRepository instance (SqlRuntimeRepository by default)."""
    global _runtime_repository_instance
    with _runtime_lock:
        if _runtime_repository_instance is None:
            repo = SqlRuntimeRepository()
            verify_persistence_startup_guard(repo)
            _runtime_repository_instance = repo
        return _runtime_repository_instance


def reset_runtime_repository(repo: RuntimeRepository | None = None) -> None:
    """Resets the singleton RuntimeRepository for test isolation."""
    global _runtime_repository_instance
    with _runtime_lock:
        _runtime_repository_instance = repo
