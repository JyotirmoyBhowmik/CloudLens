"""RBAC, Scope Grants and Access Review API Endpoints (Prompt 11).

Provides:
- GET  /api/v1/rbac/permissions: List platform permission catalogue (Item 70).
- GET  /api/v1/rbac/permissions/{code}: Permission detail (Item 70).
- GET  /api/v1/rbac/roles: List built-in and tenant custom roles (Item 70).
- GET  /api/v1/rbac/roles/{code}: Role definition and assigned permissions (Item 70).
- POST /api/v1/rbac/roles: Compose and register tenant custom role (Item 70).
- GET  /api/v1/rbac/grants: List multidimensional scope grants (Item 71).
- POST /api/v1/rbac/grants: Create declarative scope grant across all 8 dimensions (Item 71).
- DELETE /api/v1/rbac/grants/{grant_id}: Revoke scope grant (Item 71).
- POST /api/v1/rbac/evaluate: Server-side authorization decision evaluation (Item 71-73).
- GET  /api/v1/rbac/access-review: Access review audit export in JSON or CSV format (Item 75).
- POST /api/v1/rbac/filter-demo: Filter dataset/aggregates with rate masking and disclosure metadata (Item 73, 74).
"""

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from domain.identity.service import get_identity_service
from domain.models.enums import FinancialSensitivity, GranteeType, GrantEffect, SystemRole
from domain.models.exceptions import (
    CustomRoleInvalidException,
    TokenExpiredException,
    TokenInvalidException,
    TokenRevokedException,
)
from domain.observability import get_logger
from domain.rbac.models import (
    AuthorizationDecision,
    FilteredAggregateResult,
    Permission,
    ResourceTarget,
    RoleDefinition,
    ScopeGrant,
)
from domain.rbac.service import get_rbac_service

logger = get_logger("cloudlens.api.rbac")

router = APIRouter(prefix="/api/v1/rbac", tags=["RBAC & Scope Grants"])


# ==============================================================================
# Request & Response DTOs
# ==============================================================================


class CustomRoleCreateRequest(BaseModel):
    """Payload to create a custom role composed from the permission catalogue (Item 70)."""

    code: str = Field(..., description="Machine key identifier for custom role")
    display_name: str = Field(..., description="Human-readable title")
    description: str = Field(..., description="Functional purpose of custom role")
    allowed_permissions: list[str] = Field(
        ..., description="List of valid permissions chosen from the catalogue"
    )


class ScopeGrantCreateRequest(BaseModel):
    """Payload to create a declarative multidimensional scope grant (Item 71)."""

    grantee_type: GranteeType = Field(..., description="USER or ROLE")
    grantee_id: str = Field(..., description="User ID or Role Code")
    effect: GrantEffect = Field(default=GrantEffect.ALLOW, description="ALLOW or DENY")

    providers: list[str] = Field(
        default_factory=list, description="Target cloud providers or ['*']"
    )
    account_ids: list[str] = Field(
        default_factory=list, description="Target accounts or billing boundaries"
    )
    hierarchy_subtree_roots: list[str] = Field(
        default_factory=list, description="Root node IDs for subtree cascading"
    )
    cascade_hierarchy: bool = Field(
        default=True, description="Whether grant cascades to subtree descendants"
    )
    project_ids: list[str] = Field(default_factory=list, description="Target project codes")
    application_ids: list[str] = Field(default_factory=list, description="Target application codes")
    cost_centre_ids: list[str] = Field(default_factory=list, description="Target cost centre codes")
    business_unit_ids: list[str] = Field(
        default_factory=list, description="Target business unit codes"
    )
    financial_sensitivity: FinancialSensitivity = Field(
        default=FinancialSensitivity.FULL_FINANCIAL_DETAIL,
        description="Visibility tier: FULL_FINANCIAL_DETAIL, COST_TOTALS_ONLY, NON_FINANCIAL",
    )
    is_administrative: bool = Field(
        default=False, description="Whether grant permits administrative actions"
    )
    resource_exceptions: list[str] = Field(
        default_factory=list, description="Explicit resource IDs excluded or targeted"
    )
    description: str | None = Field(default=None, description="Audit reason for grant")


class EvaluateRequest(BaseModel):
    """Payload for server-side permission and scope grant evaluation (Item 71-73)."""

    permission_code: str = Field(..., description="Permission being checked")
    target: ResourceTarget | None = Field(default=None, description="Resource or context target")
    user_id: str | None = Field(default=None, description="Optional override user ID for testing")
    tenant_id: str | None = Field(default=None, description="Optional override tenant ID")
    role_codes: list[str] | None = Field(default=None, description="Optional override roles list")


