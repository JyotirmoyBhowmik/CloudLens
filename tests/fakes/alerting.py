"""In-memory fake alerting repository for testing."""

from __future__ import annotations

from typing import Any
import datetime as dt

from domain.alerting.models import (
    AlertDeliveryLog,
    AlertEntity,
    ContextualAlert,
    RecipientSubscription,
)
from domain.models.enums import AlertLifecycleStatus, ContextualAlertType
from domain.models.exceptions import MissingTenantContextException
from domain.tenant.context import TenantContext


class InMemoryAlertRepository:
    """In-memory implementation of AlertRepository for test suites."""

    is_in_memory: bool = True

    def __init__(self) -> None:
        self._alerts: dict[tuple[str, str], AlertEntity] = {}
        self._subscriptions: dict[tuple[str, str], RecipientSubscription] = {}
        self._delivery_logs: dict[tuple[str, str], AlertDeliveryLog] = {}

    def _check_context(self, tenant_context: TenantContext) -> None:
        if tenant_context is None or not getattr(tenant_context, "tenant_id", None):
            raise MissingTenantContextException("TenantContext is mandatory")

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> AlertEntity | None:
        self._check_context(tenant_context)
        return self._alerts.get((tenant_context.tenant_id, entity_id))

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AlertEntity]:
        self._check_context(tenant_context)
        all_alerts = [
            alert for (t_id, _), alert in self._alerts.items() if t_id == tenant_context.tenant_id
        ]
        all_alerts.sort(key=lambda a: a.created_at, reverse=True)
        return all_alerts[offset : offset + limit]

    def save(self, entity: AlertEntity, *, tenant_context: TenantContext) -> AlertEntity:
        entity.tenant_id = tenant_context.tenant_id
        self._alerts[(tenant_context.tenant_id, entity.id)] = entity
        return entity

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return bool(self._alerts.pop((tenant_context.tenant_id, entity_id), None))

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return (tenant_context.tenant_id, entity_id) in self._alerts

    def save_alert(self, alert: AlertEntity, *, tenant_context: TenantContext) -> AlertEntity:
        return self.save(alert, tenant_context=tenant_context)

    def get_alert(self, alert_id: str, *, tenant_context: TenantContext) -> AlertEntity | None:
        return self.get(alert_id, tenant_context=tenant_context)

    def list_alerts(
        self,
        *,
        tenant_context: TenantContext,
        status: AlertLifecycleStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AlertEntity]:
        items = [a for (tid, _), a in self._alerts.items() if tid == tenant_context.tenant_id]
        if status:
            items = [a for a in items if a.status == status]
        items.sort(key=lambda a: a.created_at, reverse=True)
        return items[offset : offset + limit]

    def find_by_fingerprint(
        self, fingerprint: str, *, tenant_context: TenantContext
    ) -> AlertEntity | None:
        for (tid, _), a in self._alerts.items():
            if tid == tenant_context.tenant_id and a.fingerprint == fingerprint:
                return a
        return None

    def find_active_by_fingerprint(
        self, fingerprint: str, *, tenant_context: TenantContext
    ) -> AlertEntity | None:
        for (tid, _), a in self._alerts.items():
            if tid == tenant_context.tenant_id and a.fingerprint == fingerprint:
                if a.status in (AlertLifecycleStatus.ACTIVE, AlertLifecycleStatus.ACKNOWLEDGED):
                    return a
        return None

    def list_active_by_scope(
        self, scope_id: str, *, tenant_context: TenantContext
    ) -> list[AlertEntity]:
        return [
            a
            for (tid, _), a in self._alerts.items()
            if tid == tenant_context.tenant_id
            and getattr(a, "scope_id", None) == scope_id
            and a.status in (AlertLifecycleStatus.ACTIVE, AlertLifecycleStatus.ACKNOWLEDGED)
        ]

    def save_subscription(
        self, sub: RecipientSubscription, *, tenant_context: TenantContext
    ) -> RecipientSubscription:
        sub.tenant_id = tenant_context.tenant_id
        self._subscriptions[(tenant_context.tenant_id, sub.id)] = sub
        return sub

    def get_subscription(
        self, sub_id: str, *, tenant_context: TenantContext
    ) -> RecipientSubscription | None:
        return self._subscriptions.get((tenant_context.tenant_id, sub_id))

    def list_subscriptions(self, *, tenant_context: TenantContext) -> list[RecipientSubscription]:
        return [s for (tid, _), s in self._subscriptions.items() if tid == tenant_context.tenant_id]

    def delete_subscription(self, sub_id: str, *, tenant_context: TenantContext) -> bool:
        return bool(self._subscriptions.pop((tenant_context.tenant_id, sub_id), None))

    def save_delivery_log(
        self, log: AlertDeliveryLog, *, tenant_context: TenantContext
    ) -> AlertDeliveryLog:
        log.tenant_id = tenant_context.tenant_id
        self._delivery_logs[(tenant_context.tenant_id, log.id)] = log
        return log

    def list_delivery_logs(
        self, alert_id: str, *, tenant_context: TenantContext
    ) -> list[AlertDeliveryLog]:
        return [
            l
            for (tid, _), l in self._delivery_logs.items()
            if tid == tenant_context.tenant_id and l.alert_id == alert_id
        ]


class InMemoryContextualAlertRepository:
    """In-memory implementation of ContextualAlertRepository for test suites."""

    is_in_memory: bool = True

    def __init__(self) -> None:
        self._alerts: dict[tuple[str, str], ContextualAlert] = {}

    def save(self, alert: ContextualAlert, *, tenant_context: TenantContext) -> ContextualAlert:
        alert.tenant_id = tenant_context.tenant_id
        self._alerts[(tenant_context.tenant_id, alert.id)] = alert
        return alert

    def get(self, alert_id: str, *, tenant_context: TenantContext) -> ContextualAlert | None:
        return self._alerts.get((tenant_context.tenant_id, alert_id))

    def list(
        self,
        *,
        tenant_context: TenantContext,
        context_entity_type: str | None = None,
        context_entity_id: str | None = None,
        include_dismissed: bool = False,
    ) -> list[ContextualAlert]:
        items = [a for (tid, _), a in self._alerts.items() if tid == tenant_context.tenant_id]
        if context_entity_type:
            items = [a for a in items if a.context_entity_type == context_entity_type]
        if context_entity_id:
            items = [a for a in items if a.context_entity_id == context_entity_id]
        if not include_dismissed:
            items = [a for a in items if not a.is_dismissed]
        return items

    def dismiss(self, alert_id: str, *, tenant_context: TenantContext) -> bool:
        alert = self.get(alert_id, tenant_context=tenant_context)
        if alert:
            alert.is_dismissed = True
            return True
        return False
