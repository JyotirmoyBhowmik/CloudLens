"""CloudLens Pagination Checkpoint Repository and Resumption Engine (Prompt P05).

Enforces:
- Pattern P1: Real PostgreSQL database persistence in connector_checkpoints table.
- Pattern P3: Injected dependency, zero mutable dict singletons in production.
- Pattern P4: Transactional RLS isolation via get_tenant_session().
- Pattern P6: Startup guard preventing InMemory repository outside development.
- Guaranteed resumption of interrupted/killed sync jobs without restarting from page 1.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
import sys
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from connectors.contract.models import JobCheckpoint
from db.session import get_tenant_session, verify_persistence_startup_guard
from domain.models.enums import ConnectorCapability
from domain.models.exceptions import MissingTenantContextException, PaginationCheckpointException
from domain.tenant.context import TenantContext

logger = logging.getLogger("cloudlens.connectors.checkpoint_store")


class SqlCheckpointStore:
    """PostgreSQL production implementation for pagination checkpoints with RLS."""

    is_in_memory: bool = False

    def _run_async(self, coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro)).result()

    def _row_to_checkpoint(self, row: Any) -> JobCheckpoint:
        cap_val = row[4]
        try:
            cap = ConnectorCapability(cap_val)
        except ValueError:
            cap = cap_val

        return JobCheckpoint(
            checkpoint_id=row[0],
            tenant_id=row[1],
            job_id=row[2],
            connector_id=row[3],
            capability=cap,
            continuation_token=row[5],
            page_number=row[6],
            records_ingested=row[7],
            last_record_id=row[8],
            status=row[9],
            created_at=row[10],
            updated_at=row[11],
        )

    async def save_checkpoint_async(
        self,
        tenant_context: TenantContext,
        job_id: str,
        connector_id: str,
        capability: ConnectorCapability,
        continuation_token: str | None,
        page_number: int,
        records_ingested: int,
        last_record_id: str | None = None,
        status: str = "IN_PROGRESS",
        session: AsyncSession | None = None,
    ) -> JobCheckpoint:
        if not tenant_context or not tenant_context.tenant_id:
            raise MissingTenantContextException(
                "Cannot save checkpoint without authenticated TenantContext."
            )
        if page_number < 1:
            raise PaginationCheckpointException(
                f"Invalid page_number {page_number}. Page numbers must be >= 1."
            )

        cap_val = capability.value if hasattr(capability, "value") else str(capability)
        now = datetime.now(UTC)

        if session is not None:
            return await self._save_with_session(
                tenant_context, job_id, connector_id, capability, cap_val,
                continuation_token, page_number, records_ingested, last_record_id, status, now, session
            )

        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await self._save_with_session(
                tenant_context, job_id, connector_id, capability, cap_val,
                continuation_token, page_number, records_ingested, last_record_id, status, now, sess
            )
            await sess.commit()
            return res

    async def _save_with_session(
        self,
        tenant_context: TenantContext,
        job_id: str,
        connector_id: str,
        capability: ConnectorCapability,
        cap_val: str,
        continuation_token: str | None,
        page_number: int,
        records_ingested: int,
        last_record_id: str | None,
        status: str,
        now: datetime,
        session: AsyncSession,
    ) -> JobCheckpoint:
        # Check existing checkpoint
        sel_q = text("""
            SELECT id, created_at
            FROM connector_checkpoints
            WHERE tenant_id = :tid AND job_id = :jid AND capability = :cap
            LIMIT 1;
        """)
        res = await session.execute(sel_q, {"tid": tenant_context.tenant_id, "jid": job_id, "cap": cap_val})
        row = res.fetchone()
        chk_id = row[0] if row else f"chk-{uuid.uuid4().hex[:12]}"
        created_at = row[1] if row else now

        upsert_q = text("""
            INSERT INTO connector_checkpoints (
                id, tenant_id, job_id, connector_id, capability, continuation_token,
                page_number, records_ingested, last_record_id, status, created_at, updated_at
            )
            VALUES (
                :id, :tenant_id, :job_id, :connector_id, :capability, :continuation_token,
                :page_number, :records_ingested, :last_record_id, :status, :created_at, :updated_at
            )
            ON CONFLICT (id) DO UPDATE SET
                continuation_token = EXCLUDED.continuation_token,
                page_number = EXCLUDED.page_number,
                records_ingested = EXCLUDED.records_ingested,
                last_record_id = EXCLUDED.last_record_id,
                status = EXCLUDED.status,
                updated_at = EXCLUDED.updated_at;
        """)
        await session.execute(
            upsert_q,
            {
                "id": chk_id,
                "tenant_id": tenant_context.tenant_id,
                "job_id": job_id,
                "connector_id": connector_id,
                "capability": cap_val,
                "continuation_token": continuation_token,
                "page_number": page_number,
                "records_ingested": records_ingested,
                "last_record_id": last_record_id,
                "status": status,
                "created_at": created_at,
                "updated_at": now,
            },
        )
        return JobCheckpoint(
            checkpoint_id=chk_id,
            tenant_id=tenant_context.tenant_id,
            job_id=job_id,
            connector_id=connector_id,
            capability=capability,
            continuation_token=continuation_token,
            page_number=page_number,
            records_ingested=records_ingested,
            last_record_id=last_record_id,
            status=status,
            created_at=created_at,
            updated_at=now,
        )

    async def get_checkpoint_async(
        self,
        tenant_id: str,
        job_id: str,
        capability: str | ConnectorCapability,
        session: AsyncSession | None = None,
    ) -> JobCheckpoint | None:
        cap_val = capability.value if hasattr(capability, "value") else str(capability)
        if session is not None:
            return await self._get_with_session(tenant_id, job_id, cap_val, session)
        async with get_tenant_session(tenant_id) as sess:
            return await self._get_with_session(tenant_id, job_id, cap_val, sess)

    async def _get_with_session(
        self, tenant_id: str, job_id: str, cap_val: str, session: AsyncSession
    ) -> JobCheckpoint | None:
        query = text("""
            SELECT id, tenant_id, job_id, connector_id, capability, continuation_token,
                   page_number, records_ingested, last_record_id, status, created_at, updated_at
            FROM connector_checkpoints
            WHERE tenant_id = :tid AND job_id = :jid AND capability = :cap
            LIMIT 1;
        """)
        result = await session.execute(query, {"tid": tenant_id, "jid": job_id, "cap": cap_val})
        row = result.fetchone()
        if not row:
            return None
        return self._row_to_checkpoint(row)

    # Sync interfaces
    def save_checkpoint(
        self,
        tenant_context: TenantContext,
        job_id: str,
        connector_id: str,
        capability: ConnectorCapability,
        continuation_token: str | None,
        page_number: int,
        records_ingested: int,
        last_record_id: str | None = None,
        status: str = "IN_PROGRESS",
    ) -> JobCheckpoint:
        return self._run_async(
            self.save_checkpoint_async(
                tenant_context=tenant_context,
                job_id=job_id,
                connector_id=connector_id,
                capability=capability,
                continuation_token=continuation_token,
                page_number=page_number,
                records_ingested=records_ingested,
                last_record_id=last_record_id,
                status=status,
            )
        )

    def get_checkpoint(
        self,
        tenant_id: str,
        job_id: str,
        capability: str | ConnectorCapability,
    ) -> JobCheckpoint | None:
        return self._run_async(self.get_checkpoint_async(tenant_id, job_id, capability))

    def get_latest_checkpoint(
        self,
        tenant_context: TenantContext,
        job_id: str,
        capability: ConnectorCapability,
    ) -> JobCheckpoint | None:
        if not tenant_context or not tenant_context.tenant_id:
            raise MissingTenantContextException(
                "Cannot retrieve checkpoint without authenticated TenantContext."
            )
        return self.get_checkpoint(
            tenant_id=tenant_context.tenant_id,
            job_id=job_id,
            capability=capability,
        )

    def mark_completed(
        self,
        tenant_context: TenantContext,
        job_id: str,
        capability: ConnectorCapability,
        total_records: int,
    ) -> JobCheckpoint:
        existing = self.get_latest_checkpoint(tenant_context, job_id, capability)
        page_num = existing.page_number if existing else 1
        connector_id = existing.connector_id if existing else "unknown"

        return self.save_checkpoint(
            tenant_context=tenant_context,
            job_id=job_id,
            connector_id=connector_id,
            capability=capability,
            continuation_token=None,
            page_number=page_num,
            records_ingested=total_records,
            status="COMPLETED",
        )

    def reset_for_test(self) -> None:
        pass


CheckpointStore = SqlCheckpointStore
_checkpoint_store_instance: Any = None


def get_checkpoint_store() -> Any:
    global _checkpoint_store_instance
    if _checkpoint_store_instance is None:
        _checkpoint_store_instance = SqlCheckpointStore()
        verify_persistence_startup_guard(_checkpoint_store_instance)
    return _checkpoint_store_instance


def reset_checkpoint_store(store: Any = None) -> Any:
    global _checkpoint_store_instance
    _checkpoint_store_instance = store
    return _checkpoint_store_instance or get_checkpoint_store()


checkpoint_store = get_checkpoint_store()

__all__ = [
    "CheckpointStore",
    "SqlCheckpointStore",
    "get_checkpoint_store",
    "checkpoint_store",
]
