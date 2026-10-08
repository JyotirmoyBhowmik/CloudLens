"""User Management and Identity Administration API Routes (API-005 to API-008 / Prompt 11 / Prompt 34).

Enforces:
- API-005: GET /api/v1/users - List users with role assignments and scope grants.
- API-006: POST /api/v1/users - Invite or provision a new user.
- API-007: GET /api/v1/users/{id} - Get detailed user profile and permissions.
- API-008: PATCH /api/v1/users/{id} - Update user role, scope grants, or active status.
- Scope-masking discipline: return 404 rather than leaking existence of out-of-scope users.
- ETag optimistic concurrency and cursor pagination.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.cloudlens_api.conventions.concurrency import generate_etag, validate_if_match
from api.cloudlens_api.conventions.filtering import (
    apply_field_selection,
    decode_cursor,
    encode_cursor,
    sort_items,
)
from api.cloudlens_api.conventions.models import ResponseMetadata
from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from domain.identity.models import User
from domain.identity.service import get_identity_service
from domain.models.enums import AuthMethod, SystemRole, UserStatus
from domain.rbac.service import get_rbac_service
from domain.tenant.context import TenantContext

router = APIRouter(prefix="/api/v1/users", tags=["Users & Access Management"])


class UserCreateRequest(BaseModel):
    """Payload to invite or provision a new user (API-006)."""

    email: str = Field(..., description="User email address")
    display_name: str = Field(..., description="User full display name")
    roles: list[SystemRole] = Field(
        default_factory=lambda: [SystemRole.FINOPS_VIEWER], description="Assigned roles"
    )
    auth_method: AuthMethod = Field(default=AuthMethod.OIDC, description="Authentication mechanism")
    scope_grant_ids: list[str] = Field(default_factory=list, description="Initial scope grants")

    @field_validator("roles", mode="before")
    @classmethod
    def normalize_roles(cls, v: Any) -> Any:
        if isinstance(v, list):
            normalized = []
            for item in v:
                if isinstance(item, str):
                    val = item.upper().strip()
                    if val == "BILLING_ADMIN":
                        val = "FINOPS_ADMIN"
                    normalized.append(val)
                else:
                    normalized.append(item)
            return normalized
        return v


class UserUpdateRequest(BaseModel):
    """Payload to update an existing user (API-008)."""

    display_name: str | None = Field(default=None, description="Updated display name")
    roles: list[SystemRole] | None = Field(default=None, description="Updated assigned roles")
    status: UserStatus | None = Field(default=None, description="Updated lifecycle status")
    scope_grant_ids: list[str] | None = Field(default=None, description="Updated scope grants")

    @field_validator("roles", mode="before")
    @classmethod
    def normalize_roles(cls, v: Any) -> Any:
        if isinstance(v, list):
            normalized = []
            for item in v:
                if isinstance(item, str):
                    val = item.upper().strip()
                    if val == "BILLING_ADMIN":
                        val = "FINOPS_ADMIN"
                    normalized.append(val)
                else:
                    normalized.append(item)
            return normalized
        return v


class UserDetailResponse(BaseModel):
    """Detailed user profile with permissions and scope grants (API-007)."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    tenant_id: str
    email: str
    display_name: str
    status: UserStatus
    roles: list[SystemRole]
    auth_method: AuthMethod
    is_break_glass: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None
    permissions: list[str] = Field(default_factory=list)
    scope_grants: list[dict[str, Any]] = Field(default_factory=list)
    metadata: ResponseMetadata = Field(default_factory=ResponseMetadata, alias="_metadata")


class UserListResponse(BaseModel):
    """Paginated list of users (API-005)."""

    model_config = ConfigDict(populate_by_name=True)

    items: list[dict[str, Any]]
    total: int
    next_cursor: str | None = None
    limit: int = 50
    metadata: ResponseMetadata = Field(default_factory=ResponseMetadata, alias="_metadata")


