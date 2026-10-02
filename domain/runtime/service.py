"""Runtime Model and Schedule Adherence Domain Service Facade (Prompt 26).

Coordinates:
- Runtime observation capture and state derivation.
- Named schedule lifecycle and inheritance resolution (RESOURCE -> SERVICE -> SCOPE -> ENV -> TENANT).
- Schedule adherence evaluation and monetary valuation of breaches.
- Temporary runtime schedule exemption lifecycle and automatic expiry.
- Phase 2 idle detection engine (ready but disabled behind feature flag).
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal

from domain.audit.service import AuditEventCreate, get_audit_service
from domain.models.enums import AuditEventType
from domain.runtime.evaluator import AdherenceEvaluator
from domain.runtime.exemptions import ExemptionManager
from domain.runtime.idle_detector import IdleDetector
from domain.runtime.models import (
    AdherenceStatus,
    NamedSchedule,
    RuntimeExemption,
    RuntimeExemptionCreateRequest,
    RuntimeObservation,
    RuntimeState,
    ScheduleAdherenceResult,
    ScheduleAttachment,
    ScheduleAttachRequest,
    ScheduleCreateRequest,
    ScheduleLevel,
)
from domain.runtime.repository import RuntimeRepository, get_runtime_repository
from domain.runtime.schedules import ScheduleEngine
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)


class RuntimeService:
    """Unified domain service for the 6-state runtime model and schedule adherence."""

    def __init__(
        self,
        repository: RuntimeRepository | None = None,
        schedule_engine: ScheduleEngine | None = None,
        exemption_manager: ExemptionManager | None = None,
        idle_detector: IdleDetector | None = None,
    ) -> None:
        self.repository = repository or get_runtime_repository()
        self.schedule_engine = schedule_engine or ScheduleEngine()
        self.exemption_manager = exemption_manager or ExemptionManager(self.repository)
        # Prompt 26 negative constraint: Disabled in MVP by default
        self.idle_detector = idle_detector or IdleDetector(enabled=False)

    # ==========================================================================
    # 1. Runtime Observations & States (API-032 / RUN-001)
    # ==========================================================================

    def record_observation(
        self,
        resource_id: str,
        interval_start: datetime,
        interval_end: datetime,
        state: RuntimeState,
        *,
        raw_provider_status: str | None = None,
        tenant_context: TenantContext,
    ) -> RuntimeObservation:
        """Persists an observed runtime telemetry point under tenant isolation."""
        obs = RuntimeObservation(
            resource_id=resource_id,
            interval_start=interval_start,
            interval_end=interval_end,
            state=state,
            raw_provider_status=raw_provider_status,
        )
        self.repository.save_observation(obs, tenant_context=tenant_context)
        return obs

    def get_resource_runtime_state(
        self,
        resource_id: str,
        start_time: datetime,
        end_time: datetime,
        *,
        tenant_context: TenantContext,
    ) -> tuple[RuntimeState, str]:
        """Resolves the current predominant runtime state and UI badge color for a resource."""
        observations = self.repository.list_observations(
            resource_id, start_time, end_time, tenant_context=tenant_context
        )
        if not observations:
            return RuntimeState.UNKNOWN, RuntimeState.UNKNOWN.get_default_color_hex()

        _, predominant_state = AdherenceEvaluator.derive_running_hours(
            observations, start_time, end_time
        )
        return predominant_state, predominant_state.get_default_color_hex()

    # ==========================================================================
    # 2. Named Schedules & Attachments (API-033 / RUN-002)
    # ==========================================================================

    def create_schedule(
        self,
        request: ScheduleCreateRequest,
        *,
        tenant_context: TenantContext,
    ) -> NamedSchedule:
        """Registers a named operational schedule."""
        schedule = NamedSchedule(
            id=request.id,
            name=request.name,
            description=request.description,
            timezone=request.timezone,
            workload_type=request.workload_type,
            working_days=request.working_days,
            daily_start_time=request.daily_start_time,
            daily_end_time=request.daily_end_time,
            exclusion_dates=request.exclusion_dates,
            warning_tolerance_hours=request.warning_tolerance_hours,
            critical_tolerance_hours=request.critical_tolerance_hours,
        )
        self.repository.save_schedule(schedule, tenant_context=tenant_context)
        self.schedule_engine.register_schedule(schedule)
        return schedule

    def get_schedule(
        self, schedule_id: str, *, tenant_context: TenantContext
    ) -> NamedSchedule | None:
        """Retrieves a schedule by ID."""
        sched = self.repository.get_schedule(schedule_id, tenant_context=tenant_context)
        if sched:
            return sched
        try:
            return self.schedule_engine.get_schedule(schedule_id)
        except Exception:
            return None

    def list_schedules(self, *, tenant_context: TenantContext) -> list[NamedSchedule]:
        """Lists all operational runtime schedules available to the tenant."""
        return self.repository.list_schedules(tenant_context=tenant_context)

    def attach_schedule(
        self,
        request: ScheduleAttachRequest,
        *,
        actor_id: str = "system",
        tenant_context: TenantContext,
    ) -> ScheduleAttachment:
        """Attaches a named schedule to a resource, service, scope, env, or tenant."""
        # Verify schedule exists
        sched = self.get_schedule(request.schedule_id, tenant_context=tenant_context)
        if not sched:
            raise ValueError(f"Schedule '{request.schedule_id}' does not exist.")

        attachment = ScheduleAttachment(
            schedule_id=request.schedule_id,
            level=request.level,
            target_id=request.target_id,
            environment=request.environment,
            business_justification=request.business_justification,
            attached_by=actor_id,
        )
        self.repository.save_attachment(attachment, tenant_context=tenant_context)

        # Audit attachment
        try:
            audit_svc = get_audit_service()
            audit_svc.append_event(
                tenant_context=tenant_context,
                event_in=AuditEventCreate(
                    event_type=AuditEventType.RUNTIME_SCHEDULE_ATTACHED,
                    actor_id=actor_id,
                    actor_roles=tenant_context.roles,
                    action="RUNTIME_SCHEDULE_ATTACHED",
                    resource_type=f"SCHEDULE_{request.level.value}",
                    resource_id=request.target_id,
                    details={
                        "schedule_id": request.schedule_id,
                        "level": request.level.value,
                        "environment": request.environment,
                    },
                    correlation_id=tenant_context.correlation_id,
                ),
            )
        except Exception as audit_err:
            logger.warning("Failed to audit schedule attachment: %s", audit_err)

        return attachment

    def resolve_schedule_for_resource(
        self,
        resource_id: str,
        *,
        service_id: str | None = None,
        scope_id: str | None = None,
        environment: str | None = None,
        tenant_context: TenantContext,
    ) -> tuple[NamedSchedule, ScheduleLevel]:
        """Resolves the applicable schedule following strict 5-level inheritance and BR-007."""
        attachments = self.repository.list_attachments(tenant_context=tenant_context)
        return self.schedule_engine.resolve_schedule(
            resource_id=resource_id,
            service_id=service_id,
            scope_id=scope_id,
            environment=environment,
            tenant_id=tenant_context.tenant_id,
            attachments=attachments,
        )

    # ==========================================================================
    # 3. Schedule Adherence Evaluation & Valuation (AC-060 / AC-061 / AC-062)
    # ==========================================================================

    def evaluate_adherence(
        self,
        resource_id: str,
        start_time: datetime,
        end_time: datetime,
        *,
        hourly_rate: Decimal | None = None,
        currency: str = "USD",
        environment: str = "production",
        resource_name: str | None = None,
        service_id: str | None = None,
        scope_id: str | None = None,
        is_stateless_or_storage: bool = False,
        tenant_context: TenantContext,
    ) -> ScheduleAdherenceResult:
        """Evaluates whether the resource adhered to its approved schedule and attaches monetary valuation."""
        # 1. Resolve schedule
        schedule, _ = self.resolve_schedule_for_resource(
            resource_id=resource_id,
            service_id=service_id,
            scope_id=scope_id,
            environment=environment,
            tenant_context=tenant_context,
        )

        # 2. Check active exemption
        active_exemp = self.exemption_manager.get_active_exemption_for_resource(
            resource_id=resource_id,
            as_of=end_time,
            tenant_context=tenant_context,
        )

        # 3. Fetch observations
        observations = self.repository.list_observations(
            resource_id, start_time, end_time, tenant_context=tenant_context
        )

        # 4. Evaluate adherence and breach valuation
        result = AdherenceEvaluator.evaluate_adherence(
            resource_id=resource_id,
            schedule=schedule,
            window_start=start_time,
            window_end=end_time,
            observations=observations,
            hourly_rate=hourly_rate,
            currency=currency,
            environment=environment,
            resource_name=resource_name,
            active_exemption=active_exemp,
            is_stateless_or_storage=is_stateless_or_storage,
            tenant_context=tenant_context,
        )

        # 5. Persist adherence evaluation result
        self.repository.save(result, tenant_context=tenant_context)

        # 6. Audit breach if status is WARNING or CRITICAL
        if result.adherence_status in (AdherenceStatus.WARNING, AdherenceStatus.CRITICAL):
            try:
                audit_svc = get_audit_service()
                audit_svc.append_event(
                    tenant_context=tenant_context,
                    event_in=AuditEventCreate(
                        event_type=AuditEventType.RUNTIME_SCHEDULE_BREACH_DETECTED,
                        actor_id="system",
                        actor_roles=["SYSTEM"],
                        action="RUNTIME_SCHEDULE_BREACH_DETECTED",
                        resource_type="RESOURCE",
                        resource_id=resource_id,
                        details={
                            "adherence_status": result.adherence_status.value,
                            "excess_running_hours": str(result.excess_running_hours),
                            "breach_cost": str(result.breach_cost),
                            "currency": result.currency,
                            "schedule_id": result.schedule_id,
                        },
                        correlation_id=tenant_context.correlation_id,
                    ),
                )
            except Exception as audit_err:
                logger.warning("Failed to audit schedule breach: %s", audit_err)

        return result

    # ==========================================================================
    # 4. Temporary Exemptions (API-034 / RUN-005 / AC-062)
    # ==========================================================================

    def create_exemption(
        self,
        request: RuntimeExemptionCreateRequest,
        *,
        actor_id: str,
        tenant_context: TenantContext,
    ) -> RuntimeExemption:
        """Creates a time-boxed runtime schedule exemption with recorded justification."""
        return self.exemption_manager.create_exemption(
            request, actor_id=actor_id, tenant_context=tenant_context
        )

    def list_active_exemptions(
        self,
        *,
        as_of: datetime | None = None,
        tenant_context: TenantContext,
    ) -> list[RuntimeExemption]:
        """Lists active unexpired exemptions across the tenant."""
        return self.exemption_manager.list_active_exemptions(
            as_of=as_of, tenant_context=tenant_context
        )


_runtime_service_instance: RuntimeService | None = None


def get_runtime_service() -> RuntimeService:
    """Returns singleton RuntimeService instance."""
    global _runtime_service_instance
    if _runtime_service_instance is None:
        _runtime_service_instance = RuntimeService()
    return _runtime_service_instance


def reset_runtime_service() -> None:
    """Resets the singleton RuntimeService instance for test isolation."""
    global _runtime_service_instance
    _runtime_service_instance = None