class FilterDemoRequest(BaseModel):
    """Payload to test aggregate filtering and disclosure reporting (Item 73, 74)."""

    permission_code: str = Field(default="billing:read", description="Permission to evaluate")
    items: list[dict[str, Any]] = Field(..., description="Raw dataset items to filter")


# ==============================================================================
# Helper Caller Context Extractor
# ==============================================================================


def _extract_caller_context(
    authorization: str | None,
    x_user_id: str | None,
    x_tenant_id: str | None,
    x_roles: str | None,
) -> tuple[str, str, list[str]]:
    """Resolves caller (user_id, tenant_id, role_codes) from Bearer token or headers."""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[len("Bearer ") :].strip()
        identity_service = get_identity_service()
        try:
            auth_ctx = identity_service.token_engine.extract_auth_context(token)
            return auth_ctx.user_id, auth_ctx.tenant_id, [r.value for r in auth_ctx.roles]
        except TokenExpiredException as e:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
        except (TokenRevokedException, TokenInvalidException) as e:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e

    # Fallback to explicit enterprise request headers for machine / service calls
    user_id = x_user_id or "system-user"
    tenant_id = x_tenant_id or "default-tenant"
    roles = [r.strip() for r in x_roles.split(",")] if x_roles else [SystemRole.GLOBAL_ADMIN.value]
    return user_id, tenant_id, roles


# ==============================================================================
# Endpoints
# ==============================================================================


@router.get("/permissions", response_model=list[Permission], summary="List Permission Catalogue")
def list_permissions() -> list[Permission]:
    """Returns all standard platform permissions declared in the catalogue (Prompt 11 Item 70)."""
    service = get_rbac_service()
    return service.list_permissions()


@router.get("/permissions/{code}", response_model=Permission, summary="Get Permission Detail")
def get_permission(code: str) -> Permission:
    """Retrieves a single permission definition by its code."""
    service = get_rbac_service()
    perm = service.get_permission(code)
    if not perm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Permission '{code}' not found in platform catalogue.",
        )
    return perm


@router.get("/roles", response_model=list[RoleDefinition], summary="List Roles")
def list_roles(
    tenant_id: str | None = Query(default=None, description="Optional tenant boundary"),
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
    x_roles: str | None = Header(default=None),
) -> list[RoleDefinition]:
    """Lists built-in platform roles and tenant-specific custom roles."""
    _, caller_tenant, _ = _extract_caller_context(authorization, x_user_id, x_tenant_id, x_roles)
    effective_tenant = tenant_id or caller_tenant
    service = get_rbac_service()
    return service.list_roles(tenant_id=effective_tenant)


@router.get("/roles/{code}", response_model=RoleDefinition, summary="Get Role Definition")
def get_role(
    code: str,
    tenant_id: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
    x_roles: str | None = Header(default=None),
) -> RoleDefinition:
    """Retrieves a role definition and its allowed permissions."""
    _, caller_tenant, _ = _extract_caller_context(authorization, x_user_id, x_tenant_id, x_roles)
    effective_tenant = tenant_id or caller_tenant
    service = get_rbac_service()
    role = service.get_role(code, tenant_id=effective_tenant)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role '{code}' not found in built-in registry or tenant custom roles.",
        )
    return role


@router.post(
    "/roles",
    response_model=RoleDefinition,
    status_code=status.HTTP_201_CREATED,
    summary="Create Custom Role",
)
def create_custom_role(
    payload: CustomRoleCreateRequest,
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
    x_roles: str | None = Header(default=None),
) -> RoleDefinition:
    """Creates a custom role composed from the platform permission catalogue (Prompt 11 Item 70)."""
    _, tenant_id, _ = _extract_caller_context(authorization, x_user_id, x_tenant_id, x_roles)
    service = get_rbac_service()
    try:
        return service.create_custom_role(
            tenant_id=tenant_id,
            code=payload.code,
            display_name=payload.display_name,
            description=payload.description,
            allowed_permissions=payload.allowed_permissions,
        )
    except CustomRoleInvalidException as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e


