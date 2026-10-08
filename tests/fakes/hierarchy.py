"""In-memory test fake for HierarchyRepository (Prompt P07 / Prompt 38)."""

from __future__ import annotations

import builtins
import threading

from domain.hierarchy.models import InventoryResource35, SavedInventoryView
from domain.tenant.context import TenantContext


class InMemoryHierarchyRepository:
    """In-memory repository fake for hierarchy resources and saved views."""

    is_in_memory: bool = True

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._resources: dict[tuple[str, str], InventoryResource35] = {}
        self._views: dict[tuple[str, str], SavedInventoryView] = {}

    def _validate_tenant_context(self, tenant_context: TenantContext) -> None:
        if not tenant_context or not tenant_context.tenant_id:
            raise ValueError("Operation requires valid TenantContext with non-empty tenant_id.")

    def save_resource(
        self, resource: InventoryResource35, *, tenant_context: TenantContext
    ) -> InventoryResource35:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            self._resources[(tenant_context.tenant_id, resource.id)] = resource.model_copy()
            return resource

    def get_resource(
        self, resource_id: str, *, tenant_context: TenantContext
    ) -> InventoryResource35 | None:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            res = self._resources.get((tenant_context.tenant_id, resource_id))
            return res.model_copy() if res else None

    def list_resources(
        self, *, tenant_context: TenantContext, limit: int = 1000
    ) -> builtins.list[InventoryResource35]:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            items = [
                r.model_copy()
                for (tid, _), r in self._resources.items()
                if tid == tenant_context.tenant_id
            ]
            return items[:limit]

    def delete_resource(self, resource_id: str, *, tenant_context: TenantContext) -> bool:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            key = (tenant_context.tenant_id, resource_id)
            if key in self._resources:
                del self._resources[key]
                return True
            return False

    def save_saved_view(
        self, view: SavedInventoryView, *, tenant_context: TenantContext
    ) -> SavedInventoryView:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            self._views[(tenant_context.tenant_id, view.id)] = view.model_copy()
            return view

    def get_saved_view(
        self, view_id: str, *, tenant_context: TenantContext
    ) -> SavedInventoryView | None:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            v = self._views.get((tenant_context.tenant_id, view_id))
            return v.model_copy() if v else None

    def list_saved_views(
        self, *, tenant_context: TenantContext
    ) -> builtins.list[SavedInventoryView]:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            return [
                v.model_copy()
                for (tid, _), v in self._views.items()
                if tid == tenant_context.tenant_id
            ]

    def delete_saved_view(self, view_id: str, *, tenant_context: TenantContext) -> bool:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            key = (tenant_context.tenant_id, view_id)
            if key in self._views:
                del self._views[key]
                return True
            return False
