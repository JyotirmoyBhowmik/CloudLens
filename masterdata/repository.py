"""Master Data SQL Repository and Protocol (Prompt P04).

Enforces:
- Pattern P1: Protocol + SqlMasterDataRepository (SQLAlchemy 2.0 async).
- Pattern P3: Injected dependency, zero mutable dict singletons as sources of truth.
- Pattern P4: Transactional isolation via get_tenant_session().
- Pattern P6: Startup guard preventing InMemory repository outside development.
- Persistent master data registry and effective-dated records in PostgreSQL.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import os
import sys
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import datetime, timezone

from db.session import get_tenant_session, run_async, verify_persistence_startup_guard
from masterdata.models import LifecycleStatus, MasterDataRecord, MasterRegistryEntry

logger = logging.getLogger("cloudlens.masterdata.repository")


@runtime_checkable
class MasterDataRepository(Protocol):
    """Authoritative protocol for master data registry and records persistence."""

    # Records
    async def get_record(self, record_id: str, session: AsyncSession | None = None) -> MasterDataRecord | None:
        ...

    async def save_record(
        self, record: MasterDataRecord, session: AsyncSession | None = None
    ) -> MasterDataRecord:
        ...

    async def list_records(
        self, master_type: str, tenant_id: str | None = None, session: AsyncSession | None = None
    ) -> list[MasterDataRecord]:
        ...

    async def delete_record(self, record_id: str, session: AsyncSession | None = None) -> bool:
        ...

    # Registry Entries
    async def get_registry_entry(
        self, code: str, session: AsyncSession | None = None
    ) -> MasterRegistryEntry | None:
        ...

    async def save_registry_entry(
        self, entry: MasterRegistryEntry, session: AsyncSession | None = None
    ) -> MasterRegistryEntry:
        ...

    async def list_registry_entries(
        self, session: AsyncSession | None = None
    ) -> list[MasterRegistryEntry]:
        ...

    # Synchronous Helpers
    def get_record_sync(self, record_id: str) -> MasterDataRecord | None:
        ...

    def save_record_sync(self, record: MasterDataRecord) -> MasterDataRecord:
        ...

    def list_records_sync(
        self, master_type: str, tenant_id: str | None = None
    ) -> list[MasterDataRecord]:
        ...

    def delete_record_sync(self, record_id: str) -> bool:
        ...

    def get_registry_entry_sync(self, code: str) -> MasterRegistryEntry | None:
        ...

    def save_registry_entry_sync(self, entry: MasterRegistryEntry) -> MasterRegistryEntry:
        ...

    def list_registry_entries_sync(self) -> list[MasterRegistryEntry]:
        ...


class SqlMasterDataRepository:
    """PostgreSQL production implementation for master data records and registry."""

    is_in_memory: bool = False

    def _run_async(self, coro):
        return run_async(coro)

    def _row_to_record(self, row: Any) -> MasterDataRecord:
        raw_attrs = row[12]
        attrs = raw_attrs if isinstance(raw_attrs, dict) else json.loads(raw_attrs or "{}")
        status_str = row[16] or "PUBLISHED"
        try:
            status = LifecycleStatus(status_str)
        except Exception:
            status = LifecycleStatus.PUBLISHED

        eff_from = row[8]
        if eff_from is not None and isinstance(eff_from, datetime) and eff_from.tzinfo is not None:
            eff_from = eff_from.astimezone(timezone.utc).replace(tzinfo=None)
        eff_to = row[9]
        if eff_to is not None and isinstance(eff_to, datetime) and eff_to.tzinfo is not None:
            eff_to = eff_to.astimezone(timezone.utc).replace(tzinfo=None)

        return MasterDataRecord(
            id=row[0],
            master_type=row[1],
            code=row[2],
            display_name=row[3],
            description=row[4],
            sort_order=row[5] or 0,
            is_system=row[6] or False,
            is_active=row[7] if row[7] is not None else True,
            effective_from=eff_from,
            effective_to=eff_to,
            version=row[10] or 1,
            parent_code=row[11],
            attributes=attrs,
            tenant_id=row[13],
            created_by=row[14] or "SYSTEM",
            approved_by=row[15],
            lifecycle_status=status,
        )

    def _row_to_registry_entry(self, row: Any) -> MasterRegistryEntry:
        raw_schema = row[3]
        schema_def = raw_schema if isinstance(raw_schema, dict) else json.loads(raw_schema or "{}")
        raw_modules = row[7]
        modules = raw_modules if isinstance(raw_modules, list) else json.loads(raw_modules or "[]")

        return MasterRegistryEntry(
            code=row[0],
            name=row[1],
            purpose=row[2],
            schema_def=schema_def,
            is_tenant_scoped=row[4],
            is_editable=row[5],
            requires_approval=row[6],
            consuming_modules=modules,
            seed_file=row[8],
            expected_review_period_days=row[9],
        )

    # -------------------------------------------------------------------------
    # Records
    # -------------------------------------------------------------------------

    async def get_record(self, record_id: str, session: AsyncSession | None = None) -> MasterDataRecord | None:
        if session is not None:
            return await self._get_record_with_session(record_id, session)
        async with get_tenant_session() as sess:
            return await self._get_record_with_session(record_id, sess)

    async def _get_record_with_session(self, record_id: str, session: AsyncSession) -> MasterDataRecord | None:
        query = text("""
            SELECT id, master_type, code, display_name, description, sort_order,
                   is_system, is_active, effective_from, effective_to, version,
                   parent_code, attributes, tenant_id, created_by, approved_by,
                   lifecycle_status, created_at, updated_at
            FROM master_data_records
            WHERE id = :rid
            LIMIT 1;
        """)
        result = await session.execute(query, {"rid": record_id})
        row = result.fetchone()
        if not row:
            return None
        return self._row_to_record(row)

    async def save_record(
        self, record: MasterDataRecord, session: AsyncSession | None = None
    ) -> MasterDataRecord:
        if session is not None:
            return await self._save_record_with_session(record, session)
        async with get_tenant_session(record.tenant_id) as sess:
            res = await self._save_record_with_session(record, sess)
            await sess.commit()
            return res

    async def _save_record_with_session(
        self, record: MasterDataRecord, session: AsyncSession
    ) -> MasterDataRecord:
        # Ensure master_type exists in master_registry before inserting record
        check_reg = await session.execute(
            text("SELECT code FROM master_registry WHERE code = :code;"),
            {"code": record.master_type},
        )
        if not check_reg.fetchone():
            from masterdata.registry import get_registered_master
            entry = get_registered_master(record.master_type)
            if entry:
                await session.execute(
                    text("""
                        INSERT INTO master_registry (
                            code, name, purpose, schema_def, is_tenant_scoped,
                            is_editable, requires_approval, consuming_modules,
                            seed_file, expected_review_period_days
                        )
                        VALUES (
                            :code, :name, :purpose, CAST(:schema_def AS jsonb), :is_tenant_scoped,
                            :is_editable, :requires_approval, CAST(:consuming_modules AS jsonb),
                            :seed_file, :period
                        )
                        ON CONFLICT (code) DO NOTHING;
                    """),
                    {
                        "code": entry.code,
                        "name": entry.name,
                        "purpose": entry.purpose,
                        "schema_def": json.dumps(entry.schema_def),
                        "is_tenant_scoped": entry.is_tenant_scoped,
                        "is_editable": entry.is_editable,
                        "requires_approval": entry.requires_approval,
                        "consuming_modules": json.dumps(entry.consuming_modules),
                        "seed_file": entry.seed_file,
                        "period": entry.expected_review_period_days,
                    },
                )

        query = text("""
            INSERT INTO master_data_records (
                id, master_type, code, display_name, description, sort_order,
                is_system, is_active, effective_from, effective_to, version,
                parent_code, attributes, tenant_id, created_by, approved_by,
                lifecycle_status, created_at, updated_at
            )
            VALUES (
                :id, :master_type, :code, :display_name, :description, :sort_order,
                :is_system, :is_active, :effective_from, :effective_to, :version,
                :parent_code, CAST(:attributes AS jsonb), :tenant_id, :created_by, :approved_by,
                :lifecycle_status, NOW(), NOW()
            )
            ON CONFLICT (id)
            DO UPDATE SET
                display_name = EXCLUDED.display_name,
                description = EXCLUDED.description,
                sort_order = EXCLUDED.sort_order,
                is_system = EXCLUDED.is_system,
                is_active = EXCLUDED.is_active,
                effective_from = EXCLUDED.effective_from,
                effective_to = EXCLUDED.effective_to,
                version = EXCLUDED.version,
                parent_code = EXCLUDED.parent_code,
                attributes = EXCLUDED.attributes,
                tenant_id = EXCLUDED.tenant_id,
                created_by = EXCLUDED.created_by,
                approved_by = EXCLUDED.approved_by,
                lifecycle_status = EXCLUDED.lifecycle_status,
                updated_at = NOW();
        """)
        await session.execute(
            query,
            {
                "id": record.id,
                "master_type": record.master_type,
                "code": record.code,
                "display_name": record.display_name,
                "description": record.description,
                "sort_order": record.sort_order,
                "is_system": record.is_system,
                "is_active": record.is_active,
                "effective_from": record.effective_from,
                "effective_to": record.effective_to,
                "version": record.version,
                "parent_code": record.parent_code,
                "attributes": json.dumps(record.attributes),
                "tenant_id": record.tenant_id,
                "created_by": record.created_by,
                "approved_by": record.approved_by,
                "lifecycle_status": record.lifecycle_status.value if hasattr(record.lifecycle_status, "value") else str(record.lifecycle_status),
            },
        )
        return record

    async def list_records(
        self, master_type: str, tenant_id: str | None = None, session: AsyncSession | None = None
    ) -> list[MasterDataRecord]:
        if session is not None:
            return await self._list_records_with_session(master_type, tenant_id, session)
        async with get_tenant_session(tenant_id) as sess:
            return await self._list_records_with_session(master_type, tenant_id, sess)

    async def _list_records_with_session(
        self, master_type: str, tenant_id: str | None, session: AsyncSession
    ) -> list[MasterDataRecord]:
        if tenant_id:
            query = text("""
                SELECT id, master_type, code, display_name, description, sort_order,
                       is_system, is_active, effective_from, effective_to, version,
                       parent_code, attributes, tenant_id, created_by, approved_by,
                       lifecycle_status, created_at, updated_at
                FROM master_data_records
                WHERE master_type = :mt AND (tenant_id = :tid OR tenant_id IS NULL)
                ORDER BY sort_order, code;
            """)
            result = await session.execute(query, {"mt": master_type, "tid": tenant_id})
        else:
            query = text("""
                SELECT id, master_type, code, display_name, description, sort_order,
                       is_system, is_active, effective_from, effective_to, version,
                       parent_code, attributes, tenant_id, created_by, approved_by,
                       lifecycle_status, created_at, updated_at
                FROM master_data_records
                WHERE master_type = :mt
                ORDER BY sort_order, code;
            """)
            result = await session.execute(query, {"mt": master_type})

        rows = result.fetchall()
        return [self._row_to_record(r) for r in rows]

    async def delete_record(self, record_id: str, session: AsyncSession | None = None) -> bool:
        if session is not None:
            return await self._delete_record_with_session(record_id, session)
        async with get_tenant_session() as sess:
            res = await self._delete_record_with_session(record_id, sess)
            await sess.commit()
            return res

    async def _delete_record_with_session(self, record_id: str, session: AsyncSession) -> bool:
        query = text("DELETE FROM master_data_records WHERE id = :rid;")
        res = await session.execute(query, {"rid": record_id})
        return res.rowcount > 0

    # -------------------------------------------------------------------------
    # Registry Entries
    # -------------------------------------------------------------------------

    async def get_registry_entry(
        self, code: str, session: AsyncSession | None = None
    ) -> MasterRegistryEntry | None:
        if session is not None:
            return await self._get_registry_entry_with_session(code, session)
        async with get_tenant_session() as sess:
            return await self._get_registry_entry_with_session(code, sess)

    async def _get_registry_entry_with_session(
        self, code: str, session: AsyncSession
    ) -> MasterRegistryEntry | None:
        query = text("""
            SELECT code, name, purpose, schema_def, is_tenant_scoped, is_editable,
                   requires_approval, consuming_modules, seed_file, expected_review_period_days
            FROM master_registry
            WHERE code = :code
            LIMIT 1;
        """)
        result = await session.execute(query, {"code": code})
        row = result.fetchone()
        if not row:
            return None
        return self._row_to_registry_entry(row)

    async def save_registry_entry(
        self, entry: MasterRegistryEntry, session: AsyncSession | None = None
    ) -> MasterRegistryEntry:
        if session is not None:
            return await self._save_registry_entry_with_session(entry, session)
        async with get_tenant_session() as sess:
            res = await self._save_registry_entry_with_session(entry, sess)
            await sess.commit()
            return res

    async def _save_registry_entry_with_session(
        self, entry: MasterRegistryEntry, session: AsyncSession
    ) -> MasterRegistryEntry:
        query = text("""
            INSERT INTO master_registry (
                code, name, purpose, schema_def, is_tenant_scoped, is_editable,
                requires_approval, consuming_modules, seed_file, expected_review_period_days
            )
            VALUES (
                :code, :name, :purpose, CAST(:schema_def AS jsonb), :is_tenant_scoped,
                :is_editable, :requires_approval, CAST(:consuming_modules AS jsonb),
                :seed_file, :period
            )
            ON CONFLICT (code)
            DO UPDATE SET
                name = EXCLUDED.name,
                purpose = EXCLUDED.purpose,
                schema_def = EXCLUDED.schema_def,
                is_tenant_scoped = EXCLUDED.is_tenant_scoped,
                is_editable = EXCLUDED.is_editable,
                requires_approval = EXCLUDED.requires_approval,
                consuming_modules = EXCLUDED.consuming_modules,
                seed_file = EXCLUDED.seed_file,
                expected_review_period_days = EXCLUDED.expected_review_period_days;
        """)
        await session.execute(
            query,
            {
                "code": entry.code,
                "name": entry.name,
                "purpose": entry.purpose,
                "schema_def": json.dumps(entry.schema_def),
                "is_tenant_scoped": entry.is_tenant_scoped,
                "is_editable": entry.is_editable,
                "requires_approval": entry.requires_approval,
                "consuming_modules": json.dumps(entry.consuming_modules),
                "seed_file": entry.seed_file,
                "period": entry.expected_review_period_days,
            },
        )
        return entry

    async def list_registry_entries(
        self, session: AsyncSession | None = None
    ) -> list[MasterRegistryEntry]:
        if session is not None:
            return await self._list_registry_entries_with_session(session)
        async with get_tenant_session() as sess:
            return await self._list_registry_entries_with_session(sess)

    async def _list_registry_entries_with_session(
        self, session: AsyncSession
    ) -> list[MasterRegistryEntry]:
        query = text("""
            SELECT code, name, purpose, schema_def, is_tenant_scoped, is_editable,
                   requires_approval, consuming_modules, seed_file, expected_review_period_days
            FROM master_registry
            ORDER BY code;
        """)
        result = await session.execute(query)
        rows = result.fetchall()
        return [self._row_to_registry_entry(r) for r in rows]

    # -------------------------------------------------------------------------
    # Synchronous Helpers
    # -------------------------------------------------------------------------

    def get_record_sync(self, record_id: str) -> MasterDataRecord | None:
        return self._run_async(self.get_record(record_id))

    def save_record_sync(self, record: MasterDataRecord) -> MasterDataRecord:
        return self._run_async(self.save_record(record))

    def list_records_sync(
        self, master_type: str, tenant_id: str | None = None
    ) -> list[MasterDataRecord]:
        return self._run_async(self.list_records(master_type, tenant_id))

    def delete_record_sync(self, record_id: str) -> bool:
        return self._run_async(self.delete_record(record_id))

    def get_registry_entry_sync(self, code: str) -> MasterRegistryEntry | None:
        return self._run_async(self.get_registry_entry(code))

    def save_registry_entry_sync(self, entry: MasterRegistryEntry) -> MasterRegistryEntry:
        return self._run_async(self.save_registry_entry(entry))

    def list_registry_entries_sync(self) -> list[MasterRegistryEntry]:
        return self._run_async(self.list_registry_entries())


_master_data_repo_instance: MasterDataRepository | None = None


def get_master_data_repository() -> MasterDataRepository:
    """Dependency provider with production startup guard."""
    global _master_data_repo_instance
    if _master_data_repo_instance is None:
        _master_data_repo_instance = SqlMasterDataRepository()
        verify_persistence_startup_guard(_master_data_repo_instance)
    return _master_data_repo_instance


def reset_master_data_repository(repo: MasterDataRepository | None = None) -> MasterDataRepository:
    """Resets master data repository singleton for test isolation."""
    global _master_data_repo_instance
    _master_data_repo_instance = repo
    return _master_data_repo_instance or get_master_data_repository()
