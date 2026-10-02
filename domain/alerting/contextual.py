"""Inline Contextual Alerts Manager (Prompt 31 Section 4).

Manages inline contextual UI alerts:
1. COST_INFORMATION: Unattached resources, idle storage, cost anomalies.
2. FREE_TIER: Approaching or exceeding free tier quotas.
3. BUDGET: In-context budget proximity warnings on pages and resources.
4. FORECAST: Forward-looking overrun projections on resource views.
5. PRICING_CHANGE: Upstream price modifications affecting specific SKUs.
6. PRICING_UNAVAILABLE: Unmatched SKUs or custom contract rates not published.

Contextual alerts are displayed inline on UI surfaces, distinct from routed notification channels.
"""

from __future__ import annotations

from typing import Any

from domain.alerting.models import ContextualAlert
from domain.audit.models import AuditEventCreate
from domain.audit.service import AuditService, get_audit_service
from domain.models.enums import (
    AlertSeverity,
    AuditEventType,
    ContextualAlertType,
    ContextualAlertVisibility,
)
from domain.models.exceptions import ContextualAlertNotFoundException
from domain.tenant.context import TenantContext


class ContextualAlertManager:
    """Manages the lifecycle and visibility of inline contextual alerts."""

    def __init__(self, audit_service: AuditService | None = None) -> None:
        self._audit_service = audit_service or get_audit_service()
        # Key: (tenant_id, alert_id) -> ContextualAlert
        self._alerts: dict[tuple[str, str], ContextualAlert] = {}

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
        """Publishes an inline contextual alert."""
        alert = ContextualAlert(
            tenant_id=tenant_context.tenant_id,
            alert_type=alert_type,
            title=title,
            message=message,
            visibility=visibility,
            context_entity_type=context_entity_type,
            context_entity_id=context_entity_id,
            severity=severity,
            dismissible=dismissible,
            metadata=metadata or {},
        )
        self._alerts[(tenant_context.tenant_id, alert.id)] = alert

        try:
            self._audit_service.append_event(
                tenant_context=tenant_context,
                event_in=AuditEventCreate(
                    event_type=AuditEventType.CONTEXTUAL_ALERT_DISPLAYED,
                    actor_id="system",
                    actor_roles=["SYSTEM"],
                    action=AuditEventType.CONTEXTUAL_ALERT_DISPLAYED.value,
                    resource_type="ContextualAlert",
                    resource_id=alert.id,
                    details={
                        "alert_type": alert_type.value,
                        "context_entity_type": context_entity_type,
                        "context_entity_id": context_entity_id,
                        "visibility": visibility.value,
                    },
                    correlation_id=tenant_context.correlation_id,
                ),
            )
        except Exception:
            pass
        return alert

    def get_alert(
        self,
        alert_id: str,
        *,
        tenant_context: TenantContext,
    ) -> ContextualAlert:
        """Retrieves a contextual alert by ID within tenant boundary."""
        key = (tenant_context.tenant_id, alert_id)
        if key not in self._alerts:
            raise ContextualAlertNotFoundException(alert_id)
        return self._alerts[key]

    def list_alerts(
        self,
        *,
        tenant_context: TenantContext,
        context_entity_type: str | None = None,
        context_entity_id: str | None = None,
        visibility: ContextualAlertVisibility | None = None,
        include_dismissed: bool = False,
    ) -> list[ContextualAlert]:
        """Lists contextual alerts matching filter criteria for the tenant."""
        results: list[ContextualAlert] = []
        for (t_id, _), alert in self._alerts.items():
            if t_id != tenant_context.tenant_id:
                continue
            if not include_dismissed and alert.is_dismissed:
                continue
            if context_entity_type and alert.context_entity_type != context_entity_type:
                continue
            if context_entity_id and alert.context_entity_id != context_entity_id:
                continue
            if visibility and alert.visibility != visibility:
                continue
            results.append(alert)
        return results

    def dismiss_alert(
        self,
        alert_id: str,
        actor: str,
        *,
        tenant_context: TenantContext,
    ) -> ContextualAlert:
        """Dismisses an active contextual alert."""
        alert = self.get_alert(alert_id, tenant_context=tenant_context)
        alert.dismiss(actor)

        try:
            self._audit_service.append_event(
                tenant_context=tenant_context,
                event_in=AuditEventCreate(
                    event_type=AuditEventType.CONTEXTUAL_ALERT_DISMISSED,
                    actor_id=actor,
                    actor_roles=tenant_context.roles or ["OPERATOR"],
                    action=AuditEventType.CONTEXTUAL_ALERT_DISMISSED.value,
                    resource_type="ContextualAlert",
                    resource_id=alert.id,
                    details={
                        "alert_type": alert.alert_type.value,
                        "dismissed_by": actor,
                        "dismissed_at": alert.dismissed_at.isoformat()
                        if alert.dismissed_at
                        else None,
                    },
                    correlation_id=tenant_context.correlation_id,
                ),
            )
        except Exception:
            pass
        return alert
