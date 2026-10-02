"""Alerting and Notifications package (Prompt 31)."""

from domain.alerting.channels import (
    ChannelAdapter,
    ChannelAdapterRegistry,
    EmailChannelAdapter,
    InAppChannelAdapter,
    InAppNotificationItem,
    WebhookChannelAdapter,
)
from domain.alerting.contextual import ContextualAlertManager
from domain.alerting.engine import AlertEngine
from domain.alerting.models import (
    AlertComment,
    AlertDeliveryLog,
    AlertEntity,
    AlertEvidence,
    ContextualAlert,
    QuietHoursConfig,
    RecipientResolutionResult,
    RecipientSubscription,
)
from domain.alerting.repository import AlertRepository
from domain.alerting.router import RecipientRouter
from domain.alerting.service import AlertService, get_alert_service, reset_alert_service

__all__ = [
    "AlertEvidence",
    "AlertComment",
    "AlertEntity",
    "ContextualAlert",
    "QuietHoursConfig",
    "RecipientSubscription",
    "RecipientResolutionResult",
    "AlertDeliveryLog",
    "AlertRepository",
    "RecipientRouter",
    "ContextualAlertManager",
    "AlertEngine",
    "AlertService",
    "get_alert_service",
    "reset_alert_service",
    "ChannelAdapter",
    "EmailChannelAdapter",
    "WebhookChannelAdapter",
    "InAppChannelAdapter",
    "InAppNotificationItem",
    "ChannelAdapterRegistry",
]
