"""Tenant-Aware SQL Repositories for Sync Jobs, Schedules, Quarantine, and First-Sync (Prompt P05).

Enforces:
- Pattern P1: Protocol + Sql implementations (SQLAlchemy 2.0 async + asyncpg).
- Pattern P3: Injected dependency, zero mutable dict singletons in production.
- Pattern P4: Transactional RLS isolation via get_tenant_session().
- Pattern P6: Startup guard preventing InMemory repository outside development.
- Database unique idempotency constraint on sync_jobs (connector, capability, period, version).
"""

from __future__ import annotations

import asyncio
import builtins
import concurrent.futures
import json
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_tenant_session
from domain.models.enums import (
    ConnectorCapability,
    ProviderType,
    QuarantineReason,
    QuarantineStatus,
    SyncJobStatus,
    SyncType,
)
from domain.sync.first_sync_models import FirstSyncProgressReport, FirstSyncStage
from domain.sync.models import ConnectorSchedule, QuarantineRecord, SyncJob, SyncScopeResult
from domain.tenant.context import TenantContext

logger = logging.getLogger("cloudlens.domain.sync.repository")


class SqlSyncJobRepository:
    """PostgreSQL production implementation for SyncJob execution audits with RLS."""

    is_in_memory: bool = False

    def _run_async(self, coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro)).result()

    def _row_to_job(self, row: Any) -> SyncJob:
        conn_type_val = row[2]
        try:
            conn_type = ProviderType(conn_type_val)
        except ValueError:
            try:
                conn_type = ProviderType(conn_type_val.lower())
            except ValueError:
                conn_type = conn_type_val

        sync_type_val = row[5]
        try:
            sync_type = SyncType(sync_type_val)
        except ValueError:
            sync_type = sync_type_val

        cap_val = row[6]
        cap = None
        if cap_val:
            try:
                cap = ConnectorCapability(cap_val)
            except ValueError:
                cap = cap_val

        status_val = row[13]
        try:
            job_status = SyncJobStatus(status_val)
        except ValueError:
            job_status = status_val

        raw_req = row[10] or []
        if isinstance(raw_req, str):
            raw_req = json.loads(raw_req)

        raw_comp = row[11] or []
        if isinstance(raw_comp, str):
            raw_comp = json.loads(raw_comp)

        raw_fail = row[12] or []
        if isinstance(raw_fail, str):
            raw_fail = json.loads(raw_fail)

        return SyncJob(
            id=row[0],
            tenant_id=row[1],
            connector_id=row[4],
            connector_type=conn_type,
            scope_id=row[3],
            sync_type=sync_type,
            capability=cap,
            dataset_version=row[7],
            idempotency_key=row[8],
            period_start=row[9],
            period_end=row[10] if False else None,  # handled via ordinal mapping
            scopes_requested=raw_req,
            scopes_completed=raw_comp,
            scopes_failed=raw_fail,
            status=job_status,
            started_at=row[14],
            completed_at=row[15],
            rows_ingested=row[16],
            error_message=row[17],
            created_at=row[18],
        )

    def _full_row_to_job(self, row: Any) -> SyncJob:
        # Columns:
        # 0: id, 1: tenant_id, 2: connector_type, 3: scope_id, 4: connector_id,
        # 5: sync_type, 6: capability, 7: dataset_version, 8: idempotency_key,
        # 9: period_start, 10: period_end, 11: scopes_requested, 12: scopes_completed,
        # 13: scopes_failed, 14: status, 15: started_at, 16: completed_at,
        # 17: rows_ingested, 18: error_message, 19: created_at
        conn_type_val = row[2]
        try:
            conn_type = ProviderType(conn_type_val)
        except ValueError:
            try:
                conn_type = ProviderType(conn_type_val.lower())
            except ValueError:
                conn_type = conn_type_val

        sync_type_val = row[5]
        try:
            sync_type = SyncType(sync_type_val)
        except ValueError:
            sync_type = sync_type_val

        cap = None
        if row[6]:
            try:
                cap = ConnectorCapability(row[6])
            except ValueError:
                cap = row[6]

        status_val = row[14]
        try:
            job_status = SyncJobStatus(status_val)
        except ValueError:
            job_status = status_val

        req = row[11] if isinstance(row[11], list) else (json.loads(row[11]) if row[11] else [])
        comp = row[12] if isinstance(row[12], list) else (json.loads(row[12]) if row[12] else [])
        fail = row[13] if isinstance(row[13], list) else (json.loads(row[13]) if row[13] else [])

        return SyncJob(
            id=row[0],
            tenant_id=row[1],
            connector_type=conn_type,
            scope_id=row[3],
            connector_id=row[4],
            sync_type=sync_type,
            capability=cap,
            dataset_version=row[7],
            idempotency_key=row[8],
            period_start=row[9],
            period_end=row[10],
            scopes_requested=req,
            scopes_completed=comp,
            scopes_failed=fail,
            status=job_status,
            started_at=row[15],
            completed_at=row[16],
            rows_ingested=row[17],
            error_message=row[18],
            created_at=row[19],
        )

    async def get_async(
        self, entity_id: str, *, tenant_context: TenantContext, session: AsyncSession | None = None
    ) -> SyncJob | None:
        if session is not None:
            return await self._get_with_session(entity_id, tenant_context, session)
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            return await self._get_with_session(entity_id, tenant_context, sess)

    async def _get_with_session(
        self, entity_id: str, tenant_context: TenantContext, session: AsyncSession
    ) -> SyncJob | None:
        query = text("""
            SELECT id, tenant_id, connector_type, scope_id, connector_id,
                   sync_type, capability, dataset_version, idempotency_key,
                   period_start, period_end, scopes_requested, scopes_completed,
                   scopes_failed, status, started_at, completed_at,
                   rows_ingested, error_message, created_at
            FROM sync_jobs
            WHERE tenant_id = :tid AND id = :id
            LIMIT 1;
        """)
        res = await session.execute(query, {"tid": tenant_context.tenant_id, "id": entity_id})
        row = res.fetchone()
        return self._full_row_to_job(row) if row else None

    async def save_async(
        self, entity: SyncJob, *, tenant_context: TenantContext, session: AsyncSession | None = None
    ) -> SyncJob:
        entity.tenant_id = tenant_context.tenant_id
        if session is not None:
            return await self._save_with_session(entity, tenant_context, session)
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await self._save_with_session(entity, tenant_context, sess)
            await sess.commit()
            return res

    async def _save_with_session(
        self, entity: SyncJob, tenant_context: TenantContext, session: AsyncSession
    ) -> SyncJob:
        now = datetime.now(UTC)
        conn_type_val = entity.connector_type.value if hasattr(entity.connector_type, "value") else str(entity.connector_type)
        sync_type_val = entity.sync_type.value if hasattr(entity.sync_type, "value") else str(entity.sync_type)
        cap_val = entity.capability.value if (entity.capability and hasattr(entity.capability, "value")) else (str(entity.capability) if entity.capability else None)
        status_val = entity.status.value if hasattr(entity.status, "value") else str(entity.status)

        req_json = json.dumps(entity.scopes_requested)
        comp_json = json.dumps(entity.scopes_completed)
        fail_json = json.dumps(entity.scopes_failed)

        query = text("""
            INSERT INTO sync_jobs (
                id, tenant_id, connector_type, scope_id, connector_id,
                sync_type, capability, dataset_version, idempotency_key,
                period_start, period_end, scopes_requested, scopes_completed,
                scopes_failed, status, started_at, completed_at,
                rows_ingested, error_message, created_at
            )
            VALUES (
                :id, :tenant_id, :connector_type, :scope_id, :connector_id,
                :sync_type, :capability, :dataset_version, :idempotency_key,
                :period_start, :period_end, CAST(:req AS jsonb), CAST(:comp AS jsonb),
                CAST(:fail AS jsonb), :status, :started_at, :completed_at,
                :rows_ingested, :error_message, :created_at
            )
            ON CONFLICT (id) DO UPDATE SET
                status = EXCLUDED.status,
                completed_at = EXCLUDED.completed_at,
                rows_ingested = EXCLUDED.rows_ingested,
                error_message = EXCLUDED.error_message,
                scopes_completed = EXCLUDED.scopes_completed,
                scopes_failed = EXCLUDED.scopes_failed;
        """)
        await session.execute(
            query,
            {
                "id": entity.id,
                "tenant_id": tenant_context.tenant_id,
                "connector_type": conn_type_val,
                "scope_id": entity.scope_id,
                "connector_id": entity.connector_id,
                "sync_type": sync_type_val,
                "capability": cap_val,
                "dataset_version": entity.dataset_version,
                "idempotency_key": entity.idempotency_key,
                "period_start": entity.period_start,
                "period_end": entity.period_end,
                "req": req_json,
                "comp": comp_json,
                "fail": fail_json,
                "status": status_val,
                "started_at": entity.started_at,
                "completed_at": entity.completed_at,
                "rows_ingested": entity.rows_ingested,
                "error_message": entity.error_message,
                "created_at": entity.created_at or now,
            },
        )
        return entity

    async def list_async(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
        session: AsyncSession | None = None,
    ) -> builtins.list[SyncJob]:
        if session is not None:
            return await self._list_with_session(tenant_context, filter_params, limit, offset, session)
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            return await self._list_with_session(tenant_context, filter_params, limit, offset, sess)

    async def _list_with_session(
        self,
        tenant_context: TenantContext,
        filter_params: Any,
        limit: int,
        offset: int,
        session: AsyncSession,
    ) -> builtins.list[SyncJob]:
        conditions = ["tenant_id = :tid"]
        params: dict[str, Any] = {"tid": tenant_context.tenant_id, "limit": limit, "offset": offset}

        if isinstance(filter_params, dict):
            status = filter_params.get("status")
            if status:
                st_val = status.value if hasattr(status, "value") else str(status)
                conditions.append("status = :status")
                params["status"] = st_val
            conn = filter_params.get("connector_id")
            if conn:
                conditions.append("connector_id = :conn_id")
                params["conn_id"] = conn

        where_clause = " AND ".join(conditions)
        query = text(f"""
            SELECT id, tenant_id, connector_type, scope_id, connector_id,
                   sync_type, capability, dataset_version, idempotency_key,
                   period_start, period_end, scopes_requested, scopes_completed,
                   scopes_failed, status, started_at, completed_at,
                   rows_ingested, error_message, created_at
            FROM sync_jobs
            WHERE {where_clause}
            ORDER BY started_at DESC
            LIMIT :limit OFFSET :offset;
        """)
        res = await session.execute(query, params)
        rows = res.fetchall()
        return [self._full_row_to_job(r) for r in rows]

    async def delete_async(
        self, entity_id: str, *, tenant_context: TenantContext, session: AsyncSession | None = None
    ) -> bool:
        query = text("DELETE FROM sync_jobs WHERE tenant_id = :tid AND id = :id;")
        params = {"tid": tenant_context.tenant_id, "id": entity_id}
        if session is not None:
            res = await session.execute(query, params)
            return res.rowcount > 0
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(query, params)
            await sess.commit()
            return res.rowcount > 0

    async def get_by_idempotency_key_async(
        self, idempotency_key: str, *, tenant_context: TenantContext, session: AsyncSession | None = None
    ) -> SyncJob | None:
        query = text("""
            SELECT id, tenant_id, connector_type, scope_id, connector_id,
                   sync_type, capability, dataset_version, idempotency_key,
                   period_start, period_end, scopes_requested, scopes_completed,
                   scopes_failed, status, started_at, completed_at,
                   rows_ingested, error_message, created_at
            FROM sync_jobs
            WHERE tenant_id = :tid AND idempotency_key = :key
            LIMIT 1;
        """)
        params = {"tid": tenant_context.tenant_id, "key": idempotency_key}
        if session is not None:
            res = await session.execute(query, params)
            row = res.fetchone()
            return self._full_row_to_job(row) if row else None
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(query, params)
            row = res.fetchone()
            return self._full_row_to_job(row) if row else None

    async def get_latest_successful_async(
        self,
        connector_id: str,
        capability: ConnectorCapability,
        *,
        tenant_context: TenantContext,
        session: AsyncSession | None = None,
    ) -> SyncJob | None:
        cap_val = capability.value if hasattr(capability, "value") else str(capability)
        query = text("""
            SELECT id, tenant_id, connector_type, scope_id, connector_id,
                   sync_type, capability, dataset_version, idempotency_key,
                   period_start, period_end, scopes_requested, scopes_completed,
                   scopes_failed, status, started_at, completed_at,
                   rows_ingested, error_message, created_at
            FROM sync_jobs
            WHERE tenant_id = :tid
              AND connector_id = :cid
              AND (capability = :cap OR capability IS NULL)
              AND status IN ('COMPLETED', 'PARTIAL_SUCCESS')
            ORDER BY COALESCE(completed_at, started_at) DESC
            LIMIT 1;
        """)
        params = {"tid": tenant_context.tenant_id, "cid": connector_id, "cap": cap_val}
        if session is not None:
            res = await session.execute(query, params)
            row = res.fetchone()
            return self._full_row_to_job(row) if row else None
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(query, params)
            row = res.fetchone()
            return self._full_row_to_job(row) if row else None

    # Sync interfaces
    def get(self, entity_id: str, *, tenant_context: TenantContext) -> SyncJob | None:
        return self._run_async(self.get_async(entity_id, tenant_context=tenant_context))

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[SyncJob]:
        return self._run_async(
            self.list_async(tenant_context=tenant_context, filter_params=filter_params, limit=limit, offset=offset)
        )

    def save(self, entity: SyncJob, *, tenant_context: TenantContext) -> SyncJob:
        return self._run_async(self.save_async(entity, tenant_context=tenant_context))

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return self._run_async(self.delete_async(entity_id, tenant_context=tenant_context))

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        res = self.get(entity_id, tenant_context=tenant_context)
        return res is not None

    def get_by_idempotency_key(
        self, idempotency_key: str, *, tenant_context: TenantContext
    ) -> SyncJob | None:
        return self._run_async(self.get_by_idempotency_key_async(idempotency_key, tenant_context=tenant_context))

    def get_latest_successful(
        self,
        connector_id: str,
        capability: ConnectorCapability,
        *,
        tenant_context: TenantContext,
    ) -> SyncJob | None:
        return self._run_async(
            self.get_latest_successful_async(connector_id, capability, tenant_context=tenant_context)
        )


