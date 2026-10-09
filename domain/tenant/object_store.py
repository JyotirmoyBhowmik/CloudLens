"""Tenant-Prefixed Object Storage Interface & Implementation (Prompt 13 Item 85).

Enforces:
- Strict tenant-prefixed isolation: all objects stored at `tenants/{tenant_id}/{object_key}`.
- Mechanical rejection of directory traversal (`..`), absolute paths, and cross-tenant prefix manipulation.
- Mandatory TenantContext on every storage operation.
"""

import threading
from abc import ABC, abstractmethod

from domain.models.exceptions import (
    CrossTenantStorageAccessException,
    InvalidStoragePathException,
)
from domain.tenant.context import TenantContext, require_tenant_context


class TenantObjectStorage(ABC):
    """Abstract object storage ensuring strict tenant-prefixed namespace boundaries."""

    @staticmethod
    def sanitize_and_resolve_key(tenant_id: str, raw_key: str) -> str:
        """Sanitizes raw key and applies mandatory tenant prefix.

        Rejects directory traversal, null bytes, backslashes, and cross-tenant tampering.
        """
        if not raw_key or not raw_key.strip():
            raise InvalidStoragePathException("Object storage key cannot be empty.")

        clean = raw_key.strip().replace("\\", "/")

        # Check for directory traversal or malicious patterns
        if "/../" in f"/{clean}/" or clean.startswith("../") or clean.endswith("/.."):
            raise InvalidStoragePathException(f"Directory traversal detected in key '{raw_key}'.")

        if "\0" in clean:
            raise InvalidStoragePathException("Null byte detected in object key.")

        # Check if caller already supplied a tenant prefix
        if clean.startswith("tenants/"):
            parts = clean.split("/")
            if len(parts) >= 2:
                specified_tenant = parts[1]
                if specified_tenant != tenant_id:
                    raise CrossTenantStorageAccessException(
                        f"Cross-tenant storage access denied: caller tenant '{tenant_id}' cannot "
                        f"access path belonging to tenant '{specified_tenant}'."
                    )
                # Strip duplicate prefix
                clean = "/".join(parts[2:])

        # Remove leading/trailing slashes
        clean = clean.strip("/")
        if not clean:
            raise InvalidStoragePathException(
                "Effective object key after prefix resolution is empty."
            )

        return f"tenants/{tenant_id}/{clean}"

    @abstractmethod
    def put_object(
        self,
        *,
        tenant_context: TenantContext,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Stores object bytes under mandatory tenant prefix."""
        raise NotImplementedError

    @abstractmethod
    def get_object(self, *, tenant_context: TenantContext, key: str) -> bytes:
        """Retrieves object bytes strictly from caller's tenant prefix."""
        raise NotImplementedError

    @abstractmethod
    def delete_object(self, *, tenant_context: TenantContext, key: str) -> bool:
        """Deletes object strictly within caller's tenant prefix."""
        raise NotImplementedError

    @abstractmethod
    def list_objects(self, *, tenant_context: TenantContext, prefix: str = "") -> list[str]:
        """Lists object keys belonging strictly to the caller's tenant."""
        raise NotImplementedError

    @abstractmethod
    def object_exists(self, tenant_context: TenantContext, key: str) -> bool:
        """Checks if an object exists strictly within caller's tenant prefix."""
        raise NotImplementedError


import os
from pathlib import Path


class FilesystemTenantObjectStorage(TenantObjectStorage):
    """Production persistent filesystem-backed object storage implementation."""

    is_in_memory: bool = False

    def __init__(self, base_dir: Path | str | None = None) -> None:
        self._lock = threading.Lock()
        self._base_dir = Path(base_dir or os.getenv("OBJECT_STORAGE_DIR", "data/object_store")).resolve()
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def put_object(
        self,
        *,
        tenant_context: TenantContext,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        tc = require_tenant_context(tenant_context)
        scoped_key = self.sanitize_and_resolve_key(tc.tenant_id, key)
        dest_path = self._base_dir / scoped_key
        with self._lock:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(data)
        return scoped_key

    def get_object(self, *, tenant_context: TenantContext, key: str) -> bytes:
        tc = require_tenant_context(tenant_context)
        scoped_key = self.sanitize_and_resolve_key(tc.tenant_id, key)
        src_path = self._base_dir / scoped_key
        with self._lock:
            if not src_path.is_file():
                raise FileNotFoundError(
                    f"Object '{key}' not found in tenant '{tc.tenant_id}' storage."
                )
            return src_path.read_bytes()

    def delete_object(self, *, tenant_context: TenantContext, key: str) -> bool:
        tc = require_tenant_context(tenant_context)
        scoped_key = self.sanitize_and_resolve_key(tc.tenant_id, key)
        target_path = self._base_dir / scoped_key
        with self._lock:
            if target_path.is_file():
                target_path.unlink()
                return True
            return False

    def list_objects(self, *, tenant_context: TenantContext, prefix: str = "") -> list[str]:
        tc = require_tenant_context(tenant_context)
        tenant_dir = self._base_dir / "tenants" / tc.tenant_id
        clean_prefix = prefix.strip("/")

        results: list[str] = []
        with self._lock:
            if not tenant_dir.is_dir():
                return []
            for root, _, files in os.walk(tenant_dir):
                for f in files:
                    full_p = Path(root) / f
                    rel_p = str(full_p.relative_to(tenant_dir)).replace("\\", "/")
                    if not clean_prefix or rel_p.startswith(clean_prefix):
                        results.append(rel_p)
        return sorted(results)

    def object_exists(self, tenant_context: TenantContext, key: str) -> bool:
        """Checks if an object exists strictly within caller's tenant prefix."""
        tc = require_tenant_context(tenant_context)
        try:
            scoped_key = self.sanitize_and_resolve_key(tc.tenant_id, key)
            target_path = self._base_dir / scoped_key
            with self._lock:
                return target_path.is_file()
        except Exception:
            return False


_GLOBAL_STORAGE: TenantObjectStorage | None = None
_STORAGE_LOCK = threading.Lock()


def get_tenant_object_storage() -> TenantObjectStorage:
    """Returns singleton TenantObjectStorage instance."""
    global _GLOBAL_STORAGE
    with _STORAGE_LOCK:
        if _GLOBAL_STORAGE is None:
            _GLOBAL_STORAGE = FilesystemTenantObjectStorage()
        return _GLOBAL_STORAGE


def set_tenant_object_storage(storage: TenantObjectStorage | None) -> None:
    """Sets active tenant object storage instance."""
    global _GLOBAL_STORAGE
    with _STORAGE_LOCK:
        _GLOBAL_STORAGE = storage


def reset_tenant_object_storage(storage: TenantObjectStorage | None = None) -> None:
    """Resets storage for test isolation."""
    global _GLOBAL_STORAGE
    with _STORAGE_LOCK:
        _GLOBAL_STORAGE = storage
