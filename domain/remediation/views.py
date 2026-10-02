"""Accountability Views and Trend Reporting Engine (Prompt 51).

Enforces:
- Views: My Tasks, My Team's Tasks, Tasks by Application, Tasks by Business Unit,
  Overdue Tasks, and Ageing Distribution.
- Leaderboard-Free Governance: Report trends over time, never individual rankings.
"""

from __future__ import annotations

import datetime as dt
import logging

from domain.models.enums import TaskState
from domain.remediation.models import (
    AgeingBucket,
    AgeingReport,
    RemediationTask,
    TrendPoint,
    TrendReport,
)
from domain.remediation.repository import RemediationRepository, get_remediation_repository
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)

TERMINAL_STATES = {TaskState.CLOSED, TaskState.REJECTED, TaskState.DUPLICATE}


class AccountabilityEngine:
    """Surfaces contextual task visibility across users, teams, and organizational boundaries."""

    def __init__(self, repository: RemediationRepository | None = None) -> None:
        self.repository = repository or get_remediation_repository()

    def get_my_tasks(
        self,
        user_id: str,
        *,
        tenant_context: TenantContext,
        include_terminal: bool = False,
    ) -> list[RemediationTask]:
        """Returns remediation tasks assigned to the specific user."""
        all_tasks = self.repository.list(tenant_context=tenant_context, limit=1000)
        return [
            t
            for t in all_tasks
            if t.assignee_id == user_id and (include_terminal or t.state not in TERMINAL_STATES)
        ]

    def get_my_team_tasks(
        self,
        team_id: str,
        *,
        tenant_context: TenantContext,
        include_terminal: bool = False,
    ) -> list[RemediationTask]:
        """Returns remediation tasks assigned to a team or within the team's scope."""
        all_tasks = self.repository.list(tenant_context=tenant_context, limit=1000)
        return [
            t
            for t in all_tasks
            if (t.assignee_id == team_id or t.subject_entity.business_unit_id == team_id)
            and (include_terminal or t.state not in TERMINAL_STATES)
        ]

    get_team_tasks = get_my_team_tasks

    def get_tasks_by_application(
        self,
        application_id: str,
        *,
        tenant_context: TenantContext,
        include_terminal: bool = False,
    ) -> list[RemediationTask]:
        """Returns remediation tasks belonging to a specific application."""
        all_tasks = self.repository.list(tenant_context=tenant_context, limit=1000)
        return [
            t
            for t in all_tasks
            if (
                t.subject_entity.application_id == application_id
                or t.subject_entity.scope_id == application_id
            )
            and (include_terminal or t.state not in TERMINAL_STATES)
        ]

    def get_tasks_by_business_unit(
        self,
        business_unit_id: str,
        *,
        tenant_context: TenantContext,
        include_terminal: bool = False,
    ) -> list[RemediationTask]:
        """Returns remediation tasks belonging to a specific business unit."""
        all_tasks = self.repository.list(tenant_context=tenant_context, limit=1000)
        return [
            t
            for t in all_tasks
            if (
                t.subject_entity.business_unit_id == business_unit_id
                or t.subject_entity.cost_centre_id == business_unit_id
            )
            and (include_terminal or t.state not in TERMINAL_STATES)
        ]

    def get_overdue_tasks(
        self,
        *,
        tenant_context: TenantContext,
    ) -> list[RemediationTask]:
        """Returns open remediation tasks that have breached their SLA due date."""
        all_tasks = self.repository.list(tenant_context=tenant_context, limit=1000)
        now = dt.datetime.now(dt.UTC)
        return [t for t in all_tasks if t.state not in TERMINAL_STATES and t.due_date < now]

    def get_ageing_report(
        self,
        *,
        tenant_context: TenantContext,
    ) -> AgeingReport:
        """Categorises open remediation tasks into 0-7d, 8-30d, 31-90d, and >90d age brackets."""
        all_tasks = self.repository.list(tenant_context=tenant_context, limit=1000)
        open_tasks = [t for t in all_tasks if t.state not in TERMINAL_STATES]
        now = dt.datetime.now(dt.UTC)

        b0_7: list[RemediationTask] = []
        b8_30: list[RemediationTask] = []
        b31_90: list[RemediationTask] = []
        b_over_90: list[RemediationTask] = []

        for t in open_tasks:
            age_days = (now - t.created_at).total_seconds() / 86400.0
            if age_days <= 7.0:
                b0_7.append(t)
            elif age_days <= 30.0:
                b8_30.append(t)
            elif age_days <= 90.0:
                b31_90.append(t)
            else:
                b_over_90.append(t)

        def _make_bucket(name: str, tasks: list[RemediationTask]) -> AgeingBucket:
            return AgeingBucket(
                bucket_name=name,
                count=len(tasks),
                total_estimated_saving=round(sum(t.estimated_saving or 0.0 for t in tasks), 2),
                task_ids=[t.id for t in tasks],
            )

        return AgeingReport(
            total_open_tasks=len(open_tasks),
            bracket_0_to_7_days=_make_bucket("0-7 Days", b0_7),
            bracket_8_to_30_days=_make_bucket("8-30 Days", b8_30),
            bracket_31_to_90_days=_make_bucket("31-90 Days", b31_90),
            bracket_over_90_days=_make_bucket("90+ Days", b_over_90),
        )

    def get_open_vs_closed_trend(
        self,
        *,
        tenant_context: TenantContext,
        window_days: int = 30,
    ) -> TrendReport:
        """Produces a leaderboard-free daily timeseries comparing opened vs closed tasks."""
        all_tasks = self.repository.list(tenant_context=tenant_context, limit=2000)
        now = dt.datetime.now(dt.UTC)
        start_date = (now - dt.timedelta(days=window_days)).date()

        # Map date -> (opened, closed, savings)
        daily_opened: dict[str, int] = {}
        daily_closed: dict[str, int] = {}
        daily_savings: dict[str, float] = {}

        for t in all_tasks:
            c_date = t.created_at.date()
            if c_date >= start_date:
                c_str = c_date.strftime("%Y-%m-%d")
                daily_opened[c_str] = daily_opened.get(c_str, 0) + 1

            if t.closed_at is not None:
                cl_date = t.closed_at.date()
                if cl_date >= start_date:
                    cl_str = cl_date.strftime("%Y-%m-%d")
                    daily_closed[cl_str] = daily_closed.get(cl_str, 0) + 1
                    if t.realised_saving:
                        daily_savings[cl_str] = round(
                            daily_savings.get(cl_str, 0.0) + t.realised_saving, 2
                        )

        # Assemble full contiguous timeline
        points: list[TrendPoint] = []
        tot_opened = 0
        tot_closed = 0

        for i in range(window_days + 1):
            curr_d = start_date + dt.timedelta(days=i)
            d_str = curr_d.strftime("%Y-%m-%d")
            op = daily_opened.get(d_str, 0)
            cl = daily_closed.get(d_str, 0)
            sav = daily_savings.get(d_str, 0.0)
            tot_opened += op
            tot_closed += cl
            points.append(
                TrendPoint(
                    date=d_str,
                    opened_count=op,
                    closed_count=cl,
                    net_backlog_delta=op - cl,
                    realised_savings_amount=sav,
                )
            )

        return TrendReport(
            window_days=window_days,
            data_points=points,
            total_opened_in_window=tot_opened,
            total_closed_in_window=tot_closed,
            net_backlog_change=tot_opened - tot_closed,
        )

    get_trend_report = get_open_vs_closed_trend
