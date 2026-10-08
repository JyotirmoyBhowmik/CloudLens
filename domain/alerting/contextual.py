"""Inline Contextual Alerts Manager (Prompt 31 Section 4, Prompt P07).

Manages inline contextual UI alerts:
1. COST_INFORMATION: Unattached resources, idle storage, cost anomalies.
2. FREE_TIER: Approaching or exceeding free tier quotas.
3. BUDGET: In-context budget proximity warnings on pages and resources.
4. FORECAST: Forward-looking overrun projections on resource views.
5. PRICING_CHANGE: Upstream price modifications affecting specific SKUs.
6. PRICING_UNAVAILABLE: Unmatched SKUs or custom contract rates not published.

Contextual alerts are displayed inline on UI surfaces, distinct from routed notification channels.
Enforces PostgreSQL RLS persistence via SqlContextualAlertRepository.
"""

from __future__ import annotations

import json
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import text

from db.session import get_tenant_session, run_async, verify_persistence_startup_guard
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


@runtime_checkable
class ContextualAlertRepository(Protocol):
    """Authoritative repository protocol for contextual alerts."""

    def save(self, alert: ContextualAlert, *, tenant_context: TenantContext) -> ContextualAlert: ...
    def get(self, alert_id: str, *, tenant_context: TenantContext) -> ContextualAlert | None: ...
    def list(
        self,
        *,
        tenant_context: TenantContext,
        context_entity_type: str | None = None,
        context_entity_id: str | None = None,
        visibility: ContextualAlertVisibility | None = None,
        include_dismissed: bool = False,
    ) -> list[ContextualAlert]: ...
    def delete(self, alert_id: str, *, tenant_context: TenantContext) -> bool: ...


class SqlContextualAlertRepository:
    """PostgreSQL production implementation with Row-Level Security."""

    is_in_memory: bool = False

    def _run_async(self, coro: Any) -> Any:
        return run_async(coro)

    def _row_to_alert(self, row: Any) -> ContextualAlert:
        m = dict(row._mapping)
        raw = m.get("alert_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "id" in raw:
            return ContextualAlert.model_validate(raw)
        return ContextualAlert.model_validate(m)

    async def save_async(self, alert: ContextualAlert, *, tenant_context: TenantContext) -> ContextualAlert:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            alert.tenant_id = tenant_context.tenant_id
            query = text("""
                INSERT INTO contextual_alerts (
                    id, tenant_id, alert_type, title, context_entity_type,
                    context_entity_id, severity, is_dismissed, alert_payload, created_at, updated_at
                ) VALUES (
                    :id, :tid, :atype, :title, :etype, :eid, :sev, :dismissed, CAST(:payload AS jsonb), NOW(), NOW()
                )
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    severity = EXCLUDED.severity,
                    is_dismissed = EXCLUDED.is_dismissed,
                    alert_payload = EXCLUDED.alert_payload,
                    updated_at = NOW();
            """)
            await sess.execute(
                query,
                {
                    "id": alert.id,
                    "tid": tenant_context.tenant_id,
                    "atype": alert.alert_type.value if hasattr(alert.alert_type, "value") else str(alert.alert_type),
                    "title": alert.title,
                    "etype": alert.context_entity_type,
                    "eid": alert.context_entity_id,
                    "sev": alert.severity.value if hasattr(alert.severity, "value") else str(alert.severity),
                    "dismissed": alert.is_dismissed,
                    "payload": json.dumps(alert.model_dump(mode="json")),
                },
            )
            await sess.commit()
            return alert

    def save(self, alert: ContextualAlert, *, tenant_context: TenantContext) -> ContextualAlert:
        return self._run_async(self.save_async(alert, tenant_context=tenant_context))

    async def get_async(self, alert_id: str, *, tenant_context: TenantContext) -> ContextualAlert | None:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT * FROM contextual_alerts WHERE id = :id AND tenant_id = :tid LIMIT 1;"),
                {"id": alert_id, "tid": tenant_context.tenant_id},
            )
            row = res.first()
            return self._row_to_alert(row) if row else None

    def get(self, alert_id: str, *, tenant_context: TenantContext) -> ContextualAlert | None:
        return self._run_async(self.get_async(alert_id, tenant_context=tenant_context))

    async def list_async(
        self,
        *,
        tenant_context: TenantContext,
        context_entity_type: str | None = None,
        context_entity_id: str | None = None,
        visibility: ContextualAlertVisibility | None = None,
        include_dismissed: bool = False,
    ) -> list[ContextualAlert]:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            sql = "SELECT * FROM contextual_alerts WHERE tenant_id = :tid"
            params: dict[str, Any] = {"tid": tenant_context.tenant_id}
            if not include_dismissed:
                sql += " AND is_dismissed = FALSE"
            if context_entity_type:
                sql += " AND context_entity_type = :etype"
                params["etype"] = context_entity_type
            if context_entity_id:
                sql += " AND context_entity_id = :eid"
                params["eid"] = context_entity_id
            sql += " ORDER BY created_at DESC;"
            res = await sess.execute(text(sql), params)
            rows = res.fetchall()
            alerts = [self._row_to_alert(r) for r in rows]
            if visibility:
                alerts = [a for a in alerts if a.visibility == visibility]
            return alerts

    def list(
        self,
        *,
        tenant_context: TenantContext,
        context_entity_type: str | None = None,
        context_entity_id: str | None = None,
        visibility: ContextualAlertVisibility | None = None,
        include_dismissed: bool = False,
    ) -> list[ContextualAlert]:
        return self._run_async(
            self.list_async(
                tenant_context=tenant_context,
                context_entity_type=context_entity_type,
                context_entity_id=context_entity_id,
                visibility=visibility,
                include_dismissed=include_dismissed,
            )
        )

    async def delete_async(self, alert_id: str, *, tenant_context: TenantContext) -> bool:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("DELETE FROM contextual_alerts WHERE id = :id AND tenant_id = :tid;"),
                {"id": alert_id, "tid": tenant_context.tenant_id},
            )
            await sess.commit()
            return res.rowcount > 0

    def delete(self, alert_id: str, *, tenant_context: TenantContext) -> bool:
        return self._run_async(self.delete_async(alert_id, tenant_context=tenant_context))


