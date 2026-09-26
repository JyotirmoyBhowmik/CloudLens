"""Tenant-Scoped Object Storage REST API Endpoints (Prompt 13 Item 85).

Enforces:
- Tenant-prefixed object storage: all objects stored under `tenants/{tenant_id}/{key}`.
- Rejection of directory traversal and cross-tenant prefix access.
- Deriving tenant strictly from authenticated identity (Item 83).
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from domain.models.exceptions import (
    CrossTenantStorageAccessException,
    InvalidStoragePathException,
)
from domain.tenant.context import TenantContext
from domain.tenant.object_store import get_tenant_object_storage

router = APIRouter(prefix="/api/v1/storage", tags=["Object Storage"])


class PutObjectRequest(BaseModel):
    """Payload to store an object in tenant storage."""

    key: str = Field(..., description="Target object storage key")
    data: str = Field(..., description="Object content (UTF-8 string or base64)")
    content_type: str = Field(default="text/plain", description="MIME content type")


class StorageObjectInfo(BaseModel):
    """Metadata regarding a stored object."""

    key: str
    tenant_id: str
    scoped_path: str


@router.post(
    "/objects",
    response_model=StorageObjectInfo,
    status_code=status.HTTP_201_CREATED,
    summary="Store an object under mandatory tenant prefix",
)
def put_object(
    payload: PutObjectRequest,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> StorageObjectInfo:
    """Stores an object under mandatory tenant-prefixed path (Item 85)."""
    storage = get_tenant_object_storage()
    try:
        data_bytes = payload.data.encode("utf-8")
        scoped_path = storage.put_object(
            tenant_context=tenant_context,
            key=payload.key,
            data=data_bytes,
            content_type=payload.content_type,
        )
        return StorageObjectInfo(
            key=payload.key,
            tenant_id=tenant_context.tenant_id,
            scoped_path=scoped_path,
        )
    except (CrossTenantStorageAccessException, InvalidStoragePathException) as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e


@router.get(
    "/objects",
    response_model=list[str],
    summary="List objects belonging to authenticated tenant",
)
def list_objects(
    prefix: str = Query(default="", description="Key prefix filter"),
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> list[str]:
    """Lists object keys strictly scoped to caller's tenant."""
    storage = get_tenant_object_storage()
    return storage.list_objects(tenant_context=tenant_context, prefix=prefix)


@router.get(
    "/objects/{key:path}",
    summary="Retrieve an object from tenant storage",
)
def get_object(
    key: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> Response:
    """Retrieves an object strictly from caller's tenant storage prefix."""
    storage = get_tenant_object_storage()
    try:
        content = storage.get_object(tenant_context=tenant_context, key=key)
        return Response(content=content, media_type="application/octet-stream")
    except (CrossTenantStorageAccessException, InvalidStoragePathException) as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.delete(
    "/objects/{key:path}",
    summary="Delete an object from tenant storage",
)
def delete_object(
    key: str,
    tenant_context: TenantContext = Depends(get_authenticated_tenant_context),
) -> dict[str, Any]:
    """Deletes an object strictly from caller's tenant storage prefix."""
    storage = get_tenant_object_storage()
    try:
        deleted = storage.delete_object(tenant_context=tenant_context, key=key)
        return {"key": key, "deleted": deleted, "tenant_id": tenant_context.tenant_id}
    except (CrossTenantStorageAccessException, InvalidStoragePathException) as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