class SqlQuarantineRepository:
    """PostgreSQL production implementation for QuarantineRecord entities with RLS."""

    is_in_memory: bool = False

    def _run_async(self, coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro)).result()

    def _row_to_record(self, row: Any) -> QuarantineRecord:
        cap_val = row[4]
        try:
            cap = ConnectorCapability(cap_val)
        except ValueError:
            cap = cap_val

        reason_val = row[5]
        try:
            reason = QuarantineReason(reason_val)
        except ValueError:
            reason = reason_val

        status_val = row[9]
        try:
            q_status = QuarantineStatus(status_val)
        except ValueError:
            q_status = status_val

        summary = row[7] if isinstance(row[7], dict) else (json.loads(row[7]) if row[7] else {})

        return QuarantineRecord(
            id=row[0],
            tenant_id=row[1],
            connector_id=row[2],
            job_id=row[3],
            capability=cap,
            quarantine_reason=reason,
            error_details=row[6],
            payload_summary=summary,
            raw_payload_path=row[8],
            status=q_status,
            quarantined_at=row[10],
            resolved_at=row[11],
            resolved_by=row[12],
        )

    async def get_async(
        self, entity_id: str, *, tenant_context: TenantContext, session: AsyncSession | None = None
    ) -> QuarantineRecord | None:
        query = text("""
            SELECT id, tenant_id, connector_id, job_id, capability,
                   quarantine_reason, error_details, payload_summary,
                   raw_payload_path, status, quarantined_at, resolved_at, resolved_by
            FROM quarantine_records
            WHERE tenant_id = :tid AND id = :id
            LIMIT 1;
        """)
        params = {"tid": tenant_context.tenant_id, "id": entity_id}
        if session is not None:
            res = await session.execute(query, params)
            row = res.fetchone()
            return self._row_to_record(row) if row else None
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(query, params)
            row = res.fetchone()
            return self._row_to_record(row) if row else None

    async def save_async(
        self, entity: QuarantineRecord, *, tenant_context: TenantContext, session: AsyncSession | None = None
    ) -> QuarantineRecord:
        entity.tenant_id = tenant_context.tenant_id
        now = datetime.now(UTC)
        cap_val = entity.capability.value if hasattr(entity.capability, "value") else str(entity.capability)
        reason_val = entity.quarantine_reason.value if hasattr(entity.quarantine_reason, "value") else str(entity.quarantine_reason)
        status_val = entity.status.value if hasattr(entity.status, "value") else str(entity.status)
        summary_json = json.dumps(entity.payload_summary)

        query = text("""
            INSERT INTO quarantine_records (
                id, tenant_id, connector_id, job_id, capability,
                quarantine_reason, error_details, payload_summary,
                raw_payload_path, status, quarantined_at, resolved_at, resolved_by
            )
            VALUES (
                :id, :tenant_id, :connector_id, :job_id, :capability,
                :quarantine_reason, :error_details, CAST(:summary AS jsonb),
                :raw_payload_path, :status, :quarantined_at, :resolved_at, :resolved_by
            )
            ON CONFLICT (id) DO UPDATE SET
                status = EXCLUDED.status,
                resolved_at = EXCLUDED.resolved_at,
                resolved_by = EXCLUDED.resolved_by;
        """)
        params = {
            "id": entity.id,
            "tenant_id": tenant_context.tenant_id,
            "connector_id": entity.connector_id,
            "job_id": entity.job_id,
            "capability": cap_val,
            "quarantine_reason": reason_val,
            "error_details": entity.error_details,
            "summary": summary_json,
            "raw_payload_path": entity.raw_payload_path,
            "status": status_val,
            "quarantined_at": entity.quarantined_at or now,
            "resolved_at": entity.resolved_at,
            "resolved_by": entity.resolved_by,
        }
        if session is not None:
            await session.execute(query, params)
            return entity
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            await sess.execute(query, params)
            await sess.commit()
            return entity

    async def list_async(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
        session: AsyncSession | None = None,
    ) -> builtins.list[QuarantineRecord]:
        conditions = ["tenant_id = :tid"]
        params: dict[str, Any] = {"tid": tenant_context.tenant_id, "limit": limit, "offset": offset}

        if isinstance(filter_params, dict):
            status = filter_params.get("status")
            if status:
                st_val = status.value if hasattr(status, "value") else str(status)
                conditions.append("status = :status")
                params["status"] = st_val
            conn = filter_params.get("connector_id")
            if conn:
                conditions.append("connector_id = :conn_id")
                params["conn_id"] = conn

        where_clause = " AND ".join(conditions)
        query = text(f"""
            SELECT id, tenant_id, connector_id, job_id, capability,
                   quarantine_reason, error_details, payload_summary,
                   raw_payload_path, status, quarantined_at, resolved_at, resolved_by
            FROM quarantine_records
            WHERE {where_clause}
            ORDER BY quarantined_at DESC
            LIMIT :limit OFFSET :offset;
        """)
        if session is not None:
            res = await session.execute(query, params)
            rows = res.fetchall()
            return [self._row_to_record(r) for r in rows]
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(query, params)
            rows = res.fetchall()
            return [self._row_to_record(r) for r in rows]

    async def delete_async(
        self, entity_id: str, *, tenant_context: TenantContext, session: AsyncSession | None = None
    ) -> bool:
        query = text("DELETE FROM quarantine_records WHERE tenant_id = :tid AND id = :id;")
        params = {"tid": tenant_context.tenant_id, "id": entity_id}
        if session is not None:
            res = await session.execute(query, params)
            return res.rowcount > 0
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(query, params)
            await sess.commit()
            return res.rowcount > 0

    # Sync interfaces
    def get(self, entity_id: str, *, tenant_context: TenantContext) -> QuarantineRecord | None:
        return self._run_async(self.get_async(entity_id, tenant_context=tenant_context))

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[QuarantineRecord]:
        return self._run_async(
            self.list_async(tenant_context=tenant_context, filter_params=filter_params, limit=limit, offset=offset)
        )

    def save(self, entity: QuarantineRecord, *, tenant_context: TenantContext) -> QuarantineRecord:
        return self._run_async(self.save_async(entity, tenant_context=tenant_context))

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return self._run_async(self.delete_async(entity_id, tenant_context=tenant_context))

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        res = self.get(entity_id, tenant_context=tenant_context)
        return res is not None

    def list_by_status(
        self,
        status: QuarantineStatus,
        *,
        tenant_context: TenantContext,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[QuarantineRecord]:
        return self.list(
            tenant_context=tenant_context,
            filter_params={"status": status},
            limit=limit,
            offset=offset,
        )


class SqlConnectorScheduleRepository:
    """PostgreSQL production implementation for ConnectorSchedule entities with RLS."""

    is_in_memory: bool = False

    def _run_async(self, coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro)).result()

    def _row_to_schedule(self, row: Any) -> ConnectorSchedule:
        cap_val = row[3]
        try:
            cap = ConnectorCapability(cap_val)
        except ValueError:
            cap = cap_val

        return ConnectorSchedule(
            id=row[0],
            tenant_id=row[1],
            connector_id=row[2],
            capability=cap,
            interval_minutes=row[4],
            cron_expression=row[5],
            lookback_days=row[6],
            is_enabled=row[7],
            last_run_at=row[8],
            last_successful_run_at=row[9],
            next_run_at=row[10],
            created_at=row[11],
            updated_at=row[12],
        )

    async def get_async(
        self, entity_id: str, *, tenant_context: TenantContext, session: AsyncSession | None = None
    ) -> ConnectorSchedule | None:
        query = text("""
            SELECT id, tenant_id, connector_id, capability, interval_minutes,
                   cron_expression, lookback_days, is_enabled, last_run_at,
                   last_successful_run_at, next_run_at, created_at, updated_at
            FROM connector_schedules
            WHERE tenant_id = :tid AND id = :id
            LIMIT 1;
        """)
        params = {"tid": tenant_context.tenant_id, "id": entity_id}
        if session is not None:
            res = await session.execute(query, params)
            row = res.fetchone()
            return self._row_to_schedule(row) if row else None
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(query, params)
            row = res.fetchone()
            return self._row_to_schedule(row) if row else None

    async def save_async(
        self, entity: ConnectorSchedule, *, tenant_context: TenantContext, session: AsyncSession | None = None
    ) -> ConnectorSchedule:
        entity.tenant_id = tenant_context.tenant_id
        now = datetime.now(UTC)
        entity.updated_at = now
        cap_val = entity.capability.value if hasattr(entity.capability, "value") else str(entity.capability)

        query = text("""
            INSERT INTO connector_schedules (
                id, tenant_id, connector_id, capability, interval_minutes,
                cron_expression, lookback_days, is_enabled, last_run_at,
                last_successful_run_at, next_run_at, created_at, updated_at
            )
            VALUES (
                :id, :tenant_id, :connector_id, :capability, :interval_minutes,
                :cron_expression, :lookback_days, :is_enabled, :last_run_at,
                :last_successful_run_at, :next_run_at, :created_at, :updated_at
            )
            ON CONFLICT (id) DO UPDATE SET
                interval_minutes = EXCLUDED.interval_minutes,
                cron_expression = EXCLUDED.cron_expression,
                lookback_days = EXCLUDED.lookback_days,
                is_enabled = EXCLUDED.is_enabled,
                last_run_at = EXCLUDED.last_run_at,
                last_successful_run_at = EXCLUDED.last_successful_run_at,
                next_run_at = EXCLUDED.next_run_at,
                updated_at = EXCLUDED.updated_at;
        """)
        params = {
            "id": entity.id,
            "tenant_id": tenant_context.tenant_id,
            "connector_id": entity.connector_id,
            "capability": cap_val,
            "interval_minutes": entity.interval_minutes,
            "cron_expression": entity.cron_expression,
            "lookback_days": entity.lookback_days,
            "is_enabled": entity.is_enabled,
            "last_run_at": entity.last_run_at,
            "last_successful_run_at": entity.last_successful_run_at,
            "next_run_at": entity.next_run_at,
            "created_at": entity.created_at or now,
            "updated_at": now,
        }
        if session is not None:
            await session.execute(query, params)
            return entity
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            await sess.execute(query, params)
            await sess.commit()
            return entity

    async def list_async(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
        session: AsyncSession | None = None,
    ) -> builtins.list[ConnectorSchedule]:
        conditions = ["tenant_id = :tid"]
        params: dict[str, Any] = {"tid": tenant_context.tenant_id, "limit": limit, "offset": offset}

        if isinstance(filter_params, dict):
            conn = filter_params.get("connector_id")
            if conn:
                conditions.append("connector_id = :conn_id")
                params["conn_id"] = conn

        where_clause = " AND ".join(conditions)
        query = text(f"""
            SELECT id, tenant_id, connector_id, capability, interval_minutes,
                   cron_expression, lookback_days, is_enabled, last_run_at,
                   last_successful_run_at, next_run_at, created_at, updated_at
            FROM connector_schedules
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset;
        """)
        if session is not None:
            res = await session.execute(query, params)
            rows = res.fetchall()
            return [self._row_to_schedule(r) for r in rows]
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(query, params)
            rows = res.fetchall()
            return [self._row_to_schedule(r) for r in rows]

    async def delete_async(
        self, entity_id: str, *, tenant_context: TenantContext, session: AsyncSession | None = None
    ) -> bool:
        query = text("DELETE FROM connector_schedules WHERE tenant_id = :tid AND id = :id;")
        params = {"tid": tenant_context.tenant_id, "id": entity_id}
        if session is not None:
            res = await session.execute(query, params)
            return res.rowcount > 0
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(query, params)
            await sess.commit()
            return res.rowcount > 0

    async def get_by_connector_and_capability_async(
        self,
        connector_id: str,
        capability: ConnectorCapability,
        *,
        tenant_context: TenantContext,
        session: AsyncSession | None = None,
    ) -> ConnectorSchedule | None:
        cap_val = capability.value if hasattr(capability, "value") else str(capability)
        query = text("""
            SELECT id, tenant_id, connector_id, capability, interval_minutes,
                   cron_expression, lookback_days, is_enabled, last_run_at,
                   last_successful_run_at, next_run_at, created_at, updated_at
            FROM connector_schedules
            WHERE tenant_id = :tid AND connector_id = :cid AND capability = :cap
            LIMIT 1;
        """)
        params = {"tid": tenant_context.tenant_id, "cid": connector_id, "cap": cap_val}
        if session is not None:
            res = await session.execute(query, params)
            row = res.fetchone()
            return self._row_to_schedule(row) if row else None
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(query, params)
            row = res.fetchone()
            return self._row_to_schedule(row) if row else None

    async def list_all_enabled_async(self) -> builtins.list[ConnectorSchedule]:
        """Queries all enabled schedules across all tenants for Beat scheduling."""
        query = text("""
            SELECT id, tenant_id, connector_id, capability, interval_minutes,
                   cron_expression, lookback_days, is_enabled, last_run_at,
                   last_successful_run_at, next_run_at, created_at, updated_at
            FROM connector_schedules
            WHERE is_enabled = true;
        """)
        async with get_tenant_session() as sess:
            await sess.execute(text("SELECT set_config('cloudlens.bypass_rls', 'on', true);"))
            res = await sess.execute(query)
            rows = res.fetchall()
            return [self._row_to_schedule(r) for r in rows]

    # Sync interfaces
    def get(self, entity_id: str, *, tenant_context: TenantContext) -> ConnectorSchedule | None:
        return self._run_async(self.get_async(entity_id, tenant_context=tenant_context))

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[ConnectorSchedule]:
        return self._run_async(
            self.list_async(tenant_context=tenant_context, filter_params=filter_params, limit=limit, offset=offset)
        )

    def save(self, entity: ConnectorSchedule, *, tenant_context: TenantContext) -> ConnectorSchedule:
        return self._run_async(self.save_async(entity, tenant_context=tenant_context))

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return self._run_async(self.delete_async(entity_id, tenant_context=tenant_context))

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        res = self.get(entity_id, tenant_context=tenant_context)
        return res is not None

    def get_by_connector_and_capability(
        self,
        connector_id: str,
        capability: ConnectorCapability,
        *,
        tenant_context: TenantContext,
    ) -> ConnectorSchedule | None:
        return self._run_async(
            self.get_by_connector_and_capability_async(connector_id, capability, tenant_context=tenant_context)
        )

    def list_for_connector(
        self, connector_id: str, *, tenant_context: TenantContext
    ) -> builtins.list[ConnectorSchedule]:
        return self.list(tenant_context=tenant_context, filter_params={"connector_id": connector_id})

    def list_all_enabled(self) -> builtins.list[ConnectorSchedule]:
        return self._run_async(self.list_all_enabled_async())


