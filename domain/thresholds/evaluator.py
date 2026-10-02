"""Threshold Evaluation Engine with Complete Anti-Flapping Controls (Prompt 27).

Enforces:
- Prompt 27: Six states (Normal, Warning, High, Critical, Informational, Unknown/No data).
- Prompt 27 Anti-Flapping:
  1. Dwell time before a state is published ('Do not publish a state on a single evaluation where dwell time applies').
  2. Asymmetric entry and exit thresholds (hysteresis).
  3. Cool-down after a transition ('value oscillating around a boundary produces at most one alert in cool-down').
  4. Scope-level storm grouping.
  5. Data-quality gate ('Do not let missing data produce a threshold breach').
- Prompt 27: Idempotency ('Re-running evaluation on unchanged data produces identical states').
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from domain.models.base import ProvenanceRecord
from domain.models.enums import OriginType
from domain.tenant.context import TenantContext
from domain.thresholds.models import (
    ThresholdBandDefinition,
    ThresholdEvaluationResult,
    ThresholdState,
)
from domain.thresholds.precedence import ResolvedThreshold

logger = logging.getLogger(__name__)


@dataclass
class AntiFlappingEntityState:
    """In-memory or persistent tracking of an entity's threshold state for anti-flapping."""

    entity_id: str
    rule_id: str
    committed_state: ThresholdState = ThresholdState.NORMAL
    pending_state: ThresholdState | None = None
    pending_consecutive_count: int = 0
    last_transition_time: datetime | None = None
    last_alert_time: datetime | None = None
    last_evaluated_value: Decimal | None = None


