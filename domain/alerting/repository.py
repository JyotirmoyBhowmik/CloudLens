"""Alerting Repository with Strict Tenant Isolation (Prompt 31, Prompt 13 Item 84, Prompt P07).

Enforces:
- Prompt 13 Item 84: Mandatory non-empty TenantContext on every public repository method.
- Pattern P1 & P4: Protocol contract and PostgreSQL RLS persistence via SqlAlertRepository.
- Production startup guard verifying no in-memory repositories in staging/production.
"""

from __future__ import annotations

import json
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_sync_bridge_loop, get_tenant_session, run_async, verify_persistence_startup_guard
from domain.alerting.models import (
    AlertDeliveryLog,
    AlertEntity,
    RecipientSubscription,
)
from domain.models.enums import AlertLifecycleStatus
from domain.tenant.context import TenantContext


@runtime_checkable
class AlertRepository(Protocol):
    """Authoritative repository protocol for alerts, subscriptions, and delivery logs."""

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> AlertEntity | None: ...
    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AlertEntity]: ...
    def save(self, entity: AlertEntity, *, tenant_context: TenantContext) -> AlertEntity: ...
    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool: ...
    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool: ...
    def save_alert(self, alert: AlertEntity, *, tenant_context: TenantContext) -> AlertEntity: ...
    def get_alert(self, alert_id: str, *, tenant_context: TenantContext) -> AlertEntity | None: ...
    def list_alerts(
        self,
        *,
        tenant_context: TenantContext,
        status: AlertLifecycleStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AlertEntity]: ...
    def find_by_fingerprint(
        self, fingerprint: str, *, tenant_context: TenantContext
    ) -> AlertEntity | None: ...
    def save_subscription(
        self, sub: RecipientSubscription, *, tenant_context: TenantContext
    ) -> RecipientSubscription: ...
    def get_subscription(
        self, sub_id: str, *, tenant_context: TenantContext
    ) -> RecipientSubscription | None: ...
    def list_subscriptions(
        self, *, tenant_context: TenantContext
    ) -> list[RecipientSubscription]: ...
    def delete_subscription(self, sub_id: str, *, tenant_context: TenantContext) -> bool: ...
    def save_delivery_log(
        self, log: AlertDeliveryLog, *, tenant_context: TenantContext
    ) -> AlertDeliveryLog: ...
    def list_delivery_logs(
        self, alert_id: str, *, tenant_context: TenantContext
    ) -> list[AlertDeliveryLog]: ...


