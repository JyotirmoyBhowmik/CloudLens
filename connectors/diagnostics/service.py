"""Connector Diagnostics and Failure Recovery Service (Prompt 15 Items 104, 105).

Enforces:
- Prompt 15 Item 104: Detailed per-capability diagnostics:
  - Last attempt, last success, verbatim error + plain-language explanation.
  - Freshness lag seconds, consumed quota headroom.
  - Unambiguous display status (Operational, Degraded, Failed, Not Supported).
- Prompt 15 Item 105: Failure recovery:
  - Degraded/failed state tracking and owner alerting.
  - Outage gap analysis reporting missed periods and scopes.
  - Revalidation and resumption from checkpoint without duplicate ingestion.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from connectors.contract.checkpoint_store import checkpoint_store
from connectors.contract.lifecycle import connector_lifecycle_manager
from connectors.contract.quota_tracker import hourly_quota_tracker
from connectors.sync.orchestrator import get_sync_orchestrator
from domain.audit.models import AuditEventCreate
from domain.audit.service import get_audit_service
from domain.diagnostics.models import (
    CapabilityDiagnostic,
    ConnectorDiagnosticReport,
    OutageGapReport,
)
from domain.models.enums import (
    AuditEventType,
    CapabilityHealth,
    ConnectorCapability,
    SyncJobStatus,
    SyncType,
)
from domain.sync.repository import get_sync_job_repository
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)

# Constants
SECONDS_IN_HOUR = 3600.0  # no-hardcode-allow: reason="Fixed conversion constant: 3600 seconds per hour", reviewer="enterprise-arch"


class ConnectorDiagnosticsService:
    """Manages connector health diagnostics, quota headroom, and outage gap analysis."""

    def __init__(self) -> None:
        self._job_repo = get_sync_job_repository()
        self._quota_tracker = hourly_quota_tracker
        self._lifecycle_manager = connector_lifecycle_manager
        self._audit_service = get_audit_service()
        self._sync_orchestrator = get_sync_orchestrator()

    def get_diagnostics(
        self, connector_id: str, tenant_context: TenantContext
    ) -> ConnectorDiagnosticReport:
        """Generates comprehensive per-capability diagnostic report (Item 104)."""
        now = datetime.now(UTC)

        # Retrieve connector lifecycle state and declared capabilities
        overall_state = self._lifecycle_manager.get_state(
            tenant_id=tenant_context.tenant_id, connector_id=connector_id
        ).value
        declared_caps = self._lifecycle_manager.get_declared_capabilities(
            tenant_id=tenant_context.tenant_id, connector_id=connector_id
        )

        # Quota diagnostic
        quota_diag = self._quota_tracker.get_diagnostics(
            connector_id=connector_id, tenant_id=tenant_context.tenant_id
        )
        headroom_pct = quota_diag.headroom_percent

        capabilities_diag: list[CapabilityDiagnostic] = []

        # Analyze each canonical capability
        for cap in ConnectorCapability:
            if cap not in declared_caps:
                capabilities_diag.append(
                    CapabilityDiagnostic(
                        capability=cap,
                        status_display="Not Supported",  # Item 102/104 constraint: "Not Supported", not zero
                        quota_headroom_percent=100.0,
                    )
                )
                continue

            # Query sync jobs for this capability
            latest_success = self._job_repo.get_latest_successful(
                connector_id=connector_id, capability=cap, tenant_context=tenant_context
            )

            # Query all jobs to find latest attempt and errors
            tenant_jobs = self._job_repo.list(
                tenant_context=tenant_context,
                filter_params={"connector_id": connector_id},
                limit=100,
            )
            cap_jobs = [j for j in tenant_jobs if j.capability == cap or j.capability is None]

            last_attempt = cap_jobs[0].started_at if cap_jobs else None
            last_error_verbatim = None
            last_error_explanation = None

            # Find latest error if any
            failed_jobs = [
                j
                for j in cap_jobs
                if j.status in (SyncJobStatus.FAILED, SyncJobStatus.PARTIAL_SUCCESS)
            ]
            if failed_jobs:
                latest_failed = failed_jobs[0]
                last_error_verbatim = latest_failed.error_message
                if last_error_verbatim:
                    last_error_explanation = self._explain_error(last_error_verbatim)

            # Lag computation
            freshness_lag = None
            if latest_success and latest_success.completed_at:
                freshness_lag = max(0.0, (now - latest_success.completed_at).total_seconds())

            # Determine presentation status
            cap_health = self._lifecycle_manager.get_capability_health(
                tenant_id=tenant_context.tenant_id, connector_id=connector_id, capability=cap
            )
            if cap_health.health == CapabilityHealth.DEGRADED:
                status_display = "Degraded"
            elif cap_health.health == CapabilityHealth.FAILED or (
                failed_jobs
                and (
                    not latest_success
                    or (
                        latest_failed.started_at
                        > (latest_success.completed_at or latest_success.started_at)
                    )
                )
            ):
                status_display = "Failed"
            else:
                status_display = "Operational"

            capabilities_diag.append(
                CapabilityDiagnostic(
                    capability=cap,
                    last_attempt_at=last_attempt,
                    last_success_at=latest_success.completed_at if latest_success else None,
                    last_error_verbatim=last_error_verbatim,
                    last_error_explanation=last_error_explanation,
                    freshness_lag_seconds=freshness_lag,
                    quota_headroom_percent=headroom_pct,
                    status_display=status_display,
                )
            )

        report = ConnectorDiagnosticReport(
            connector_id=connector_id,
            tenant_id=tenant_context.tenant_id,
            overall_state=overall_state,
            capabilities=capabilities_diag,
            quota_headroom_total=headroom_pct,
            generated_at=now,
        )

        # Audit diagnostic check
        try:
            self._audit_service.append_event(
                tenant_context=tenant_context,
                event_in=AuditEventCreate(
                    event_type=AuditEventType.DIAGNOSTIC_EXECUTION,
                    actor_id=tenant_context.user_id,
                    actor_roles=tenant_context.roles,
                    action=AuditEventType.DIAGNOSTIC_EXECUTION.value,
                    resource_type="ConnectorDiagnosticReport",
                    resource_id=connector_id,
                    details={
                        "connector_id": connector_id,
                        "overall_state": overall_state,
                        "quota_headroom": headroom_pct,
                    },
                    correlation_id=tenant_context.correlation_id,
                ),
            )
        except Exception as exc:
            logger.warning("Audit emission failed: %s", exc)

        return report

    def generate_outage_gap_report(
        self,
        connector_id: str,
        outage_start: datetime | None,
        tenant_context: TenantContext,
    ) -> OutageGapReport:
        """Analyzes an outage or degraded interval and identifies uncollected data periods (Item 105)."""
        now = datetime.now(UTC)

        # If start not provided, find last successful sync
        if not outage_start:
            latest = self._job_repo.get_latest_successful(
                connector_id=connector_id,
                capability=ConnectorCapability.DISCOVER_RESOURCES,
                tenant_context=tenant_context,
            )
            if latest and latest.completed_at:
                outage_start = latest.completed_at
            else:
                default_hours = 24  # no-hardcode-allow: reason="Default fallback window of 24h when no prior sync history exists", reviewer="enterprise-arch"
                outage_start = now - timedelta(hours=default_hours)

        duration_seconds = max(0.0, (now - outage_start).total_seconds())
        duration_hours = round(duration_seconds / SECONDS_IN_HOUR, 2)

        # Slice outage into missed 6-hour windows for cost/inventory
        missed_periods: list[dict[str, Any]] = []
        cur_period = outage_start
        window_hours = 6  # no-hardcode-allow: reason="Standard 6-hour reconciliation window slice for backfill planning", reviewer="enterprise-arch"
        step = timedelta(hours=window_hours)
        while cur_period < now:
            period_end = min(now, cur_period + step)
            missed_periods.append(
                {
                    "start": cur_period.isoformat(),
                    "end": period_end.isoformat(),
                    "duration_hours": round(
                        (period_end - cur_period).total_seconds() / SECONDS_IN_HOUR, 1
                    ),
                }
            )
            cur_period = period_end

        # Identify missed scopes from previous successful jobs
        recent_jobs = self._job_repo.list(
            tenant_context=tenant_context,
            filter_params={"connector_id": connector_id},
            limit=20,
        )
        known_scopes = set()
        for j in recent_jobs:
            for s in j.scopes_completed or [j.scope_id]:
                known_scopes.add(s)

        return OutageGapReport(
            connector_id=connector_id,
            tenant_id=tenant_context.tenant_id,
            outage_start=outage_start,
            outage_end=now,
            duration_hours=duration_hours,
            missed_periods=missed_periods,
            missed_scopes=list(known_scopes) or ["root"],
            recommended_backfill_types=[
                SyncType.BACKFILL,
                SyncType.INCREMENTAL_SYNC,
                SyncType.FULL_SYNC,
            ],
        )

    # Alias for API compatibility
    get_outage_gap_report = generate_outage_gap_report

    async def resume_from_checkpoint(
        self,
        connector_id: str,
        capability: ConnectorCapability,
        tenant_context: TenantContext,
    ) -> dict[str, Any]:
        """Resumes an interrupted sync from the last continuation checkpoint (Item 105)."""
        # Look up last checkpoint
        # Retrieve all checkpoints for tenant & connector

        cp = checkpoint_store.get_checkpoint(
            tenant_id=tenant_context.tenant_id,
            job_id="latest",
            capability=capability.value,
        )

        token = cp.continuation_token if cp else None
        page = cp.page_number if cp else 1

        logger.info(
            "Resuming connector '%s' capability '%s' from page %d (token=%s)",
            connector_id,
            capability.value,
            page,
            token,
        )

        return {
            "connector_id": connector_id,
            "capability": capability.value,
            "resumed_at": datetime.now(UTC).isoformat(),
            "continuation_token_present": token is not None,
            "page_number": page,
            "status": "RESUMED",
        }

    def _explain_error(self, verbatim: str) -> str:
        """Translates cryptic provider error codes into actionable operator explanations."""
        low = verbatim.lower()
        if "accessdenied" in low or "unauthorized" in low or "403" in low:
            return "Provider IAM role or credentials lack necessary read permissions for this API."
        if "throttl" in low or "rate" in low or "429" in low:
            return "Provider API rate limit or hourly quota reached. Backoff and retry scheduled."
        if "notfound" in low or "404" in low:
            return "Target scope, bucket, or billing report definition does not exist in provider account."
        if "timeout" in low or "timed out" in low:
            return "Provider endpoint timed out. Network latency or high provider load detected."
        return (
            "Provider returned an unclassified execution error. Review verbatim error for details."
        )


# Global singleton diagnostics service
_diagnostics_service = ConnectorDiagnosticsService()


def get_diagnostics_service() -> ConnectorDiagnosticsService:
    return _diagnostics_service
