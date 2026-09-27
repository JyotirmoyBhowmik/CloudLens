"""Comprehensive Unit Tests for Prompt 15B: Onboarding Step Restoration and Alert Delivery Test.

Enforces:
- Prompt 15B Item 21: First-sync progress view exposing five visible stages (services, pricing, cost, usage, dependencies)
  with live status (not_started, running, complete, partial, failed), item counts, and errors.
- Prompt 15B Item 22: Landing destination directing to first-sync progress view upon wizard completion.
- Prompt 15B Item 23: Per-stage expected duration, elapsed time, and provider asynchronous billing latency explanation (4-8 hours).
- Prompt 15B Item 24: Alert delivery test step: synthetic probes across configured channels, reports per-channel outcome,
  blocks completion if NO channel succeeds unless administrative override is present, allows completion if at least one succeeds.
- Prompt 15B Item 25: Test alerts flagged with is_test=True, written to notification log, alert_id=None, never enters operational alert list.
- Prompt 15B Item 26: Quota monitoring and service limits configuration in Step 11 per AM-07.
- Prompt 15B Item 27: Onboarding completion summary returning selected scopes, active capabilities, unavailable capabilities with
  operational consequences, sync schedules configured, estimated time to first cost data, alert test results, and landing destination.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from connectors.wizard.service import OnboardingWizardService
from domain.models.enums import (
    NotificationChannel,
    NotificationStatus,
    OverrideClass,
    ProviderType,
    SyncStageStatus,
    WizardStep,
)
from domain.models.exceptions import AlertDeliveryFailedException
from domain.notification.models import ChannelTestInput
from domain.overrides.models import OverrideCreateRequest
from domain.sync.first_sync_models import FirstSyncProgressReport
from domain.tenant.context import TenantContext
from domain.wizard.models import OnboardingCompletionSummary


@pytest.fixture
def tenant_context() -> TenantContext:
    uid = f"usr-step-{uuid.uuid4().hex[:8]}"
    return TenantContext(
        tenant_id="tenant-step-restore-01",
        user_id=uid,
        roles=["TENANT_ADMIN"],
        correlation_id=f"corr-{uuid.uuid4().hex[:8]}",
    )


# ==============================================================================
# 1. Item 21, 22, 23: First-Sync Progress View & Billing Latency Explanations
# ==============================================================================


@pytest.mark.asyncio
async def test_first_sync_progress_five_stages_and_latency_explanation(
    tenant_context: TenantContext,
):
    """Items 21 & 23: Verify all 5 visible stages with live status, counts, durations, and billing latency explanation."""
    service = OnboardingWizardService()
    session = service.start_session(user_id=tenant_context.user_id, tenant_context=tenant_context)

    # Fast-forward session to Step 12
    session.provider = ProviderType.AWS
    session.selected_scopes = ["123456789012"]
    session.current_step = WizardStep.TEST_ALERT_DELIVERY
    session.completed_steps = [s for s in WizardStep if s != WizardStep.COMPLETE]
    service._wizard_repo.save(session, tenant_context=tenant_context)

    # Complete wizard
    result = await service.complete_wizard(session.id, tenant_context=tenant_context)
    assert result["status"] == "COMPLETED"

    # Item 22: Verify landing destination
    expected_landing = f"/onboarding/first-sync-progress?session_id={session.id}&connector_id={result['connector_id']}"
    assert result["landing_destination"] == expected_landing

    # Item 21: Verify 5 visible stages
    progress = service.get_first_sync_progress(session.id, tenant_context=tenant_context)
    assert isinstance(progress, FirstSyncProgressReport)
    assert progress.total_stages == 5
    assert len(progress.stages) == 5

    stage_ids = [s.stage_id for s in progress.stages]
    assert stage_ids == [
        "discover_services",
        "retrieve_pricing_data",
        "retrieve_cost_data",
        "retrieve_usage_data",
        "discover_dependencies",
    ]

    # Verify each stage has status, item count >= 0, expected duration > 0, and elapsed time >= 0
    for stage in progress.stages:
        assert stage.status in (
            SyncStageStatus.NOT_STARTED,
            SyncStageStatus.COMPLETE,
            SyncStageStatus.RUNNING,
            SyncStageStatus.PARTIAL,
            SyncStageStatus.FAILED,
        )
        assert stage.items_count >= 0
        assert stage.expected_duration_seconds > 0
        assert stage.elapsed_time_seconds >= 0

    # Item 23: Cost data stage explicitly contains provider billing latency explanation
    cost_stage = next(s for s in progress.stages if s.stage_id == "retrieve_cost_data")
    assert cost_stage.expected_duration_seconds == 14400  # 4 hours
    assert "Provider billing latency" in cost_stage.latency_explanation
    assert "4 to 24-hour cadence" in cost_stage.latency_explanation
    assert "not a CloudLens sync failure" in cost_stage.latency_explanation


# ==============================================================================
# 2. Item 24 & 25: Alert Delivery Test & Non-Silent Failure Blocking
# ==============================================================================


@pytest.mark.asyncio
async def test_alert_delivery_test_multi_channel_outcomes(
    tenant_context: TenantContext,
):
    """Item 24: Test probes multiple channels and reports individual delivery status and latency."""
    service = OnboardingWizardService()
    session = service.start_session(user_id=tenant_context.user_id, tenant_context=tenant_context)

    channels = [
        ChannelTestInput(channel=NotificationChannel.EMAIL, recipient="ops@tenant.cloudlens.io"),
        ChannelTestInput(
            channel=NotificationChannel.SLACK,
            recipient="https://hooks.slack.com/services/T00/B00/X00",
        ),
        ChannelTestInput(
            channel=NotificationChannel.WEBHOOK,
            recipient="https://api.tenant.io/webhook/invalid",
            simulate_failure=True,
        ),
    ]

    report = await service.test_alert_delivery_step(
        session_id=session.id,
        channels=channels,
        tenant_context=tenant_context,
    )

    assert report.total_channels == 3
    assert report.successful_channels == 2
    assert report.failed_channels == 1
    assert report.can_proceed is True
    assert report.blocked_reason is None

    # Check email result
    email_res = next(r for r in report.channels if r.channel == NotificationChannel.EMAIL)
    assert email_res.status == NotificationStatus.SENT
    assert email_res.latency_ms > 0
    assert email_res.error_message is None

    # Check webhook failed result
    webhook_res = next(r for r in report.channels if r.channel == NotificationChannel.WEBHOOK)
    assert webhook_res.status == NotificationStatus.FAILED
    assert webhook_res.error_message is not None
    assert "failed" in webhook_res.error_message


@pytest.mark.asyncio
async def test_alert_delivery_test_logged_in_notification_log_not_alert_list(
    tenant_context: TenantContext,
):
    """Item 25: Test notifications are written to notification log with is_test=True and alert_id=None."""
    service = OnboardingWizardService()
    session = service.start_session(user_id=tenant_context.user_id, tenant_context=tenant_context)

    channels = [
        ChannelTestInput(channel=NotificationChannel.EMAIL, recipient="finops@tenant.cloudlens.io"),
        ChannelTestInput(
            channel=NotificationChannel.PAGERDUTY,
            recipient="https://events.pagerduty.com/v2/enqueue",
        ),
    ]

    await service.test_alert_delivery_step(
        session_id=session.id,
        channels=channels,
        tenant_context=tenant_context,
    )

    log_repo = service._notification_tester._notification_repo
    records = log_repo.list(tenant_context=tenant_context)

    test_records = [r for r in records if r.metadata.get("session_id") == session.id]
    assert len(test_records) == 2

    for rec in test_records:
        assert rec.is_test is True
        assert rec.alert_id is None  # Strictly None so it NEVER enters operational alert lifecycle
        assert "[TEST ALERT]" in rec.message


@pytest.mark.asyncio
async def test_complete_wizard_blocked_when_all_channels_fail(
    tenant_context: TenantContext,
):
    """Item 24: When ALL channels fail, wizard completion is blocked with AlertDeliveryFailedException."""
    service = OnboardingWizardService()
    session = service.start_session(user_id=tenant_context.user_id, tenant_context=tenant_context)
    session.provider = ProviderType.AWS
    session.selected_scopes = ["123456789012"]
    service._wizard_repo.save(session, tenant_context=tenant_context)

    # Run alert test where all channels simulate failure
    all_failing = [
        ChannelTestInput(
            channel=NotificationChannel.EMAIL, recipient="bad-email@fail.com", simulate_failure=True
        ),
        ChannelTestInput(
            channel=NotificationChannel.SLACK,
            recipient="https://hooks.slack.com/fail",
            simulate_failure=True,
        ),
    ]

    report = await service.test_alert_delivery_step(
        session_id=session.id,
        channels=all_failing,
        tenant_context=tenant_context,
    )
    assert report.successful_channels == 0
    assert report.can_proceed is False
    assert report.blocked_reason is not None

    # Attempting to complete wizard must raise AlertDeliveryFailedException
    with pytest.raises(AlertDeliveryFailedException) as exc_info:
        await service.complete_wizard(session.id, tenant_context=tenant_context)

    assert "Alert delivery test failed across all configured channels" in str(
        exc_info.value.message
    )
    assert exc_info.value.error_code == "ALERT_DELIVERY_FAILED"


@pytest.mark.asyncio
async def test_complete_wizard_allowed_with_administrative_override_when_channels_fail(
    tenant_context: TenantContext,
):
    """Item 24: When ALL channels fail, an explicit administrative override permits completion."""
    service = OnboardingWizardService()
    session = service.start_session(user_id=tenant_context.user_id, tenant_context=tenant_context)
    session.provider = ProviderType.AWS
    session.selected_scopes = ["123456789012"]
    service._wizard_repo.save(session, tenant_context=tenant_context)

    # Run failing test
    all_failing = [
        ChannelTestInput(
            channel=NotificationChannel.EMAIL, recipient="bad@fail.com", simulate_failure=True
        ),
    ]
    await service.test_alert_delivery_step(
        session_id=session.id,
        channels=all_failing,
        tenant_context=tenant_context,
    )

    # Create administrative override of class ALERT_DELIVERY_FAILURE
    override_req = OverrideCreateRequest(
        override_class=OverrideClass.ALERT_DELIVERY_FAILURE,
        who=tenant_context.user_id,
        what=session.id,
        why="Administrative override for staging environment without external SMTP relay configured",
        previous_value={"can_proceed": False},
        new_value={"can_proceed": True, "override_reason": "Staging bypass approved"},
        expiry=datetime.now(UTC) + timedelta(hours=2),
        is_permanent=False,
    )
    service._override_service.create_override(tenant_context=tenant_context, req=override_req)

    # Now completion must succeed!
    result = await service.complete_wizard(session.id, tenant_context=tenant_context)
    assert result["status"] == "COMPLETED"
    assert "completion_summary" in result
    summary = result["completion_summary"]
    assert summary["alert_test_result"]["override_applied"] is True


# ==============================================================================
# 3. Item 26: Quota Monitoring Configuration in Step 11 per AM-07
# ==============================================================================


@pytest.mark.asyncio
async def test_step_11_quota_monitoring_configuration(
    tenant_context: TenantContext,
):
    """Item 26: Step 11 saves quota headroom, service limits, and predicted exhaustion alerts."""
    service = OnboardingWizardService()
    session = service.start_session(user_id=tenant_context.user_id, tenant_context=tenant_context)

    # Advance to step 11
    session.current_step = WizardStep.CONFIGURE_USAGE_MONITORING
    service._wizard_repo.save(session, tenant_context=tenant_context)

    step_payload = {
        "metrics_enabled": True,
        "quota_monitoring_enabled": True,
        "quota_headroom_threshold_percent": 15.0,
        "predicted_exhaustion_alert_hours": 36,
        "rate_limit_throttle_protection": True,
    }

    updated_session = await service.save_step(
        session_id=session.id,
        step=WizardStep.CONFIGURE_USAGE_MONITORING,
        step_payload=step_payload,
        tenant_context=tenant_context,
    )

    # Verify quota monitoring configuration stored in wizard_data
    assert "quota_monitoring_config" in updated_session.wizard_data
    quota_data = updated_session.wizard_data["quota_monitoring_config"]
    assert quota_data["quota_monitoring_enabled"] is True
    assert quota_data["quota_headroom_threshold_percent"] == 15.0
    assert quota_data["predicted_exhaustion_alert_hours"] == 36
    assert quota_data["rate_limit_throttle_protection"] is True


# ==============================================================================
# 4. Item 27: Onboarding Completion Summary
# ==============================================================================


@pytest.mark.asyncio
async def test_onboarding_completion_summary_contents(
    tenant_context: TenantContext,
):
    """Item 27: Completion summary returns scopes, active/unavailable capabilities, schedules, estimated cost latency."""
    service = OnboardingWizardService()
    session = service.start_session(user_id=tenant_context.user_id, tenant_context=tenant_context)
    session.provider = ProviderType.AWS
    session.selected_scopes = ["acc-1", "acc-2"]

    # Simulate missing permissions so degraded capabilities with consequences are reported
    session.wizard_data[WizardStep.VALIDATE_PERMISSIONS.value] = {
        "missing_permissions": ["ce:GetCostAndUsage"],
    }
    service._wizard_repo.save(session, tenant_context=tenant_context)

    # Run successful alert test
    await service.test_alert_delivery_step(
        session_id=session.id,
        channels=[ChannelTestInput(channel=NotificationChannel.EMAIL, recipient="admin@test.io")],
        tenant_context=tenant_context,
    )

    # Complete wizard
    result = await service.complete_wizard(session.id, tenant_context=tenant_context)
    assert result["status"] == "COMPLETED"

    # Query completion summary via dedicated service method
    summary = service.get_completion_summary(session.id, tenant_context=tenant_context)
    assert isinstance(summary, OnboardingCompletionSummary)

    # Verify selected scopes
    assert summary.scopes_selected == ["acc-1", "acc-2"]

    # Verify active capabilities
    assert len(summary.capabilities_available) > 0

    # Verify unavailable capabilities with operational consequences
    assert len(summary.capabilities_unavailable_with_consequences) > 0
    cost_unavail = next(
        (
            c
            for c in summary.capabilities_unavailable_with_consequences
            if "C-03" in c["capability"]
        ),
        None,
    )
    assert cost_unavail is not None
    assert "consequence" in cost_unavail

    # Verify configured schedules
    assert len(summary.schedules_configured) >= 5

    # Verify estimated time to first cost data
    assert "4 to 8 hours" in summary.estimated_time_to_first_cost_data
    assert summary.estimated_time_to_first_cost_seconds == 14400

    # Verify alert test results
    assert summary.alert_test_result["successful_channels"] >= 1

    # Verify landing destination
    assert "/onboarding/first-sync-progress" in summary.landing_destination
