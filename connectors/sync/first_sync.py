"""First-Sync Progress Service exposing the Five Folded Stages (Prompt 15B Items 21, 22, 23).

Enforces:
- Prompt 15B Item 21: Live status for the five folded background sync stages:
  1. Discover services
  2. Retrieve pricing data
  3. Retrieve cost data
  4. Retrieve usage data
  5. Discover dependencies
  Each stage exposes not started, running, complete, partial or failed, with counts and any error.
- Prompt 15B Item 22: Landing destination on wizard completion.
- Prompt 15B Item 23: Per-stage expected duration, elapsed time, and explicit explanation
  of provider billing latency (4-8 hours) so asynchronous export generation is not mistaken for failure.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any

from connectors.contract.base import BaseCloudConnector
from connectors.contract.models import PagedResult
from domain.audit.models import AuditEventCreate
from domain.audit.service import AuditService, get_audit_service
from domain.models.enums import (
    AuditEventType,
    ConnectorCapability,
    SyncStageStatus,
)
from domain.models.exceptions import FirstSyncNotFoundException
from domain.sync.first_sync_models import FirstSyncProgressReport, FirstSyncStage
from domain.sync.repository import (
    FirstSyncProgressRepository,
    get_first_sync_progress_repository,
)
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)

# Canonical latency explanations (Prompt 15B Item 23)
STAGE_METADATA: list[dict[str, Any]] = [
    {
        "stage_id": "discover_services",
        "name": "Discover Services",
        "capability": ConnectorCapability.DISCOVER_SERVICES,
        "expected_duration_seconds": 15,
        "latency_explanation": (
            "Fast metadata API discovery enumerating active provider services, product families, "
            "and resource types across all selected accounts."
        ),
    },
    {
        "stage_id": "retrieve_pricing_data",
        "name": "Retrieve Pricing Data",
        "capability": ConnectorCapability.COLLECT_PRICING_PUBLIC,
        "expected_duration_seconds": 45,
        "latency_explanation": (
            "Public pricing catalog and rate card synchronization for compute, storage, "
            "and database SKUs against cloud provider master catalogs."
        ),
    },
    {
        "stage_id": "retrieve_cost_data",
        "name": "Retrieve Cost Data",
        "capability": ConnectorCapability.COLLECT_COST_BULK,
        "expected_duration_seconds": 14400,  # 4 hours
        "latency_explanation": (
            "Provider billing latency: Cloud providers (AWS Cost & Usage Reports, Azure Cost Management "
            "Exports, GCP Billing Export) generate billing files asynchronously on a 4 to 24-hour cadence. "
            "The initial historical bulk export file generation typically takes between 4 and 8 hours. "
            "This latency is normal provider batch behavior and is not a CloudLens sync failure."
        ),
    },
    {
        "stage_id": "retrieve_usage_data",
        "name": "Retrieve Usage Data",
        "capability": ConnectorCapability.COLLECT_USAGE,
        "expected_duration_seconds": 60,
        "latency_explanation": (
            "Polls operational telemetry and utilization metrics (CPUUtilization, NetworkIn, "
            "DiskReadOps) from provider monitoring APIs."
        ),
    },
    {
        "stage_id": "discover_dependencies",
        "name": "Discover Dependencies",
        "capability": ConnectorCapability.DISCOVER_RELATIONSHIPS,
        "expected_duration_seconds": 60,
        "latency_explanation": (
            "Extracts network attachments, VPC peerings, and block storage mounts to establish "
            "topological dependencies across infrastructure assets."
        ),
    },
]


def _extract_items_count(result: Any) -> int:
    """Helper to safely determine items count from PagedResult or list."""
    if isinstance(result, PagedResult):
        return len(result.items)
    if isinstance(result, list):
        return len(result)
    return 0


class FirstSyncService:
    """Orchestrates and tracks the five visible first-sync stages."""

    def __init__(
        self,
        progress_repo: FirstSyncProgressRepository | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self._progress_repo = progress_repo or get_first_sync_progress_repository()
        self._audit_service = audit_service or get_audit_service()

    def initialize_report(
        self,
        session_id: str,
        connector_id: str,
        job_id: str,
        tenant_context: TenantContext,
    ) -> FirstSyncProgressReport:
        """Initializes a new first-sync report with all 5 stages in NOT_STARTED state (Item 21)."""
        stages = [
            FirstSyncStage(
                stage_id=meta["stage_id"],
                name=meta["name"],
                capability=meta["capability"],
                status=SyncStageStatus.NOT_STARTED,
                items_count=0,
                expected_duration_seconds=meta["expected_duration_seconds"],
                elapsed_time_seconds=0,
                latency_explanation=meta["latency_explanation"],
                error_message=None,
            )
            for meta in STAGE_METADATA
        ]

        landing_dest = (
            f"/onboarding/first-sync-progress?session_id={session_id}&connector_id={connector_id}"
        )
        report = FirstSyncProgressReport(
            id=f"fsp-{session_id}",
            tenant_id=tenant_context.tenant_id,
            session_id=session_id,
            connector_id=connector_id,
            initial_sync_job_id=job_id,
            overall_status="RUNNING",
            stages=stages,
            total_stages=len(stages),
            completed_stages=0,
            estimated_time_to_first_cost_seconds=14400,
            landing_destination=landing_dest,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        return self._progress_repo.save(report, tenant_context=tenant_context)

    async def execute_first_sync_stages(
        self,
        session_id: str,
        connector: BaseCloudConnector,
        job_id: str,
        tenant_context: TenantContext,
    ) -> FirstSyncProgressReport:
        """Executes extraction for each stage and updates live progress (Prompt 15B Item 21)."""
        report = self._progress_repo.get_by_session_id(session_id, tenant_context=tenant_context)
        if not report:
            report = self.initialize_report(
                session_id=session_id,
                connector_id=connector.connector_id,
                job_id=job_id,
                tenant_context=tenant_context,
            )

        updated_stages: list[FirstSyncStage] = []

        for stage in report.stages:
            stage_start = time.monotonic()
            started_at = datetime.now(UTC)
            stage.status = SyncStageStatus.RUNNING
            stage.started_at = started_at

            # Check capability support
            if not connector.has_capability(stage.capability):
                stage.status = SyncStageStatus.NOT_STARTED
                stage.error_message = (
                    f"Capability '{stage.capability.value}' is not supported or was degraded "
                    f"due to missing permissions. Stage skipped gracefully."
                )
                stage.elapsed_time_seconds = 0
                stage.completed_at = datetime.now(UTC)
                updated_stages.append(stage)
                continue

            try:
                # 1. Discover Services
                if stage.capability == ConnectorCapability.DISCOVER_SERVICES:
                    res = await connector.discover_services()
                    stage.items_count = _extract_items_count(res)
                    stage.status = SyncStageStatus.COMPLETE

                # 2. Retrieve Pricing Data
                elif stage.capability == ConnectorCapability.COLLECT_PRICING_PUBLIC:
                    res = await connector.collect_pricing_public()
                    stage.items_count = _extract_items_count(res)
                    stage.status = SyncStageStatus.COMPLETE

                # 3. Retrieve Cost Data (Provider Billing Latency Explained)
                elif stage.capability == ConnectorCapability.COLLECT_COST_BULK:
                    res = await connector.collect_cost_bulk()
                    count = _extract_items_count(res)
                    stage.items_count = count
                    # If records arrive immediately (e.g. simulator), mark complete.
                    # Otherwise, marked RUNNING with explicit latency explanation.
                    stage.status = (
                        SyncStageStatus.COMPLETE if count > 0 else SyncStageStatus.RUNNING
                    )

                # 4. Retrieve Usage Data
                elif stage.capability == ConnectorCapability.COLLECT_USAGE:
                    res = await connector.collect_usage(scope_id="root")
                    stage.items_count = _extract_items_count(res)
                    stage.status = SyncStageStatus.COMPLETE

                # 5. Discover Dependencies
                elif stage.capability == ConnectorCapability.DISCOVER_RELATIONSHIPS:
                    res = await connector.discover_relationships(scope_id="root")
                    stage.items_count = _extract_items_count(res)
                    stage.status = SyncStageStatus.COMPLETE

                elapsed = int(time.monotonic() - stage_start)
                stage.elapsed_time_seconds = max(elapsed, 1)
                stage.completed_at = datetime.now(UTC)

            except Exception as exc:
                elapsed = int(time.monotonic() - stage_start)
                stage.elapsed_time_seconds = max(elapsed, 1)
                stage.status = SyncStageStatus.FAILED
                stage.error_message = f"Stage execution failed: {str(exc)}"
                stage.completed_at = datetime.now(UTC)
                logger.warning(
                    "Stage '%s' failed for connector '%s': %s",
                    stage.stage_id,
                    connector.connector_id,
                    exc,
                )

            updated_stages.append(stage)

        completed_count = sum(1 for s in updated_stages if s.status == SyncStageStatus.COMPLETE)
        failed_count = sum(1 for s in updated_stages if s.status == SyncStageStatus.FAILED)

        if failed_count == 0 and completed_count == len(updated_stages):
            overall = "COMPLETED"
        elif completed_count > 0:
            overall = "PARTIAL"
        else:
            overall = "FAILED"

        report.stages = updated_stages
        report.completed_stages = completed_count
        report.overall_status = overall
        report.updated_at = datetime.now(UTC)

        saved = self._progress_repo.save(report, tenant_context=tenant_context)

        # Audit emission
        try:
            self._audit_service.append_event(
                tenant_context=tenant_context,
                event_in=AuditEventCreate(
                    event_type=AuditEventType.FIRST_SYNC_PROGRESS_VIEWED,
                    actor_id=tenant_context.user_id,
                    actor_roles=tenant_context.roles,
                    action=AuditEventType.FIRST_SYNC_PROGRESS_VIEWED.value,
                    resource_type="FirstSyncProgressReport",
                    resource_id=report.id,
                    details={
                        "session_id": session_id,
                        "connector_id": connector.connector_id,
                        "completed_stages": completed_count,
                        "overall_status": overall,
                    },
                    correlation_id=tenant_context.correlation_id,
                ),
            )
        except Exception as exc:
            logger.warning("Audit emission failed for first sync progress: %s", exc)

        return saved

    def get_progress(
        self, session_id: str, tenant_context: TenantContext
    ) -> FirstSyncProgressReport:
        """Retrieves the live first-sync progress report by session ID."""
        report = self._progress_repo.get_by_session_id(session_id, tenant_context=tenant_context)
        if not report:
            raise FirstSyncNotFoundException(session_id)
        return report

    def get_progress_by_connector(
        self, connector_id: str, tenant_context: TenantContext
    ) -> FirstSyncProgressReport:
        """Retrieves the live first-sync progress report by connector ID."""
        report = self._progress_repo.get_by_connector_id(
            connector_id, tenant_context=tenant_context
        )
        if not report:
            raise FirstSyncNotFoundException(connector_id)
        return report


_first_sync_service = FirstSyncService()


def get_first_sync_service() -> FirstSyncService:
    return _first_sync_service


__all__ = [
    "FirstSyncService",
    "get_first_sync_service",
    "STAGE_METADATA",
]
