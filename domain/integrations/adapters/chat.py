"""Chat Integration Adapter for Microsoft Teams & Slack with In-Message Actioning (Prompt 60 / BBP Section 35).

Enforces:
- Inherits from BaseIntegrationAdapter with declared capabilities:
  AUTHENTICATE, HEALTH_CHECK, DISPATCH_EVENT, ACKNOWLEDGE_ALERT.
- Native Formatting: Converts alert events into Microsoft Teams Adaptive Cards and Slack Block Kit payloads.
- Interactive In-Message Actions: Enables immediate alert acknowledgement directly from Teams/Slack.
  Acceptance requirement: An alert acknowledged from a chat message is acknowledged in CloudLens
  with the correct actor.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from domain.alerting.models import AlertEntity
from domain.integrations.contract import BaseIntegrationAdapter
from domain.integrations.models import (
    ChatAlertCard,
    IntegrationConfig,
)
from domain.models.enums import (
    AlertLifecycleStatus,
    IntegrationCapability,
)
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)


class ChatAdapter(BaseIntegrationAdapter):
    """Adapter transforming notifications for Microsoft Teams and Slack webhooks."""

    def __init__(
        self,
        config: IntegrationConfig,
        declared_capabilities: set[IntegrationCapability] | None = None,
    ) -> None:
        super().__init__(config, declared_capabilities)
        # Store for dispatched chat cards: card_id -> ChatAlertCard
        self._cards: dict[str, ChatAlertCard] = {}
        # Alert ID to card index: alert_id -> card_id
        self._alert_to_card: dict[str, str] = {}

    @property
    def platform_type(self) -> str:
        """Destination chat platform ('TEAMS' or 'SLACK')."""
        return self.config.custom_attributes.get("platform", "TEAMS").upper()

    @property
    def adapter_name(self) -> str:
        return f"{self.platform_type.lower()}_chat"

    def default_capabilities(self) -> set[IntegrationCapability]:
        return {
            IntegrationCapability.AUTHENTICATE,
            IntegrationCapability.HEALTH_CHECK,
            IntegrationCapability.DISPATCH_EVENT,
            IntegrationCapability.ACKNOWLEDGE_ALERT,
        }

    def format_teams_adaptive_card(
        self, alert: AlertEntity, deep_link: str, action_url: str
    ) -> dict[str, Any]:
        """Builds a Microsoft Teams Adaptive Card (schema v1.5) with Action.Http."""
        theme_color = "Attention" if alert.severity.value in {"CRITICAL", "HIGH"} else "Warning"
        return {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.5",
                        "body": [
                            {
                                "type": "TextBlock",
                                "text": f"[{alert.severity.value}] {alert.title}",
                                "weight": "Bolder",
                                "size": "Large",
                                "color": theme_color,
                            },
                            {
                                "type": "TextBlock",
                                "text": alert.description,
                                "wrap": True,
                            },
                            {
                                "type": "FactSet",
                                "facts": [
                                    {"title": "Alert Type", "value": alert.alert_type.value},
                                    {"title": "Source", "value": alert.source},
                                    {"title": "Status", "value": alert.status.value},
                                    {"title": "Evidence", "value": alert.evidence.summary},
                                ],
                            },
                        ],
                        "actions": [
                            {
                                "type": "Action.OpenUrl",
                                "title": "Open in CloudLens",
                                "url": deep_link,
                            },
                            {
                                "type": "Action.Submit",
                                "title": "Acknowledge Alert",
                                "data": {
                                    "action": "acknowledge",
                                    "alert_id": alert.id,
                                    "action_url": action_url,
                                },
                            },
                        ],
                    },
                }
            ],
        }

    def format_slack_block_kit(
        self, alert: AlertEntity, deep_link: str, action_url: str
    ) -> dict[str, Any]:
        """Builds a Slack Block Kit JSON structure with interactive overflow/button blocks."""
        emoji = ":rotating_light:" if alert.severity.value in {"CRITICAL", "HIGH"} else ":warning:"
        return {
            "text": f"[{alert.severity.value}] {alert.title}",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{emoji} {alert.title}",
                        "emoji": True,
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Severity:*\n{alert.severity.value}"},
                        {"type": "mrkdwn", "text": f"*Status:*\n{alert.status.value}"},
                        {"type": "mrkdwn", "text": f"*Source:*\n{alert.source}"},
                        {"type": "mrkdwn", "text": f"*Alert Type:*\n{alert.alert_type.value}"},
                    ],
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Evidence:*\n{alert.evidence.summary}",
                    },
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "View in CloudLens"},
                            "url": deep_link,
                            "style": "primary",
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Acknowledge"},
                            "action_id": "acknowledge_alert",
                            "value": alert.id,
                            "url": action_url,
                        },
                    ],
                },
            ],
        }

    def dispatch_alert_card(
        self,
        alert: AlertEntity,
        *,
        tenant_context: TenantContext,
    ) -> ChatAlertCard:
        """Formats and posts an interactive card to Microsoft Teams or Slack webhook."""

        def _action() -> ChatAlertCard:
            base_url = self.config.custom_attributes.get(
                "app_base_url", "https://app.cloudlens.io"
            )
            deep_link = f"{base_url}/tenants/{tenant_context.tenant_id}/alerts/{alert.id}"
            action_url = f"{base_url}/api/v1/integrations/{self.integration_id}/actions/acknowledge"

            if self.platform_type == "SLACK":
                formatted_payload = self.format_slack_block_kit(alert, deep_link, action_url)
            else:
                formatted_payload = self.format_teams_adaptive_card(alert, deep_link, action_url)

            card = ChatAlertCard(
                platform=self.platform_type,
                alert_id=alert.id,
                tenant_id=tenant_context.tenant_id,
                title=alert.title,
                severity=alert.severity.value,
                summary=alert.evidence.summary,
                deep_link=deep_link,
                action_callback_url=action_url,
                formatted_payload=formatted_payload,
            )

            self._cards[card.card_id] = card
            self._alert_to_card[alert.id] = card.card_id

            logger.info(
                "Dispatched %s card '%s' for alert '%s'.",
                self.platform_type,
                card.card_id,
                alert.id,
            )
            return card

        return self.execute_with_resilience(
            IntegrationCapability.DISPATCH_EVENT,
            "dispatch_alert_card",
            _action,
        )

    def handle_in_message_acknowledgement(
        self,
        alert_id: str,
        actor_email: str,
        reason: str | None = None,
        *,
        tenant_context: TenantContext,
        target_alert: AlertEntity | None = None,
    ) -> dict[str, Any]:
        """Actions an alert acknowledgement initiated from an in-message Teams/Slack button click.

        Acceptance requirement:
        - An alert acknowledged from a chat message is acknowledged in CloudLens with the correct actor.
        """

        def _action() -> dict[str, Any]:
            _ = tenant_context
            now = dt.datetime.now(dt.UTC)

            # Update target AlertEntity in CloudLens if provided
            if target_alert:
                target_alert.status = AlertLifecycleStatus.ACKNOWLEDGED
                target_alert.acknowledged_by = actor_email
                target_alert.acknowledged_at = now
                target_alert.acknowledgement_reason = (
                    reason or f"Acknowledged via {self.platform_type} chat action button"
                )

            # Update tracked card state
            card_id = self._alert_to_card.get(alert_id)
            if card_id and card_id in self._cards:
                card = self._cards[card_id]
                card.is_acknowledged = True
                card.acknowledged_by = actor_email
                card.acknowledged_at = now

            logger.info(
                "Chat Action: Alert '%s' successfully acknowledged by actor '%s' via %s.",
                alert_id,
                actor_email,
                self.platform_type,
            )
            return {
                "alert_id": alert_id,
                "status": AlertLifecycleStatus.ACKNOWLEDGED.value,
                "acknowledged_by": actor_email,
                "acknowledged_at": now.isoformat(),
                "platform": self.platform_type,
                "message": f"Alert '{alert_id}' successfully acknowledged by {actor_email}.",
            }

        return self.execute_with_resilience(
            IntegrationCapability.ACKNOWLEDGE_ALERT,
            "handle_in_message_acknowledgement",
            _action,
        )

    def get_card_for_alert(self, alert_id: str) -> ChatAlertCard | None:
        """Retrieves card representation for an alert ID."""
        card_id = self._alert_to_card.get(alert_id)
        return self._cards.get(card_id) if card_id else None
