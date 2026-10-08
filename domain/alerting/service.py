"""Alerting Service Facade (Prompt 31).

Provides high-level orchestration across AlertEngine, AlertRepository,
ContextualAlertManager, and RecipientRouter.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from domain.alerting.channels.registry import ChannelAdapterRegistry
from domain.alerting.contextual import ContextualAlertManager
from domain.alerting.engine import AlertEngine
from domain.alerting.models import (
    AlertDeliveryLog,
    AlertEntity,
    ContextualAlert,
    RecipientSubscription,
)
from domain.alerting.repository import AlertRepository, get_alert_repository
from domain.alerting.router import RecipientRouter
from domain.audit.service import AuditService, get_audit_service
from domain.models.enums import (
    AlertSeverity,
    ContextualAlertType,
    ContextualAlertVisibility,
)
from domain.tenant.context import TenantContext


class AlertService:
    """Unified service facade for alerting, notifications, and contextual alerts."""

    def __init__(
        self,
        repository: AlertRepository | None = None,
        router: RecipientRouter | None = None,
        registry: ChannelAdapterRegistry | None = None,
        audit_service: AuditService | None = None,
        contextual_manager: ContextualAlertManager | None = None,
        scope_storm_threshold: int = 10,
    ) -> None:
        self.repository = repository or get_alert_repository()
        self.router = router or RecipientRouter()
        self.registry = registry or ChannelAdapterRegistry()
        self.audit_service = audit_service or get_audit_service()
        self.engine = AlertEngine(
            repository=self.repository,
            router=self.router,
            registry=self.registry,
            audit_service=self.audit_service,
            scope_storm_threshold=scope_storm_threshold,
        )
        self.contextual_manager = contextual_manager or ContextualAlertManager(
            audit_service=self.audit_service
        )

    # ==========================================================================
    # Alert Lifecycle Operations
    # ==========================================================================

    def raise_alert(
        self,
        alert: AlertEntity,
        *,
        tenant_context: TenantContext,
        resource_metadata: dict[str, Any] | None = None,
        scope_metadata: dict[str, Any] | None = None,
        auto_dispatch: bool = True,
        dispatch_options: dict[str, Any] | None = None,
    ) -> AlertEntity:
        """Processes and raises an operational or governance alert."""
        return self.engine.raise_alert(
            alert,
            tenant_context=tenant_context,
            resource_metadata=resource_metadata,
            scope_metadata=scope_metadata,
            auto_dispatch=auto_dispatch,
            dispatch_options=dispatch_options,
        )

    def get_alert(
        self,
        alert_id: str,
        *,
        tenant_context: TenantContext,
    ) -> AlertEntity | None:
        """Retrieves an alert by ID."""
        return self.repository.get_alert(alert_id, tenant_context=tenant_context)

    def list_alerts(
        self,
        *,
        tenant_context: TenantContext,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AlertEntity]:
        """Lists alerts for the current tenant."""
        return self.repository.list(tenant_context=tenant_context, limit=limit, offset=offset)

    def acknowledge_alert(
        self,
        alert_id: str,
        actor: str,
        *,
        tenant_context: TenantContext,
        reason: str | None = None,
        remediation_task_id: str | None = None,
    ) -> AlertEntity:
        """Acknowledges an active alert."""
        return self.engine.acknowledge_alert(
            alert_id,
            actor,
            tenant_context=tenant_context,
            reason=reason,
            remediation_task_id=remediation_task_id,
        )

    def resolve_alert(
        self,
        alert_id: str,
        actor: str,
        *,
        tenant_context: TenantContext,
        reason: str | None = None,
    ) -> AlertEntity:
        """Manually resolves an active alert."""
        return self.engine.resolve_alert(
            alert_id, actor, tenant_context=tenant_context, reason=reason
        )

    def add_comment(
        self,
        alert_id: str,
        author: str,
        text: str,
        *,
        tenant_context: TenantContext,
    ) -> AlertEntity:
        """Adds a comment to an alert."""
        return self.engine.add_comment(alert_id, author, text, tenant_context=tenant_context)

    def mark_condition_cleared(
        self,
        alert_id: str,
        *,
        tenant_context: TenantContext,
        now: dt.datetime | None = None,
    ) -> AlertEntity:
        """Marks the underlying condition cleared, beginning dwell time window."""
        return self.engine.mark_condition_cleared(alert_id, tenant_context=tenant_context, now=now)

    def evaluate_auto_resolutions(
        self,
        *,
        tenant_context: TenantContext,
        now: dt.datetime | None = None,
    ) -> list[AlertEntity]:
        """Evaluates active alerts and auto-resolves eligible ones past dwell time."""
        return self.engine.evaluate_auto_resolutions(tenant_context=tenant_context, now=now)

    def evaluate_escalations(
        self,
        *,
        tenant_context: TenantContext,
        escalation_timeout_seconds: int | None = None,
        now: dt.datetime | None = None,
    ) -> list[AlertEntity]:
        """Evaluates high-severity alerts and triggers escalation when unacknowledged."""
        return self.engine.evaluate_escalations(
            tenant_context=tenant_context,
            escalation_timeout_seconds=escalation_timeout_seconds,
            now=now,
        )

    # ==========================================================================
    # Contextual Alerts Operations
    # ==========================================================================

    def create_contextual_alert(
        self,
        alert_type: ContextualAlertType,
        title: str,
        message: str,
        context_entity_type: str,
        context_entity_id: str,
        *,
        tenant_context: TenantContext,
        visibility: ContextualAlertVisibility = ContextualAlertVisibility.PAGE_INLINE,
        severity: AlertSeverity = AlertSeverity.INFO,
        dismissible: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> ContextualAlert:
        """Creates an inline contextual UI alert."""
        return self.contextual_manager.create_contextual_alert(
            alert_type=alert_type,
            title=title,
            message=message,
            context_entity_type=context_entity_type,
            context_entity_id=context_entity_id,
            tenant_context=tenant_context,
            visibility=visibility,
            severity=severity,
            dismissible=dismissible,
            metadata=metadata,
        )

    def list_contextual_alerts(
        self,
        *,
        tenant_context: TenantContext,
        context_entity_type: str | None = None,
        context_entity_id: str | None = None,
        visibility: ContextualAlertVisibility | None = None,
        include_dismissed: bool = False,
    ) -> list[ContextualAlert]:
        """Lists contextual alerts for the tenant."""
        return self.contextual_manager.list_alerts(
            tenant_context=tenant_context,
            context_entity_type=context_entity_type,
            context_entity_id=context_entity_id,
            visibility=visibility,
            include_dismissed=include_dismissed,
        )

    def dismiss_contextual_alert(
        self,
        alert_id: str,
        actor: str,
        *,
        tenant_context: TenantContext,
    ) -> ContextualAlert:
        """Dismisses an inline contextual alert."""
        return self.contextual_manager.dismiss_alert(
            alert_id=alert_id,
            actor=actor,
            tenant_context=tenant_context,
        )

    def acknowledge_contextual_alert(
        self,
        alert_id: str,
        actor: str,
        note: str | None = None,
        *,
        tenant_context: TenantContext,
    ) -> ContextualAlert:
        """Acknowledges an inline contextual alert with audit event."""
        return self.contextual_manager.acknowledge_alert(
            alert_id=alert_id,
            actor=actor,
            note=note,
            tenant_context=tenant_context,
        )

    # ==========================================================================
    # Subscription Operations
    # ==========================================================================

    def create_subscription(
        self,
        subscription: RecipientSubscription,
        *,
        tenant_context: TenantContext,
    ) -> RecipientSubscription:
        """Creates a recipient subscription."""
        return self.repository.save_subscription(subscription, tenant_context=tenant_context)

    def list_subscriptions(
        self,
        *,
        tenant_context: TenantContext,
    ) -> list[RecipientSubscription]:
        """Lists all subscriptions configured for the tenant."""
        return self.repository.list_subscriptions(tenant_context=tenant_context)

    def delete_subscription(
        self,
        subscription_id: str,
        *,
        tenant_context: TenantContext,
    ) -> bool:
        """Deletes a recipient subscription."""
        return self.repository.delete_subscription(subscription_id, tenant_context=tenant_context)

    # ==========================================================================
    # Delivery Logs Operations
    # ==========================================================================

    def list_delivery_logs(
        self,
        *,
        tenant_context: TenantContext,
        alert_id: str | None = None,
    ) -> list[AlertDeliveryLog]:
        """Lists delivery logs for the tenant."""
        return self.repository.list_delivery_logs(tenant_context=tenant_context, alert_id=alert_id)


_ALERT_SERVICE: AlertService | None = None


def get_alert_service() -> AlertService:
    """Returns the singleton instance of AlertService."""
    global _ALERT_SERVICE
    if _ALERT_SERVICE is None:
        _ALERT_SERVICE = AlertService()
    return _ALERT_SERVICE


def reset_alert_service() -> None:
    """Resets the singleton AlertService (used for test isolation)."""
    global _ALERT_SERVICE
    _ALERT_SERVICE = None
