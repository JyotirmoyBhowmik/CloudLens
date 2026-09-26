"""Operational and Governance Overrides REST API Endpoints (Prompt 13 Item 87).

Enforces:
- Tenant-scoped override management strictly derived from authenticated identity (Items 83, 84).
- Mandatory eight attributes: who, what, why (min length >= 20 chars), when, previous value,
  new value, expiry, approval where required.
- Prohibition of permanent overrides without explicit configuration and approval.
- Automatic expiry reversion with audited state transition.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from domain.models.exceptions import (
    OverrideNotFoundException,
    OverrideValidationException,
    PermanentOverrideNotAllowedException,
)
from domain.overrides.models import (
    OverrideCreateRequest,
    OverrideResponse,
)
from domain.overrides.service import get_override_service
from domain.tenant.context import TenantContext

router = APIRouter(prefix="/api/v1/overrides", tags=["Governance Overrides"])


class RevertOverrideRequest(BaseModel):
    """Payload to manually revert an active override."""

    # no-hardcode-allow: reason="Minimum characters for reversion rationale", reviewer="SecurityArchitect"
    reason: str = Field(..., min_length=5, description="Operational rationale for reversion")


def _to_response_dto(record: Any) -> OverrideResponse:
    return OverrideResponse(
        id=record.id,
        tenant_id=record.tenant_id,
        override_class=record.override_class,
        who=record.who,
        what=record.what,
        why=record.why,
        when=record.when,
        previous_value=record.previous_value,
        new_value=record.new_value,
        expiry=record.expiry,
        is_permanent=record.is_permanent,
        approval=record.approval,
        status=record.status,
        reverted_at=record.reverted_at,
        reverted_by=record.reverted_by,
        reversion_reason=record.reversion_reason,
    )


@router.post(
    "",
    response_model=OverrideResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create and activate a new override",
)
def create_override(
    payload: OverrideCreateRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> OverrideResponse:
    """Creates an override verifying all eight mandatory attributes (Item 87)."""
    service = get_override_service()
    try:
        record = service.create_override(tenant_context=tenant_context, req=payload)
        return _to_response_dto(record)
    except PermanentOverrideNotAllowedException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except OverrideValidationException as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e


@router.get(
    "",
    response_model=list[OverrideResponse],
    summary="List overrides for authenticated tenant",
)
def list_overrides(
    # no-hardcode-allow: reason="Default pagination limit", reviewer="SecurityArchitect"
    limit: int = Query(default=50, ge=1, le=500, description="Page size limit"),
    # no-hardcode-allow: reason="Default pagination offset", reviewer="SecurityArchitect"
    offset: int = Query(default=0, ge=0, description="Offset index"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> list[OverrideResponse]:
    """Lists overrides belonging strictly to caller's authenticated tenant."""
    service = get_override_service()
    records = service.list_overrides(tenant_context=tenant_context, limit=limit, offset=offset)
    return [_to_response_dto(r) for r in records]


@router.get(
    "/{override_id}",
    response_model=OverrideResponse,
    summary="Retrieve an individual override record",
)
def get_override(
    override_id: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> OverrideResponse:
    """Retrieves an override record, guaranteeing tenant isolation."""
    service = get_override_service()
    try:
        record = service.get_override(tenant_context=tenant_context, override_id=override_id)
        return _to_response_dto(record)
    except OverrideNotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post(
    "/{override_id}/revert",
    response_model=OverrideResponse,
    summary="Manually revert an active override",
)
def revert_override(
    override_id: str,
    payload: RevertOverrideRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> OverrideResponse:
    """Reverts an active override and records an audited reversion event."""
    service = get_override_service()
    try:
        record = service.revert_override(
            tenant_context=tenant_context,
            override_id=override_id,
            reason=payload.reason,
            actor_id=tenant_context.user_id,
        )
        return _to_response_dto(record)
    except OverrideNotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except OverrideValidationException as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e


@router.post(
    "/revert-expired",
    response_model=list[OverrideResponse],
    summary="Trigger automatic expiration reversion for tenant",
)
def revert_expired_overrides(
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> list[OverrideResponse]:
    """Scans and reverts expired overrides, auditing each automatic reversion (Item 87)."""
    service = get_override_service()
    reverted = service.revert_expired_overrides(tenant_context=tenant_context)
    return [_to_response_dto(r) for r in reverted]