class SqlFirstSyncProgressRepository:
    """PostgreSQL production implementation for FirstSyncProgressReport entities with RLS."""

    is_in_memory: bool = False

    def _run_async(self, coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro)).result()

    def _row_to_report(self, row: Any) -> FirstSyncProgressReport:
        raw_stages = row[6] or []
        if isinstance(raw_stages, str):
            raw_stages = json.loads(raw_stages)
        stages = [FirstSyncStage.model_validate(s) if isinstance(s, dict) else s for s in raw_stages]

        return FirstSyncProgressReport(
            id=row[0],
            tenant_id=row[1],
            session_id=row[2],
            connector_id=row[3],
            initial_sync_job_id=row[4],
            overall_status=row[5],
            stages=stages,
            total_stages=row[7],
            completed_stages=row[8],
            estimated_time_to_first_cost_seconds=row[9],
            landing_destination=row[10],
            created_at=row[11],
            updated_at=row[12],
        )

    async def get_async(
        self, entity_id: str, *, tenant_context: TenantContext, session: AsyncSession | None = None
    ) -> FirstSyncProgressReport | None:
        query = text("""
            SELECT id, tenant_id, session_id, connector_id, initial_sync_job_id,
                   overall_status, stages_data, total_stages, completed_stages,
                   estimated_time_to_first_cost_seconds, landing_destination,
                   created_at, updated_at
            FROM first_sync_progress
            WHERE tenant_id = :tid AND id = :id
            LIMIT 1;
        """)
        params = {"tid": tenant_context.tenant_id, "id": entity_id}
        if session is not None:
            res = await session.execute(query, params)
            row = res.fetchone()
            return self._row_to_report(row) if row else None
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(query, params)
            row = res.fetchone()
            return self._row_to_report(row) if row else None

    async def get_by_session_id_async(
        self, session_id: str, *, tenant_context: TenantContext, session: AsyncSession | None = None
    ) -> FirstSyncProgressReport | None:
        query = text("""
            SELECT id, tenant_id, session_id, connector_id, initial_sync_job_id,
                   overall_status, stages_data, total_stages, completed_stages,
                   estimated_time_to_first_cost_seconds, landing_destination,
                   created_at, updated_at
            FROM first_sync_progress
            WHERE tenant_id = :tid AND session_id = :sid
            LIMIT 1;
        """)
        params = {"tid": tenant_context.tenant_id, "sid": session_id}
        if session is not None:
            res = await session.execute(query, params)
            row = res.fetchone()
            return self._row_to_report(row) if row else None
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(query, params)
            row = res.fetchone()
            return self._row_to_report(row) if row else None

    async def get_by_connector_id_async(
        self, connector_id: str, *, tenant_context: TenantContext, session: AsyncSession | None = None
    ) -> FirstSyncProgressReport | None:
        query = text("""
            SELECT id, tenant_id, session_id, connector_id, initial_sync_job_id,
                   overall_status, stages_data, total_stages, completed_stages,
                   estimated_time_to_first_cost_seconds, landing_destination,
                   created_at, updated_at
            FROM first_sync_progress
            WHERE tenant_id = :tid AND connector_id = :cid
            ORDER BY created_at DESC
            LIMIT 1;
        """)
        params = {"tid": tenant_context.tenant_id, "cid": connector_id}
        if session is not None:
            res = await session.execute(query, params)
            row = res.fetchone()
            return self._row_to_report(row) if row else None
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(query, params)
            row = res.fetchone()
            return self._row_to_report(row) if row else None

    async def save_async(
        self, entity: FirstSyncProgressReport, *, tenant_context: TenantContext, session: AsyncSession | None = None
    ) -> FirstSyncProgressReport:
        entity.tenant_id = tenant_context.tenant_id
        now = datetime.now(UTC)
        entity.updated_at = now
        stages_json = json.dumps([s.model_dump(mode="json") if hasattr(s, "model_dump") else s for s in entity.stages])

        query = text("""
            INSERT INTO first_sync_progress (
                id, tenant_id, session_id, connector_id, initial_sync_job_id,
                overall_status, stages_data, total_stages, completed_stages,
                estimated_time_to_first_cost_seconds, landing_destination,
                created_at, updated_at
            )
            VALUES (
                :id, :tenant_id, :session_id, :connector_id, :initial_sync_job_id,
                :overall_status, CAST(:stages AS jsonb), :total_stages, :completed_stages,
                :estimated_time_to_first_cost_seconds, :landing_destination,
                :created_at, :updated_at
            )
            ON CONFLICT (id) DO UPDATE SET
                initial_sync_job_id = EXCLUDED.initial_sync_job_id,
                overall_status = EXCLUDED.overall_status,
                stages_data = EXCLUDED.stages_data,
                completed_stages = EXCLUDED.completed_stages,
                updated_at = EXCLUDED.updated_at;
        """)
        params = {
            "id": entity.id,
            "tenant_id": tenant_context.tenant_id,
            "session_id": entity.session_id,
            "connector_id": entity.connector_id,
            "initial_sync_job_id": entity.initial_sync_job_id,
            "overall_status": entity.overall_status,
            "stages": stages_json,
            "total_stages": entity.total_stages,
            "completed_stages": entity.completed_stages,
            "estimated_time_to_first_cost_seconds": entity.estimated_time_to_first_cost_seconds,
            "landing_destination": entity.landing_destination,
            "created_at": entity.created_at or now,
            "updated_at": now,
        }
        if session is not None:
            await session.execute(query, params)
            return entity
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            await sess.execute(query, params)
            await sess.commit()
            return entity

    async def list_async(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
        session: AsyncSession | None = None,
    ) -> builtins.list[FirstSyncProgressReport]:
        query = text("""
            SELECT id, tenant_id, session_id, connector_id, initial_sync_job_id,
                   overall_status, stages_data, total_stages, completed_stages,
                   estimated_time_to_first_cost_seconds, landing_destination,
                   created_at, updated_at
            FROM first_sync_progress
            WHERE tenant_id = :tid
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset;
        """)
        params = {"tid": tenant_context.tenant_id, "limit": limit, "offset": offset}
        if session is not None:
            res = await session.execute(query, params)
            rows = res.fetchall()
            return [self._row_to_report(r) for r in rows]
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(query, params)
            rows = res.fetchall()
            return [self._row_to_report(r) for r in rows]

    async def delete_async(
        self, entity_id: str, *, tenant_context: TenantContext, session: AsyncSession | None = None
    ) -> bool:
        query = text("DELETE FROM first_sync_progress WHERE tenant_id = :tid AND id = :id;")
        params = {"tid": tenant_context.tenant_id, "id": entity_id}
        if session is not None:
            res = await session.execute(query, params)
            return res.rowcount > 0
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(query, params)
            await sess.commit()
            return res.rowcount > 0

    # Sync interfaces
    def get(self, entity_id: str, *, tenant_context: TenantContext) -> FirstSyncProgressReport | None:
        return self._run_async(self.get_async(entity_id, tenant_context=tenant_context))

    def get_by_session_id(
        self, session_id: str, *, tenant_context: TenantContext
    ) -> FirstSyncProgressReport | None:
        return self._run_async(self.get_by_session_id_async(session_id, tenant_context=tenant_context))

    def get_by_connector_id(
        self, connector_id: str, *, tenant_context: TenantContext
    ) -> FirstSyncProgressReport | None:
        return self._run_async(self.get_by_connector_id_async(connector_id, tenant_context=tenant_context))

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[FirstSyncProgressReport]:
        return self._run_async(
            self.list_async(tenant_context=tenant_context, filter_params=filter_params, limit=limit, offset=offset)
        )

    def save(
        self, entity: FirstSyncProgressReport, *, tenant_context: TenantContext
    ) -> FirstSyncProgressReport:
        return self._run_async(self.save_async(entity, tenant_context=tenant_context))

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return self._run_async(self.delete_async(entity_id, tenant_context=tenant_context))

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        res = self.get(entity_id, tenant_context=tenant_context)
        return res is not None


