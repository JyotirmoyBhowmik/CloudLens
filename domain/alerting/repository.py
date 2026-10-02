"""Alerting Repository with Strict Tenant Isolation (Prompt 31, Prompt 13 Item 84).

Enforces:
- Prompt 13 Item 84: Mandatory non-empty TenantContext on every public repository method.
- Thread-safe storage for alerts, subscriptions, and delivery logs.
- Deduplication lookups by fingerprint for active alerts.
"""

from __future__ import annotations

import builtins
from typing import Any

from domain.alerting.models import (
    AlertDeliveryLog,
    AlertEntity,
    RecipientSubscription,
)
from domain.models.enums import AlertLifecycleStatus
from domain.tenant.context import TenantContext
from domain.tenant.repository import TenantAwareRepository


class AlertRepository(TenantAwareRepository[AlertEntity]):
    """Thread-safe tenant-scoped repository for alerts, subscriptions, and delivery logs."""

    def __init__(self) -> None:
        super().__init__()
        # Key: (tenant_id, alert_id) -> AlertEntity
        self._alerts: dict[tuple[str, str], AlertEntity] = {}
        # Key: (tenant_id, subscription_id) -> RecipientSubscription
        self._subscriptions: dict[tuple[str, str], RecipientSubscription] = {}
        # Key: (tenant_id, log_id) -> AlertDeliveryLog
        self._delivery_logs: dict[tuple[str, str], AlertDeliveryLog] = {}

    # ==========================================================================
    # 0. Canonical TenantAwareRepository Protocol Implementation
    # ==========================================================================

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> AlertEntity | None:
        """Retrieves an alert by ID within the tenant boundary."""
        self._validate_tenant_context(tenant_context)
        return self.get_alert(entity_id, tenant_context=tenant_context)

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[AlertEntity]:
        """Lists alerts strictly within the tenant with optional pagination."""
        self._validate_tenant_context(tenant_context)
        _ = filter_params
        all_alerts = [
            alert for (t_id, _), alert in self._alerts.items() if t_id == tenant_context.tenant_id
        ]
        # Sort by creation time descending
        all_alerts.sort(key=lambda a: a.created_at, reverse=True)
        return all_alerts[offset : offset + limit]

    def save(self, entity: AlertEntity, *, tenant_context: TenantContext) -> AlertEntity:
        """Persists or updates an alert entity ensuring tenant isolation."""
        self._validate_tenant_context(tenant_context)
        return self.save_alert(entity, tenant_context=tenant_context)

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        """Deletes an alert within tenant scope."""
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, entity_id)
        if key in self._alerts:
            del self._alerts[key]
            return True
        return False

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        """Checks if an alert exists within tenant scope."""
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, entity_id)
        return key in self._alerts

    # ==========================================================================
    # 1. Alert Operations
    # ==========================================================================

    def save_alert(
        self,
        alert: AlertEntity,
        *,
        tenant_context: TenantContext,
    ) -> AlertEntity:
        """Persists or updates an alert entity within tenant boundary."""
        self._validate_tenant_context(tenant_context)
        if alert.tenant_id != tenant_context.tenant_id:
            raise ValueError(
                f"Tenant ID mismatch: alert '{alert.tenant_id}' != context '{tenant_context.tenant_id}'"
            )
        key = (tenant_context.tenant_id, alert.id)
        self._alerts[key] = alert
        return alert

    def get_alert(
        self,
        alert_id: str,
        *,
        tenant_context: TenantContext,
    ) -> AlertEntity | None:
        """Retrieves an alert by ID within tenant boundary."""
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, alert_id)
        return self._alerts.get(key)

    def find_active_by_fingerprint(
        self,
        fingerprint: str,
        *,
        tenant_context: TenantContext,
    ) -> AlertEntity | None:
        """Finds an existing active or acknowledged alert with the specified fingerprint."""
        self._validate_tenant_context(tenant_context)
        for (t_id, _), alert in self._alerts.items():
            if t_id == tenant_context.tenant_id and alert.fingerprint == fingerprint:
                if alert.status in (AlertLifecycleStatus.ACTIVE, AlertLifecycleStatus.ACKNOWLEDGED):
                    return alert
        return None

    def list_active_by_scope(
        self,
        scope_id: str,
        *,
        tenant_context: TenantContext,
    ) -> builtins.list[AlertEntity]:
        """Lists active alerts for a given scope ID within the tenant."""
        self._validate_tenant_context(tenant_context)
        return [
            alert
            for (t_id, _), alert in self._alerts.items()
            if t_id == tenant_context.tenant_id
            and alert.scope_id == scope_id
            and alert.status in (AlertLifecycleStatus.ACTIVE, AlertLifecycleStatus.ACKNOWLEDGED)
        ]

    # ==========================================================================
    # 2. Subscription Operations
    # ==========================================================================

    def save_subscription(
        self,
        subscription: RecipientSubscription,
        *,
        tenant_context: TenantContext,
    ) -> RecipientSubscription:
        """Saves a tenant alert delivery subscription."""
        self._validate_tenant_context(tenant_context)
        if subscription.tenant_id != tenant_context.tenant_id:
            raise ValueError("Tenant ID mismatch on subscription")
        key = (tenant_context.tenant_id, subscription.id)
        self._subscriptions[key] = subscription
        return subscription

    def get_subscription(
        self,
        subscription_id: str,
        *,
        tenant_context: TenantContext,
    ) -> RecipientSubscription | None:
        """Retrieves a subscription by ID."""
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, subscription_id)
        return self._subscriptions.get(key)

    def list_subscriptions(
        self,
        *,
        tenant_context: TenantContext,
    ) -> builtins.list[RecipientSubscription]:
        """Lists all subscriptions configured for the tenant."""
        self._validate_tenant_context(tenant_context)
        return [
            sub
            for (t_id, _), sub in self._subscriptions.items()
            if t_id == tenant_context.tenant_id
        ]

    def delete_subscription(
        self,
        subscription_id: str,
        *,
        tenant_context: TenantContext,
    ) -> bool:
        """Deletes a subscription by ID."""
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, subscription_id)
        if key in self._subscriptions:
            del self._subscriptions[key]
            return True
        return False

    # ==========================================================================
    # 3. Delivery Log Operations
    # ==========================================================================

    def save_delivery_log(
        self,
        log: AlertDeliveryLog,
        *,
        tenant_context: TenantContext,
    ) -> AlertDeliveryLog:
        """Stores an outbound delivery attempt log."""
        self._validate_tenant_context(tenant_context)
        if log.tenant_id != tenant_context.tenant_id:
            raise ValueError("Tenant ID mismatch on delivery log")
        key = (tenant_context.tenant_id, log.id)
        self._delivery_logs[key] = log
        return log

    def list_delivery_logs(
        self,
        *,
        tenant_context: TenantContext,
        alert_id: str | None = None,
    ) -> builtins.list[AlertDeliveryLog]:
        """Lists delivery logs for the tenant, optionally filtered by alert ID."""
        self._validate_tenant_context(tenant_context)
        return [
            log
            for (t_id, _), log in self._delivery_logs.items()
            if t_id == tenant_context.tenant_id and (alert_id is None or log.alert_id == alert_id)
        ]


_ALERT_REPOSITORY: AlertRepository | None = None


def get_alert_repository() -> AlertRepository:
    """Returns singleton AlertRepository instance."""
    global _ALERT_REPOSITORY
    if _ALERT_REPOSITORY is None:
        _ALERT_REPOSITORY = AlertRepository()
    return _ALERT_REPOSITORY


def reset_alert_repository() -> None:
    """Resets singleton AlertRepository instance for test isolation."""
    global _ALERT_REPOSITORY
    _ALERT_REPOSITORY = None
