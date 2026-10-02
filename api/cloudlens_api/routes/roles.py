"""Role and Permission Definition API Routes (API-009 / Prompt 11 / Prompt 34).

Enforces:
- API-009: GET /api/v1/roles - List available roles and permission definitions.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel

from api.cloudlens_api.conventions.filtering import (
    apply_field_selection,
    decode_cursor,
    encode_cursor,
    sort_items,
)
from api.cloudlens_api.conventions.models import ResponseMetadata
from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from domain.rbac.service import get_rbac_service
from domain.tenant.context import TenantContext

router = APIRouter(prefix="/api/v1/roles", tags=["Roles & Permissions"])


class RoleListResponse(BaseModel):
    """Paginated response model for available roles and permission definitions (API-009)."""

    items: list[dict[str, Any]]
    total: int
    next_cursor: str | None = None
    limit: int = 50
    _metadata: ResponseMetadata | None = None


@router.get("", response_model=RoleListResponse, status_code=status.HTTP_200_OK)
async def list_roles(
    is_custom: bool | None = Query(
        default=None, description="Filter by system built-in or custom role"
    ),
    search: str | None = Query(default=None, description="Search term in code or display name"),
    sort: str | None = Query(default="code", description="Sort string (e.g. code, -is_custom)"),
    fields: str | None = Query(default=None, description="Comma-separated field selection"),
    limit: int = Query(default=50, ge=1, le=500, description="Page size"),
    cursor: str | None = Query(default=None, description="Opaque pagination cursor"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> RoleListResponse:
    """Lists available system roles and tenant custom roles with assigned permissions (API-009)."""
    rbac_service = get_rbac_service()
    all_roles = rbac_service.list_roles(tenant_id=tenant_context.tenant_id)
    offset = decode_cursor(cursor)

    items: list[dict[str, Any]] = []
    for r in all_roles:
        role_is_custom = not r.is_built_in
        if is_custom is not None and role_is_custom != is_custom:
            continue
        if search:
            q = search.lower()
            if q not in r.code.lower() and q not in r.display_name.lower():
                continue
        role_dict = r.model_dump()
        role_dict["is_custom"] = role_is_custom
        items.append(role_dict)

    sorted_items = sort_items(items, sort)
    total = len(sorted_items)
    sliced = sorted_items[offset : offset + limit]
    projected = [apply_field_selection(item, fields) for item in sliced]

    next_cursor = encode_cursor(offset + limit) if (offset + limit) < total else None
    return RoleListResponse(
        items=projected,
        total=total,
        next_cursor=next_cursor,
        limit=limit,
        _metadata=ResponseMetadata(),
    )
