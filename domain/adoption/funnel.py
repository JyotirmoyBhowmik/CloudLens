"""Scope & Tenant Onboarding Maturity Funnel Engine (Prompt 61 / BBP Section 43).

Enforces:
- Five Canonical Onboarding Milestones:
  1. CONNECTOR_ADDED (cloud credentials & provider enrolled)
  2. FIRST_DATA_INGESTED (first cost and usage telemetry landed)
  3. FIRST_BUDGET_SET (financial envelope declared)
  4. FIRST_ALERT_ACKNOWLEDGED (operational responsiveness proven)
  5. FIRST_TASK_CLOSED (governance and waste reduction loop closed)
- Stalled Scope Detection: Flags scopes stuck at a stage for >14 days without forward momentum.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from domain.adoption.models import (
    FunnelProgressStep,
    OnboardingFunnelReport,
    ScopeOnboardingFunnel,
)
from domain.models.enums import FunnelStage
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)

FUNNEL_STAGES_SEQUENCE = [
    FunnelStage.CONNECTOR_ADDED,
    FunnelStage.FIRST_DATA_INGESTED,
    FunnelStage.FIRST_BUDGET_SET,
    FunnelStage.FIRST_ALERT_ACKNOWLEDGED,
    FunnelStage.FIRST_TASK_CLOSED,
]


class OnboardingFunnelService:
    """Tracks and evaluates onboarding maturity progression for tenants and business units."""

    def build_funnel(
        self,
        scope_id: str,
        scope_type: str,
        milestone_timestamps: dict[FunnelStage, dt.datetime | None],
        start_time: dt.datetime | None = None,
        stalled_threshold_days: float = 14.0,
    ) -> ScopeOnboardingFunnel:
        """Constructs a detailed funnel record for an onboarding scope."""
        now = dt.datetime.now(dt.UTC)
        onboard_start = start_time or (milestone_timestamps.get(FunnelStage.CONNECTOR_ADDED) or now)

        steps: list[FunnelProgressStep] = []
        highest_stage = FunnelStage.CONNECTOR_ADDED
        is_stalled = False
        stalled_stage: FunnelStage | None = None

        for stage in FUNNEL_STAGES_SEQUENCE:
            achieved_time = milestone_timestamps.get(stage)
            if achieved_time is not None:
                elapsed = max(0.0, (achieved_time - onboard_start).total_seconds() / 86400.0)
                steps.append(
                    FunnelProgressStep(
                        stage=stage,
                        achieved=True,
                        achieved_at=achieved_time,
                        elapsed_days_from_start=round(elapsed, 1),
                    )
                )
                highest_stage = stage
            else:
                steps.append(
                    FunnelProgressStep(
                        stage=stage,
                        achieved=False,
                    )
                )

        # Check if stalled: if highest_stage is not the final stage, check elapsed time since highest stage
        if highest_stage != FunnelStage.FIRST_TASK_CLOSED:
            last_achieved_time = milestone_timestamps.get(highest_stage) or onboard_start
            days_in_stage = (now - last_achieved_time).total_seconds() / 86400.0
            if days_in_stage > stalled_threshold_days:
                is_stalled = True
                stalled_stage = highest_stage

        return ScopeOnboardingFunnel(
            scope_id=scope_id,
            scope_type=scope_type,
            current_stage=highest_stage,
            steps=steps,
            is_stalled=is_stalled,
            stalled_stage=stalled_stage,
            onboarding_started_at=onboard_start,
        )

    def generate_funnel_report(
        self,
        scope_milestones: list[dict[str, Any]],
        *,
        tenant_context: TenantContext,
    ) -> OnboardingFunnelReport:
        """Produces tenant-wide onboarding funnel analytics across all participating scopes."""
        funnels: list[ScopeOnboardingFunnel] = []
        completed = 0
        stalled = 0

        for item in scope_milestones:
            scope_id = item["scope_id"]
            scope_type = item.get("scope_type", "BUSINESS_UNIT")
            timestamps = item.get("milestones", {})
            start = item.get("start_time")

            f = self.build_funnel(
                scope_id=scope_id,
                scope_type=scope_type,
                milestone_timestamps=timestamps,
                start_time=start,
            )
            funnels.append(f)

            if f.current_stage == FunnelStage.FIRST_TASK_CLOSED:
                completed += 1
            if f.is_stalled:
                stalled += 1

        report = OnboardingFunnelReport(
            tenant_id=tenant_context.tenant_id,
            total_scopes=len(funnels),
            completed_funnels=completed,
            stalled_funnels=stalled,
            funnels=funnels,
        )

        logger.info(
            "Generated Onboarding Funnel report for tenant '%s': %d total scopes, %d completed, %d stalled.",
            tenant_context.tenant_id,
            len(funnels),
            completed,
            stalled,
        )
        return report
