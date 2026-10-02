"""Abstract Base Adapter for Outbound Alert Delivery Channels (Prompt 31).

Enforces:
- Consistent contract across delivery channels (Email, Webhook, In-App, Chat, ITSM).
- Attachment of full evidence payload in every dispatch.
- Mandatory TenantContext propagation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from domain.alerting.models import AlertDeliveryLog, AlertEntity
from domain.models.enums import NotificationChannel
from domain.tenant.context import TenantContext


class ChannelAdapter(ABC):
    """Abstract contract for delivering alerts to an outbound channel."""

    @property
    @abstractmethod
    def channel_type(self) -> NotificationChannel:
        """The notification channel type handled by this adapter."""
        ...

    @abstractmethod
    def send(
        self,
        alert: AlertEntity,
        recipient: str,
        *,
        tenant_context: TenantContext,
        options: dict[str, Any] | None = None,
    ) -> AlertDeliveryLog:
        """Dispatches the alert with attached empirical evidence to the given recipient."""
        ...
