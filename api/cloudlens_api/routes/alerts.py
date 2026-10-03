"""Alerting and Notification API Routes (Prompt 31, BBP Section 35, FR-560 to FR-566).

Enforces:
- Full alert lifecycle management (creation, deduplication, acknowledgement, resolution, audit).
- Mandatory empirical evidence attachment.
- Six inline contextual alert surfaces.
- Subscriptions, quiet hours, and delivery logs.
- Strict route precedence (literal paths before parameterized paths).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, Field

from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from domain.alerting.catalogue import (
    AlertCatalogueDefinition,
    get_default_alert_catalogue,
)
from domain.alerting.models import (
    AlertDeliveryLog,
    AlertEntity,
    AlertEvidence,
    ContextualAlert,
    QuietHoursConfig,
    RecipientSubscription,
)
from domain.alerting.service import AlertService, get_alert_service
from domain.models.enums import (
    AlertLifecycleStatus,
    AlertSeverity,
    AlertType,
    ContextualAlertType,
    ContextualAlertVisibility,
    NotificationChannel,
)
from domain.models.exceptions import AlertNotFoundException
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/alerts", tags=["Alerting & Notifications"])


# ==============================================================================
# Request & Response DTOs
# ==============================================================================


class AlertCreateDTO(BaseModel):
    """Payload for raising an operational or governance alert."""

    alert_type: AlertType = Field(..., description="Canonical alert type")
    severity: AlertSeverity = Field(..., description="Severity level")
    title: str = Field(..., min_length=3, description="Alert title")
    description: str = Field(..., description="Alert description and details")
    source: str = Field(..., description="Originating subsystem (e.g. 'budget_engine')")
    rule_id: str | None = Field(default=None, description="Originating rule or policy ID")
    affected_resource_id: str | None = Field(default=None, description="Affected resource ID")
    scope_type: str | None = Field(default=None, description="Scope type")
    scope_id: str | None = Field(default=None, description="Scope ID")
    current_value: float | str | None = Field(default=None, description="Observed value")
    threshold_value: float | str | None = Field(default=None, description="Limit value")
    previous_value: float | str | None = Field(default=None, description="Previous value")
    evidence: AlertEvidence = Field(..., description="Mandatory empirical evidence")
    dwell_time_seconds: int = Field(default=300, ge=0, description="Dwell time for auto-resolution")
    resource_metadata: dict[str, Any] | None = Field(
        default=None, description="Resource metadata/tags for routing"
    )
    scope_metadata: dict[str, Any] | None = Field(
        default=None, description="Scope metadata for routing"
    )


class AlertAcknowledgeDTO(BaseModel):
    """Payload for acknowledging an active alert."""

    actor: str = Field(..., min_length=1, description="Username or email acknowledging alert")
    reason: str | None = Field(
        default=None, description="Optional acknowledgement reason code or comment"
    )


class AlertResolveDTO(BaseModel):
    """Payload for resolving an alert."""

    actor: str = Field(..., min_length=1, description="Username or email resolving alert")
    reason: str | None = Field(default=None, description="Resolution reason or action summary")


class AlertCommentDTO(BaseModel):
    """Payload for adding an operational note to an alert."""

    author: str = Field(..., min_length=1, description="Author identifier")
    text: str = Field(..., min_length=1, description="Comment text")


class ContextualAlertCreateDTO(BaseModel):
    """Payload for publishing an inline contextual UI alert."""

    alert_type: ContextualAlertType = Field(..., description="Contextual alert type")
    title: str = Field(..., min_length=3, description="Contextual title")
    message: str = Field(..., min_length=1, description="Contextual message")
    context_entity_type: str = Field(..., description="Entity context type (e.g. 'resource')")
    context_entity_id: str = Field(..., description="Entity ID or page route")
    visibility: ContextualAlertVisibility = Field(
        default=ContextualAlertVisibility.PAGE_INLINE,
        description="Target presentation surface",
    )
    severity: AlertSeverity = Field(default=AlertSeverity.INFO, description="Severity")
    dismissible: bool = Field(default=True, description="Whether dismissible")
    metadata: dict[str, Any] | None = Field(default=None, description="Custom metadata")


class ContextualDismissDTO(BaseModel):
    """Payload for dismissing an inline contextual alert."""

    actor: str = Field(..., min_length=1, description="Actor username dismissing alert")


class ContextualAcknowledgeDTO(BaseModel):
    """Payload for acknowledging an inline contextual alert."""

    actor: str = Field(..., min_length=1, description="Actor username acknowledging alert")
    note: str | None = Field(default=None, description="Optional acknowledgement note")


class SubscriptionCreateDTO(BaseModel):
    """Payload for registering a notification subscription."""

    recipient: str = Field(..., min_length=1, description="Destination handle, email, or webhook")
    channel: NotificationChannel = Field(..., description="Target delivery channel")
    scope_id: str | None = Field(default=None, description="Scope filter; None for tenant-wide")
    alert_types: list[AlertType] = Field(default_factory=list, description="Subscribed alert types")
    severities: list[AlertSeverity] = Field(
        default_factory=list, description="Subscribed severities"
    )
    digest_enabled: bool = Field(
        default=False, description="Whether to buffer low-severity alerts for digest"
    )
    quiet_hours: QuietHoursConfig | None = Field(default=None, description="Quiet hours config")


class EvaluateEscalationsDTO(BaseModel):
    """Payload for manual or scheduled escalation sweep."""

    timeout_seconds: int | None = Field(default=None, description="Custom SLA timeout in seconds")


class AlertListResponse(BaseModel):
    items: list[AlertEntity]
    total: int


class ContextualListResponse(BaseModel):
    items: list[ContextualAlert]
    total: int


class SubscriptionListResponse(BaseModel):
    items: list[RecipientSubscription]
    total: int


class DeliveryLogListResponse(BaseModel):
    items: list[AlertDeliveryLog]
    total: int


class AlertCatalogueListResponse(BaseModel):
    """Response envelope for the default master data alert catalogue (AL-01 to AL-20)."""

    items: list[AlertCatalogueDefinition]
    total: int


# ==============================================================================
# 1. Literal Path Endpoints (Registered FIRST before /{alert_id})
# ==============================================================================


@router.get("/catalogue", response_model=AlertCatalogueListResponse)
async def get_catalogue() -> AlertCatalogueListResponse:
    """Returns the authoritative default alert catalogue (AL-01 to AL-20) from master data."""
    catalogue = get_default_alert_catalogue()
    return AlertCatalogueListResponse(items=catalogue, total=len(catalogue))


@router.post("", response_model=AlertEntity, status_code=status.HTTP_201_CREATED)
async def create_alert(
    payload: AlertCreateDTO,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    alert_service: AlertService = Depends(get_alert_service),
) -> AlertEntity:
    """Raises an operational or governance alert with mandatory evidence."""
    entity = AlertEntity(
        tenant_id=tenant_context.tenant_id,
        alert_type=payload.alert_type,
        severity=payload.severity,
        title=payload.title,
        description=payload.description,
        source=payload.source,
        rule_id=payload.rule_id,
        affected_resource_id=payload.affected_resource_id,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        current_value=payload.current_value,
        threshold_value=payload.threshold_value,
        previous_value=payload.previous_value,
        evidence=payload.evidence,
        dwell_time_seconds=payload.dwell_time_seconds,
    )
    return alert_service.raise_alert(
        entity,
        tenant_context=tenant_context,
        resource_metadata=payload.resource_metadata,
        scope_metadata=payload.scope_metadata,
    )


@router.get("", response_model=AlertListResponse)
async def list_alerts(
    status_filter: AlertLifecycleStatus | None = Query(default=None, alias="status"),
    severity: AlertSeverity | None = Query(default=None),
    alert_type: AlertType | None = Query(default=None),
    scope_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    alert_service: AlertService = Depends(get_alert_service),
) -> AlertListResponse:
    """Lists alerts for the authenticated tenant with optional filters."""
    alerts = alert_service.list_alerts(tenant_context=tenant_context, limit=1000, offset=0)
    filtered = alerts
    if status_filter:
        filtered = [a for a in filtered if a.status == status_filter]
    if severity:
        filtered = [a for a in filtered if a.severity == severity]
    if alert_type:
        filtered = [a for a in filtered if a.alert_type == alert_type]
    if scope_id:
        filtered = [a for a in filtered if a.scope_id == scope_id]

    paginated = filtered[offset : offset + limit]
    return AlertListResponse(items=paginated, total=len(filtered))


@router.get("/contextual", response_model=ContextualListResponse)
async def list_contextual_alerts(
    context_entity_type: str | None = Query(default=None),
    context_entity_id: str | None = Query(default=None),
    visibility: ContextualAlertVisibility | None = Query(default=None),
    include_dismissed: bool = Query(default=False),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    alert_service: AlertService = Depends(get_alert_service),
) -> ContextualListResponse:
    """Lists inline contextual alerts matching query criteria."""
    items = alert_service.list_contextual_alerts(
        tenant_context=tenant_context,
        context_entity_type=context_entity_type,
        context_entity_id=context_entity_id,
        visibility=visibility,
        include_dismissed=include_dismissed,
    )
    return ContextualListResponse(items=items, total=len(items))


@router.post("/contextual", response_model=ContextualAlert, status_code=status.HTTP_201_CREATED)
async def create_contextual_alert(
    payload: ContextualAlertCreateDTO,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    alert_service: AlertService = Depends(get_alert_service),
) -> ContextualAlert:
    """Creates a new inline contextual alert."""
    return alert_service.create_contextual_alert(
        alert_type=payload.alert_type,
        title=payload.title,
        message=payload.message,
        context_entity_type=payload.context_entity_type,
        context_entity_id=payload.context_entity_id,
        tenant_context=tenant_context,
        visibility=payload.visibility,
        severity=payload.severity,
        dismissible=payload.dismissible,
        metadata=payload.metadata,
    )


@router.post("/contextual/{contextual_id}/dismiss", response_model=ContextualAlert)
async def dismiss_contextual_alert(
    contextual_id: str,
    payload: ContextualDismissDTO,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    alert_service: AlertService = Depends(get_alert_service),
) -> ContextualAlert:
    """Dismisses an active inline contextual alert."""
    return alert_service.dismiss_contextual_alert(
        alert_id=contextual_id,
        actor=payload.actor,
        tenant_context=tenant_context,
    )


@router.post("/contextual/{contextual_id}/acknowledge", response_model=ContextualAlert)
async def acknowledge_contextual_alert(
    contextual_id: str,
    payload: ContextualAcknowledgeDTO,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    alert_service: AlertService = Depends(get_alert_service),
) -> ContextualAlert:
    """Acknowledges an active inline contextual alert with audit event."""
    return alert_service.acknowledge_contextual_alert(
        alert_id=contextual_id,
        actor=payload.actor,
        note=payload.note,
        tenant_context=tenant_context,
    )


@router.get("/subscriptions", response_model=SubscriptionListResponse)
async def list_subscriptions(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    alert_service: AlertService = Depends(get_alert_service),
) -> SubscriptionListResponse:
    """Lists configured alert subscriptions for the tenant."""
    items = alert_service.list_subscriptions(tenant_context=tenant_context)
    return SubscriptionListResponse(items=items, total=len(items))


@router.post(
    "/subscriptions", response_model=RecipientSubscription, status_code=status.HTTP_201_CREATED
)
async def create_subscription(
    payload: SubscriptionCreateDTO,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    alert_service: AlertService = Depends(get_alert_service),
) -> RecipientSubscription:
    """Registers an alert recipient subscription."""
    sub = RecipientSubscription(
        tenant_id=tenant_context.tenant_id,
        recipient=payload.recipient,
        channel=payload.channel,
        scope_id=payload.scope_id,
        alert_types=payload.alert_types,
        severities=payload.severities,
        digest_enabled=payload.digest_enabled,
        quiet_hours=payload.quiet_hours,
    )
    return alert_service.create_subscription(sub, tenant_context=tenant_context)


@router.delete("/subscriptions/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subscription(
    subscription_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    alert_service: AlertService = Depends(get_alert_service),
) -> Response:
    """Deletes an alert subscription."""
    alert_service.delete_subscription(subscription_id, tenant_context=tenant_context)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/delivery-logs", response_model=DeliveryLogListResponse)
async def list_delivery_logs(
    alert_id: str | None = Query(default=None),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    alert_service: AlertService = Depends(get_alert_service),
) -> DeliveryLogListResponse:
    """Lists outbound delivery logs."""
    items = alert_service.list_delivery_logs(tenant_context=tenant_context, alert_id=alert_id)
    return DeliveryLogListResponse(items=items, total=len(items))


@router.post("/evaluate-auto-resolutions", response_model=AlertListResponse)
async def evaluate_auto_resolutions(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    alert_service: AlertService = Depends(get_alert_service),
) -> AlertListResponse:
    """Executes auto-resolution evaluation across active alerts with expired dwell time."""
    resolved = alert_service.evaluate_auto_resolutions(tenant_context=tenant_context)
    return AlertListResponse(items=resolved, total=len(resolved))


@router.post("/evaluate-escalations", response_model=AlertListResponse)
async def evaluate_escalations(
    payload: EvaluateEscalationsDTO | None = None,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    alert_service: AlertService = Depends(get_alert_service),
) -> AlertListResponse:
    """Executes escalation sweep on unacknowledged high-severity alerts."""
    timeout = payload.timeout_seconds if payload else None
    escalated = alert_service.evaluate_escalations(
        tenant_context=tenant_context, escalation_timeout_seconds=timeout
    )
    return AlertListResponse(items=escalated, total=len(escalated))


# ==============================================================================
# 2. Parameterized Path Endpoints (Registered AFTER literal paths)
# ==============================================================================


@router.get("/{alert_id}", response_model=AlertEntity)
async def get_alert(
    alert_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    alert_service: AlertService = Depends(get_alert_service),
) -> AlertEntity:
    """Retrieves a single alert by ID."""
    alert = alert_service.get_alert(alert_id, tenant_context=tenant_context)
    if not alert:
        raise AlertNotFoundException(alert_id)
    return alert


@router.post("/{alert_id}/acknowledge", response_model=AlertEntity)
@router.post("/{alert_id}/ack", response_model=AlertEntity)
async def acknowledge_alert(
    alert_id: str,
    payload: AlertAcknowledgeDTO,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    alert_service: AlertService = Depends(get_alert_service),
) -> AlertEntity:
    """Acknowledges an active alert (API-044)."""
    return alert_service.acknowledge_alert(
        alert_id=alert_id,
        actor=payload.actor,
        tenant_context=tenant_context,
        reason=payload.reason,
    )


@router.post("/{alert_id}/resolve", response_model=AlertEntity)
async def resolve_alert(
    alert_id: str,
    payload: AlertResolveDTO,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    alert_service: AlertService = Depends(get_alert_service),
) -> AlertEntity:
    """Manually resolves an active alert."""
    return alert_service.resolve_alert(
        alert_id=alert_id,
        actor=payload.actor,
        tenant_context=tenant_context,
        reason=payload.reason,
    )


@router.post("/{alert_id}/comments", response_model=AlertEntity)
async def add_comment(
    alert_id: str,
    payload: AlertCommentDTO,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    alert_service: AlertService = Depends(get_alert_service),
) -> AlertEntity:
    """Adds a comment to an alert."""
    return alert_service.add_comment(
        alert_id=alert_id,
        author=payload.author,
        text=payload.text,
        tenant_context=tenant_context,
    )


@router.post("/{alert_id}/clear-condition", response_model=AlertEntity)
async def mark_condition_cleared(
    alert_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
    alert_service: AlertService = Depends(get_alert_service),
) -> AlertEntity:
    """Signals that the underlying condition cleared, beginning anti-flapping dwell timer."""
    return alert_service.mark_condition_cleared(alert_id=alert_id, tenant_context=tenant_context)
