"""Domain Models for Alerting, Notification, and Contextual Alerts (Prompt 31).

Enforces:
- Prompt 31 / BBP Section 35: The sixteen canonical alert types and contextual alerts.
- BBP Section 35.2: Mandatory empirical evidence attached to every alert.
  Alerts without evidence are strictly rejected via MissingAlertEvidenceException.
- Anti-flapping: Dwell time validation before auto-resolution is published.
- Grouping: Scope storm grouping of >10 alerts into a single scope alert.
- Recipient resolution hierarchy: Entity -> Scope -> Subscriptions -> Fallback admin.
- High-severity escalation SLA tracking (never disappear silently).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from typing import Any

from pydantic import BaseModel, Field, field_validator

from domain.models.base import CanonicalEntity
from domain.models.enums import (
    AlertLifecycleStatus,
    AlertSeverity,
    AlertType,
    ContextualAlertType,
    ContextualAlertVisibility,
    DeliveryOutcome,
    EscalationState,
    NotificationChannel,
)
from domain.models.exceptions import MissingAlertEvidenceException


class AlertEvidence(BaseModel):
    """Empirical evidence and metric records that produced an alert (BBP Section 35.2).

    MANDATORY RULE: Alerts cannot be emitted without empirical evidence.
    """

    summary: str = Field(
        ...,
        min_length=3,
        description="Human-readable explanation of the empirical data triggering the alert",
    )
    datapoints: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Metric measurements, timeseries points, or threshold comparison values",
    )
    records: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Raw records, log entries, or entity snapshots backing the condition",
    )
    observed_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC),
        description="Timestamp when the empirical condition was observed",
    )
    metric_name: str | None = Field(
        default=None,
        description="Name of the underlying metric or rule criterion (if applicable)",
    )
    threshold_condition: str | None = Field(
        default=None,
        description="Formal condition string (e.g. 'actual ($1200) > threshold ($1000)')",
    )
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Supporting context parameters (scope, provider, currency, etc.)",
    )

    @field_validator("summary")
    @classmethod
    def validate_summary_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise MissingAlertEvidenceException("Alert evidence summary cannot be empty.")
        return v.strip()

    def model_post_init(self, __context: Any) -> None:
        # Enforce that either datapoints or records or context contains empirical data
        if not self.datapoints and not self.records and not self.context:
            raise MissingAlertEvidenceException(
                "Alert evidence must contain at least one datapoint, record, or context entry."
            )


class AlertComment(BaseModel):
    """Operational comment or note appended to an alert."""

    comment_id: str = Field(
        default_factory=lambda: f"comm-{uuid.uuid4().hex[:8]}",
        description="Unique identifier of comment",
    )
    author: str = Field(..., min_length=1, description="Actor username or email")
    comment_text: str = Field(..., min_length=1, description="Comment body")
    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC),
        description="Creation timestamp in UTC",
    )


class AlertEntity(CanonicalEntity):
    """Canonical Alert Entity representing an operational or governance signal (Prompt 31)."""

    tenant_id: str = Field(..., description="Organization tenant ID")
    alert_type: AlertType = Field(
        ..., description="One of the sixteen canonical alert types or storm grouping"
    )
    severity: AlertSeverity = Field(
        ..., description="Alert urgency level (INFO, WARNING, HIGH, CRITICAL)"
    )
    title: str = Field(..., min_length=3, description="Concise human-readable title")
    description: str = Field(..., description="Detailed description and recommended action")
    source: str = Field(
        ...,
        description="Subsystem generating alert (e.g. 'budget_engine', 'threshold_engine', 'policy_engine')",
    )
    rule_id: str | None = Field(default=None, description="Originating rule or policy ID")
    affected_resource_id: str | None = Field(
        default=None, description="Affected resource ID if resource-scoped"
    )
    scope_type: str | None = Field(
        default=None, description="Scope dimension (e.g. subscription, project)"
    )
    scope_id: str | None = Field(default=None, description="Scope identifier")
    current_value: float | str | None = Field(default=None, description="Observed value at breach")
    threshold_value: float | str | None = Field(
        default=None, description="Target limit or baseline value"
    )
    previous_value: float | str | None = Field(
        default=None, description="Previous cycle measurement"
    )
    evidence: AlertEvidence = Field(..., description="Mandatory empirical evidence")
    status: AlertLifecycleStatus = Field(
        default=AlertLifecycleStatus.ACTIVE, description="Lifecycle status"
    )
    acknowledged_at: dt.datetime | None = Field(
        default=None, description="Acknowledgement timestamp"
    )
    acknowledged_by: str | None = Field(default=None, description="Actor who acknowledged alert")
    acknowledgement_reason: str | None = Field(
        default=None, description="Reason code or note for acknowledgement"
    )
    resolved_at: dt.datetime | None = Field(default=None, description="Resolution timestamp")
    resolved_by: str | None = Field(default=None, description="Actor who marked alert resolved")
    resolution_reason: str | None = Field(
        default=None, description="Reason code or note for resolution"
    )
    is_auto_resolved: bool = Field(
        default=False, description="True if auto-resolved by engine when condition cleared"
    )
    dwell_time_seconds: int = Field(
        default=300, ge=0, description="Dwell time in seconds required before auto-resolution"
    )
    condition_cleared_at: dt.datetime | None = Field(
        default=None, description="Timestamp when the underlying condition cleared"
    )
    comments: list[AlertComment] = Field(default_factory=list, description="Audit comment thread")
    recipients: list[str] = Field(
        default_factory=list, description="Resolved notification recipients"
    )
    governance_exception_raised: bool = Field(
        default=False,
        description="True if routed to scope administrator fallback due to absent resource/scope owners",
    )
    grouped_parent_id: str | None = Field(
        default=None, description="Parent grouped alert ID if suppressed into a scope storm"
    )
    child_alert_ids: list[str] = Field(
        default_factory=list, description="IDs of child alerts aggregated into this grouped alert"
    )
    repeat_count: int = Field(default=1, ge=1, description="Deduplication occurrence counter")
    fingerprint: str = Field(default="", description="Hash key for deduplicating active alerts")
    escalation_level: int = Field(
        default=0, ge=0, description="Escalation stage (0=normal, 1+=escalated)"
    )
    escalation_state: EscalationState = Field(
        default=EscalationState.NONE, description="Escalation tracking state"
    )
    escalated_at: dt.datetime | None = Field(
        default=None, description="Timestamp of latest escalation"
    )
    digest_buffered: bool = Field(default=False, description="True if buffered for digest delivery")
    quiet_hours_suppressed: bool = Field(
        default=False, description="True if suppressed due to quiet hours"
    )

    @field_validator("evidence", mode="before")
    @classmethod
    def validate_evidence_present(cls, v: Any) -> Any:
        if v is None:
            raise MissingAlertEvidenceException(
                "Alert cannot be created without empirical evidence."
            )
        return v

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(__context)
        if not self.fingerprint:
            self.fingerprint = self.compute_fingerprint()

    def compute_fingerprint(self) -> str:
        """Computes a deterministic fingerprint for deduplicating recurring alerts."""
        target = self.affected_resource_id or self.scope_id or "global"
        raw = f"{self.tenant_id}|{self.alert_type}|{target}|{self.rule_id or 'none'}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def acknowledge(self, actor: str, reason: str | None = None) -> None:
        """Acknowledges the alert by a verified human actor."""
        self.status = AlertLifecycleStatus.ACKNOWLEDGED
        self.acknowledged_by = actor
        self.acknowledgement_reason = reason
        self.acknowledged_at = dt.datetime.now(dt.UTC)
        if (
            self.escalation_state == EscalationState.PENDING
            or self.escalation_state == EscalationState.ESCALATED
        ):
            self.escalation_state = EscalationState.ACKNOWLEDGED

    def resolve(self, actor: str, reason: str | None = None) -> None:
        """Manually resolves the alert with audit actor attribution."""
        self.status = AlertLifecycleStatus.RESOLVED
        self.resolved_by = actor
        self.resolution_reason = reason
        self.resolved_at = dt.datetime.now(dt.UTC)
        self.is_auto_resolved = False

    def mark_condition_cleared(self, now: dt.datetime | None = None) -> None:
        """Notes that the condition is no longer observed, starting dwell time window."""
        self.condition_cleared_at = now or dt.datetime.now(dt.UTC)

    def mark_condition_retriggered(self) -> None:
        """Resets the condition cleared timestamp if the condition reoccurs during dwell time."""
        self.condition_cleared_at = None

    def check_auto_resolve_eligible(self, now: dt.datetime | None = None) -> bool:
        """Checks whether the alert has remained clear past the dwell time threshold."""
        if not self.condition_cleared_at:
            return False
        current_time = now or dt.datetime.now(dt.UTC)
        elapsed = (current_time - self.condition_cleared_at).total_seconds()
        return elapsed >= self.dwell_time_seconds

    def auto_resolve(self, now: dt.datetime | None = None) -> None:
        """Completes auto-resolution after dwell time has passed."""
        self.status = AlertLifecycleStatus.AUTO_RESOLVED
        self.resolved_by = "engine:auto_resolve"
        self.resolution_reason = f"Underlying condition cleared and remained healthy past {self.dwell_time_seconds}s dwell time"
        self.resolved_at = now or dt.datetime.now(dt.UTC)
        self.is_auto_resolved = True

    def add_comment(self, author: str, text: str) -> AlertComment:
        """Appends an operational note to the alert comment log."""
        comment = AlertComment(author=author, comment_text=text)
        self.comments.append(comment)
        return comment

    def escalate(self, now: dt.datetime | None = None) -> None:
        """Escalates an unacknowledged high/critical severity alert to next management tier."""
        self.escalation_level += 1
        self.escalation_state = EscalationState.ESCALATED
        self.escalated_at = now or dt.datetime.now(dt.UTC)


class ContextualAlert(CanonicalEntity):
    """Inline UI contextual alert (Prompt 31 Section 4).

    Displays contextual guidance directly within pages/views (cost info, free tier,
    budget proximity, forecast trends, pricing changes, or unavailable pricing).
    """

    tenant_id: str = Field(..., description="Organization tenant ID")
    alert_type: ContextualAlertType = Field(
        ..., description="One of the six contextual alert types"
    )
    title: str = Field(..., min_length=3, description="Contextual title")
    message: str = Field(..., description="Contextual message or advice")
    visibility: ContextualAlertVisibility = Field(
        default=ContextualAlertVisibility.PAGE_INLINE,
        description="Target UI surface",
    )
    context_entity_type: str = Field(
        ..., description="Entity type context (e.g. 'resource', 'budget', 'billing_page')"
    )
    context_entity_id: str = Field(..., description="Target entity ID or page route")
    severity: AlertSeverity = Field(default=AlertSeverity.INFO, description="Visual badge urgency")
    dismissible: bool = Field(default=True, description="Whether the user can dismiss this alert")
    is_dismissed: bool = Field(default=False, description="Whether dismissed by a user")
    dismissed_by: str | None = Field(default=None, description="Actor who dismissed alert")
    dismissed_at: dt.datetime | None = Field(default=None, description="Dismissal timestamp")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Custom presentation metadata"
    )

    def dismiss(self, actor: str) -> None:
        """Dismisses the contextual alert."""
        if not self.dismissible:
            return
        self.is_dismissed = True
        self.dismissed_by = actor
        self.dismissed_at = dt.datetime.now(dt.UTC)


class QuietHoursConfig(BaseModel):
    """Quiet hours configuration for suppressing non-critical alerts."""

    recipient_id: str | None = Field(default=None, description="User ID or None for tenant default")
    enabled: bool = Field(default=True, description="Whether quiet hours schedule is active")
    start_time: str = Field(default="22:00", description="Start time in HH:MM format (24-hour)")
    end_time: str = Field(default="08:00", description="End time in HH:MM format (24-hour)")
    time_zone: str = Field(default="UTC", description="Timezone name")
    suppressed_severities: list[AlertSeverity] = Field(
        default_factory=lambda: [AlertSeverity.INFO, AlertSeverity.WARNING],
        description="Severities suppressed during quiet hours. High and Critical cannot be suppressed.",
    )

    def is_in_quiet_hours(self, dt_val: dt.datetime, severity: AlertSeverity) -> bool:
        """Returns True if the timestamp falls within quiet hours and severity is suppressed."""
        if not self.enabled:
            return False
        # CRITICAL and HIGH severities strictly bypass quiet hours
        if severity in (AlertSeverity.CRITICAL, AlertSeverity.HIGH, AlertSeverity.ERROR):
            return False
        if severity not in self.suppressed_severities:
            return False

        try:
            hour_minute = f"{dt_val.hour:02d}:{dt_val.minute:02d}"
            if self.start_time <= self.end_time:
                # Same day window (e.g., 09:00 to 17:00)
                return self.start_time <= hour_minute < self.end_time
            else:
                # Overnight window (e.g., 22:00 to 08:00)
                return hour_minute >= self.start_time or hour_minute < self.end_time
        except Exception:
            return False


class RecipientSubscription(CanonicalEntity):
    """Explicit tenant subscription directing alerts to specific channels/recipients."""

    tenant_id: str = Field(..., description="Tenant ID")
    recipient: str = Field(..., description="Target email, webhook URL, or user ID")
    channel: NotificationChannel = Field(..., description="Delivery channel")
    scope_id: str | None = Field(default=None, description="Scope filter; None for all scopes")
    alert_types: list[AlertType] = Field(
        default_factory=list, description="Subscribed alert types; empty for all"
    )
    severities: list[AlertSeverity] = Field(
        default_factory=list, description="Subscribed severities; empty for all"
    )
    digest_enabled: bool = Field(
        default=False, description="Whether to buffer low-severity alerts for periodic digest"
    )
    quiet_hours: QuietHoursConfig | None = Field(
        default=None, description="Per-recipient quiet hours"
    )


class RecipientResolutionResult(BaseModel):
    """Result of resolving alert recipients through ownership and subscription hierarchy."""

    recipients: list[str] = Field(
        default_factory=list, description="List of recipient addresses/handles"
    )
    channels: list[NotificationChannel] = Field(
        default_factory=list, description="Target delivery channels"
    )
    resolution_source: str = Field(
        ...,
        description="Source of resolution: 'entity_owner', 'scope_owner', 'explicit_subscription', or 'scope_default_administrator_fallback'",
    )
    governance_exception_raised: bool = Field(
        default=False, description="True if no owner or subscription found and fallback admin used"
    )
    fallback_reason: str | None = Field(default=None, description="Diagnostic reason for fallback")


class AlertDeliveryLog(CanonicalEntity):
    """Outbound dispatch log for tracking delivery attempts, retries, and failures."""

    tenant_id: str = Field(..., description="Tenant ID")
    alert_id: str = Field(..., description="ID of alert being delivered")
    channel: NotificationChannel = Field(..., description="Delivery channel used")
    recipient: str = Field(..., description="Destination recipient")
    outcome: DeliveryOutcome = Field(default=DeliveryOutcome.QUEUED, description="Delivery status")
    attempt_count: int = Field(default=1, ge=1, description="Number of dispatch attempts")
    max_attempts: int = Field(
        default=3, ge=1, description="Maximum allowed attempts before permanent failure"
    )
    error_message: str | None = Field(default=None, description="Error message if attempt failed")
    delivered_at: dt.datetime | None = Field(
        default=None, description="Successful delivery timestamp"
    )
    next_retry_at: dt.datetime | None = Field(
        default=None, description="Scheduled next retry timestamp"
    )
    payload: dict[str, Any] = Field(
        default_factory=dict, description="Delivered message body / headers"
    )


__all__ = [
    "AlertEvidence",
    "AlertComment",
    "AlertEntity",
    "ContextualAlert",
    "QuietHoursConfig",
    "RecipientSubscription",
    "RecipientResolutionResult",
    "AlertDeliveryLog",
]
