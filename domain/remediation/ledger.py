"""Realised-Saving Ledger and Financial Accountability Engine (Prompt 51).

Enforces:
- Empirical ROI Recording: When a task carried an estimated financial impact
  and the condition demonstrably cleared, record the realised saving in the ledger.
- Method Attribution: Always store the calculation method used to compute the saving.
- Multi-dimensional Aggregation: Report cumulative realised saving by period, by team, and by category.
"""

from __future__ import annotations

import datetime as dt
import logging

from domain.models.enums import RealisedSavingMethod, TaskCategory
from domain.remediation.models import (
    RealisedSavingEntry,
    RealisedSavingReport,
    RemediationTask,
)
from domain.remediation.repository import RemediationRepository, get_remediation_repository
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)


class RealisedSavingLedger:
    """Manages recording and multi-dimensional reporting of empirical cost savings achieved via remediation."""

    def __init__(self, repository: RemediationRepository | None = None) -> None:
        self.repository = repository or get_remediation_repository()

    def record_saving(
        self,
        task: RemediationTask,
        *,
        amount: float | None = None,
        realised_amount: float | None = None,
        method: RealisedSavingMethod | None = None,
        period: str | None = None,
        verified_by: str | None = None,
        tenant_context: TenantContext,
    ) -> RealisedSavingEntry:
        """Records an empirical saving entry when a task is verified and closed."""
        target_amount = (
            amount
            if amount is not None
            else (
                realised_amount if realised_amount is not None else (task.estimated_saving or 0.0)
            )
        )
        calc_method = method or self._infer_method(task.category)

        now = dt.datetime.now(dt.UTC)
        target_period = period or now.strftime("%Y-%m")

        # Determine team or cost center from entity or assignee
        if task.assignee_type == "TEAM" and task.assignee_id:
            team_id = task.assignee_id
        else:
            team_id = (
                task.subject_entity.business_unit_id
                or task.subject_entity.cost_centre_id
                or task.assignee_id
                or "enterprise-finops"
            )

        entry = RealisedSavingEntry(
            tenant_id=tenant_context.tenant_id,
            task_id=task.id,
            entity_id=task.subject_entity.entity_id,
            category=task.category.value,
            team_id=team_id,
            period=target_period,
            realised_amount=round(float(target_amount), 2),
            currency="USD",
            calculation_method=calc_method,
            verified_at=now,
            verified_by=verified_by or "system-verifier",
        )

        saved = self.repository.save_saving_entry(entry, tenant_context=tenant_context)
        task.realised_saving = saved.realised_amount
        task.realised_saving_method = saved.calculation_method

        logger.info(
            f"Recorded realised saving of ${saved.realised_amount:.2f} for task '{task.id}' "
            f"[Category: {saved.category}, Team: {saved.team_id}, Method: {saved.calculation_method.value}]."
        )
        return saved

    def get_savings_report(
        self,
        *,
        tenant_context: TenantContext,
        start_period: str | None = None,
        end_period: str | None = None,
        period: str | None = None,
    ) -> RealisedSavingReport:
        """Produces cumulative realised saving report aggregated across period, team, and category."""
        entries = self.repository.list_saving_entries(tenant_context=tenant_context)

        # Period filtering
        if period:
            entries = [e for e in entries if e.period == period]
        if start_period:
            entries = [e for e in entries if e.period >= start_period]
        if end_period:
            entries = [e for e in entries if e.period <= end_period]

        total = sum(e.realised_amount for e in entries)
        by_period: dict[str, float] = {}
        by_team: dict[str, float] = {}
        by_cat: dict[str, float] = {}
        by_method: dict[str, float] = {}

        for e in entries:
            by_period[e.period] = round(by_period.get(e.period, 0.0) + e.realised_amount, 2)
            by_team[e.team_id] = round(by_team.get(e.team_id, 0.0) + e.realised_amount, 2)
            by_cat[e.category] = round(by_cat.get(e.category, 0.0) + e.realised_amount, 2)
            meth_val = e.calculation_method.value
            by_method[meth_val] = round(by_method.get(meth_val, 0.0) + e.realised_amount, 2)

        return RealisedSavingReport(
            total_realised_saving=round(total, 2),
            currency="USD",
            savings_by_period=by_period,
            savings_by_team=by_team,
            savings_by_category=by_cat,
            savings_by_method=by_method,
            entries_count=len(entries),
            entries=entries,
        )

    get_report = get_savings_report

    def _infer_method(self, category: TaskCategory) -> RealisedSavingMethod:
        """Infers the appropriate financial calculation method from task category."""
        if category == TaskCategory.SCHEDULE_BREACH:
            return RealisedSavingMethod.SCHEDULE_EXCESS_AVOIDANCE
        if category == TaskCategory.IDLE_RESOURCE:
            return RealisedSavingMethod.IDLE_TERMINATION_DELTA
        if category == TaskCategory.BUDGET_BREACH:
            return RealisedSavingMethod.RUN_RATE_ELIMINATION
        return RealisedSavingMethod.DIRECT_ESTIMATE_VERIFIED


_realised_saving_ledger_instance: RealisedSavingLedger | None = None


def get_realised_saving_ledger(
    repository: RemediationRepository | None = None,
) -> RealisedSavingLedger:
    """Returns singleton RealisedSavingLedger instance."""
    global _realised_saving_ledger_instance
    if _realised_saving_ledger_instance is None:
        _realised_saving_ledger_instance = RealisedSavingLedger(repository=repository)
    return _realised_saving_ledger_instance


def reset_realised_saving_ledger() -> None:
    """Resets ledger singleton for test isolation."""
    global _realised_saving_ledger_instance
    _realised_saving_ledger_instance = None
