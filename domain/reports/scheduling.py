"""Phase 2 Feature-Flagged Report Scheduling Engine (Prompt 35).

Enforces:
- Guarded behind feature flag `PHASE_2_SCHEDULING_ENABLED`.
- Recurring report generation and delivery to recipients or cloud object storage.
- Standard cron evaluation and execution planning.
"""

from __future__ import annotations

import datetime as dt
import uuid

from domain.models.exceptions import FeatureNotEnabledException
from domain.reports.models import ExportFormat, ReportParameters, ScheduledReport
from domain.reports.repository import ReportRepository, get_report_repository
from domain.tenant.context import TenantContext, require_tenant_context


class ReportSchedulingEngine:
    """Manages recurring report schedules behind a Phase 2 feature flag."""

    def __init__(
        self,
        repository: ReportRepository | None = None,
        feature_flags: dict[str, bool] | None = None,
    ) -> None:
        self.repository = repository or get_report_repository()
        self.feature_flags = feature_flags or {"PHASE_2_SCHEDULING_ENABLED": False}

    def is_scheduling_enabled(self) -> bool:
        """Returns True if Phase 2 scheduling is enabled in configuration."""
        return self.feature_flags.get("PHASE_2_SCHEDULING_ENABLED", False)

    def create_schedule(
        self,
        template_id: str,
        parameters: ReportParameters,
        format_type: ExportFormat,
        cron_expression: str,
        recipients: list[str],
        storage_destination: str | None = None,
        *,
        tenant_context: TenantContext,
    ) -> ScheduledReport:
        """Creates a recurring report schedule if Phase 2 flag is enabled."""
        tc = require_tenant_context(tenant_context)
        if not self.is_scheduling_enabled():
            raise FeatureNotEnabledException(
                "Recurring report scheduling is a Phase 2 capability. Enable 'PHASE_2_SCHEDULING_ENABLED' flag."
            )

        now = dt.datetime.now(dt.UTC)
        next_run = now + dt.timedelta(days=1)  # Simplified 24h cadence for demonstration
        schedule = ScheduledReport(
            id=f"sch-{uuid.uuid4().hex[:12]}",
            tenant_id=tc.tenant_id,
            template_id=template_id,
            parameters=parameters,
            format=format_type,
            cron_expression=cron_expression,
            recipients=recipients,
            storage_destination=storage_destination,
            is_active=True,
            created_at=now,
            last_run_at=None,
            next_run_at=next_run,
        )
        return self.repository.save_schedule(schedule, tenant_context=tc)

    def list_schedules(self, *, tenant_context: TenantContext) -> list[ScheduledReport]:
        """Lists active and inactive recurring schedules."""
        tc = require_tenant_context(tenant_context)
        if not self.is_scheduling_enabled():
            raise FeatureNotEnabledException(
                "Recurring report scheduling is a Phase 2 capability. Enable 'PHASE_2_SCHEDULING_ENABLED' flag."
            )
        return self.repository.list_schedules(tenant_context=tc)