# Backwards compatibility class aliases
SyncJobRepository = SqlSyncJobRepository
QuarantineRepository = SqlQuarantineRepository
ConnectorScheduleRepository = SqlConnectorScheduleRepository
FirstSyncProgressRepository = SqlFirstSyncProgressRepository

_sync_job_repo_instance: Any = None
_quarantine_repo_instance: Any = None
_sched_repo_instance: Any = None
_first_sync_repo_instance: Any = None


def _check_startup_guard(repo_name: str) -> None:
    env = os.getenv("CLOUDLENS_ENV", "development").strip().lower()
    mode = os.getenv("PERSISTENCE_MODE", "sql").strip().lower()
    if mode == "inmemory" and env in ("staging", "production"):
        logger.critical(
            "FATAL STARTUP GUARD: Staging/production refuses InMemory %s repository configuration.",
            repo_name,
        )
        sys.exit(1)


def get_sync_job_repository() -> Any:
    global _sync_job_repo_instance
    mode = os.getenv("PERSISTENCE_MODE", "sql").strip().lower()
    _check_startup_guard("SyncJob")
    if mode == "inmemory":
        from tests.fakes.sync import InMemorySyncJobRepository
        return InMemorySyncJobRepository()
    if _sync_job_repo_instance is None:
        _sync_job_repo_instance = SqlSyncJobRepository()
    return _sync_job_repo_instance