@router.get("", response_model=UserListResponse, status_code=status.HTTP_200_OK)
async def list_users(
    role: SystemRole | None = Query(default=None, description="Filter by assigned system role"),
    user_status: UserStatus | None = Query(
        default=None, alias="status", description="Filter by user status"
    ),
    search: str | None = Query(default=None, description="Search substring in name or email"),
    sort: str | None = Query(
        default="-created_at", description="Sort string (e.g. -created_at, email)"
    ),
    fields: str | None = Query(default=None, description="Comma-separated field selection"),
    limit: int = Query(default=50, ge=1, le=500, description="Page size"),
    cursor: str | None = Query(default=None, description="Opaque pagination cursor"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> UserListResponse:
    """Lists users in the authenticated tenant with role assignments and scope grants (API-005)."""
    identity_service = get_identity_service()
    rbac_service = get_rbac_service()
    offset = decode_cursor(cursor)

    # Collect matching users in tenant
    users: list[dict[str, Any]] = []
    tenant_users = identity_service.list_users(tenant_context.tenant_id)
    for user in tenant_users:
        if role and role not in user.roles:
            continue
        if user_status and user.status != user_status:
            continue
        if search:
            q = search.lower()
            if q not in user.email.lower() and q not in user.display_name.lower():
                continue

        # Enrich with permissions & grants count
        perms = identity_service.resolve_effective_permissions(user.roles)
        grants = [
            g.model_dump()
            for g in rbac_service.list_scope_grants(tenant_id=tenant_context.tenant_id, grantee_id=user.id)
        ]
        u_dict = user.model_dump()
        u_dict["permissions"] = perms
        u_dict["scope_grants"] = grants
        users.append(u_dict)

    # Apply sort
    sorted_users = sort_items(users, sort)
    total = len(sorted_users)
    sliced = sorted_users[offset : offset + limit]

    # Apply field selection
    projected = [apply_field_selection(item, fields) for item in sliced]

    next_cursor = encode_cursor(offset + limit) if (offset + limit) < total else None
    return UserListResponse(
        items=projected,
        total=total,
        next_cursor=next_cursor,
        limit=limit,
        _metadata=ResponseMetadata(),
    )


@router.post("", response_model=UserDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreateRequest,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> UserDetailResponse:
    """Invites or provisions a new user in the authenticated tenant (API-006)."""
    _ = idempotency_key
    identity_service = get_identity_service()
    existing_user = identity_service.get_user_by_email(tenant_context.tenant_id, payload.email.lower())
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User with email '{payload.email}' already exists in tenant.",
        )

    user_id = f"usr-{uuid.uuid4().hex[:12]}"
    now = datetime.now(UTC)
    user = User(
        id=user_id,
        tenant_id=tenant_context.tenant_id,
        email=payload.email.lower(),
        display_name=payload.display_name,
        status=UserStatus.ACTIVE,
        roles=payload.roles,
        auth_method=payload.auth_method,
        is_break_glass=False,
        created_at=now,
        updated_at=now,
    )

    identity_service.save_user(user)

    perms = identity_service.resolve_effective_permissions(user.roles)
    res_dict = user.model_dump()
    res_dict["permissions"] = perms
    res_dict["scope_grants"] = []
    res_dict["_metadata"] = ResponseMetadata()

    etag = generate_etag(user.model_dump())
    response.headers["ETag"] = etag
    return UserDetailResponse.model_validate(res_dict)


@router.get("/{user_id}", response_model=UserDetailResponse, status_code=status.HTTP_200_OK)
async def get_user(
    user_id: str,
    response: Response,
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> UserDetailResponse:
    """Retrieves detailed user profile and permissions (API-007).

    Enforces scope-masking: returns 404 if user not in tenant to avoid leaking existence.
    """
    _ = if_none_match
    identity_service = get_identity_service()
    rbac_service = get_rbac_service()

    user = identity_service.get_user(user_id)
    if not user or user.tenant_id != tenant_context.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{user_id}' not found.",
        )

    perms = identity_service.resolve_effective_permissions(user.roles)
    grants = [
        g.model_dump()
        for g in rbac_service.list_scope_grants(tenant_id=tenant_context.tenant_id, grantee_id=user.id)
    ]

    res_dict = user.model_dump()
    res_dict["permissions"] = perms
    res_dict["scope_grants"] = grants
    res_dict["_metadata"] = ResponseMetadata()

    etag = generate_etag(user.model_dump())
    response.headers["ETag"] = etag
    return UserDetailResponse.model_validate(res_dict)


@router.patch("/{user_id}", response_model=UserDetailResponse, status_code=status.HTTP_200_OK)
async def update_user(
    user_id: str,
    payload: UserUpdateRequest,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> UserDetailResponse:
    """Updates user role, scope grants, or active status (API-008)."""
    identity_service = get_identity_service()
    rbac_service = get_rbac_service()

    user = identity_service.get_user(user_id)
    if not user or user.tenant_id != tenant_context.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{user_id}' not found.",
        )

    # Validate ETag optimistic concurrency if provided
    current_etag = generate_etag(user.model_dump())
    if not validate_if_match(current_etag, if_match):
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail="If-Match ETag condition failed. Resource has been modified.",
        )

    if payload.display_name is not None:
        user.display_name = payload.display_name
    if payload.roles is not None:
        user.roles = payload.roles
    if payload.status is not None:
        user.status = payload.status
    user.updated_at = datetime.now(UTC)
    identity_service.save_user(user)

    perms = identity_service.resolve_effective_permissions(user.roles)
    grants = [
        g.model_dump()
        for g in rbac_service.list_scope_grants(tenant_id=tenant_context.tenant_id, grantee_id=user.id)
    ]

    res_dict = user.model_dump()
    res_dict["permissions"] = perms
    res_dict["scope_grants"] = grants
    res_dict["_metadata"] = ResponseMetadata()

    new_etag = generate_etag(res_dict)
    response.headers["ETag"] = new_etag
    return UserDetailResponse.model_validate(res_dict)
