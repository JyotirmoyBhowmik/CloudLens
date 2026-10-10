"""In-Memory Tenant Repository Fake for isolated unit testing."""

from __future__ import annotations

from domain.tenant.models import Tenant
from domain.tenant.repository import TenantRepository


class InMemoryTenantRepository:
    is_in_memory: bool = True

    def __init__(self) -> None:
        self._items: dict[str, Tenant] = {}

    async def get(self, tenant_id: str, session=None) -> Tenant | None:
        return self._items.get(tenant_id)

    async def list(self, session=None) -> list[Tenant]:
        return list(self._items.values())

    async def save(self, tenant: Tenant, session=None) -> Tenant:
        self._items[tenant.id] = tenant
        return tenant

    async def delete(self, tenant_id: str, session=None) -> bool:
        return bool(self._items.pop(tenant_id, None))

    async def get_by_code(self, code: str, session=None) -> Tenant | None:
        norm = code.strip().upper()
        for t in self._items.values():
            if t.code.strip().upper() == norm:
                return t
        return None

    def get_sync(self, tenant_id: str) -> Tenant | None:
        return self._items.get(tenant_id)

    def get_by_code_sync(self, code: str) -> Tenant | None:
        norm = code.strip().upper()
        for t in self._items.values():
            if t.code.strip().upper() == norm:
                return t
        return None

    def list_sync(self) -> list[Tenant]:
        return list(self._items.values())

    def save_sync(self, tenant: Tenant) -> Tenant:
        self._items[tenant.id] = tenant
        return tenant

    def delete_sync(self, tenant_id: str) -> bool:
        return bool(self._items.pop(tenant_id, None))


import threading
from domain.tenant.context import TenantContext, require_tenant_context
from domain.tenant.object_store import TenantObjectStorage


class InMemoryTenantObjectStorage(TenantObjectStorage):
    """Thread-safe in-memory object storage test fake."""

    is_in_memory: bool = True

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store: dict[str, tuple[bytes, str]] = {}

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
        with self._lock:
            self._store[scoped_key] = (data, content_type)
        return scoped_key

    def get_object(self, *, tenant_context: TenantContext, key: str) -> bytes:
        tc = require_tenant_context(tenant_context)
        scoped_key = self.sanitize_and_resolve_key(tc.tenant_id, key)
        with self._lock:
            if scoped_key not in self._store:
                raise FileNotFoundError(
                    f"Object '{key}' not found in tenant '{tc.tenant_id}' storage."
                )
            return self._store[scoped_key][0]

    def delete_object(self, *, tenant_context: TenantContext, key: str) -> bool:
        tc = require_tenant_context(tenant_context)
        scoped_key = self.sanitize_and_resolve_key(tc.tenant_id, key)
        with self._lock:
            if scoped_key in self._store:
                del self._store[scoped_key]
                return True
            return False

    def list_objects(self, *, tenant_context: TenantContext, prefix: str = "") -> list[str]:
        tc = require_tenant_context(tenant_context)
        tenant_root = f"tenants/{tc.tenant_id}/"
        clean_prefix = prefix.strip("/")
        full_prefix = f"{tenant_root}{clean_prefix}" if clean_prefix else tenant_root

        results: list[str] = []
        with self._lock:
            for scoped_key in self._store.keys():
                if scoped_key.startswith(full_prefix):
                    relative_key = scoped_key[len(tenant_root) :]
                    results.append(relative_key)
        return sorted(results)

    def object_exists(self, tenant_context: TenantContext, key: str) -> bool:
        tc = require_tenant_context(tenant_context)
        try:
            scoped_key = self.sanitize_and_resolve_key(tc.tenant_id, key)
            with self._lock:
                return scoped_key in self._store
        except Exception:
            return False
