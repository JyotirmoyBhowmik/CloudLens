"""Alert Recipient Resolution and Routing Engine (Prompt 31).

Enforces:
- Strict resolution hierarchy:
  1. Entity / Resource Owner (from tags or metadata).
  2. Scope Owner (subscription, project, account, or cost centre owner).
  3. Explicit Subscriptions (tenant subscriptions by alert type, severity, scope).
  4. Fallback: Scope default administrator + raise a governance exception.
- Quiet hours evaluation: Non-critical alerts (INFO/WARNING) suppressed/buffered during quiet hours;
  HIGH and CRITICAL alerts unconditionally bypass quiet hours.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from domain.alerting.models import (
    AlertEntity,
    QuietHoursConfig,
    RecipientResolutionResult,
    RecipientSubscription,
)
from domain.models.enums import (
    AlertSeverity,
    NotificationChannel,
)
from domain.tenant.context import TenantContext


class RecipientRouter:
    """Resolves alert recipients through the four-stage governance hierarchy."""

    def __init__(
        self,
        default_scope_admin: str = "governance-admin@cloudlens.internal",
        default_admin_channel: NotificationChannel = NotificationChannel.EMAIL,
    ) -> None:
        self.default_scope_admin = default_scope_admin
        self.default_admin_channel = default_admin_channel

    def resolve_recipients(
        self,
        alert: AlertEntity,
        *,
        tenant_context: TenantContext,
        resource_metadata: dict[str, Any] | None = None,
        scope_metadata: dict[str, Any] | None = None,
        subscriptions: list[RecipientSubscription] | None = None,
        now: dt.datetime | None = None,
    ) -> RecipientResolutionResult:
        """Executes the 4-stage recipient resolution algorithm."""
        _ = tenant_context
        eval_time = now or dt.datetime.now(dt.UTC)
        candidates: list[tuple[str, NotificationChannel, QuietHoursConfig | None]] = []
        resolution_source = ""
        governance_exception_raised = False
        fallback_reason: str | None = None

        # Stage 1: Resource / Entity Ownership
        if resource_metadata:
            tags = resource_metadata.get("tags", {})
            owner = (
                tags.get("owner")
                or tags.get("Owner")
                or tags.get("contact")
                or tags.get("team")
                or resource_metadata.get("owner")
            )
            if owner and isinstance(owner, str) and owner.strip():
                channel = NotificationChannel.EMAIL if "@" in owner else NotificationChannel.IN_APP
                candidates.append((owner.strip(), channel, None))
                resolution_source = "entity_owner"

        # Stage 2: Scope Ownership (if Stage 1 produced nothing)
        if not candidates and scope_metadata:
            scope_owner = (
                scope_metadata.get("owner")
                or scope_metadata.get("administrator")
                or scope_metadata.get("contact")
            )
            if scope_owner and isinstance(scope_owner, str) and scope_owner.strip():
                channel = (
                    NotificationChannel.EMAIL if "@" in scope_owner else NotificationChannel.IN_APP
                )
                candidates.append((scope_owner.strip(), channel, None))
                resolution_source = "scope_owner"

        # Stage 3: Explicit Subscriptions
        if subscriptions:
            for sub in subscriptions:
                if sub.scope_id and alert.scope_id and sub.scope_id != alert.scope_id:
                    continue
                if sub.alert_types and alert.alert_type not in sub.alert_types:
                    continue
                if sub.severities and alert.severity not in sub.severities:
                    continue

                candidates.append((sub.recipient, sub.channel, sub.quiet_hours))
                if not resolution_source:
                    resolution_source = "explicit_subscription"

        # Stage 4: Fallback to Scope Default Administrator + Governance Exception
        if not candidates:
            candidates.append((self.default_scope_admin, self.default_admin_channel, None))
            resolution_source = "scope_default_administrator_fallback"
            governance_exception_raised = True
            fallback_reason = (
                f"No resource owner, scope owner, or explicit subscriptions found for alert "
                f"'{alert.id}' (scope={alert.scope_id}, resource={alert.affected_resource_id}). "
                f"Routed to default administrator and flagged governance exception."
            )

        # Process candidates with Quiet Hours filtering
        active_recipients: list[str] = []
        active_channels: list[NotificationChannel] = []

        is_high_or_critical = alert.severity in (
            AlertSeverity.CRITICAL,
            AlertSeverity.HIGH,
            AlertSeverity.ERROR,
        )

        for recipient, channel, quiet_hours in candidates:
            if quiet_hours and not is_high_or_critical:
                if quiet_hours.is_in_quiet_hours(eval_time, alert.severity):
                    # Suppressed by quiet hours
                    alert.quiet_hours_suppressed = True
                    alert.digest_buffered = True
                    continue

            if recipient not in active_recipients:
                active_recipients.append(recipient)
                active_channels.append(channel)

        # If all candidates were suppressed by quiet hours, ensure we return result indicating quiet hours
        if not active_recipients and candidates:
            # All candidates suppressed for this cycle
            return RecipientResolutionResult(
                recipients=[],
                channels=[],
                resolution_source=resolution_source,
                governance_exception_raised=governance_exception_raised,
                fallback_reason="Recipients suppressed during quiet hours (digest buffered)",
            )

        return RecipientResolutionResult(
            recipients=active_recipients,
            channels=active_channels,
            resolution_source=resolution_source,
            governance_exception_raised=governance_exception_raised,
            fallback_reason=fallback_reason,
        )
