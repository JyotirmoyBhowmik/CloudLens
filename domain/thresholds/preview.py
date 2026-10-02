"""Phase 2 Threshold Preview and Simulation Engine (Prompt 27).

Enforces:
- Prompt 27: 'Phase 2 Preview Capability: Simulation against historical series flag-gated behind
  ENABLE_THRESHOLD_PREVIEW = False in MVP.'
- Prompt 27 Negative Constraint:
  'Do not enable preview simulation in MVP unless explicitly requested.'
- Raises ThresholdPreviewDisabledException when flag is False.
"""

from __future__ import annotations

import builtins
import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from domain.models.exceptions import ThresholdPreviewDisabledException
from domain.tenant.context import TenantContext
from domain.thresholds.evaluator import ThresholdEvaluator
from domain.thresholds.models import (
    ThresholdEvaluationResult,
    ThresholdRule,
    ThresholdSourceType,
    ThresholdState,
)
from domain.thresholds.precedence import ResolvedThreshold

logger = logging.getLogger(__name__)

# Feature flag per Prompt 27 specification (Disabled by default in MVP)
ENABLE_THRESHOLD_PREVIEW: bool = False


class HistoricalDataPoint(BaseModel):
    """Historical metric sample for simulation."""

    timestamp: datetime
    value: Decimal | None


class SimulationStepResult(BaseModel):
    """Per-step outcome in simulation replay."""

    timestamp: datetime
    measured_value: Decimal | None
    evaluated_state: ThresholdState
    committed_state: ThresholdState
    is_alert_dispatched: bool
    is_flapping_suppressed: bool
    suppression_reason: str | None = None


class ThresholdPreviewSimulationResult(BaseModel):
    """Aggregated outcome of simulating a threshold rule against historical series."""

    id: str = Field(default_factory=lambda: f"sim-{uuid.uuid4().hex[:8]}")
    rule_id: str
    rule_name: str
    total_data_points: int
    total_transitions: int
    alerts_dispatched_count: int
    flapping_suppressed_count: int
    data_quality_issues_count: int
    time_in_state_percentages: dict[str, Decimal]
    steps: builtins.list[SimulationStepResult]
    simulated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def simulate_threshold_rule(
    *,
    rule: ThresholdRule,
    data_points: Sequence[HistoricalDataPoint],
    tenant_context: TenantContext,
    scope_id: str | None = None,
    override_enabled_flag: bool | None = None,
) -> ThresholdPreviewSimulationResult:
    """Simulates threshold rule evaluation over historical series.

    Strictly gated by ENABLE_THRESHOLD_PREVIEW flag.
    """
    flag_enabled = (
        override_enabled_flag if override_enabled_flag is not None else ENABLE_THRESHOLD_PREVIEW
    )
    if not flag_enabled:
        raise ThresholdPreviewDisabledException()

    # Isolated evaluator for simulation
    evaluator = ThresholdEvaluator()
    sim_entity_id = f"sim-{rule.id}"
    resolved = ResolvedThreshold(
        rule=rule,
        bands=rule.bands,
        source_type=ThresholdSourceType.LOCAL,
        source_id=rule.id,
        source_display=f"Simulated rule '{rule.name}'",
    )

    steps: builtins.list[SimulationStepResult] = []
    total_transitions = 0
    alerts_dispatched = 0
    flapping_suppressed = 0
    dq_issues = 0
    state_counts: dict[ThresholdState, int] = dict.fromkeys(ThresholdState, 0)

    for pt in data_points:
        eval_res: ThresholdEvaluationResult = evaluator.evaluate(
            entity_id=sim_entity_id,
            value=pt.value,
            resolved=resolved,
            scope_id=scope_id,
            evaluated_at=pt.timestamp,
            tenant_context=tenant_context,
        )
        if eval_res.transition_occurred:
            total_transitions += 1
        if eval_res.is_alert_dispatched:
            alerts_dispatched += 1
        if eval_res.is_flapping_suppressed:
            flapping_suppressed += 1
        if eval_res.is_data_quality_issue:
            dq_issues += 1

        state_counts[eval_res.committed_state] = state_counts.get(eval_res.committed_state, 0) + 1

        steps.append(
            SimulationStepResult(
                timestamp=pt.timestamp,
                measured_value=pt.value,
                evaluated_state=eval_res.evaluated_state,
                committed_state=eval_res.committed_state,
                is_alert_dispatched=eval_res.is_alert_dispatched,
                is_flapping_suppressed=eval_res.is_flapping_suppressed,
                suppression_reason=eval_res.suppression_reason,
            )
        )

    total_pts = len(data_points)
    time_in_state: dict[str, Decimal] = {}
    for st, count in state_counts.items():
        pct = (
            (Decimal(count) / Decimal(total_pts) * Decimal("100.0")).quantize(Decimal("0.1"))
            if total_pts > 0
            else Decimal("0.0")
        )
        time_in_state[st.value] = pct

    return ThresholdPreviewSimulationResult(
        rule_id=rule.id,
        rule_name=rule.name,
        total_data_points=total_pts,
        total_transitions=total_transitions,
        alerts_dispatched_count=alerts_dispatched,
        flapping_suppressed_count=flapping_suppressed,
        data_quality_issues_count=dq_issues,
        time_in_state_percentages=time_in_state,
        steps=steps,
    )
