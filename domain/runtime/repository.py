"""Tenant-Scoped Repository for Runtime Observations, Schedules, and Adherence (Prompt 26).

Enforces:
- Prompt 13 Item 84: 100% TenantContext validation across all repository operations.
- Tenant isolation per BBP Section 41 and SEC-015.
"""

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
from domain.tenant.repository import TenantAwareRepository

logger = logging.getLogger(__name__)


class RuntimeRepository(TenantAwareRepository[ScheduleAdherenceResult]):
    """Tenant-scoped repository persisting runtime adherence results, schedules, and exemptions."""

    def __init__(self) -> None:
        # Key: (tenant_id, result_id) -> ScheduleAdherenceResult
        self._results: dict[tuple[str, str], ScheduleAdherenceResult] = {}
        # Key: (tenant_id, resource_id, observation_id) -> RuntimeObservation
        self._observations: dict[tuple[str, str, str], RuntimeObservation] = {}
        # Key: (tenant_id, schedule_id) -> NamedSchedule
        self._schedules: dict[tuple[str, str], NamedSchedule] = {}
        # Key: (tenant_id, attachment_id) -> ScheduleAttachment
        self._attachments: dict[tuple[str, str], ScheduleAttachment] = {}
        # Key: (tenant_id, exemption_id) -> RuntimeExemption
        self._exemptions: dict[tuple[str, str], RuntimeExemption] = {}

        # Seed default built-in standard schedules for all tenants
        for sched in STANDARD_SCHEDULES.values():
            self._schedules[("global", sched.id)] = sched

    # ==========================================================================
    # 1. TenantAwareRepository Required Base Methods
    # ==========================================================================

    def get(
        self, entity_id: str, *, tenant_context: TenantContext
    ) -> ScheduleAdherenceResult | None:
        """Retrieves a single adherence evaluation result by ID within tenant scope."""
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
        """Lists adherence evaluation results within the tenant scope."""
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
        """Persists or updates an adherence result ensuring tenant isolation."""
        self._validate_tenant_context(tenant_context)
        if entity.tenant_id != tenant_context.tenant_id:
            raise ValueError(
                f"Adherence entity tenant '{entity.tenant_id}' mismatches context '{tenant_context.tenant_id}'."
            )
        self._results[(tenant_context.tenant_id, entity.id)] = entity
        return entity

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        """Deletes an adherence result within tenant scope."""
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, entity_id)
        if key in self._results:
            del self._results[key]
            return True
        return False

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        """Checks if an adherence result exists within tenant scope."""
        self._validate_tenant_context(tenant_context)
        return (tenant_context.tenant_id, entity_id) in self._results

    # ==========================================================================
    # 2. Runtime Observations Storage
    # ==========================================================================

    def save_observation(
        self, observation: RuntimeObservation, *, tenant_context: TenantContext
    ) -> None:
        """Persists a discrete runtime observation."""
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
        """Lists observations for a resource overlapping the specified time window."""
        self._validate_tenant_context(tenant_context)
        res: list[RuntimeObservation] = []
        for (t_id, r_id, _), obs in self._observations.items():
            if t_id == tenant_context.tenant_id and r_id == resource_id:
                if obs.interval_start < end_time and obs.interval_end > start_time:
                    res.append(obs)
        res.sort(key=lambda o: o.interval_start)
        return res

    # ==========================================================================
    # 3. Named Schedules & Attachments Storage
    # ==========================================================================

    def save_schedule(self, schedule: NamedSchedule, *, tenant_context: TenantContext) -> None:
        """Saves a named operational runtime schedule for the tenant."""
        self._validate_tenant_context(tenant_context)
        self._schedules[(tenant_context.tenant_id, schedule.id)] = schedule

    def get_schedule(
        self, schedule_id: str, *, tenant_context: TenantContext
    ) -> NamedSchedule | None:
        """Retrieves a schedule, checking tenant overrides first then global defaults."""
        self._validate_tenant_context(tenant_context)
        tenant_sched = self._schedules.get((tenant_context.tenant_id, schedule_id))
        if tenant_sched:
            return tenant_sched
        return self._schedules.get(("global", schedule_id))

    def list_schedules(self, *, tenant_context: TenantContext) -> builtins.list[NamedSchedule]:
        """Lists all schedules accessible to the tenant (global defaults + tenant overrides)."""
        self._validate_tenant_context(tenant_context)
        sched_map: dict[str, NamedSchedule] = {}
        # Global first
        for (t_id, _), s in self._schedules.items():
            if t_id == "global":
                sched_map[s.id] = s
        # Tenant overrides
        for (t_id, _), s in self._schedules.items():
            if t_id == tenant_context.tenant_id:
                sched_map[s.id] = s
        return list(sched_map.values())

    def save_attachment(
        self, attachment: ScheduleAttachment, *, tenant_context: TenantContext
    ) -> None:
        """Persists a schedule attachment record."""
        self._validate_tenant_context(tenant_context)
        self._attachments[(tenant_context.tenant_id, attachment.id)] = attachment

    def list_attachments(
        self, *, tenant_context: TenantContext
    ) -> builtins.list[ScheduleAttachment]:
        """Lists all schedule attachments for the tenant."""
        self._validate_tenant_context(tenant_context)
        return [
            att for (t_id, _), att in self._attachments.items() if t_id == tenant_context.tenant_id
        ]

    # ==========================================================================
    # 4. Runtime Exemptions Storage
    # ==========================================================================

    def save_exemption(self, exemption: RuntimeExemption, *, tenant_context: TenantContext) -> None:
        """Persists or updates a temporary runtime schedule exemption."""
        self._validate_tenant_context(tenant_context)
        self._exemptions[(tenant_context.tenant_id, exemption.id)] = exemption

    def get_exemption(
        self, exemption_id: str, *, tenant_context: TenantContext
    ) -> RuntimeExemption | None:
        """Retrieves a specific runtime exemption by ID."""
        self._validate_tenant_context(tenant_context)
        return self._exemptions.get((tenant_context.tenant_id, exemption_id))

    def list_exemptions_for_resource(
        self, resource_id: str, *, tenant_context: TenantContext
    ) -> builtins.list[RuntimeExemption]:
        """Lists all exemptions for a specific resource."""
        self._validate_tenant_context(tenant_context)
        return [
            ex
            for (t_id, _), ex in self._exemptions.items()
            if t_id == tenant_context.tenant_id and ex.resource_id == resource_id
        ]

    def list_all_exemptions(
        self, *, tenant_context: TenantContext
    ) -> builtins.list[RuntimeExemption]:
        """Lists all exemptions belonging to the tenant."""
        self._validate_tenant_context(tenant_context)
        return [
            ex for (t_id, _), ex in self._exemptions.items() if t_id == tenant_context.tenant_id
        ]


_runtime_repository_instance: RuntimeRepository | None = None


def get_runtime_repository() -> RuntimeRepository:
    """Returns singleton RuntimeRepository instance."""
    global _runtime_repository_instance
    if _runtime_repository_instance is None:
        _runtime_repository_instance = RuntimeRepository()
    return _runtime_repository_instance


def reset_runtime_repository() -> None:
    """Resets the singleton RuntimeRepository for test isolation."""
    global _runtime_repository_instance
    _runtime_repository_instance = None
