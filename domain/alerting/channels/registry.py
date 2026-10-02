"""Channel Adapter Registry with Negative Constraint Enforcement (Prompt 31).

Enforces:
- Central registry of outbound delivery adapters.
- Pluggable extension for Phase 2 chat (Slack, Teams) and ITSM (Jira, ServiceNow).
- STRICT NEGATIVE CONSTRAINT: SMS and Voice are categorically forbidden. Any attempt
  to register, query, or dispatch via SMS or Voice raises ChannelNotSupportedException.
"""

from __future__ import annotations

from domain.alerting.channels.adapter import ChannelAdapter
from domain.alerting.channels.email import EmailChannelAdapter
from domain.alerting.channels.in_app import InAppChannelAdapter
from domain.alerting.channels.webhook import WebhookChannelAdapter
from domain.models.enums import NotificationChannel
from domain.models.exceptions import ChannelNotSupportedException

FORBIDDEN_CHANNELS = {"SMS", "VOICE", "CALL", "PHONE", "PAGING"}


class ChannelAdapterRegistry:
    """Registry managing active notification delivery channel adapters."""

    def __init__(self) -> None:
        self._adapters: dict[NotificationChannel, ChannelAdapter] = {}
        # Register default MVP adapters
        self.register(EmailChannelAdapter())
        self.register(WebhookChannelAdapter())
        self.register(InAppChannelAdapter())

    def register(self, adapter: ChannelAdapter) -> None:
        """Registers a channel adapter."""
        channel_name = adapter.channel_type.value.upper()
        if channel_name in FORBIDDEN_CHANNELS:
            raise ChannelNotSupportedException(channel_name)
        self._adapters[adapter.channel_type] = adapter

    def get(self, channel: NotificationChannel | str) -> ChannelAdapter:
        """Retrieves an adapter for the specified channel.

        Raises ChannelNotSupportedException if channel is forbidden or not registered.
        """
        raw_name = (
            channel.value.upper()
            if isinstance(channel, NotificationChannel)
            else str(channel).upper()
        )
        if raw_name in FORBIDDEN_CHANNELS:
            raise ChannelNotSupportedException(raw_name)

        target_channel: NotificationChannel | None = None
        for ch in NotificationChannel:
            if ch.value.upper() == raw_name:
                target_channel = ch
                break

        if target_channel is None or target_channel not in self._adapters:
            raise ChannelNotSupportedException(raw_name)

        return self._adapters[target_channel]

    def is_channel_supported(self, channel: str) -> bool:
        """Checks if a channel string is valid and supported."""
        raw_name = channel.upper()
        if raw_name in FORBIDDEN_CHANNELS:
            return False
        return any(ch.value.upper() == raw_name for ch in self._adapters)

    def list_supported_channels(self) -> list[NotificationChannel]:
        """Lists all currently active delivery channels."""
        return list(self._adapters.keys())
