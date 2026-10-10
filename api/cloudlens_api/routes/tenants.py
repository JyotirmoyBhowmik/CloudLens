"""Tenant Administration REST API Endpoints (Prompt P12).

Enforces:
- Administrative role verification (Super Admin / Platform Admin only).
- Non-admin callers receive HTTP 403 Forbidden.
- Full CRUD on tenant organizations with audit logging.
- Invariant: DEMO tenants cannot be transitioned to PRODUCTION (HTTP 400).
- Suspend and resume requiring non-empty rationale.
- Tenant-scoped user grants and invitation CRUD.
"""

from __future__ import annotations

import logging
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from api.cloudlens_api.tenant_context import require_auth
from domain.models.enums import FinancialSensitivity, GrantEffect, GranteeType, SystemRole
from domain.rbac.models import ScopeGrant
from domain.tenant.context import TenantContext
from domain.tenant.models import Tenant, TenantStatus, TenantType
from domain.tenant.service import (
    InvalidTenantTransitionException,
    TenantCodeConflictException,
    TenantCreateDTO,
    TenantNotFoundException,
    TenantUpdateDTO,
    UnauthorizedTenantOperationException,
    get_tenant_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tenants", tags=["Tenant Administration"])


# ==============================================================================
# Authorization Guard
# ==============================================================================


def require_platform_admin(tc: TenantContext = Depends(require_auth)) -> TenantContext:
    """Enforces Super Admin or Platform Admin authority for tenant administration (Prompt P12)."""
    if tc.is_super_admin or tc.is_superuser:
        return tc
    for r in tc.roles:
        role_str = r.value if hasattr(r, "value") else str(r)
        if role_str in (SystemRole.SUPER_ADMIN, SystemRole.PLATFORM_ADMIN, "SUPER_ADMIN", "PLATFORM_ADMIN"):
            return tc
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Forbidden: Tenant administration requires Super Admin or Platform Admin authority.",
    )


# ==============================================================================
# Request & Response Models
# ==============================================================================


class TenantCreateRequest(BaseModel):
    """Payload for creating a new tenant organization."""

    code: str = Field(..., min_length=2, max_length=64, description="Unique tenant code (e.g. 'SNPL_PROD')")
    name: str = Field(..., min_length=2, max_length=255, description="Tenant organization display name")
    type: TenantType = Field(default=TenantType.PRODUCTION, description="Environment type")
    reporting_currency: str = Field(default="USD", description="Base reporting ISO currency code")
    fiscal_year_start: int = Field(default=1, ge=1, le=12, description="Starting month of fiscal calendar (1-12)")
    iana_timezone: str = Field(default="UTC", description="IANA Time Zone identifier")
    retention_profile: str = Field(default="STANDARD", description="Data retention policy profile")


class TenantUpdateRequest(BaseModel):
    """Payload for updating mutable tenant parameters."""

    name: str | None = Field(default=None, min_length=2, max_length=255)
    type: TenantType | None = None
    reporting_currency: str | None = None
    fiscal_year_start: int | None = Field(default=None, ge=1, le=12)
    iana_timezone: str | None = None
    retention_profile: str | None = None


class TenantActionReasonRequest(BaseModel):
    """Payload for suspend or resume operations."""

    reason: str = Field(..., min_length=5, description="Non-empty rationale for status change")


class TenantGrantCreateRequest(BaseModel):
    """Payload for assigning a scope grant within a tenant."""

    grantee_type: GranteeType = Field(default=GranteeType.USER)
    grantee_id: str = Field(..., description="User ID or Role Code receiving grant")
    effect: GrantEffect = Field(default=GrantEffect.ALLOW)
    providers: list[str] = Field(default_factory=lambda: ["*"])
    account_ids: list[str] = Field(default_factory=list)
    hierarchy_subtree_roots: list[str] = Field(default_factory=list)
    cascade_hierarchy: bool = Field(default=True)
    financial_sensitivity: FinancialSensitivity = Field(default=FinancialSensitivity.FULL_FINANCIAL_DETAIL)
    description: str | None = Field(default=None)


class TenantUserInviteRequest(BaseModel):
    """Payload for inviting/provisioning a user into a tenant."""

    email: str = Field(..., min_length=5, description="User email address")
    display_name: str = Field(..., min_length=2, description="User full display name")
    roles: list[SystemRole] = Field(default_factory=lambda: [SystemRole.FINANCE_USER])


# ==============================================================================
# Endpoints
# ==============================================================================


@router.get("", response_model=list[Tenant], status_code=status.HTTP_200_OK)
def list_tenants(tc: TenantContext = Depends(require_platform_admin)) -> list[Tenant]:
    """Lists all tenant organizations (Super / Platform Admin only)."""
    service = get_tenant_service()
    return service.list_tenants(tc)


@router.post("", response_model=Tenant, status_code=status.HTTP_201_CREATED)
def create_tenant(
    payload: TenantCreateRequest, tc: TenantContext = Depends(require_platform_admin)
) -> Tenant:
    """Provisions a new tenant organization (Super / Platform Admin only)."""
    service = get_tenant_service()
    try:
        dto = TenantCreateDTO(
            code=payload.code,
            name=payload.name,
            type=payload.type,
            reporting_currency=payload.reporting_currency,
            fiscal_year_start=payload.fiscal_year_start,
            iana_timezone=payload.iana_timezone,
            retention_profile=payload.retention_profile,
        )
        return service.create_tenant(dto, tc)
    except TenantCodeConflictException as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e


