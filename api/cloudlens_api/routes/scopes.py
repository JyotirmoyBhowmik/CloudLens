"""Canonical Hierarchy Scopes API Routes (API-010 / Prompt 05 / Prompt 34).

Enforces:
- API-010: GET /api/v1/scopes - Canonical hierarchy scopes tree.
- Multidimensional hierarchy filtering and tree projection.
- Scope-masking discipline and cursor-based pagination.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field

from api.cloudlens_api.conventions.filtering import (
    apply_field_selection,
    decode_cursor,
    encode_cursor,
    sort_items,
)
from api.cloudlens_api.conventions.models import ResponseMetadata
from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from domain.models.enums import ProviderType, ScopeRole
from domain.models.scope import Scope
from domain.synthetic.estate_generator import SyntheticEstateGenerator
from domain.tenant.context import TenantContext

router = APIRouter(prefix="/api/v1/scopes", tags=["Scopes & Hierarchies"])

# In-memory tenant scopes store
_tenant_scopes: dict[str, list[Scope]] = {}


def get_or_create_tenant_scopes(tenant_id: str) -> list[Scope]:
    """Retrieves or lazily initializes canonical scopes for tenant."""
    if tenant_id not in _tenant_scopes:
        gen = SyntheticEstateGenerator(seed=42)
        scopes = gen.generate_hierarchies(tenant_id=tenant_id)
        _tenant_scopes[tenant_id] = scopes
    return _tenant_scopes[tenant_id]


class ScopeNodeResponse(BaseModel):
    """Canonical Scope node model."""

    id: str
    tenant_id: str
    name: str
    canonical_role: ScopeRole
    provider: ProviderType
    native_type: str
    native_id: str
    parent_id: str | None = None
    materialized_path: str = ""
    depth: int = 0
    children: list[ScopeNodeResponse] = Field(default_factory=list)


class ScopeListResponse(BaseModel):
    """Paginated list / tree of canonical scopes (API-010)."""

    model_config = ConfigDict(populate_by_name=True)

    items: list[dict[str, Any]]
    total: int
    next_cursor: str | None = None
    limit: int = 50
    metadata: ResponseMetadata = Field(default_factory=ResponseMetadata, alias="_metadata")


@router.get("", response_model=ScopeListResponse, status_code=status.HTTP_200_OK)
async def list_scopes(
    provider: ProviderType | None = Query(default=None, description="Filter by cloud provider"),
    role: ScopeRole | None = Query(default=None, description="Filter by canonical scope role"),
    as_tree: bool = Query(
        default=False, description="Whether to return nested hierarchy tree instead of flat list"
    ),
    search: str | None = Query(default=None, description="Search term in scope name"),
    sort: str | None = Query(default="depth,name", description="Sort string (e.g. depth, -name)"),
    fields: str | None = Query(default=None, description="Comma-separated field selection"),
    limit: int = Query(default=50, ge=1, le=500, description="Page size"),
    cursor: str | None = Query(default=None, description="Opaque pagination cursor"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> ScopeListResponse:
    """Lists canonical hierarchy scopes tree or flat list for tenant (API-010)."""
    scopes = get_or_create_tenant_scopes(tenant_context.tenant_id)
    offset = decode_cursor(cursor)

    filtered: list[dict[str, Any]] = []
    for s in scopes:
        if provider and s.provider != provider:
            continue
        if role and s.canonical_role != role:
            continue
        if search and search.lower() not in s.name.lower():
            continue
        filtered.append(s.model_dump())

    if as_tree:
        # Build nested tree
        scope_map = {item["id"]: dict(item) for item in filtered}
        for item in scope_map.values():
            item["children"] = []

        roots: list[dict[str, Any]] = []
        for item in scope_map.values():
            pid = item.get("parent_id")
            if pid and pid in scope_map:
                scope_map[pid]["children"].append(item)
            else:
                roots.append(item)
        items_to_return = roots
    else:
        items_to_return = filtered

    sorted_items = sort_items(items_to_return, sort)
    total = len(sorted_items)
    sliced = sorted_items[offset : offset + limit]
    projected = [apply_field_selection(item, fields) for item in sliced]

    next_cursor = encode_cursor(offset + limit) if (offset + limit) < total else None
    return ScopeListResponse(
        items=projected,
        total=total,
        next_cursor=next_cursor,
        limit=limit,
        _metadata=ResponseMetadata(),
    )
