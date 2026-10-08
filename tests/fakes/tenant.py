"""In-Memory Tenant Repository Fake for isolated unit testing."""

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

    def get_sync(self, tenant_id: str) -> Tenant | None:
        return self._items.get(tenant_id)

    def list_sync(self) -> list[Tenant]:
        return list(self._items.values())

    def save_sync(self, tenant: Tenant) -> Tenant:
        self._items[tenant.id] = tenant
        return tenant

    def delete_sync(self, tenant_id: str) -> bool:
        return bool(self._items.pop(tenant_id, None))
