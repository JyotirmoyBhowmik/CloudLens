"""In-memory fake for MasterDataRepository unit testing."""

from __future__ import annotations

from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

from masterdata.models import MasterDataRecord, MasterRegistryEntry


class InMemoryMasterDataRepository:
    """In-memory test fake for MasterDataRepository."""

    is_in_memory: bool = True

    def __init__(self) -> None:
        # id -> record
        self._records: dict[str, MasterDataRecord] = {}
        # code -> registry entry
        self._registry: dict[str, MasterRegistryEntry] = {}

    async def get_record(self, record_id: str, session: AsyncSession | None = None) -> MasterDataRecord | None:
        return self._records.get(record_id)

    async def save_record(
        self, record: MasterDataRecord, session: AsyncSession | None = None
    ) -> MasterDataRecord:
        self._records[record.id] = record
        return record

    async def list_records(
        self, master_type: str, tenant_id: str | None = None, session: AsyncSession | None = None
    ) -> list[MasterDataRecord]:
        results = [r for r in self._records.values() if r.master_type == master_type]
        if tenant_id:
            results = [r for r in results if r.tenant_id in (tenant_id, None)]
        return results

    async def delete_record(self, record_id: str, session: AsyncSession | None = None) -> bool:
        return bool(self._records.pop(record_id, None))

    async def get_registry_entry(
        self, code: str, session: AsyncSession | None = None
    ) -> MasterRegistryEntry | None:
        return self._registry.get(code)

    async def save_registry_entry(
        self, entry: MasterRegistryEntry, session: AsyncSession | None = None
    ) -> MasterRegistryEntry:
        self._registry[entry.code] = entry
        return entry

    async def list_registry_entries(
        self, session: AsyncSession | None = None
    ) -> list[MasterRegistryEntry]:
        return list(self._registry.values())

    def get_record_sync(self, record_id: str) -> MasterDataRecord | None:
        return self._records.get(record_id)

    def save_record_sync(self, record: MasterDataRecord) -> MasterDataRecord:
        self._records[record.id] = record
        return record

    def list_records_sync(
        self, master_type: str, tenant_id: str | None = None
    ) -> list[MasterDataRecord]:
        results = [r for r in self._records.values() if r.master_type == master_type]
        if tenant_id:
            results = [r for r in results if r.tenant_id in (tenant_id, None)]
        return results

    def delete_record_sync(self, record_id: str) -> bool:
        return bool(self._records.pop(record_id, None))

    def get_registry_entry_sync(self, code: str) -> MasterRegistryEntry | None:
        return self._registry.get(code)

    def save_registry_entry_sync(self, entry: MasterRegistryEntry) -> MasterRegistryEntry:
        self._registry[entry.code] = entry
        return entry

    def list_registry_entries_sync(self) -> list[MasterRegistryEntry]:
        return list(self._registry.values())
