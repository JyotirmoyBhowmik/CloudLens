"""Append-Only Audit Stream REST API Endpoints (Prompt 13 Item 86).

Enforces:
- Tenant-scoped audit stream access strictly derived from authenticated identity (Items 83, 84).
- Rejection of UPDATE and DELETE operations across all roles (including Super Admin), with the
  mutation attempt itself audited into the append-only stream.
- Cryptographic hash chain verification for tamper evidence.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from domain.audit.models import AuditEventFilter, AuditEventResponse
from domain.audit.service import get_audit_service
from domain.models.enums import AuditEventType
from domain.models.exceptions import (
    AuditRecordNotFoundException,
    AuditTamperForbiddenException,
)
from domain.tenant.context import TenantContext

router = APIRouter(prefix="/api/v1/audit", tags=["Audit & Compliance"])


def _to_response_dto(event: Any) -> AuditEventResponse:
    return AuditEventResponse(
        id=event.id,
        tenant_id=event.tenant_id,
        event_type=event.event_type,
        actor_id=event.actor_id,
        actor_roles=list(event.actor_roles),
        action=event.action,
        resource_type=event.resource_type,
        resource_id=event.resource_id,
        details=dict(event.details),
        correlation_id=event.correlation_id,
        ip_address=event.ip_address,
        user_agent=event.user_agent,
        timestamp=event.timestamp,
        previous_event_hash=event.previous_event_hash,
        event_hash=event.event_hash,
    )


@router.get(
    "/events",
    response_model=list[AuditEventResponse],
    summary="List audit events for authenticated tenant",
)
def list_audit_events(
    event_type: AuditEventType | None = Query(default=None, description="Filter by event type"),
    actor_id: str | None = Query(default=None, description="Filter by principal identity"),
    resource_type: str | None = Query(default=None, description="Filter by resource type"),
    resource_id: str | None = Query(default=None, description="Filter by resource ID"),
    # no-hardcode-allow: reason="Default pagination page limit", reviewer="SecurityArchitect"
    limit: int = Query(default=50, ge=1, le=500, description="Page size limit"),
    # no-hardcode-allow: reason="Default pagination offset", reviewer="SecurityArchitect"
    offset: int = Query(default=0, ge=0, description="Offset index"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> list[AuditEventResponse]:
    """Retrieves audit events strictly isolated to caller's authenticated tenant."""
    service = get_audit_service()
    filters = AuditEventFilter(
        event_type=event_type,
        actor_id=actor_id,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    events = service.list_events(
        tenant_context=tenant_context,
        filter_params=filters,
        limit=limit,
        offset=offset,
    )
    return [_to_response_dto(e) for e in events]


@router.get(
    "/events/{event_id}",
    response_model=AuditEventResponse,
    summary="Retrieve an individual audit event",
)
def get_audit_event(
    event_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> AuditEventResponse:
    """Retrieves an audit event, guaranteeing tenant isolation."""
    service = get_audit_service()
    try:
        event = service.get_event(tenant_context=tenant_context, event_id=event_id)
        return _to_response_dto(event)
    except AuditRecordNotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.delete(
    "/events/{event_id}",
    summary="Attempt to delete an audit event (Forbidden & Audited)",
)
def delete_audit_event(
    event_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> None:
    """Rejects deletion attempt across all roles, auditing the mutation attempt (Item 86)."""
    service = get_audit_service()
    try:
        service.attempt_mutation(
            tenant_context=tenant_context,
            event_id=event_id,
            operation="DELETE",
        )
    except AuditTamperForbiddenException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e


@router.put(
    "/events/{event_id}",
    summary="Attempt to update an audit event (Forbidden & Audited)",
)
def update_audit_event(
    event_id: str,
    payload: dict[str, Any],
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> None:
    """Rejects update attempt across all roles, auditing the mutation attempt (Item 86)."""
    _ = payload
    service = get_audit_service()
    try:
        service.attempt_mutation(
            tenant_context=tenant_context,
            event_id=event_id,
            operation="UPDATE",
        )
    except AuditTamperForbiddenException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e


@router.post(
    "/verify-integrity",
    summary="Verify cryptographic hash chain integrity of tenant audit stream",
)
def verify_audit_stream_integrity(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> dict[str, Any]:
    """Verifies SHA-256 hash chaining continuity across all tenant audit events."""
    service = get_audit_service()
    is_valid = service.verify_stream_integrity(tenant_context=tenant_context)
    return {
        "tenant_id": tenant_context.tenant_id,
        "is_chain_valid": is_valid,
        "tamper_detected": not is_valid,
    }
