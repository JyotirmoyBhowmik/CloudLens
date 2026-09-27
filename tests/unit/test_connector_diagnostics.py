"""Unit Tests for Connector Diagnostics and Failure Recovery (Prompt 15 Items 104, 105).

Enforces:
- Prompt 15 Item 104: Detailed per-capability diagnostics:
  - Last attempt, last success, verbatim error, plain-language explanation.
  - Freshness lag seconds, consumed quota headroom percent.
  - Unambiguous status display (Operational, Degraded, Failed, Not Supported).
- Prompt 15 Item 105: Failure recovery:
  - Degraded/failed state tracking and error translation.
  - Outage gap analysis reporting missed periods and scopes.
  - Resumption from checkpoint without restarting from page 1.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from connectors.contract.checkpoint_store import checkpoint_store
from connectors.contract.lifecycle import connector_lifecycle_manager
from connectors.diagnostics.service import ConnectorDiagnosticsService
from connectors.simulator.connector import ProviderSimulatorConnector
from connectors.simulator.models import SimulatorProfile
from connectors.sync.orchestrator import SyncOrchestrator
from domain.models.enums import (
    ConnectorCapability,
    ConnectorLifecycleState,
    ProviderType,
    SyncJobStatus,
    SyncType,
)
from domain.sync.models import SyncJob
from domain.tenant.context import TenantContext


@pytest.fixture
def tenant_context() -> TenantContext:
    return TenantContext(
        tenant_id="tenant-diag-test",
        user_id="usr-diag-operator",
        roles=["TENANT_ADMIN"],
        correlation_id="corr-diag-001",
    )


@pytest.fixture
def diagnostics_service() -> ConnectorDiagnosticsService:
    return ConnectorDiagnosticsService()


# ==============================================================================
# 1. Per-Capability Diagnostics (Item 104)
# ==============================================================================


@pytest.mark.asyncio
async def test_connector_diagnostics_report(
    diagnostics_service: ConnectorDiagnosticsService, tenant_context: TenantContext
):
    """Item 104: Diagnostic report provides per-capability last attempt, last success, lag, and headroom."""
    connector_id = "conn-diag-aws-01"
    connector = ProviderSimulatorConnector(
        connector_id=connector_id,
        tenant_id=tenant_context.tenant_id,
        profile=SimulatorProfile.AWS,
    )

    # Initialize connector in ACTIVE state
    connector_lifecycle_manager.transition_state(
        tenant_context=tenant_context,
        connector_id=connector_id,
        target_state=ConnectorLifecycleState.CREDENTIAL_BOUND,
    )
    connector_lifecycle_manager.transition_state(
        tenant_context=tenant_context,
        connector_id=connector_id,
        target_state=ConnectorLifecycleState.VALIDATED,
    )
    connector_lifecycle_manager.transition_state(
        tenant_context=tenant_context,
        connector_id=connector_id,
        target_state=ConnectorLifecycleState.ACTIVE,
    )

    # Run a successful sync for DISCOVER_RESOURCES
    orchestrator = SyncOrchestrator()
    await orchestrator.execute_sync(
        connector=connector,
        sync_type=SyncType.SCHEDULED_SYNC,
        tenant_context=tenant_context,
        capability=ConnectorCapability.DISCOVER_RESOURCES,
        allow_idempotent_skip=False,
    )

    report = diagnostics_service.get_diagnostics(
        connector_id=connector_id, tenant_context=tenant_context
    )

    assert report.connector_id == connector_id
    assert report.tenant_id == tenant_context.tenant_id
    assert report.overall_state == ConnectorLifecycleState.ACTIVE.value
    assert len(report.capabilities) == len(ConnectorCapability)

    res_diag = next(
        c for c in report.capabilities if c.capability == ConnectorCapability.DISCOVER_RESOURCES
    )
    assert res_diag.last_attempt_at is not None
    assert res_diag.last_success_at is not None
    assert res_diag.freshness_lag_seconds is not None
    assert res_diag.freshness_lag_seconds < 15.0
    assert res_diag.quota_headroom_percent >= 0.0
    assert res_diag.status_display == "Operational"


# ==============================================================================
# 2. Verbatim Error Translation & Plain-Language Explanation (Item 104)
# ==============================================================================


def test_plain_language_error_explanation(
    diagnostics_service: ConnectorDiagnosticsService,
):
    """Item 104: Cryptic provider error codes map to plain-language operator explanations."""
    err_iam = "AccessDenied: User arn:aws:iam::123:user/finops is not authorized to perform sts:AssumeRole"
    expl_iam = diagnostics_service._explain_error(err_iam)
    assert "IAM" in expl_iam or "permission" in expl_iam.lower()

    err_throttle = "ThrottlingException: Rate exceeded for API DescribeCostAndUsage"
    expl_throttle = diagnostics_service._explain_error(err_throttle)
    assert "rate limit" in expl_throttle.lower() or "quota" in expl_throttle.lower()

    err_404 = "ResourceNotFoundException: Report definition CUR_DAILY does not exist"
    expl_404 = diagnostics_service._explain_error(err_404)
    assert "not exist" in expl_404.lower() or "bucket" in expl_404.lower()

    err_timeout = "EndpointConnectionError: Could not connect to the endpoint URL timed out"
    expl_timeout = diagnostics_service._explain_error(err_timeout)
    assert "timed out" in expl_timeout.lower() or "latency" in expl_timeout.lower()


# ==============================================================================
# 3. Outage Gap Analysis (Item 105)
# ==============================================================================


@pytest.mark.asyncio
async def test_outage_gap_report(
    diagnostics_service: ConnectorDiagnosticsService, tenant_context: TenantContext
):
    """Item 105: Outage gap report computes duration, missed windows, scopes, and recommended backfills."""
    connector_id = "conn-outage-test"
    now = datetime.now(UTC)
    outage_start = now - timedelta(hours=18)

    # Save a mock sync job for known scopes
    from domain.sync.repository import get_sync_job_repository

    job_repo = get_sync_job_repository()
    job_repo.save(
        SyncJob(
            id="sync-prev-001",
            tenant_id=tenant_context.tenant_id,
            connector_id=connector_id,
            connector_type=ProviderType.AWS,
            scope_id="acc-prod-101",
            sync_type=SyncType.FULL_SYNC,
            capability=ConnectorCapability.DISCOVER_RESOURCES,
            idempotency_key="mock-idem-1",
            scopes_requested=["acc-prod-101", "acc-analytics-102"],
            scopes_completed=["acc-prod-101", "acc-analytics-102"],
            scopes_failed=[],
            scope_results=[],
            status=SyncJobStatus.COMPLETED,
            started_at=outage_start - timedelta(hours=2),
            completed_at=outage_start - timedelta(hours=1, minutes=50),
            rows_ingested=50,
        ),
        tenant_context=tenant_context,
    )

    gap_report = diagnostics_service.get_outage_gap_report(
        connector_id=connector_id,
        outage_start=outage_start,
        tenant_context=tenant_context,
    )

    assert gap_report.connector_id == connector_id
    assert gap_report.duration_hours >= 17.5
    assert len(gap_report.missed_periods) >= 2
    assert "acc-prod-101" in gap_report.missed_scopes
    assert SyncType.BACKFILL in gap_report.recommended_backfill_types
    assert SyncType.FULL_SYNC in gap_report.recommended_backfill_types


# ==============================================================================
# 4. Checkpoint Resumption (Item 105)
# ==============================================================================


@pytest.mark.asyncio
async def test_checkpoint_resumption(
    diagnostics_service: ConnectorDiagnosticsService, tenant_context: TenantContext
):
    """Item 105: Resumes interrupted connector sync directly from saved page checkpoint."""
    connector_id = "conn-resume-test"
    capability = ConnectorCapability.DISCOVER_RESOURCES

    # Simulate saved pagination checkpoint after page 3
    checkpoint_store.save_checkpoint(
        tenant_context=tenant_context,
        job_id="latest",
        connector_id=connector_id,
        capability=capability,
        continuation_token="token-page-4-continuation",
        page_number=3,
        records_ingested=150,
    )

    resume_info = await diagnostics_service.resume_from_checkpoint(
        connector_id=connector_id,
        capability=capability,
        tenant_context=tenant_context,
    )

    assert resume_info["status"] == "RESUMED"
    assert resume_info["connector_id"] == connector_id
    assert resume_info["capability"] == capability.value
    assert resume_info["page_number"] == 3
    assert resume_info["continuation_token_present"] is True