def get_quarantine_repository() -> Any:
    global _quarantine_repo_instance
    mode = os.getenv("PERSISTENCE_MODE", "sql").strip().lower()
    _check_startup_guard("Quarantine")
    if mode == "inmemory":
        from tests.fakes.sync import InMemoryQuarantineRepository
        return InMemoryQuarantineRepository()
    if _quarantine_repo_instance is None:
        _quarantine_repo_instance = SqlQuarantineRepository()
    return _quarantine_repo_instance


def get_connector_schedule_repository() -> Any:
    global _sched_repo_instance
    mode = os.getenv("PERSISTENCE_MODE", "sql").strip().lower()
    _check_startup_guard("ConnectorSchedule")
    if mode == "inmemory":
        from tests.fakes.sync import InMemoryConnectorScheduleRepository
        return InMemoryConnectorScheduleRepository()
    if _sched_repo_instance is None:
        _sched_repo_instance = SqlConnectorScheduleRepository()
    return _sched_repo_instance


def get_first_sync_progress_repository() -> Any:
    global _first_sync_repo_instance
    mode = os.getenv("PERSISTENCE_MODE", "sql").strip().lower()
    _check_startup_guard("FirstSyncProgress")
    if mode == "inmemory":
        from tests.fakes.sync import InMemoryFirstSyncProgressRepository
        return InMemoryFirstSyncProgressRepository()
    if _first_sync_repo_instance is None:
        _first_sync_repo_instance = SqlFirstSyncProgressRepository()
    return _first_sync_repo_instance


def reset_sync_repositories() -> None:
    global _sync_job_repo_instance, _quarantine_repo_instance, _sched_repo_instance, _first_sync_repo_instance
    _sync_job_repo_instance = None
    _quarantine_repo_instance = None
    _sched_repo_instance = None
    _first_sync_repo_instance = None


__all__ = [
    "SqlSyncJobRepository",
    "SqlQuarantineRepository",
    "SqlConnectorScheduleRepository",
    "SqlFirstSyncProgressRepository",
    "SyncJobRepository",
    "QuarantineRepository",
    "ConnectorScheduleRepository",
    "FirstSyncProgressRepository",
    "get_sync_job_repository",
    "get_quarantine_repository",
    "get_connector_schedule_repository",
    "get_first_sync_progress_repository",
    "reset_sync_repositories",
]
