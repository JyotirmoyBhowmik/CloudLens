"""Governance Operations Telemetry and Process Velocity Engine (Prompt 61 / BBP Section 43).

Enforces:
- Process Health: verifies the FinOps & governance machine is actively operating rather than idling.
- Flow Metrics: alerts raised vs acknowledged vs actioned; tasks created vs closed vs verified.
- Time Velocity: Mean Time to Acknowledge (MTTA) and Mean Time to Close (MTTC) in hours.
- SLA Compliance: overdue task aging brackets (1-7 days, 8-30 days, 30+ days).
- Safety Inspection: exemption granted and bypass counts.
- Longitudinal Trends: open-versus-closed volume trajectory over time.
"""

from __future__ import annotations

import datetime as dt
import logging

from domain.adoption.models import (
    AlertGovernanceMetrics,
    ExemptionBypassMetrics,
    GovernanceOperationsReport,
    GovernanceTrendPoint,
    OverdueAgingBreakdown,
    TaskGovernanceMetrics,
)
from domain.alerting.models import AlertEntity
from domain.models.enums import AlertLifecycleStatus, TaskState
from domain.remediation.models import RemediationTask
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)


class GovernanceMetricsService:
    """Computes operational throughput, velocity, and process adherence metrics."""

    def compute_governance_report(
        self,
        period: str,
        alerts: list[AlertEntity],
        tasks: list[RemediationTask],
        exemptions_count: int = 0,
        bypasses_count: int = 0,
        active_exemptions_count: int = 0,
        *,
        tenant_context: TenantContext,
    ) -> GovernanceOperationsReport:
        """Computes comprehensive governance process health metrics for a tenant."""
        now = dt.datetime.now(dt.UTC)

        # 1. Alert Metrics
        raised_count = len(alerts)
        acknowledged_count = sum(
            1 for a in alerts if a.status in {AlertLifecycleStatus.ACKNOWLEDGED, AlertLifecycleStatus.RESOLVED}
        )
        actioned_count = sum(
            1 for a in alerts if a.status in {AlertLifecycleStatus.RESOLVED, AlertLifecycleStatus.AUTO_RESOLVED}
        )

        ack_times: list[float] = []
        for a in alerts:
            if a.acknowledged_at:
                created = a.created_at if hasattr(a, "created_at") else a.evidence.observed_at
                delta = (a.acknowledged_at - created).total_seconds() / 3600.0
                if delta >= 0:
                    ack_times.append(delta)

        mtta = round(sum(ack_times) / len(ack_times), 2) if ack_times else 0.0
        ack_rate = round((acknowledged_count / raised_count * 100.0) if raised_count > 0 else 100.0, 1)

        alert_metrics = AlertGovernanceMetrics(
            raised_count=raised_count,
            acknowledged_count=acknowledged_count,
            actioned_count=actioned_count,
            mean_time_to_acknowledge_hours=mtta,
            acknowledgement_rate=ack_rate,
        )

        # 2. Task Metrics
        created_count = len(tasks)
        closed_count = sum(1 for t in tasks if t.state in {TaskState.CLOSED, TaskState.RESOLVED})
        verified_count = sum(1 for t in tasks if t.state in {TaskState.VERIFIED, TaskState.CLOSED})

        close_times: list[float] = []
        for t in tasks:
            if t.state in {TaskState.CLOSED, TaskState.RESOLVED}:
                # Calculate duration from creation to last history change or update
                created = t.created_at
                resolved_time = t.updated_at
                delta = (resolved_time - created).total_seconds() / 3600.0
                if delta >= 0:
                    close_times.append(delta)

        mttc = round(sum(close_times) / len(close_times), 2) if close_times else 0.0
        closure_rate = round((closed_count / created_count * 100.0) if created_count > 0 else 100.0, 1)

        task_metrics = TaskGovernanceMetrics(
            created_count=created_count,
            closed_count=closed_count,
            verified_count=verified_count,
            mean_time_to_close_hours=mttc,
            closure_rate=closure_rate,
        )

        # 3. Overdue Aging Brackets
        overdue_1_7 = 0
        overdue_8_30 = 0
        overdue_30_plus = 0

        for t in tasks:
            if t.state not in {TaskState.CLOSED, TaskState.RESOLVED, TaskState.REJECTED}:
                if t.due_date and t.due_date < now:
                    days_overdue = (now - t.due_date).total_seconds() / 86400.0
                    if days_overdue <= 7.0:
                        overdue_1_7 += 1
                    elif days_overdue <= 30.0:
                        overdue_8_30 += 1
                    else:
                        overdue_30_plus += 1

        total_overdue = overdue_1_7 + overdue_8_30 + overdue_30_plus
        aging = OverdueAgingBreakdown(
            overdue_1_to_7_days=overdue_1_7,
            overdue_8_to_30_days=overdue_8_30,
            overdue_30_plus_days=overdue_30_plus,
            total_overdue=total_overdue,
        )

        # 4. Exemption and Bypass
        exemptions = ExemptionBypassMetrics(
            exemption_count=exemptions_count,
            bypass_count=bypasses_count,
            active_exemptions=active_exemptions_count,
        )

        # 5. Longitudinal Trends
        active_tasks = created_count - closed_count
        trend_point = GovernanceTrendPoint(
            date_label=period,
            open_tasks=max(active_tasks, 0),
            closed_tasks=closed_count,
            active_alerts=raised_count - actioned_count,
        )

        report = GovernanceOperationsReport(
            period=period,
            tenant_id=tenant_context.tenant_id,
            alerts=alert_metrics,
            tasks=task_metrics,
            overdue_aging=aging,
            exemptions=exemptions,
            trends=[trend_point],
        )

        logger.info(
            "Computed governance operations report for period '%s' [Alerts Acked: %d/%d, Tasks Closed: %d/%d, Overdue: %d]",
            period,
            acknowledged_count,
            raised_count,
            closed_count,
            created_count,
            total_overdue,
        )
        return report
