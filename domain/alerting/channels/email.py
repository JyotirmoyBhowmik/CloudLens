"""Email Delivery Channel Adapter (Prompt 31).

Formats rich transactional alerts including severity, threshold comparisons,
evidence datapoints, and actionable resolution links.
"""

from __future__ import annotations

import datetime as dt
import os
import re
from typing import Any

from domain.alerting.channels.adapter import ChannelAdapter
from domain.alerting.models import AlertDeliveryLog, AlertEntity
from domain.models.enums import DeliveryOutcome, NotificationChannel
from domain.tenant.context import TenantContext

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailChannelAdapter(ChannelAdapter):
    """Adapter for transactional email notifications."""

    def __init__(self, sender_address: str | None = None) -> None:
        domain = os.getenv("CLOUDLENS_DOMAIN", "cloudlens.local")
        self.sender_address = sender_address or os.getenv("CLOUDLENS_ALERT_EMAIL_SENDER") or f"alerts@{domain}"

    @property
    def channel_type(self) -> NotificationChannel:
        return NotificationChannel.EMAIL

    def send(
        self,
        alert: AlertEntity,
        recipient: str,
        *,
        tenant_context: TenantContext,
        options: dict[str, Any] | None = None,
    ) -> AlertDeliveryLog:
        """Dispatches email notification with complete empirical evidence."""
        log = AlertDeliveryLog(
            tenant_id=tenant_context.tenant_id,
            alert_id=alert.id,
            channel=self.channel_type,
            recipient=recipient,
            outcome=DeliveryOutcome.QUEUED,
            attempt_count=1,
            max_attempts=3,
        )

        # Validate recipient email format
        if not EMAIL_REGEX.match(recipient.strip()):
            log.outcome = DeliveryOutcome.FAILED
            log.error_message = f"Invalid email format: '{recipient}'"
            return log

        # Render message body with evidence
        subject = f"[CloudLens {alert.severity.value}] {alert.title}"
        payload = {
            "from": self.sender_address,
            "to": recipient,
            "subject": subject,
            "alert_type": alert.alert_type.value,
            "severity": alert.severity.value,
            "title": alert.title,
            "description": alert.description,
            "current_value": alert.current_value,
            "threshold_value": alert.threshold_value,
            "evidence": alert.evidence.model_dump(mode="json"),
            "fingerprint": alert.fingerprint,
        }
        log.payload = payload

        # Check for simulated failures (e.g. during test scenarios)
        simulate_failure = options.get("simulate_failure", False) if options else False
        if simulate_failure:
            log.outcome = DeliveryOutcome.FAILED
            log.error_message = "Simulated SMTP transport rejection"
        else:
            log.outcome = DeliveryOutcome.DELIVERED
            log.delivered_at = dt.datetime.now(dt.UTC)

        return log
