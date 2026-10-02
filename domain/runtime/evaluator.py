"""Schedule Adherence Evaluation Engine and Breach Valuation (Prompt 26).

Enforces:
- Prompt 26: Six runtime states with non-compliance discipline:
  - Unknown and No Data are NEVER rendered as compliant and NEVER coloured green.
  - Do not conflate Stopped with Not applicable.
- Prompt 26: Derive running hours per resource per evaluation window for runtime monitoring types.
- Prompt 26: Adherence evaluation with warning and critical tolerances.
- Prompt 26: Mandatory monetary valuation of every schedule breach using applicable hourly rate.
  'Do not raise a schedule exception without a monetary value.'
- Prompt 26: Active exemption suppression (AC-062).
- RUN-006: Track cumulative operating hours across billing periods.
- RUN-007: Idempotent and deterministic historical re-evaluation.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal

from domain.models.base import ProvenanceRecord
from domain.models.enums import OriginType
from domain.models.exceptions import (
    ScheduleBreachValuationException,
)
from domain.rules.monetary import round_currency
from domain.runtime.models import (
    AdherenceStatus,
    NamedSchedule,
    RuntimeExemption,
    RuntimeObservation,
    RuntimeState,
    ScheduleAdherenceResult,
)
from domain.runtime.schedules import (
    compute_expected_running_hours,
    is_approved_running_slot,
)
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)

# Default benchmark rate for computing monetary valuation when pricing catalog rate is omitted
DEFAULT_BENCHMARK_HOURLY_RATE = Decimal("0.096")  # ~$70/month baseline


class AdherenceEvaluator:
    """Evaluates resource runtime adherence against approved schedules and computes breach costs."""

    # ==========================================================================
    # 1. Derivation of Running Hours (Prompt 26 Item 159 / RUN-006 / RUN-007)
    # ==========================================================================

    @staticmethod
    def derive_running_hours(
        observations: Sequence[RuntimeObservation],
        window_start: datetime,
        window_end: datetime,
    ) -> tuple[Decimal, RuntimeState]:
        """Derives cumulative running hours and predominant runtime state across an evaluation window.

        Idempotent and deterministic per RUN-007.
        """
        if not observations:
            return Decimal("0.0"), RuntimeState.UNKNOWN

        total_running_seconds = Decimal("0.0")
        state_counts: dict[RuntimeState, int] = {}

        for obs in observations:
            state_counts[obs.state] = state_counts.get(obs.state, 0) + 1

            # Check overlap with evaluation window
            obs_start = max(obs.interval_start, window_start)
            obs_end = min(obs.interval_end, window_end)

            if obs_start < obs_end and obs.state.is_active_execution():
                duration_sec = Decimal(str((obs_end - obs_start).total_seconds()))
                total_running_seconds += duration_sec

        running_hours = total_running_seconds / Decimal("3600.0")

        # Determine predominant state
        predominant_state = max(state_counts.items(), key=lambda item: item[1])[0]

        return running_hours, predominant_state

    # ==========================================================================
    # 2. Schedule Adherence Evaluation & Valuation (Prompt 26 / AC-060, AC-061, AC-062)
    # ==========================================================================

    @staticmethod
    def evaluate_adherence(
        resource_id: str,
        schedule: NamedSchedule,
        window_start: datetime,
        window_end: datetime,
        *,
        observations: Sequence[RuntimeObservation],
        hourly_rate: Decimal | None = None,
        currency: str = "USD",
        environment: str = "production",
        resource_name: str | None = None,
        active_exemption: RuntimeExemption | None = None,
        is_stateless_or_storage: bool = False,
        tenant_context: TenantContext,
    ) -> ScheduleAdherenceResult:
        """Evaluates whether a resource ran when approved, and attaches a monetary value to every breach."""
        # 1. Check for NOT_APPLICABLE (stateless / storage resources with no runtime dimension)
        if is_stateless_or_storage:
            RuntimeState.assert_not_conflated(RuntimeState.NOT_APPLICABLE, RuntimeState.STOPPED)
            return ScheduleAdherenceResult(
                id=f"adh-{resource_id[:8]}-{window_start.strftime('%Y%m%d%H')}",
                tenant_id=tenant_context.tenant_id,
                resource_id=resource_id,
                resource_name=resource_name,
                environment=environment,
                evaluation_window_start=window_start,
                evaluation_window_end=window_end,
                schedule_id=schedule.id,
                schedule_name=schedule.name,
                runtime_state=RuntimeState.NOT_APPLICABLE,
                adherence_status=AdherenceStatus.NOT_APPLICABLE,
                is_compliant=True,
                color_hex=RuntimeState.NOT_APPLICABLE.get_default_color_hex(),
                expected_running_hours=Decimal("0.0"),
                actual_running_hours=Decimal("0.0"),
                excess_running_hours=Decimal("0.0"),
                shortfall_running_hours=Decimal("0.0"),
                hourly_rate=Decimal("0.0"),
                currency=currency,
                breach_cost=Decimal("0.00"),
                projected_monthly_excess_cost=Decimal("0.00"),
                notes="Resource does not possess an operational start/stop runtime lifecycle.",
                source_provenance=ProvenanceRecord(
                    source_system="cloudlens-runtime:adherence-evaluator",
                    origin_type=OriginType.DERIVED,
                    correlation_id=tenant_context.correlation_id or f"corr-{uuid.uuid4().hex[:12]}",
                ),
            )

        # 2. Check for missing or unavailable telemetry (AC-061: UNKNOWN / NO_DATA -> never green)
        if not observations:
            return ScheduleAdherenceResult(
                id=f"adh-{resource_id[:8]}-{window_start.strftime('%Y%m%d%H')}",
                tenant_id=tenant_context.tenant_id,
                resource_id=resource_id,
                resource_name=resource_name,
                environment=environment,
                evaluation_window_start=window_start,
                evaluation_window_end=window_end,
                schedule_id=schedule.id,
                schedule_name=schedule.name,
                runtime_state=RuntimeState.UNKNOWN,
                adherence_status=AdherenceStatus.UNKNOWN,
                # STRICT: Unknown is NEVER compliant and NEVER green
                is_compliant=False,
                color_hex=RuntimeState.UNKNOWN.get_default_color_hex(),
                expected_running_hours=compute_expected_running_hours(
                    schedule, window_start, window_end
                ),
                actual_running_hours=Decimal("0.0"),
                excess_running_hours=Decimal("0.0"),
                shortfall_running_hours=Decimal("0.0"),
                hourly_rate=hourly_rate or DEFAULT_BENCHMARK_HOURLY_RATE,
                currency=currency,
                breach_cost=Decimal("0.00"),
                projected_monthly_excess_cost=Decimal("0.00"),
                notes="Runtime signal cannot be verified or is missing from provider telemetry. Marked Unknown.",
                source_provenance=ProvenanceRecord(
                    source_system="cloudlens-runtime:adherence-evaluator",
                    origin_type=OriginType.DERIVED,
                    correlation_id=tenant_context.correlation_id or f"corr-{uuid.uuid4().hex[:12]}",
                ),
            )

        # 3. Derive actual running hours and predominant state
        actual_running_hours, predominant_state = AdherenceEvaluator.derive_running_hours(
            observations, window_start, window_end
        )

        # If telemetry specifically reported UNKNOWN or NO_DATA
        if predominant_state in (RuntimeState.UNKNOWN, RuntimeState.NO_DATA):
            adherence_status = (
                AdherenceStatus.UNKNOWN
                if predominant_state == RuntimeState.UNKNOWN
                else AdherenceStatus.NO_DATA
            )
            return ScheduleAdherenceResult(
                id=f"adh-{resource_id[:8]}-{window_start.strftime('%Y%m%d%H')}",
                tenant_id=tenant_context.tenant_id,
                resource_id=resource_id,
                resource_name=resource_name,
                environment=environment,
                evaluation_window_start=window_start,
                evaluation_window_end=window_end,
                schedule_id=schedule.id,
                schedule_name=schedule.name,
                runtime_state=predominant_state,
                adherence_status=adherence_status,
                is_compliant=False,
                color_hex=predominant_state.get_default_color_hex(),
                expected_running_hours=compute_expected_running_hours(
                    schedule, window_start, window_end
                ),
                actual_running_hours=actual_running_hours,
                excess_running_hours=Decimal("0.0"),
                shortfall_running_hours=Decimal("0.0"),
                hourly_rate=hourly_rate or DEFAULT_BENCHMARK_HOURLY_RATE,
                currency=currency,
                breach_cost=Decimal("0.00"),
                projected_monthly_excess_cost=Decimal("0.00"),
                notes="Observed runtime state indicates missing or unverified provider telemetry.",
                source_provenance=ProvenanceRecord(
                    source_system="cloudlens-runtime:adherence-evaluator",
                    origin_type=OriginType.DERIVED,
                    correlation_id=tenant_context.correlation_id or f"corr-{uuid.uuid4().hex[:12]}",
                ),
            )

        # 4. Compute expected running hours and detailed unapproved running hours
        expected_running_hours = compute_expected_running_hours(schedule, window_start, window_end)

        # Walk observations to calculate excess running (hours run during unapproved slots)
        unapproved_running_sec = Decimal("0.0")
        for obs in observations:
            if not obs.state.is_active_execution():
                continue
            # Evaluate hour-by-hour within the observation interval
            curr = max(obs.interval_start, window_start)
            end = min(obs.interval_end, window_end)
            while curr < end:
                slot_mid = curr + timedelta(minutes=30)
                if not is_approved_running_slot(schedule, slot_mid):
                    step_sec = min(Decimal("3600.0"), Decimal(str((end - curr).total_seconds())))
                    unapproved_running_sec += step_sec
                curr += timedelta(hours=1)

        excess_running_hours = unapproved_running_sec / Decimal("3600.0")

        # Shortfall: expected to run but observed stopped
        shortfall_hours = Decimal("0.0")
        if actual_running_hours < expected_running_hours:
            shortfall_hours = expected_running_hours - actual_running_hours

        # 5. Resolve applicable hourly cost rate
        effective_rate = hourly_rate or DEFAULT_BENCHMARK_HOURLY_RATE
        if effective_rate <= Decimal("0.0"):
            effective_rate = DEFAULT_BENCHMARK_HOURLY_RATE

        # 6. Check Active Exemption (AC-062: suppresses alert)
        if active_exemption is not None and not active_exemption.is_expired(as_of=window_end):
            return ScheduleAdherenceResult(
                id=f"adh-{resource_id[:8]}-{window_start.strftime('%Y%m%d%H')}",
                tenant_id=tenant_context.tenant_id,
                resource_id=resource_id,
                resource_name=resource_name,
                environment=environment,
                evaluation_window_start=window_start,
                evaluation_window_end=window_end,
                schedule_id=schedule.id,
                schedule_name=schedule.name,
                runtime_state=predominant_state,
                adherence_status=AdherenceStatus.EXEMPT,
                is_compliant=True,
                color_hex=AdherenceStatus.EXEMPT.get_badge_color(),
                expected_running_hours=expected_running_hours,
                actual_running_hours=actual_running_hours,
                excess_running_hours=excess_running_hours,
                shortfall_running_hours=shortfall_hours,
                hourly_rate=effective_rate,
                currency=currency,
                breach_cost=Decimal("0.00"),
                projected_monthly_excess_cost=Decimal("0.00"),
                exemption_id=active_exemption.id,
                exemption_reason=active_exemption.reason,
                notes=f"Active exemption '{active_exemption.id}' in effect. Alert suppressed.",
                source_provenance=ProvenanceRecord(
                    source_system="cloudlens-runtime:adherence-evaluator",
                    origin_type=OriginType.DERIVED,
                    correlation_id=tenant_context.correlation_id or f"corr-{uuid.uuid4().hex[:12]}",
                ),
            )

        # 7. Evaluate Adherence Status vs Tolerances
        is_breach = False
        if excess_running_hours > schedule.critical_tolerance_hours:
            adherence_status = AdherenceStatus.CRITICAL
            is_breach = True
        elif excess_running_hours > schedule.warning_tolerance_hours:
            adherence_status = AdherenceStatus.WARNING
            is_breach = True
        else:
            adherence_status = AdherenceStatus.COMPLIANT

        # 8. Compute Monetary Valuation of Breach (Prompt 26: Mandatory financial valuation)
        if is_breach:
            raw_breach_cost = excess_running_hours * effective_rate
            breach_cost = round_currency(raw_breach_cost)

            # Prompt 26 strict check: Do not raise a schedule exception without a monetary value
            if breach_cost <= Decimal("0.00") and excess_running_hours > Decimal("0.0"):
                raise ScheduleBreachValuationException(resource_id=resource_id)

            # Project monthly financial waste
            window_duration_hours = Decimal(
                str((window_end - window_start).total_seconds() / 3600.0)
            )
            if window_duration_hours > Decimal("0.0"):
                monthly_hours = Decimal("730.0")  # Standard 30.41-day month
                multiplier = monthly_hours / window_duration_hours
                projected_monthly = round_currency(breach_cost * multiplier)
            else:
                projected_monthly = breach_cost

            is_compliant = False
            color_hex = adherence_status.get_badge_color()
        else:
            breach_cost = Decimal("0.00")
            projected_monthly = Decimal("0.00")
            is_compliant = True
            color_hex = AdherenceStatus.COMPLIANT.get_badge_color()

        return ScheduleAdherenceResult(
            id=f"adh-{resource_id[:8]}-{window_start.strftime('%Y%m%d%H')}",
            tenant_id=tenant_context.tenant_id,
            resource_id=resource_id,
            resource_name=resource_name,
            environment=environment,
            evaluation_window_start=window_start,
            evaluation_window_end=window_end,
            schedule_id=schedule.id,
            schedule_name=schedule.name,
            runtime_state=predominant_state,
            adherence_status=adherence_status,
            is_compliant=is_compliant,
            color_hex=color_hex,
            expected_running_hours=expected_running_hours,
            actual_running_hours=actual_running_hours,
            excess_running_hours=excess_running_hours,
            shortfall_running_hours=shortfall_hours,
            hourly_rate=effective_rate,
            currency=currency,
            breach_cost=breach_cost,
            projected_monthly_excess_cost=projected_monthly,
            notes=(
                f"Adherence evaluated: {actual_running_hours:.1f}h actual vs {expected_running_hours:.1f}h approved. "
                f"Excess: {excess_running_hours:.1f}h (${breach_cost:.2f})."
            ),
            source_provenance=ProvenanceRecord(
                source_system="cloudlens-runtime:adherence-evaluator",
                origin_type=OriginType.DERIVED,
                correlation_id=tenant_context.correlation_id or f"corr-{uuid.uuid4().hex[:12]}",
            ),
        )