class ThresholdEvaluator:
    """Core evaluation engine that turns measured values into explainable, non-flapping states."""

    def __init__(self) -> None:
        # Key: (tenant_id, entity_id, rule_id) -> AntiFlappingEntityState
        self._entity_states: dict[tuple[str, str, str], AntiFlappingEntityState] = {}
        # Cycle transitions for storm grouping: (tenant_id, scope_id, cycle_minute) -> list[str]
        self._cycle_transitions: dict[tuple[str, str, str], list[str]] = {}

    def get_or_create_entity_state(
        self, tenant_id: str, entity_id: str, rule_id: str
    ) -> AntiFlappingEntityState:
        """Retrieves or initializes the anti-flapping state tracker for an entity."""
        key = (tenant_id, entity_id, rule_id)
        if key not in self._entity_states:
            self._entity_states[key] = AntiFlappingEntityState(entity_id=entity_id, rule_id=rule_id)
        return self._entity_states[key]

    # ==========================================================================
    # 1. Raw Band Evaluation
    # ==========================================================================

    @staticmethod
    def evaluate_raw_band(
        value: Decimal,
        bands: Sequence[ThresholdBandDefinition],
        current_committed_state: ThresholdState = ThresholdState.NORMAL,
    ) -> ThresholdState:
        """Determines matching threshold band considering asymmetric hysteresis."""
        # Check if currently in an active breach band with asymmetric exit thresholds (hysteresis)
        for band in bands:
            if band.state == current_committed_state and band.state.is_breach():
                # If asymmetric lower exit threshold is defined:
                # Value must drop below exit_threshold_lower to leave this band downwards
                if (
                    band.exit_threshold_lower is not None
                    and band.lower_bound is not None
                    and value >= band.exit_threshold_lower
                ):
                    # Check upper bound before holding
                    if band.upper_bound is None or value < band.upper_bound:
                        return band.state

        # Standard band lookup
        for band in bands:
            lower_ok = True
            if band.lower_bound is not None:
                lower_ok = (
                    value >= band.lower_bound if band.lower_inclusive else value > band.lower_bound
                )

            upper_ok = True
            if band.upper_bound is not None:
                upper_ok = (
                    value <= band.upper_bound if band.upper_inclusive else value < band.upper_bound
                )

            if lower_ok and upper_ok:
                return band.state

        # Fallback to last band or Normal
        return bands[-1].state if bands else ThresholdState.NORMAL

    # ==========================================================================
    # 2. Main Evaluation with Anti-Flapping
    # ==========================================================================

    def evaluate(
        self,
        *,
        entity_id: str,
        value: Decimal | None,
        resolved: ResolvedThreshold,
        scope_id: str | None = None,
        evaluated_at: datetime | None = None,
        tenant_context: TenantContext,
    ) -> ThresholdEvaluationResult:
        """Evaluates a measured value against a resolved threshold with complete anti-flapping."""
        now = evaluated_at or datetime.now(UTC)
        rule = resolved.rule
        bands = resolved.bands
        af_config = rule.anti_flapping

        state_tracker = self.get_or_create_entity_state(
            tenant_context.tenant_id, entity_id, rule.id
        )
        prev_committed = state_tracker.committed_state

        # ----------------------------------------------------------------------
        # A. Data-Quality Gate (Prompt 27 Negative Constraint: Missing data != breach)
        # ----------------------------------------------------------------------
        if value is None:
            # STRICT: Missing data produces a data-quality signal, NEVER a breach alert
            result_id = f"eval-{entity_id[:8]}-{uuid.uuid4().hex[:6]}"
            return ThresholdEvaluationResult(
                id=result_id,
                tenant_id=tenant_context.tenant_id,
                entity_id=entity_id,
                rule_id=rule.id,
                rule_name=rule.name,
                basis=rule.basis,
                measured_value=None,
                evaluated_state=ThresholdState.UNKNOWN,
                committed_state=ThresholdState.UNKNOWN,
                color_hex=ThresholdState.UNKNOWN.get_color_hex(),
                resolved_source_type=resolved.source_type,
                resolved_source_id=resolved.source_id,
                resolved_source_display=resolved.source_display,
                is_alert_dispatched=False,
                is_flapping_suppressed=False,
                is_data_quality_issue=True,
                evaluated_at=now,
                transition_occurred=prev_committed != ThresholdState.UNKNOWN,
                previous_committed_state=prev_committed,
                source_provenance=ProvenanceRecord(
                    source_system="cloudlens-threshold:data-quality-gate",
                    origin_type=OriginType.DERIVED,
                    correlation_id=tenant_context.correlation_id or f"corr-{uuid.uuid4().hex[:12]}",
                ),
            )

        # ----------------------------------------------------------------------
        # B. Idempotency Check (Unchanged inputs produce identical state)
        # ----------------------------------------------------------------------
        if (
            state_tracker.last_evaluated_value == value
            and state_tracker.last_transition_time is not None
        ):
            # Re-running evaluation on unchanged data reproduces current committed state without extra alerts
            result_id = f"eval-{entity_id[:8]}-{uuid.uuid4().hex[:6]}"
            return ThresholdEvaluationResult(
                id=result_id,
                tenant_id=tenant_context.tenant_id,
                entity_id=entity_id,
                rule_id=rule.id,
                rule_name=rule.name,
                basis=rule.basis,
                measured_value=value,
                evaluated_state=prev_committed,
                committed_state=prev_committed,
                color_hex=prev_committed.get_color_hex(),
                resolved_source_type=resolved.source_type,
                resolved_source_id=resolved.source_id,
                resolved_source_display=resolved.source_display,
                is_alert_dispatched=False,
                is_flapping_suppressed=False,
                is_data_quality_issue=False,
                evaluated_at=now,
                transition_occurred=False,
                previous_committed_state=prev_committed,
                source_provenance=ProvenanceRecord(
                    source_system="cloudlens-threshold:idempotent-replay",
                    origin_type=OriginType.DERIVED,
                    correlation_id=tenant_context.correlation_id or f"corr-{uuid.uuid4().hex[:12]}",
                ),
            )

        # ----------------------------------------------------------------------
        # C. Raw State Derivation with Hysteresis
        # ----------------------------------------------------------------------
        raw_state = self.evaluate_raw_band(value, bands, prev_committed)
        state_tracker.last_evaluated_value = value

        # ----------------------------------------------------------------------
        # D. Dwell Time Anti-Flapping Filter
        # ----------------------------------------------------------------------
        committed_state = prev_committed
        is_suppressed = False
        suppression_reason: str | None = None
        transition_occurred = False

        if raw_state != prev_committed:
            # Check dwell time requirement
            if af_config.dwell_evaluations > 1:
                if state_tracker.pending_state == raw_state:
                    state_tracker.pending_consecutive_count += 1
                else:
                    state_tracker.pending_state = raw_state
                    state_tracker.pending_consecutive_count = 1

                # Has dwell time threshold been satisfied?
                if state_tracker.pending_consecutive_count >= af_config.dwell_evaluations:
                    # Dwell satisfied: Commit transition
                    committed_state = raw_state
                    transition_occurred = True
                    state_tracker.committed_state = committed_state
                    state_tracker.pending_state = None
                    state_tracker.pending_consecutive_count = 0
                    state_tracker.last_transition_time = now
                else:
                    # Dwell pending: Hold previous state
                    committed_state = prev_committed
                    is_suppressed = True
                    suppression_reason = (
                        f"Dwell time pending: {state_tracker.pending_consecutive_count}/"
                        f"{af_config.dwell_evaluations} evaluations in state '{raw_state.value}'."
                    )
            else:
                # Immediate transition (dwell = 1)
                committed_state = raw_state
                transition_occurred = True
                state_tracker.committed_state = committed_state
                state_tracker.last_transition_time = now
        else:
            # State is unchanged; clear any pending candidate
            state_tracker.pending_state = None
            state_tracker.pending_consecutive_count = 0

        # ----------------------------------------------------------------------
        # E. Cool-Down Anti-Flapping Filter (AC-063: at most 1 alert in cool-down)
        # ----------------------------------------------------------------------
        is_alert_dispatched = False
        if transition_occurred and committed_state.is_breach():
            in_cooldown = False
            if state_tracker.last_alert_time is not None:
                elapsed_sec = (now - state_tracker.last_alert_time).total_seconds()
                if elapsed_sec < af_config.cooldown_seconds:
                    in_cooldown = True
                    rem = int(af_config.cooldown_seconds - elapsed_sec)
                    is_suppressed = True
                    suppression_reason = f"Alert suppressed by cool-down period ({rem}s remaining)."

            if not in_cooldown:
                # --------------------------------------------------------------
                # F. Scope-Level Grouping (Storm Suppression)
                # --------------------------------------------------------------
                if scope_id:
                    cycle_key = (
                        tenant_context.tenant_id,
                        scope_id,
                        now.strftime("%Y%m%d%H%M"),
                    )
                    trans_list = self._cycle_transitions.setdefault(cycle_key, [])
                    trans_list.append(entity_id)

                    if len(trans_list) > af_config.grouping_storm_threshold:
                        is_suppressed = True
                        suppression_reason = (
                            f"Alert storm suppressed: grouped into parent scope '{scope_id}' event "
                            f"({len(trans_list)} child transitions in cycle)."
                        )
                        is_alert_dispatched = False
                    else:
                        is_alert_dispatched = True
                        state_tracker.last_alert_time = now
                else:
                    is_alert_dispatched = True
                    state_tracker.last_alert_time = now

        result_id = f"eval-{entity_id[:8]}-{uuid.uuid4().hex[:6]}"
        return ThresholdEvaluationResult(
            id=result_id,
            tenant_id=tenant_context.tenant_id,
            entity_id=entity_id,
            rule_id=rule.id,
            rule_name=rule.name,
            basis=rule.basis,
            measured_value=value,
            evaluated_state=raw_state,
            committed_state=committed_state,
            color_hex=committed_state.get_color_hex(),
            resolved_source_type=resolved.source_type,
            resolved_source_id=resolved.source_id,
            resolved_source_display=resolved.source_display,
            is_alert_dispatched=is_alert_dispatched,
            is_flapping_suppressed=is_suppressed,
            suppression_reason=suppression_reason,
            is_data_quality_issue=False,
            evaluated_at=now,
            transition_occurred=transition_occurred,
            previous_committed_state=prev_committed,
            source_provenance=ProvenanceRecord(
                source_system="cloudlens-threshold:anti-flapping-evaluator",
                origin_type=OriginType.DERIVED,
                correlation_id=tenant_context.correlation_id or f"corr-{uuid.uuid4().hex[:12]}",
            ),
        )
