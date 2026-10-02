"""Channel adapters package for alert delivery."""

from domain.alerting.channels.adapter import ChannelAdapter
from domain.alerting.channels.email import EmailChannelAdapter
from domain.alerting.channels.in_app import InAppChannelAdapter, InAppNotificationItem
from domain.alerting.channels.registry import ChannelAdapterRegistry
from domain.alerting.channels.webhook import WebhookChannelAdapter

__all__ = [
    "ChannelAdapter",
    "EmailChannelAdapter",
    "WebhookChannelAdapter",
    "InAppChannelAdapter",
    "InAppNotificationItem",
    "ChannelAdapterRegistry",
]