@router.get("/grants", response_model=list[ScopeGrant], summary="List Scope Grants")
def list_scope_grants(
    grantee_id: str | None = Query(
        default=None, description="Optional grantee user ID or role code"
    ),
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
    x_roles: str | None = Header(default=None),
) -> list[ScopeGrant]:
    """Lists active multidimensional scope grants for caller's tenant (Prompt 11 Item 71)."""
    _, tenant_id, _ = _extract_caller_context(authorization, x_user_id, x_tenant_id, x_roles)
    service = get_rbac_service()
    return service.list_scope_grants(tenant_id=tenant_id, grantee_id=grantee_id)


@router.post(
    "/grants",
    response_model=ScopeGrant,
    status_code=status.HTTP_201_CREATED,
    summary="Create Scope Grant",
)
def create_scope_grant(
    payload: ScopeGrantCreateRequest,
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
    x_roles: str | None = Header(default=None),
) -> ScopeGrant:
    """Registers a declarative multidimensional scope grant (Prompt 11 Item 71)."""
    user_id, tenant_id, _ = _extract_caller_context(authorization, x_user_id, x_tenant_id, x_roles)
    service = get_rbac_service()
    grant = ScopeGrant(
        tenant_id=tenant_id,
        grantee_type=payload.grantee_type,
        grantee_id=payload.grantee_id,
        effect=payload.effect,
        providers=payload.providers,
        account_ids=payload.account_ids,
        hierarchy_subtree_roots=payload.hierarchy_subtree_roots,
        cascade_hierarchy=payload.cascade_hierarchy,
        project_ids=payload.project_ids,
        application_ids=payload.application_ids,
        cost_centre_ids=payload.cost_centre_ids,
        business_unit_ids=payload.business_unit_ids,
        financial_sensitivity=payload.financial_sensitivity,
        is_administrative=payload.is_administrative,
        resource_exceptions=payload.resource_exceptions,
        created_by=user_id,
        description=payload.description,
    )
    return service.create_scope_grant(grant)


@router.delete(
    "/grants/{grant_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete Scope Grant"
)
def delete_scope_grant(grant_id: str) -> None:
    """Revokes an active scope grant."""
    service = get_rbac_service()
    deleted = service.delete_scope_grant(grant_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scope grant '{grant_id}' not found.",
        )


@router.post(
    "/evaluate", response_model=AuthorizationDecision, summary="Evaluate Authorization Decision"
)
def evaluate_authorization(
    payload: EvaluateRequest,
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
    x_roles: str | None = Header(default=None),
) -> AuthorizationDecision:
    """Evaluates caller permissions and scope grants for target context (Prompt 11 Item 71-73)."""
    user_id, tenant_id, roles = _extract_caller_context(
        authorization, x_user_id, x_tenant_id, x_roles
    )
    eff_user_id = payload.user_id or user_id
    eff_tenant_id = payload.tenant_id or tenant_id
    eff_roles = payload.role_codes or roles

    service = get_rbac_service()
    return service.authorize(
        user_id=eff_user_id,
        tenant_id=eff_tenant_id,
        role_codes=eff_roles,
        permission_code=payload.permission_code,
        target=payload.target,
    )


@router.get("/access-review", summary="Export Access Review Audit Report")
def export_access_review(
    tenant_id: str | None = Query(default=None, description="Target tenant ID"),
    # no-hardcode-allow: reason="Query parameter default for export format", reviewer="SecurityArchitect"
    format: str = Query(default="json", description="Export format: 'json' or 'csv'"),
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
    x_roles: str | None = Header(default=None),
) -> Any:
    """Exports comprehensive access review audit report in JSON or CSV format (Prompt 11 Item 75)."""
    _, caller_tenant, _ = _extract_caller_context(authorization, x_user_id, x_tenant_id, x_roles)
    target_tenant = tenant_id or caller_tenant
    service = get_rbac_service()

    if format.lower() == "csv":
        csv_data = service.export_access_review_csv(target_tenant)
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=access_review_{target_tenant}.csv"
            },
        )

    return service.generate_access_review(target_tenant)


@router.post(
    "/filter-demo", response_model=FilteredAggregateResult, summary="Filter Aggregate Dataset Demo"
)
def filter_aggregate_demo(
    payload: FilterDemoRequest,
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
    x_roles: str | None = Header(default=None),
) -> FilteredAggregateResult:
    """Filters dataset records against caller scope grants with mandatory disclosure metadata (Item 73, 74)."""
    user_id, tenant_id, roles = _extract_caller_context(
        authorization, x_user_id, x_tenant_id, x_roles
    )
    service = get_rbac_service()
    return service.filter_dataset(
        user_id=user_id,
        tenant_id=tenant_id,
        role_codes=roles,
        permission_code=payload.permission_code,
        items=payload.items,
    )
