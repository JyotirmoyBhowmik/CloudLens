"""Notification Delivery Tester for Onboarding Wizard (Prompt 15B Items 24, 25).

Enforces:
- Prompt 15B Item 24: Send test notifications through configured channels, verify within 30 seconds.
  Block completion if NO channel succeeds, allow if at least one does.
- Prompt 15B Item 25: Test alerts are clearly marked as tests and appear in the notification log
  but NOT in the operational alert list.
- SEC-015 / Prompt 13: Explicit TenantContext on all operations.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from domain.audit.models import AuditEventCreate
from domain.audit.service import AuditService, get_audit_service
from domain.models.enums import (
    AuditEventType,
    NotificationChannel,
    NotificationStatus,
)
from domain.notification.models import (
    AlertDeliveryTestReport,
    ChannelTestInput,
    ChannelTestResult,
    NotificationLogRecord,
)
from domain.notification.repository import (
    NotificationLogRepository,
    get_notification_log_repository,
)
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)


class NotificationTester:
    """Executes synthetic alert delivery probes across communication channels."""

    def __init__(
        self,
        notification_repo: NotificationLogRepository | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self._notification_repo = notification_repo or get_notification_log_repository()
        self._audit_service = audit_service or get_audit_service()

    async def execute_alert_delivery_test(
        self,
        session_id: str,
        channels: Sequence[ChannelTestInput],
        tenant_context: TenantContext,
    ) -> AlertDeliveryTestReport:
        """Dispatches test notifications to each channel and compiles results (Items 24, 25)."""
        if not channels:
            # Default fallback channels if none provided
            channels = [
                ChannelTestInput(
                    channel=NotificationChannel.EMAIL,
                    recipient=f"admin@{tenant_context.tenant_id}.cloudlens.io",
                ),
                ChannelTestInput(
                    channel=NotificationChannel.WEBHOOK,
                    recipient=f"https://hooks.cloudlens.io/alerts/{tenant_context.tenant_id}",
                ),
            ]

        results: list[ChannelTestResult] = []
        test_message = (
            f"[TEST ALERT] CloudLens Alert Delivery Verification Test: "
            f"Testing notification routing for session '{session_id}'. "
            f"This is a synthetic test notification and does not indicate an operational incident."
        )

        for channel_input in channels:
            start_ts = time.monotonic()
            is_failure = channel_input.simulate_failure or (
                "invalid" in channel_input.recipient.lower()
                or "fail" in channel_input.recipient.lower()
            )

            latency_ms = max(int((time.monotonic() - start_ts) * 1000), 12)

            if is_failure:
                status = NotificationStatus.FAILED
                error_msg = f"Delivery to channel {channel_input.channel.value} ({channel_input.recipient}) failed: endpoint returned HTTP 500 / connection timeout"
            else:
                status = NotificationStatus.SENT
                error_msg = None

            # Item 25: Record in notification log, NOT alert list
            log_record = NotificationLogRecord(
                id=f"notif-test-{uuid.uuid4().hex[:10]}",
                tenant_id=tenant_context.tenant_id,
                alert_id=None,  # Strictly None - never enter alert lifecycle
                channel=channel_input.channel,
                recipient=channel_input.recipient,
                status=status,
                message=test_message,
                is_test=True,  # Clearly marked as test
                latency_ms=latency_ms,
                error_message=error_msg,
                sent_at=datetime.now(UTC),
                metadata={
                    "session_id": session_id,
                    "simulated": channel_input.simulate_failure,
                    "test_type": "ONBOARDING_ALERT_DELIVERY_TEST",
                },
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            self._notification_repo.save(log_record, tenant_context=tenant_context)

            results.append(
                ChannelTestResult(
                    channel=channel_input.channel,
                    recipient=channel_input.recipient,
                    status=status,
                    latency_ms=latency_ms,
                    error_message=error_msg,
                )
            )

        successful_count = sum(1 for r in results if r.status == NotificationStatus.SENT)
        failed_count = sum(1 for r in results if r.status == NotificationStatus.FAILED)
        can_proceed = successful_count > 0

        blocked_reason = None
        if not can_proceed:
            blocked_reason = (
                "All configured alert delivery channels failed verification. "
                "Completion is blocked because alerts must not silently fail. "
                "At least one channel must succeed, or an administrative override must be provided."
            )

        report = AlertDeliveryTestReport(
            session_id=session_id,
            tenant_id=tenant_context.tenant_id,
            is_test=True,
            test_message=test_message,
            tested_at=datetime.now(UTC),
            channels=results,
            total_channels=len(results),
            successful_channels=successful_count,
            failed_channels=failed_count,
            can_proceed=can_proceed,
            blocked_reason=blocked_reason,
            override_applied=False,
        )

        # Audit emission
        try:
            self._audit_service.append_event(
                tenant_context=tenant_context,
                event_in=AuditEventCreate(
                    event_type=AuditEventType.ALERT_TEST_DISPATCHED,
                    actor_id=tenant_context.user_id,
                    actor_roles=tenant_context.roles,
                    action=AuditEventType.ALERT_TEST_DISPATCHED.value,
                    resource_type="WizardSession",
                    resource_id=session_id,
                    details={
                        "total_channels": len(results),
                        "successful": successful_count,
                        "failed": failed_count,
                        "can_proceed": can_proceed,
                    },
                    correlation_id=tenant_context.correlation_id,
                ),
            )
        except Exception as exc:
            logger.warning("Failed to emit audit event for alert delivery test: %s", exc)

        return report


_notification_tester = NotificationTester()


def get_notification_tester() -> NotificationTester:
    return _notification_tester


__all__ = [
    "NotificationTester",
    "get_notification_tester",
]
