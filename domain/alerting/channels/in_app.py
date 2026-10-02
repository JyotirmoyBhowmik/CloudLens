"""In-App Notification Center Channel Adapter (Prompt 31).

Dispatches alerts to the user's notification centre inbox with read/unread tracking.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from domain.alerting.channels.adapter import ChannelAdapter
from domain.alerting.models import AlertDeliveryLog, AlertEntity
from domain.models.enums import DeliveryOutcome, NotificationChannel
from domain.tenant.context import TenantContext


class InAppNotificationItem:
    """Represents an in-app inbox notification entry."""

    def __init__(
        self,
        item_id: str,
        tenant_id: str,
        recipient_user_id: str,
        alert_id: str,
        title: str,
        message: str,
        severity: str,
        is_read: bool = False,
        created_at: dt.datetime | None = None,
    ) -> None:
        self.item_id = item_id
        self.tenant_id = tenant_id
        self.recipient_user_id = recipient_user_id
        self.alert_id = alert_id
        self.title = title
        self.message = message
        self.severity = severity
        self.is_read = is_read
        self.created_at = created_at or dt.datetime.now(dt.UTC)


class InAppChannelAdapter(ChannelAdapter):
    """Adapter for internal in-app notification center."""

    def __init__(self) -> None:
        # Key: (tenant_id, recipient_user_id) -> list[InAppNotificationItem]
        self._inboxes: dict[tuple[str, str], list[InAppNotificationItem]] = {}

    @property
    def channel_type(self) -> NotificationChannel:
        return NotificationChannel.IN_APP

    def send(
        self,
        alert: AlertEntity,
        recipient: str,
        *,
        tenant_context: TenantContext,
        options: dict[str, Any] | None = None,
    ) -> AlertDeliveryLog:
        """Publishes an in-app notification item into the recipient's inbox."""
        _ = options
        log = AlertDeliveryLog(
            tenant_id=tenant_context.tenant_id,
            alert_id=alert.id,
            channel=self.channel_type,
            recipient=recipient,
            outcome=DeliveryOutcome.DELIVERED,
            attempt_count=1,
            max_attempts=1,
            delivered_at=dt.datetime.now(dt.UTC),
        )

        item = InAppNotificationItem(
            item_id=f"inapp-{alert.id}-{len(self._inboxes.get((tenant_context.tenant_id, recipient), [])) + 1}",
            tenant_id=tenant_context.tenant_id,
            recipient_user_id=recipient,
            alert_id=alert.id,
            title=alert.title,
            message=alert.description,
            severity=alert.severity.value,
        )

        key = (tenant_context.tenant_id, recipient)
        if key not in self._inboxes:
            self._inboxes[key] = []
        self._inboxes[key].append(item)

        log.payload = {
            "inbox_item_id": item.item_id,
            "recipient": recipient,
            "title": item.title,
            "is_read": item.is_read,
        }
        return log

    def get_inbox(
        self,
        recipient: str,
        *,
        tenant_context: TenantContext,
    ) -> list[InAppNotificationItem]:
        """Retrieves in-app notification items for a user within tenant boundary."""
        return list(self._inboxes.get((tenant_context.tenant_id, recipient), []))

    def mark_read(
        self,
        item_id: str,
        recipient: str,
        *,
        tenant_context: TenantContext,
    ) -> bool:
        """Marks an in-app notification as read."""
        for item in self._inboxes.get((tenant_context.tenant_id, recipient), []):
            if item.item_id == item_id:
                item.is_read = True
                return True
        return False