@router.get("/{tenant_id}", response_model=Tenant, status_code=status.HTTP_200_OK)
def get_tenant(tenant_id: str, tc: TenantContext = Depends(require_auth)) -> Tenant:
    """Retrieves tenant record by ID."""
    service = get_tenant_service()
    try:
        return service.get_tenant(tenant_id, tc)
    except TenantNotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except UnauthorizedTenantOperationException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e


@router.patch("/{tenant_id}", response_model=Tenant, status_code=status.HTTP_200_OK)
def update_tenant(
    tenant_id: str,
    payload: TenantUpdateRequest,
    tc: TenantContext = Depends(require_platform_admin),
) -> Tenant:
    """Updates mutable tenant parameters, enforcing business rules (e.g. DEMO cannot become PRODUCTION)."""
    service = get_tenant_service()
    try:
        dto = TenantUpdateDTO(
            name=payload.name,
            type=payload.type,
            reporting_currency=payload.reporting_currency,
            fiscal_year_start=payload.fiscal_year_start,
            iana_timezone=payload.iana_timezone,
            retention_profile=payload.retention_profile,
        )
        return service.update_tenant(tenant_id, dto, tc)
    except TenantNotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except InvalidTenantTransitionException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e


@router.post("/{tenant_id}/suspend", response_model=Tenant, status_code=status.HTTP_200_OK)
def suspend_tenant(
    tenant_id: str,
    payload: TenantActionReasonRequest,
    tc: TenantContext = Depends(require_platform_admin),
) -> Tenant:
    """Suspends operational activity for tenant with mandatory audited reason."""
    service = get_tenant_service()
    try:
        return service.suspend_tenant(tenant_id, payload.reason, tc)
    except TenantNotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/{tenant_id}/resume", response_model=Tenant, status_code=status.HTTP_200_OK)
def resume_tenant(
    tenant_id: str,
    payload: TenantActionReasonRequest,
    tc: TenantContext = Depends(require_platform_admin),
) -> Tenant:
    """Restores active status to a suspended tenant with mandatory audited reason."""
    service = get_tenant_service()
    try:
        return service.resume_tenant(tenant_id, payload.reason, tc)
    except TenantNotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


# ------------------------------------------------------------------------------
# Tenant User Grants & Identity Endpoints
# ------------------------------------------------------------------------------


@router.get("/{tenant_id}/grants", response_model=list[ScopeGrant], status_code=status.HTTP_200_OK)
def list_tenant_grants(
    tenant_id: str,
    grantee_id: str | None = Query(default=None),
    tc: TenantContext = Depends(require_platform_admin),
) -> list[ScopeGrant]:
    """Lists scope grants for target tenant."""
    service = get_tenant_service()
    return service.list_tenant_grants(tenant_id, grantee_id, tc)


@router.post("/{tenant_id}/grants", response_model=ScopeGrant, status_code=status.HTTP_201_CREATED)
def create_tenant_grant(
    tenant_id: str,
    payload: TenantGrantCreateRequest,
    tc: TenantContext = Depends(require_platform_admin),
) -> ScopeGrant:
    """Creates a new scope grant bound to target tenant."""
    service = get_tenant_service()
    grant = ScopeGrant(
        tenant_id=tenant_id,
        grantee_type=payload.grantee_type,
        grantee_id=payload.grantee_id,
        effect=payload.effect,
        providers=payload.providers,
        account_ids=payload.account_ids,
        hierarchy_subtree_roots=payload.hierarchy_subtree_roots,
        cascade_hierarchy=payload.cascade_hierarchy,
        financial_sensitivity=payload.financial_sensitivity,
        description=payload.description,
        created_by=tc.user_id,
    )
    return service.create_tenant_grant(tenant_id, grant, tc)


@router.delete(
    "/{tenant_id}/grants/{grant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_tenant_grant(
    tenant_id: str, grant_id: str, tc: TenantContext = Depends(require_platform_admin)
) -> Response:
    """Revokes a scope grant from target tenant."""
    service = get_tenant_service()
    deleted = service.delete_tenant_grant(tenant_id, grant_id, tc)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scope grant not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{tenant_id}/users", status_code=status.HTTP_200_OK)
def list_tenant_users(
    tenant_id: str, tc: TenantContext = Depends(require_platform_admin)
) -> list[dict[str, Any]]:
    """Lists users registered in target tenant."""
    service = get_tenant_service()
    users = service.list_tenant_users(tenant_id, tc)
    return [u.model_dump() for u in users]


@router.post("/{tenant_id}/users", status_code=status.HTTP_201_CREATED)
def invite_tenant_user(
    tenant_id: str,
    payload: TenantUserInviteRequest,
    tc: TenantContext = Depends(require_platform_admin),
) -> dict[str, Any]:
    """Invites/provisions a user into target tenant."""
    service = get_tenant_service()
    try:
        user = service.invite_tenant_user(
            tenant_id=tenant_id,
            email=payload.email,
            display_name=payload.display_name,
            roles=payload.roles,
            tenant_context=tc,
        )
        return user.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
