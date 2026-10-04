"""Privacy-Respecting Aggregate Usage Telemetry Engine (Prompt 61 / BBP Section 43).

Enforces:
- Absolute Anti-Surveillance Invariant: Telemetry is strictly aggregated by system role
  and organizational team.
- Individual user tracking, profiling, surveillance, or leaderboard ranking is strictly
  rejected via IndividualSurveillanceForbiddenException.
- The interface plainly displays the privacy guarantee notice on all reports.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from domain.adoption.exceptions import IndividualSurveillanceForbiddenException
from domain.adoption.models import (
    PRIVACY_POLICY_STATEMENT,
    UsageAggregationRecord,
    UsageTelemetryEvent,
    UsageTelemetryReport,
)
from domain.models.enums import TelemetryActionType
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)

FORBIDDEN_IDENTIFIER_KEYS = {
    "user_id",
    "user",
    "username",
    "email",
    "user_email",
    "actor_id",
    "actor_name",
    "employee_id",
}


class UsageTelemetryService:
    """Manages aggregate, non-surveillance user behavior telemetry."""

    def __init__(self) -> None:
        # In-memory store: tenant_id -> list[UsageTelemetryEvent]
        self._events: dict[str, list[UsageTelemetryEvent]] = {}

    def record_usage(
        self,
        role: str,
        team_id: str,
        screen_or_feature: str,
        action_type: TelemetryActionType,
        result: str = "SUCCESS",
        *,
        tenant_context: TenantContext,
        timestamp: dt.datetime | None = None,
        **forbidden_kwargs: Any,
    ) -> UsageTelemetryEvent:
        """Records an operational usage event, enforcing strict absence of user-identifying attributes."""
        # 1. Enforce strict anti-surveillance privacy invariant
        for forbidden_key in FORBIDDEN_IDENTIFIER_KEYS:
            if forbidden_key in forbidden_kwargs:
                raise IndividualSurveillanceForbiddenException(
                    f"Privacy Policy Violation: Usage telemetry strictly prohibits individual "
                    f"surveillance attribute '{forbidden_key}'. Only role and team aggregation is permitted."
                )

        event = UsageTelemetryEvent(
            tenant_id=tenant_context.tenant_id,
            role=role.upper().strip(),
            team_id=team_id.strip(),
            screen_or_feature=screen_or_feature.strip(),
            action_type=action_type,
            result=result.upper().strip(),
            timestamp=timestamp or dt.datetime.now(dt.UTC),
        )

        self._events.setdefault(tenant_context.tenant_id, []).append(event)
        logger.debug(
            "Recorded aggregate telemetry: role=%s, team=%s, feature=%s, action=%s",
            event.role,
            event.team_id,
            event.screen_or_feature,
            event.action_type.value,
        )
        return event

    def generate_report(
        self,
        period: str,
        *,
        tenant_context: TenantContext,
    ) -> UsageTelemetryReport:
        """Generates an aggregated usage report by role and team with mandatory privacy disclosure."""
        tenant_id = tenant_context.tenant_id
        events = self._events.get(tenant_id, [])

        by_role: dict[str, dict[str, UsageAggregationRecord]] = {}
        by_team: dict[str, dict[str, UsageAggregationRecord]] = {}

        for ev in events:
            # 1. Aggregation by Role
            role_dict = by_role.setdefault(ev.role, {})
            if ev.screen_or_feature not in role_dict:
                role_dict[ev.screen_or_feature] = UsageAggregationRecord(
                    role=ev.role,
                    team_id="ALL",
                    screen_or_feature=ev.screen_or_feature,
                )
            rec_role = role_dict[ev.screen_or_feature]
            if ev.action_type in {
                TelemetryActionType.SCREEN_VIEW,
                TelemetryActionType.DASHBOARD_VIEWED,
            }:
                rec_role.view_count += 1
            else:
                rec_role.action_count += 1

            if ev.result == "SUCCESS":
                rec_role.success_count += 1
            else:
                rec_role.failure_count += 1

            rec_role.last_used_at = ev.timestamp

            # 2. Aggregation by Team
            team_dict = by_team.setdefault(ev.team_id, {})
            if ev.screen_or_feature not in team_dict:
                team_dict[ev.screen_or_feature] = UsageAggregationRecord(
                    role="ALL",
                    team_id=ev.team_id,
                    screen_or_feature=ev.screen_or_feature,
                )
            rec_team = team_dict[ev.screen_or_feature]
            if ev.action_type in {
                TelemetryActionType.SCREEN_VIEW,
                TelemetryActionType.DASHBOARD_VIEWED,
            }:
                rec_team.view_count += 1
            else:
                rec_team.action_count += 1

            if ev.result == "SUCCESS":
                rec_team.success_count += 1
            else:
                rec_team.failure_count += 1

            rec_team.last_used_at = ev.timestamp

        # Compute success rates
        for role_recs in by_role.values():
            for r in role_recs.values():
                total = r.success_count + r.failure_count
                r.success_rate = round((r.success_count / total * 100.0) if total > 0 else 100.0, 1)

        for team_recs in by_team.values():
            for t in team_recs.values():
                total = t.success_count + t.failure_count
                t.success_rate = round((t.success_count / total * 100.0) if total > 0 else 100.0, 1)

        report = UsageTelemetryReport(
            tenant_id=tenant_id,
            privacy_policy_notice=PRIVACY_POLICY_STATEMENT,
            period=period,
            aggregations_by_role={k: list(v.values()) for k, v in by_role.items()},
            aggregations_by_team={k: list(v.values()) for k, v in by_team.items()},
            total_events=len(events),
        )

        logger.info(
            "Generated privacy-preserving usage report for tenant '%s' (%d total events across %d roles, %d teams).",
            tenant_id,
            len(events),
            len(by_role),
            len(by_team),
        )
        return report