class SqlAlertRepository:
    """PostgreSQL production implementation with Row-Level Security enforcement."""

    is_in_memory: bool = False

    def _run_async(self, coro: Any) -> Any:
        return run_async(coro)

    def _row_to_alert(self, row: Any) -> AlertEntity:
        m = dict(row._mapping)
        raw = m.get("alert_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "id" in raw:
            return AlertEntity.model_validate(raw)
        return AlertEntity.model_validate(m)

    # --------------------------------------------------------------------------
    # Alerts Operations
    # --------------------------------------------------------------------------

    async def get_async(self, entity_id: str, *, tenant_context: TenantContext) -> AlertEntity | None:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            query = text("""
                SELECT * FROM alerts
                WHERE id = :id AND tenant_id = :tid
                LIMIT 1;
            """)
            res = await sess.execute(query, {"id": entity_id, "tid": tenant_context.tenant_id})
            row = res.first()
            return self._row_to_alert(row) if row else None

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> AlertEntity | None:
        return self._run_async(self.get_async(entity_id, tenant_context=tenant_context))

    async def save_async(self, entity: AlertEntity, *, tenant_context: TenantContext) -> AlertEntity:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            entity.tenant_id = tenant_context.tenant_id
            query = text("""
                INSERT INTO alerts (
                    id, tenant_id, alert_type, severity, message, status,
                    triggered_at, created_at, updated_at, fingerprint, alert_payload
                ) VALUES (
                    :id, :tenant_id, :alert_type, :severity, :message, :status,
                    :triggered_at, :created_at, NOW(), :fingerprint, CAST(:payload AS jsonb)
                )
                ON CONFLICT (id) DO UPDATE SET
                    status = EXCLUDED.status,
                    severity = EXCLUDED.severity,
                    message = EXCLUDED.message,
                    fingerprint = EXCLUDED.fingerprint,
                    updated_at = NOW(),
                    alert_payload = EXCLUDED.alert_payload;
            """)
            await sess.execute(
                query,
                {
                    "id": entity.id,
                    "tenant_id": tenant_context.tenant_id,
                    "alert_type": entity.alert_type.value if hasattr(entity.alert_type, "value") else str(entity.alert_type),
                    "severity": entity.severity.value if hasattr(entity.severity, "value") else str(entity.severity),
                    "message": entity.description,
                    "status": entity.status.value if hasattr(entity.status, "value") else str(entity.status),
                    "triggered_at": entity.created_at,
                    "created_at": entity.created_at,
                    "fingerprint": entity.fingerprint or None,
                    "payload": json.dumps(entity.model_dump(mode="json")),
                },
            )
            await sess.commit()
            return entity

    def save(self, entity: AlertEntity, *, tenant_context: TenantContext) -> AlertEntity:
        return self._run_async(self.save_async(entity, tenant_context=tenant_context))

    def save_alert(self, alert: AlertEntity, *, tenant_context: TenantContext) -> AlertEntity:
        return self.save(alert, tenant_context=tenant_context)

    def get_alert(self, alert_id: str, *, tenant_context: TenantContext) -> AlertEntity | None:
        return self.get(alert_id, tenant_context=tenant_context)

    async def list_alerts_async(
        self,
        *,
        tenant_context: TenantContext,
        status: AlertLifecycleStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AlertEntity]:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            sql = "SELECT * FROM alerts WHERE tenant_id = :tid"
            params: dict[str, Any] = {"tid": tenant_context.tenant_id, "lim": limit, "off": offset}
            if status:
                sql += " AND status = :st"
                params["st"] = status.value if hasattr(status, "value") else str(status)
            sql += " ORDER BY created_at DESC LIMIT :lim OFFSET :off;"
            res = await sess.execute(text(sql), params)
            rows = res.fetchall()
            return [self._row_to_alert(r) for r in rows]

    def list_alerts(
        self,
        *,
        tenant_context: TenantContext,
        status: AlertLifecycleStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AlertEntity]:
        return self._run_async(self.list_alerts_async(tenant_context=tenant_context, status=status, limit=limit, offset=offset))

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AlertEntity]:
        st = filter_params.get("status") if isinstance(filter_params, dict) else None
        return self.list_alerts(tenant_context=tenant_context, status=st, limit=limit, offset=offset)

    async def delete_async(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("DELETE FROM alerts WHERE id = :id AND tenant_id = :tid;"),
                {"id": entity_id, "tid": tenant_context.tenant_id},
            )
            await sess.commit()
            return res.rowcount > 0

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return self._run_async(self.delete_async(entity_id, tenant_context=tenant_context))

    async def exists_async(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT 1 FROM alerts WHERE id = :id AND tenant_id = :tid LIMIT 1;"),
                {"id": entity_id, "tid": tenant_context.tenant_id},
            )
            return res.first() is not None

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return self._run_async(self.exists_async(entity_id, tenant_context=tenant_context))

    async def find_by_fingerprint_async(
        self, fingerprint: str, *, tenant_context: TenantContext
    ) -> AlertEntity | None:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT * FROM alerts WHERE tenant_id = :tid AND fingerprint = :fp LIMIT 1;"),
                {"tid": tenant_context.tenant_id, "fp": fingerprint},
            )
            row = res.first()
            return self._row_to_alert(row) if row else None

    def find_by_fingerprint(
        self, fingerprint: str, *, tenant_context: TenantContext
    ) -> AlertEntity | None:
        return self._run_async(self.find_by_fingerprint_async(fingerprint, tenant_context=tenant_context))

    # --------------------------------------------------------------------------
    # Subscriptions Operations
    # --------------------------------------------------------------------------

    async def save_subscription_async(
        self, sub: RecipientSubscription, *, tenant_context: TenantContext
    ) -> RecipientSubscription:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            sub.tenant_id = tenant_context.tenant_id
            query = text("""
                INSERT INTO alert_subscriptions (id, tenant_id, name, subscription_payload, created_at, updated_at)
                VALUES (:id, :tid, :name, CAST(:payload AS jsonb), NOW(), NOW())
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    subscription_payload = EXCLUDED.subscription_payload,
                    updated_at = NOW();
            """)
            await sess.execute(
                query,
                {
                    "id": sub.id,
                    "tid": tenant_context.tenant_id,
                    "name": getattr(sub, "name", sub.id),
                    "payload": json.dumps(sub.model_dump(mode="json")),
                },
            )
            await sess.commit()
            return sub

    def save_subscription(
        self, sub: RecipientSubscription, *, tenant_context: TenantContext
    ) -> RecipientSubscription:
        return self._run_async(self.save_subscription_async(sub, tenant_context=tenant_context))

    async def get_subscription_async(
        self, sub_id: str, *, tenant_context: TenantContext
    ) -> RecipientSubscription | None:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT subscription_payload FROM alert_subscriptions WHERE id = :id AND tenant_id = :tid;"),
                {"id": sub_id, "tid": tenant_context.tenant_id},
            )
            row = res.first()
            if not row:
                return None
            raw = row[0]
            if isinstance(raw, str):
                raw = json.loads(raw)
            return RecipientSubscription.model_validate(raw)

    def get_subscription(
        self, sub_id: str, *, tenant_context: TenantContext
    ) -> RecipientSubscription | None:
        return self._run_async(self.get_subscription_async(sub_id, tenant_context=tenant_context))

    async def list_subscriptions_async(
        self, *, tenant_context: TenantContext
    ) -> list[RecipientSubscription]:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT subscription_payload FROM alert_subscriptions WHERE tenant_id = :tid ORDER BY created_at DESC;"),
                {"tid": tenant_context.tenant_id},
            )
            rows = res.fetchall()
            out: list[RecipientSubscription] = []
            for r in rows:
                raw = r[0]
                if isinstance(raw, str):
                    raw = json.loads(raw)
                out.append(RecipientSubscription.model_validate(raw))
            return out

    def list_subscriptions(
        self, *, tenant_context: TenantContext
    ) -> list[RecipientSubscription]:
        return self._run_async(self.list_subscriptions_async(tenant_context=tenant_context))

    async def delete_subscription_async(self, sub_id: str, *, tenant_context: TenantContext) -> bool:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("DELETE FROM alert_subscriptions WHERE id = :id AND tenant_id = :tid;"),
                {"id": sub_id, "tid": tenant_context.tenant_id},
            )
            await sess.commit()
            return res.rowcount > 0

    def delete_subscription(self, sub_id: str, *, tenant_context: TenantContext) -> bool:
        return self._run_async(self.delete_subscription_async(sub_id, tenant_context=tenant_context))

    # --------------------------------------------------------------------------
    # Delivery Logs Operations
    # --------------------------------------------------------------------------

    async def save_delivery_log_async(
        self, log: AlertDeliveryLog, *, tenant_context: TenantContext
    ) -> AlertDeliveryLog:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            log.tenant_id = tenant_context.tenant_id
            query = text("""
                INSERT INTO alert_delivery_logs (id, tenant_id, alert_id, channel, outcome, delivery_payload, attempted_at)
                VALUES (:id, :tid, :aid, :chan, :out, CAST(:payload AS jsonb), NOW())
                ON CONFLICT (id) DO UPDATE SET
                    outcome = EXCLUDED.outcome,
                    delivery_payload = EXCLUDED.delivery_payload;
            """)
            await sess.execute(
                query,
                {
                    "id": log.id,
                    "tid": tenant_context.tenant_id,
                    "aid": log.alert_id,
                    "chan": log.channel.value if hasattr(log.channel, "value") else str(log.channel),
                    "out": log.outcome.value if hasattr(log.outcome, "value") else str(log.outcome),
                    "payload": json.dumps(log.model_dump(mode="json")),
                },
            )
            await sess.commit()
            return log

    def save_delivery_log(
        self, log: AlertDeliveryLog, *, tenant_context: TenantContext
    ) -> AlertDeliveryLog:
        return self._run_async(self.save_delivery_log_async(log, tenant_context=tenant_context))

    async def list_delivery_logs_async(
        self, alert_id: str, *, tenant_context: TenantContext
    ) -> list[AlertDeliveryLog]:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT delivery_payload FROM alert_delivery_logs WHERE tenant_id = :tid AND alert_id = :aid ORDER BY attempted_at DESC;"),
                {"tid": tenant_context.tenant_id, "aid": alert_id},
            )
            rows = res.fetchall()
            out: list[AlertDeliveryLog] = []
            for r in rows:
                raw = r[0]
                if isinstance(raw, str):
                    raw = json.loads(raw)
                out.append(AlertDeliveryLog.model_validate(raw))
            return out

    def list_delivery_logs(
        self, alert_id: str, *, tenant_context: TenantContext
    ) -> list[AlertDeliveryLog]:
        return self._run_async(self.list_delivery_logs_async(alert_id, tenant_context=tenant_context))


# Singleton instance & factory
_alert_repo_instance: AlertRepository | None = None


def get_alert_repository() -> AlertRepository:
    """Returns singleton AlertRepository with production startup guard."""
    global _alert_repo_instance
    if _alert_repo_instance is None:
        _alert_repo_instance = SqlAlertRepository()
        verify_persistence_startup_guard(_alert_repo_instance)
    return _alert_repo_instance


def reset_alert_repository(repo: AlertRepository | None = None) -> None:
    """Resets singleton AlertRepository for testing."""
    global _alert_repo_instance
    _alert_repo_instance = repo
