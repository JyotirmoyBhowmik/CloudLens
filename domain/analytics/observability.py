"""Extract Observability, SLA Tracking & Lateness/Emptiness Alerting (Prompt 56).

Enforces:
- Full observability over extract executions: row count, duration, schema version, watermark, failure reason.
- Automated SLA lateness detection triggering ANALYTICAL_EXTRACT_LATE_OR_EMPTY_ALERT_DISPATCHED.
- Automated emptiness detection raising an alert when active partitions produce zero records.
- Immutable cryptographic audit trail logging via AuditService.
"""

from __future__ import annotations

import datetime as dt
import logging

from domain.alerting.models import AlertEntity, AlertEvidence, AlertLifecycleStatus
from domain.alerting.service import AlertService, get_alert_service
from domain.analytics.models import AnalyticsExtractJob
from domain.audit.service import AuditService, get_audit_service
from domain.models.enums import (
    AlertSeverity,
    AlertType,
    AuditEventType,
)
from domain.models.exceptions import EmptyExtractException, LateExtractException
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)


class ExtractObservabilityEngine:
    """Observability monitor tracking execution history and enforcing SLA / emptiness alerting."""

    def __init__(
        self,
        audit_service: AuditService | None = None,
        alert_service: AlertService | None = None,
    ) -> None:
        self.audit_service = audit_service or get_audit_service()
        self.alert_service = alert_service or get_alert_service()

    def record_job_completion(
        self, job: AnalyticsExtractJob, *, tenant_context: TenantContext
    ) -> None:
        """Records extract job metrics in the immutable audit stream."""
        self.audit_service.record_event(
            tenant_context=tenant_context,
            event_type=AuditEventType.REPORT_GENERATED,
            actor=job.service_identity_id,
            action="ANALYTICAL_EXTRACT_COMPLETED",
            resource_type="ANALYTICAL_EXTRACT",
            resource_id=job.id,
            payload={
                "extract_id": job.id,
                "period": job.period,
                "version": job.version,
                "row_count": job.row_count,
                "duration_ms": job.duration_ms,
                "schema_version": job.schema_version,
                "watermark": job.watermark,
                "storage_destination": job.storage_destination,
            },
        )
        logger.info(
            "Analytical extract completed successfully",
            extra={
                "tenant_id": tenant_context.tenant_id,
                "extract_id": job.id,
                "rows": job.row_count,
                "duration_ms": job.duration_ms,
            },
        )

    def evaluate_emptiness(
        self,
        job: AnalyticsExtractJob,
        *,
        tenant_context: TenantContext,
        raise_exception: bool = False,
    ) -> bool:
        """Evaluates whether an extract for an active period produced zero records.

        Dispatches ANALYTICAL_EXTRACT_LATE_OR_EMPTY_ALERT_DISPATCHED if empty.
        """
        if job.row_count == 0:
            details = {
                "extract_id": job.id,
                "period": job.period,
                "reason": "EXTRACT_EMPTY",
                "message": f"Analytical extract for period {job.period} completed with 0 records.",
            }

            # 1. Dispatch Audit Event
            self.audit_service.record_event(
                tenant_context=tenant_context,
                event_type=AuditEventType.ANALYTICAL_EXTRACT_LATE_OR_EMPTY_ALERT_DISPATCHED,
                actor="OBSERVABILITY_MONITOR",
                action="EXTRACT_EMPTINESS_DETECTED",
                resource_type="ANALYTICAL_EXTRACT",
                resource_id=job.id,
                payload=details,
            )

            # 2. Dispatch Contextual/System Alert
            evidence = AlertEvidence(
                summary=f"Analytical extract for period {job.period} completed with 0 records.",
                context=details,
            )
            alert = AlertEntity(
                tenant_id=tenant_context.tenant_id,
                alert_type=AlertType.ANALYTICAL_EXTRACT_LATE_OR_EMPTY,
                severity=AlertSeverity.HIGH,
                title=f"Analytical Extract Empty: Period {job.period}",
                description=f"Scheduled analytical extract {job.id} for period {job.period} yielded zero records.",
                source="ExtractObservabilityEngine",
                rule_id="RULE-EXTRACT-NON-EMPTY",
                affected_resource_id=job.id,
                scope_type="ACCOUNT",
                scope_id=job.tenant_id,
                current_value=0.0,
                threshold_value=1.0,
                evidence=evidence,
                status=AlertLifecycleStatus.ACTIVE,
            )
            self.alert_service.repository.save(alert, tenant_context=tenant_context)

            if raise_exception:
                raise EmptyExtractException(period=job.period, tenant_id=tenant_context.tenant_id)
            return True

        return False

    def evaluate_lateness(
        self,
        *,
        scheduled_for: dt.datetime,
        actual_completion: dt.datetime | None,
        sla_window_minutes: float = 60.0,
        schedule_id: str,
        tenant_context: TenantContext,
        raise_exception: bool = False,
    ) -> bool:
        """Evaluates whether an extract completed within the SLA window.

        Dispatches ANALYTICAL_EXTRACT_LATE_OR_EMPTY_ALERT_DISPATCHED if late.
        """
        now = dt.datetime.now(dt.UTC)
        completion = actual_completion or now
        delay_minutes = (completion - scheduled_for).total_seconds() / 60.0

        if delay_minutes > sla_window_minutes:
            details = {
                "schedule_id": schedule_id,
                "scheduled_for": scheduled_for.isoformat(),
                "completion_time": completion.isoformat(),
                "delay_minutes": round(delay_minutes, 1),
                "sla_window_minutes": sla_window_minutes,
                "reason": "EXTRACT_LATE",
            }

            # 1. Audit event
            self.audit_service.record_event(
                tenant_context=tenant_context,
                event_type=AuditEventType.ANALYTICAL_EXTRACT_LATE_OR_EMPTY_ALERT_DISPATCHED,
                actor="OBSERVABILITY_MONITOR",
                action="EXTRACT_LATENESS_DETECTED",
                resource_type="ANALYTICAL_SCHEDULE",
                resource_id=schedule_id,
                payload=details,
            )

            # 2. Alert
            evidence = AlertEvidence(
                summary=f"Extract schedule {schedule_id} exceeded delivery SLA by {delay_minutes:.1f} minutes.",
                context=details,
            )
            alert = AlertEntity(
                tenant_id=tenant_context.tenant_id,
                alert_type=AlertType.ANALYTICAL_EXTRACT_LATE_OR_EMPTY,
                severity=AlertSeverity.WARNING,
                title=f"Analytical Extract Delivery Late: {schedule_id}",
                description=f"Extract schedule {schedule_id} exceeded delivery SLA by {delay_minutes:.1f} minutes.",
                source="ExtractObservabilityEngine",
                rule_id="RULE-EXTRACT-SLA-WINDOW",
                affected_resource_id=schedule_id,
                scope_type="ACCOUNT",
                scope_id=tenant_context.tenant_id,
                current_value=delay_minutes,
                threshold_value=sla_window_minutes,
                evidence=evidence,
                status=AlertLifecycleStatus.ACTIVE,
            )
            self.alert_service.repository.save(alert, tenant_context=tenant_context)

            if raise_exception:
                raise LateExtractException(schedule_id=schedule_id, delay_minutes=delay_minutes)
            return True

        return False