class ContextualAlertManager:
    """Manages the lifecycle and visibility of inline contextual alerts."""

    def __init__(
        self,
        repository: ContextualAlertRepository | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self._repository = repository or SqlContextualAlertRepository()
        self._audit_service = audit_service or get_audit_service()
        verify_persistence_startup_guard(self._repository)

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
        self._repository.save(alert, tenant_context=tenant_context)

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
        alert = self._repository.get(alert_id, tenant_context=tenant_context)
        if not alert:
            raise ContextualAlertNotFoundException(alert_id)
        return alert

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
        return self._repository.list(
            tenant_context=tenant_context,
            context_entity_type=context_entity_type,
            context_entity_id=context_entity_id,
            visibility=visibility,
            include_dismissed=include_dismissed,
        )

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
        self._repository.save(alert, tenant_context=tenant_context)

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

    def acknowledge_alert(
        self,
        alert_id: str,
        actor: str,
        note: str | None = None,
        *,
        tenant_context: TenantContext,
    ) -> ContextualAlert:
        """Acknowledges an active contextual alert with audit provenance."""
        alert = self.get_alert(alert_id, tenant_context=tenant_context)
        alert.acknowledge(actor=actor, note=note)
        self._repository.save(alert, tenant_context=tenant_context)

        try:
            self._audit_service.append_event(
                tenant_context=tenant_context,
                event_in=AuditEventCreate(
                    event_type=AuditEventType.CONTEXTUAL_ALERT_ACKNOWLEDGED,
                    actor_id=actor,
                    actor_roles=tenant_context.roles or ["OPERATOR"],
                    action=AuditEventType.CONTEXTUAL_ALERT_ACKNOWLEDGED.value,
                    resource_type="ContextualAlert",
                    resource_id=alert.id,
                    details={
                        "alert_type": alert.alert_type.value,
                        "acknowledged_by": actor,
                        "acknowledged_at": alert.acknowledged_at.isoformat()
                        if alert.acknowledged_at
                        else None,
                        "acknowledgement_note": note,
                    },
                    correlation_id=tenant_context.correlation_id,
                ),
            )
        except Exception:
            pass
        return alert


_manager_instance: ContextualAlertManager | None = None


def get_contextual_alert_manager(
    repo: ContextualAlertRepository | None = None,
) -> ContextualAlertManager:
    """Returns singleton ContextualAlertManager."""
    global _manager_instance
    if _manager_instance is None or repo is not None:
        _manager_instance = ContextualAlertManager(repository=repo)
    return _manager_instance


def reset_contextual_alert_manager() -> None:
    """Resets singleton ContextualAlertManager for test isolation."""
    global _manager_instance
    _manager_instance = None
