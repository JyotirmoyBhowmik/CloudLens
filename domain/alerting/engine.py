"""Alert Processing Engine (Prompt 31).

Enforces:
- Deduplication against active alerts by fingerprint.
- Scope storm grouping: >10 child alerts generated in a scope/cycle -> single grouped scope alert.
- Mandatory empirical evidence validation.
- Auto-resolution after condition clearance and anti-flapping dwell time.
- High-severity escalation SLA tracking (never let high-severity alerts disappear silently).
- Recipient routing hierarchy with fallback governance exception.
- Audit emission on all state transitions and delivery attempts.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from domain.alerting.channels.registry import ChannelAdapterRegistry
from domain.alerting.models import (
    AlertDeliveryLog,
    AlertEntity,
    AlertEvidence,
    RecipientResolutionResult,
)
from domain.alerting.repository import AlertRepository
from domain.alerting.router import RecipientRouter
from domain.audit.models import AuditEventCreate
from domain.audit.service import AuditService, get_audit_service
from domain.models.enums import (
    AlertLifecycleStatus,
    AlertSeverity,
    AlertType,
    AuditEventType,
    DeliveryOutcome,
    EscalationState,
    NotificationChannel,
)
from domain.models.exceptions import (
    AlertNotFoundException,
    MissingAlertEvidenceException,
)
from domain.tenant.context import TenantContext


class AlertEngine:
    """Core state engine and lifecycle coordinator for alerts."""

    def __init__(
        self,
        repository: AlertRepository,
        router: RecipientRouter | None = None,
        registry: ChannelAdapterRegistry | None = None,
        audit_service: AuditService | None = None,
        scope_storm_threshold: int = 10,
        default_escalation_timeout_seconds: int = 3600,
    ) -> None:
        self.repository = repository
        self.router = router or RecipientRouter()
        self.registry = registry or ChannelAdapterRegistry()
        self.audit_service = audit_service or get_audit_service()
        self.scope_storm_threshold = scope_storm_threshold
        self.default_escalation_timeout_seconds = default_escalation_timeout_seconds

    def _emit_audit(
        self,
        event_type: AuditEventType,
        actor: str,
        *,
        tenant_context: TenantContext,
        target_id: str,
        target_type: str,
        details: dict[str, Any],
    ) -> None:
        """Appends an event to the tenant's append-only audit stream safely."""
        try:
            roles = (
                ["SYSTEM"]
                if "engine:" in actor or actor == "system"
                else (tenant_context.roles or ["OPERATOR"])
            )
            self.audit_service.append_event(
                tenant_context=tenant_context,
                event_in=AuditEventCreate(
                    event_type=event_type,
                    actor_id=actor,
                    actor_roles=roles,
                    action=event_type.value,
                    resource_type=target_type,
                    resource_id=target_id,
                    details=details,
                    correlation_id=tenant_context.correlation_id,
                ),
            )
        except Exception:
            pass

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
        """Processes and raises an incoming alert candidate.

        Validates mandatory empirical evidence, performs deduplication, handles
        storm grouping, routes recipients, and dispatches outbound notifications.
        """
        # 1. Mandatory Evidence Rule
        if not alert.evidence:
            raise MissingAlertEvidenceException(
                "Alert cannot be emitted without empirical evidence."
            )

        # 2. Deduplication check
        existing = self.repository.find_active_by_fingerprint(
            alert.fingerprint, tenant_context=tenant_context
        )
        if existing:
            existing.repeat_count += 1
            existing.current_value = alert.current_value
            existing.previous_value = alert.previous_value
            existing.evidence = alert.evidence
            existing.updated_at = dt.datetime.now(dt.UTC)
            # If it was in the process of clearing, retrigger resets the dwell timer
            if existing.condition_cleared_at:
                existing.mark_condition_retriggered()
            self.repository.save_alert(existing, tenant_context=tenant_context)
            return existing

        # 3. Check for Scope Storm Grouping (>10 active alerts in same scope)
        if alert.scope_id:
            active_scope_alerts = self.repository.list_active_by_scope(
                alert.scope_id, tenant_context=tenant_context
            )
            if len(active_scope_alerts) >= self.scope_storm_threshold:
                # Trigger Scope Storm Grouping
                return self._group_scope_storm(
                    new_alert=alert,
                    existing_alerts=active_scope_alerts,
                    tenant_context=tenant_context,
                    auto_dispatch=auto_dispatch,
                    dispatch_options=dispatch_options,
                )

        # 4. Resolve Recipients
        subscriptions = self.repository.list_subscriptions(tenant_context=tenant_context)
        routing_result = self.router.resolve_recipients(
            alert,
            tenant_context=tenant_context,
            resource_metadata=resource_metadata,
            scope_metadata=scope_metadata,
            subscriptions=subscriptions,
        )
        alert.recipients = routing_result.recipients
        alert.governance_exception_raised = routing_result.governance_exception_raised

        # Set escalation state for HIGH and CRITICAL alerts
        if alert.severity in (AlertSeverity.HIGH, AlertSeverity.CRITICAL):
            alert.escalation_state = EscalationState.PENDING

        # 5. Persist the alert
        saved = self.repository.save_alert(alert, tenant_context=tenant_context)

        # 6. Audit Trail for Generation
        self._emit_audit(
            event_type=AuditEventType.ALERT_GENERATED,
            actor=alert.source,
            tenant_context=tenant_context,
            target_id=saved.id,
            target_type="AlertEntity",
            details={
                "alert_type": saved.alert_type.value,
                "severity": saved.severity.value,
                "title": saved.title,
                "source": saved.source,
                "scope_id": saved.scope_id,
                "affected_resource_id": saved.affected_resource_id,
                "current_value": str(saved.current_value),
                "threshold_value": str(saved.threshold_value),
                "recipients_count": len(saved.recipients),
                "governance_exception_raised": saved.governance_exception_raised,
            },
        )

        # 7. Audit Governance Exception if fallback was used
        if saved.governance_exception_raised:
            self._emit_audit(
                event_type=AuditEventType.GOVERNANCE_EXCEPTION_RAISED,
                actor="engine:router",
                tenant_context=tenant_context,
                target_id=saved.id,
                target_type="AlertEntity",
                details={
                    "alert_id": saved.id,
                    "reason": routing_result.fallback_reason,
                    "fallback_recipient": saved.recipients[0] if saved.recipients else "none",
                },
            )

        # 8. Outbound Dispatch
        if auto_dispatch and saved.recipients:
            self._dispatch_alert(
                saved,
                routing_result=routing_result,
                tenant_context=tenant_context,
                dispatch_options=dispatch_options,
            )

        return saved

    def _group_scope_storm(
        self,
        new_alert: AlertEntity,
        existing_alerts: list[AlertEntity],
        *,
        tenant_context: TenantContext,
        auto_dispatch: bool,
        dispatch_options: dict[str, Any] | None,
    ) -> AlertEntity:
        """Consolidates >10 scope alerts into a single grouped scope storm alert."""
        # Save new alert as grouped child
        all_children = existing_alerts + [new_alert]
        child_ids = [c.id for c in all_children]

        parent_evidence = AlertEvidence(
            summary=f"Scope storm detected: {len(all_children)} alerts raised in scope '{new_alert.scope_id}'.",
            datapoints=[
                {
                    "alert_id": c.id,
                    "type": c.alert_type.value,
                    "severity": c.severity.value,
                    "title": c.title,
                }
                for c in all_children
            ],
            context={"scope_id": new_alert.scope_id, "child_count": len(all_children)},
        )

        parent_alert = AlertEntity(
            tenant_id=tenant_context.tenant_id,
            alert_type=AlertType.SCOPE_STORM_GROUPED,
            severity=AlertSeverity.HIGH,
            title=f"Scope Alert Storm: {len(all_children)} alerts in scope '{new_alert.scope_id}'",
            description=(
                f"More than {self.scope_storm_threshold} alerts occurred simultaneously in scope '{new_alert.scope_id}'. "
                f"Individual notifications have been suppressed and grouped to avoid alert fatigue."
            ),
            source="engine:storm_detector",
            scope_id=new_alert.scope_id,
            scope_type=new_alert.scope_type,
            evidence=parent_evidence,
            child_alert_ids=child_ids,
        )

        saved_parent = self.repository.save_alert(parent_alert, tenant_context=tenant_context)

        # Update and suppress child alerts
        for child in all_children:
            child.grouped_parent_id = saved_parent.id
            child.status = AlertLifecycleStatus.GROUPED
            self.repository.save_alert(child, tenant_context=tenant_context)

        self._emit_audit(
            event_type=AuditEventType.ALERT_GROUPED,
            actor="engine:storm_detector",
            tenant_context=tenant_context,
            target_id=saved_parent.id,
            target_type="AlertEntity",
            details={
                "parent_alert_id": saved_parent.id,
                "scope_id": new_alert.scope_id,
                "child_count": len(child_ids),
                "child_alert_ids": child_ids,
            },
        )

        if auto_dispatch:
            routing_result = self.router.resolve_recipients(
                saved_parent,
                tenant_context=tenant_context,
            )
            saved_parent.recipients = routing_result.recipients
            self._dispatch_alert(
                saved_parent,
                routing_result=routing_result,
                tenant_context=tenant_context,
                dispatch_options=dispatch_options,
            )

        return saved_parent

    def _dispatch_alert(
        self,
        alert: AlertEntity,
        routing_result: RecipientResolutionResult,
        *,
        tenant_context: TenantContext,
        dispatch_options: dict[str, Any] | None = None,
    ) -> None:
        """Dispatches outbound delivery for each resolved recipient."""
        for idx, recipient in enumerate(routing_result.recipients):
            channel = (
                routing_result.channels[idx]
                if idx < len(routing_result.channels)
                else NotificationChannel.EMAIL
            )
            try:
                adapter = self.registry.get(channel)
                log = adapter.send(
                    alert,
                    recipient,
                    tenant_context=tenant_context,
                    options=dispatch_options,
                )
                self.repository.save_delivery_log(log, tenant_context=tenant_context)

                audit_type = (
                    AuditEventType.ALERT_DELIVERED
                    if log.outcome == DeliveryOutcome.DELIVERED
                    else AuditEventType.ALERT_DELIVERY_FAILED
                )
                self._emit_audit(
                    event_type=audit_type,
                    actor="engine:dispatcher",
                    tenant_context=tenant_context,
                    target_id=alert.id,
                    target_type="AlertEntity",
                    details={
                        "channel": channel.value,
                        "recipient": recipient,
                        "outcome": log.outcome.value,
                        "error_message": log.error_message,
                    },
                )
            except Exception as e:
                # Log dispatch error without failing the core alert creation
                err_log = AlertDeliveryLog(
                    tenant_id=tenant_context.tenant_id,
                    alert_id=alert.id,
                    channel=channel,
                    recipient=recipient,
                    outcome=DeliveryOutcome.FAILED,
                    error_message=str(e),
                )
                self.repository.save_delivery_log(err_log, tenant_context=tenant_context)
                self._emit_audit(
                    event_type=AuditEventType.ALERT_DELIVERY_FAILED,
                    actor="engine:dispatcher",
                    tenant_context=tenant_context,
                    target_id=alert.id,
                    target_type="AlertEntity",
                    details={"channel": channel.value, "recipient": recipient, "error": str(e)},
                )

    def acknowledge_alert(
        self,
        alert_id: str,
        actor: str,
        *,
        tenant_context: TenantContext,
        reason: str | None = None,
    ) -> AlertEntity:
        """Acknowledges an active alert."""
        alert = self.repository.get_alert(alert_id, tenant_context=tenant_context)
        if not alert:
            raise AlertNotFoundException(alert_id)

        alert.acknowledge(actor, reason=reason)
        saved = self.repository.save_alert(alert, tenant_context=tenant_context)

        self._emit_audit(
            event_type=AuditEventType.ALERT_ACKNOWLEDGED,
            actor=actor,
            tenant_context=tenant_context,
            target_id=alert.id,
            target_type="AlertEntity",
            details={"acknowledged_by": actor, "reason": reason},
        )
        return saved

    def resolve_alert(
        self,
        alert_id: str,
        actor: str,
        *,
        tenant_context: TenantContext,
        reason: str | None = None,
    ) -> AlertEntity:
        """Manually marks an alert resolved."""
        alert = self.repository.get_alert(alert_id, tenant_context=tenant_context)
        if not alert:
            raise AlertNotFoundException(alert_id)

        alert.resolve(actor, reason=reason)
        saved = self.repository.save_alert(alert, tenant_context=tenant_context)

        self._emit_audit(
            event_type=AuditEventType.ALERT_RESOLVED,
            actor=actor,
            tenant_context=tenant_context,
            target_id=alert.id,
            target_type="AlertEntity",
            details={"resolved_by": actor, "reason": reason},
        )
        return saved

    def add_comment(
        self,
        alert_id: str,
        author: str,
        text: str,
        *,
        tenant_context: TenantContext,
    ) -> AlertEntity:
        """Appends an operational note to an alert."""
        alert = self.repository.get_alert(alert_id, tenant_context=tenant_context)
        if not alert:
            raise AlertNotFoundException(alert_id)

        alert.add_comment(author, text)
        return self.repository.save_alert(alert, tenant_context=tenant_context)

    def mark_condition_cleared(
        self,
        alert_id: str,
        *,
        tenant_context: TenantContext,
        now: dt.datetime | None = None,
    ) -> AlertEntity:
        """Marks underlying condition as healthy, initiating dwell timer for auto-resolution."""
        alert = self.repository.get_alert(alert_id, tenant_context=tenant_context)
        if not alert:
            raise AlertNotFoundException(alert_id)

        alert.mark_condition_cleared(now=now)
        return self.repository.save_alert(alert, tenant_context=tenant_context)

    def evaluate_auto_resolutions(
        self,
        *,
        tenant_context: TenantContext,
        now: dt.datetime | None = None,
    ) -> list[AlertEntity]:
        """Evaluates all active alerts and auto-resolves those whose condition stayed clear past dwell time."""
        eval_time = now or dt.datetime.now(dt.UTC)
        auto_resolved: list[AlertEntity] = []

        all_alerts = self.repository.list(tenant_context=tenant_context, limit=1000)
        for alert in all_alerts:
            if alert.status in (AlertLifecycleStatus.ACTIVE, AlertLifecycleStatus.ACKNOWLEDGED):
                if alert.check_auto_resolve_eligible(eval_time):
                    alert.auto_resolve(eval_time)
                    self.repository.save_alert(alert, tenant_context=tenant_context)
                    auto_resolved.append(alert)

                    self._emit_audit(
                        event_type=AuditEventType.ALERT_AUTO_RESOLVED,
                        actor="engine:auto_resolve",
                        tenant_context=tenant_context,
                        target_id=alert.id,
                        target_type="AlertEntity",
                        details={
                            "alert_id": alert.id,
                            "dwell_time_seconds": alert.dwell_time_seconds,
                            "resolved_at": alert.resolved_at.isoformat()
                            if alert.resolved_at
                            else None,
                        },
                    )
        return auto_resolved

    def evaluate_escalations(
        self,
        *,
        tenant_context: TenantContext,
        escalation_timeout_seconds: int | None = None,
        now: dt.datetime | None = None,
    ) -> list[AlertEntity]:
        """Escalates unacknowledged HIGH and CRITICAL alerts.

        Constraint: High-severity alerts must NEVER disappear silently.
        """
        eval_time = now or dt.datetime.now(dt.UTC)
        timeout = escalation_timeout_seconds or self.default_escalation_timeout_seconds
        escalated_alerts: list[AlertEntity] = []

        all_alerts = self.repository.list(tenant_context=tenant_context, limit=1000)
        for alert in all_alerts:
            if alert.status == AlertLifecycleStatus.ACTIVE:
                if alert.severity in (AlertSeverity.HIGH, AlertSeverity.CRITICAL):
                    # Check age since creation or last escalation
                    reference_time = alert.escalated_at or alert.created_at
                    elapsed = (eval_time - reference_time).total_seconds()
                    if elapsed >= timeout:
                        alert.escalate(eval_time)
                        self.repository.save_alert(alert, tenant_context=tenant_context)
                        escalated_alerts.append(alert)

                        self._emit_audit(
                            event_type=AuditEventType.ALERT_ESCALATED,
                            actor="engine:escalation_timer",
                            tenant_context=tenant_context,
                            target_id=alert.id,
                            target_type="AlertEntity",
                            details={
                                "alert_id": alert.id,
                                "escalation_level": alert.escalation_level,
                                "severity": alert.severity.value,
                                "elapsed_seconds": int(elapsed),
                            },
                        )
        return escalated_alerts
