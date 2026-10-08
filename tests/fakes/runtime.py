"""In-memory test fake for RuntimeRepository (Prompt P07 / Prompt 26)."""

from __future__ import annotations

import builtins
import logging
from datetime import datetime
from typing import Any

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


class InMemoryRuntimeRepository:
    """In-memory repository fake persisting runtime adherence results, schedules, and exemptions."""

    is_in_memory: bool = True

    def __init__(self) -> None:
        self._results: dict[tuple[str, str], ScheduleAdherenceResult] = {}
        self._observations: dict[tuple[str, str, str], RuntimeObservation] = {}
        self._schedules: dict[tuple[str, str], NamedSchedule] = {}
        self._attachments: dict[tuple[str, str], ScheduleAttachment] = {}
        self._exemptions: dict[tuple[str, str], RuntimeExemption] = {}

        for sched in STANDARD_SCHEDULES.values():
            self._schedules[("global", sched.id)] = sched

    def _validate_tenant_context(self, tenant_context: TenantContext) -> None:
        if not tenant_context or not tenant_context.tenant_id:
            raise ValueError("Operation requires valid TenantContext with non-empty tenant_id.")

    def get(
        self, entity_id: str, *, tenant_context: TenantContext
    ) -> ScheduleAdherenceResult | None:
        self._validate_tenant_context(tenant_context)
        return self._results.get((tenant_context.tenant_id, entity_id))

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[ScheduleAdherenceResult]:
        self._validate_tenant_context(tenant_context)
        _ = filter_params
        matching = [
            res for (t_id, _), res in self._results.items() if t_id == tenant_context.tenant_id
        ]
        matching.sort(key=lambda r: r.evaluation_window_end, reverse=True)
        return matching[offset : offset + limit]

    def save(
        self, entity: ScheduleAdherenceResult, *, tenant_context: TenantContext
    ) -> ScheduleAdherenceResult:
        self._validate_tenant_context(tenant_context)
        if entity.tenant_id != tenant_context.tenant_id:
            raise ValueError(
                f"Adherence entity tenant '{entity.tenant_id}' mismatches context '{tenant_context.tenant_id}'."
            )
        self._results[(tenant_context.tenant_id, entity.id)] = entity
        return entity

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, entity_id)
        if key in self._results:
            del self._results[key]
            return True
        return False

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        self._validate_tenant_context(tenant_context)
        return (tenant_context.tenant_id, entity_id) in self._results

    def save_observation(
        self, observation: RuntimeObservation, *, tenant_context: TenantContext
    ) -> None:
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, observation.resource_id, observation.id)
        self._observations[key] = observation

    def list_observations(
        self,
        resource_id: str,
        start_time: datetime,
        end_time: datetime,
        *,
        tenant_context: TenantContext,
    ) -> builtins.list[RuntimeObservation]:
        self._validate_tenant_context(tenant_context)
        res: list[RuntimeObservation] = []
        for (t_id, r_id, _), obs in self._observations.items():
            if t_id == tenant_context.tenant_id and r_id == resource_id:
                if obs.interval_start < end_time and obs.interval_end > start_time:
                    res.append(obs)
        res.sort(key=lambda o: o.interval_start)
        return res

    def save_schedule(self, schedule: NamedSchedule, *, tenant_context: TenantContext) -> None:
        self._validate_tenant_context(tenant_context)
        self._schedules[(tenant_context.tenant_id, schedule.id)] = schedule

    def get_schedule(
        self, schedule_id: str, *, tenant_context: TenantContext
    ) -> NamedSchedule | None:
        self._validate_tenant_context(tenant_context)
        tenant_sched = self._schedules.get((tenant_context.tenant_id, schedule_id))
        if tenant_sched:
            return tenant_sched
        return self._schedules.get(("global", schedule_id))

    def list_schedules(self, *, tenant_context: TenantContext) -> builtins.list[NamedSchedule]:
        self._validate_tenant_context(tenant_context)
        sched_map: dict[str, NamedSchedule] = {}
        for (t_id, _), s in self._schedules.items():
            if t_id == "global":
                sched_map[s.id] = s
        for (t_id, _), s in self._schedules.items():
            if t_id == tenant_context.tenant_id:
                sched_map[s.id] = s
        return list(sched_map.values())

    def save_attachment(
        self, attachment: ScheduleAttachment, *, tenant_context: TenantContext
    ) -> None:
        self._validate_tenant_context(tenant_context)
        self._attachments[(tenant_context.tenant_id, attachment.id)] = attachment

    def list_attachments(
        self, *, tenant_context: TenantContext
    ) -> builtins.list[ScheduleAttachment]:
        self._validate_tenant_context(tenant_context)
        return [
            att for (t_id, _), att in self._attachments.items() if t_id == tenant_context.tenant_id
        ]

    def save_exemption(self, exemption: RuntimeExemption, *, tenant_context: TenantContext) -> None:
        self._validate_tenant_context(tenant_context)
        self._exemptions[(tenant_context.tenant_id, exemption.id)] = exemption

    def get_exemption(
        self, exemption_id: str, *, tenant_context: TenantContext
    ) -> RuntimeExemption | None:
        self._validate_tenant_context(tenant_context)
        return self._exemptions.get((tenant_context.tenant_id, exemption_id))

    def list_exemptions_for_resource(
        self, resource_id: str, *, tenant_context: TenantContext
    ) -> builtins.list[RuntimeExemption]:
        self._validate_tenant_context(tenant_context)
        return [
            ex
            for (t_id, _), ex in self._exemptions.items()
            if t_id == tenant_context.tenant_id and ex.resource_id == resource_id
        ]

    def list_all_exemptions(
        self, *, tenant_context: TenantContext
    ) -> builtins.list[RuntimeExemption]:
        self._validate_tenant_context(tenant_context)
        return [
            ex for (t_id, _), ex in self._exemptions.items() if t_id == tenant_context.tenant_id
        ]
