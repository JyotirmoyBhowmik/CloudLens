"""Feature Flag SQL Repository and Protocol (Prompt P04).

Enforces:
- Pattern P1: Protocol + SqlFeatureFlagRepository (SQLAlchemy 2.0 async).
- Pattern P3: Injected dependency, zero mutable dict singletons as sources of truth.
- Pattern P4: Transactional isolation via get_tenant_session().
- Pattern P6: Startup guard preventing InMemory repository outside development.
- Persistent tenant-scoped and global feature flag overrides and audit trails.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
import sys
import uuid
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_tenant_session
from domain.config.feature_flags import FlagAuditEvent

logger = logging.getLogger("cloudlens.domain.config.feature_flags_repository")


@runtime_checkable
class FeatureFlagRepository(Protocol):
    """Authoritative protocol for feature flag overrides and audit persistence."""

    async def get_override(
        self, flag_key: str, tenant_id: str | None = None, session: AsyncSession | None = None
    ) -> bool | None:
        ...

    async def set_override(
        self,
        flag_key: str,
        enabled: bool,
        tenant_id: str | None = None,
        updated_by: str = "system",
        reason: str = "",
        session: AsyncSession | None = None,
    ) -> None:
        ...

    async def record_audit(
        self, event: FlagAuditEvent, session: AsyncSession | None = None
    ) -> None:
        ...

    async def get_audit_log(
        self,
        flag_key: str | None = None,
        tenant_id: str | None = None,
        session: AsyncSession | None = None,
    ) -> list[FlagAuditEvent]:
        ...

    def get_override_sync(self, flag_key: str, tenant_id: str | None = None) -> bool | None:
        ...

    def set_override_sync(
        self,
        flag_key: str,
        enabled: bool,
        tenant_id: str | None = None,
        updated_by: str = "system",
        reason: str = "",
    ) -> None:
        ...

    def record_audit_sync(self, event: FlagAuditEvent) -> None:
        ...

    def get_audit_log_sync(
        self, flag_key: str | None = None, tenant_id: str | None = None
    ) -> list[FlagAuditEvent]:
        ...


class SqlFeatureFlagRepository:
    """PostgreSQL production implementation for feature flag overrides and audit trail."""

    is_in_memory: bool = False

    def _run_async(self, coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro)).result()

    async def get_override(
        self, flag_key: str, tenant_id: str | None = None, session: AsyncSession | None = None
    ) -> bool | None:
        if session is not None:
            return await self._get_override_with_session(flag_key, tenant_id, session)
        async with get_tenant_session(tenant_id) as sess:
            return await self._get_override_with_session(flag_key, tenant_id, sess)

    async def _get_override_with_session(
        self, flag_key: str, tenant_id: str | None, session: AsyncSession
    ) -> bool | None:
        if tenant_id:
            query = text("""
                SELECT enabled FROM feature_flags
                WHERE scope = 'TENANT' AND tenant_id = :tid AND flag_key = :key
                LIMIT 1;
            """)
            result = await session.execute(query, {"tid": tenant_id, "key": flag_key})
        else:
            query = text("""
                SELECT enabled FROM feature_flags
                WHERE scope = 'GLOBAL' AND flag_key = :key
                LIMIT 1;
            """)
            result = await session.execute(query, {"key": flag_key})

        row = result.fetchone()
        return row[0] if row else None

    async def set_override(
        self,
        flag_key: str,
        enabled: bool,
        tenant_id: str | None = None,
        updated_by: str = "system",
        reason: str = "",
        session: AsyncSession | None = None,
    ) -> None:
        if session is not None:
            await self._set_override_with_session(flag_key, enabled, tenant_id, updated_by, reason, session)
            return
        async with get_tenant_session(tenant_id) as sess:
            await self._set_override_with_session(flag_key, enabled, tenant_id, updated_by, reason, sess)
            await sess.commit()

    async def _set_override_with_session(
        self,
        flag_key: str,
        enabled: bool,
        tenant_id: str | None,
        updated_by: str,
        reason: str,
        session: AsyncSession,
    ) -> None:
        scope = "TENANT" if tenant_id else "GLOBAL"
        override_id = f"ff-{tenant_id or 'global'}-{flag_key}"

        query = text("""
            INSERT INTO feature_flags (id, scope, tenant_id, flag_key, enabled, updated_by, reason, updated_at)
            VALUES (:id, :scope, :tid, :key, :enabled, :updated_by, :reason, NOW())
            ON CONFLICT (id)
            DO UPDATE SET
                enabled = EXCLUDED.enabled,
                updated_by = EXCLUDED.updated_by,
                reason = EXCLUDED.reason,
                updated_at = NOW();
        """)
        await session.execute(
            query,
            {
                "id": override_id,
                "scope": scope,
                "tid": tenant_id,
                "key": flag_key,
                "enabled": enabled,
                "updated_by": updated_by,
                "reason": reason,
            },
        )

    async def record_audit(
        self, event: FlagAuditEvent, session: AsyncSession | None = None
    ) -> None:
        if session is not None:
            await self._record_audit_with_session(event, session)
            return
        async with get_tenant_session(event.tenant_id) as sess:
            await self._record_audit_with_session(event, sess)
            await sess.commit()

    async def _record_audit_with_session(
        self, event: FlagAuditEvent, session: AsyncSession
    ) -> None:
        audit_id = f"ffaud-{uuid.uuid4().hex[:12]}"
        query = text("""
            INSERT INTO feature_flag_audit (id, flag_key, tenant_id, old_value, new_value, changed_by, reason, timestamp)
            VALUES (:id, :key, :tid, :old_val, :new_val, :changed_by, :reason, NOW());
        """)
        await session.execute(
            query,
            {
                "id": audit_id,
                "key": event.flag_key,
                "tid": event.tenant_id,
                "old_val": event.old_value,
                "new_val": event.new_value,
                "changed_by": event.changed_by,
                "reason": event.reason,
            },
        )

    async def get_audit_log(
        self,
        flag_key: str | None = None,
        tenant_id: str | None = None,
        session: AsyncSession | None = None,
    ) -> list[FlagAuditEvent]:
        if session is not None:
            return await self._get_audit_log_with_session(flag_key, tenant_id, session)
        async with get_tenant_session(tenant_id) as sess:
            return await self._get_audit_log_with_session(flag_key, tenant_id, sess)

    async def _get_audit_log_with_session(
        self, flag_key: str | None, tenant_id: str | None, session: AsyncSession
    ) -> list[FlagAuditEvent]:
        clauses = []
        params: dict[str, Any] = {}
        if flag_key:
            clauses.append("flag_key = :key")
            params["key"] = flag_key
        if tenant_id:
            clauses.append("tenant_id = :tid")
            params["tid"] = tenant_id

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = text(f"""
            SELECT flag_key, tenant_id, old_value, new_value, changed_by, reason, timestamp
            FROM feature_flag_audit
            {where_sql}
            ORDER BY timestamp DESC;
        """)
        result = await session.execute(query, params)
        rows = result.fetchall()
        return [
            FlagAuditEvent(
                flag_key=r[0],
                tenant_id=r[1],
                old_value=r[2],
                new_value=r[3],
                changed_by=r[4],
                reason=r[5],
                timestamp=r[6].isoformat() if hasattr(r[6], "isoformat") else str(r[6]),
            )
            for r in rows
        ]

    def get_override_sync(self, flag_key: str, tenant_id: str | None = None) -> bool | None:
        return self._run_async(self.get_override(flag_key, tenant_id))

    def set_override_sync(
        self,
        flag_key: str,
        enabled: bool,
        tenant_id: str | None = None,
        updated_by: str = "system",
        reason: str = "",
    ) -> None:
        self._run_async(self.set_override(flag_key, enabled, tenant_id, updated_by, reason))

    def record_audit_sync(self, event: FlagAuditEvent) -> None:
        self._run_async(self.record_audit(event))

    def get_audit_log_sync(
        self, flag_key: str | None = None, tenant_id: str | None = None
    ) -> list[FlagAuditEvent]:
        return self._run_async(self.get_audit_log(flag_key, tenant_id))


_feature_flag_repo_instance: FeatureFlagRepository | None = None


def get_feature_flag_repository() -> FeatureFlagRepository:
    """Dependency provider with production startup guard."""
    global _feature_flag_repo_instance
    mode = os.getenv("PERSISTENCE_MODE", "sql").strip().lower()
    env = os.getenv("CLOUDLENS_ENV", "development").strip().lower()

    if mode == "inmemory":
        if env in ("staging", "production"):
            logger.critical("FATAL STARTUP GUARD: Staging/production refuses InMemory repository.")
            sys.exit(1)
        from tests.fakes.feature_flags import InMemoryFeatureFlagRepository
        return InMemoryFeatureFlagRepository()

    if _feature_flag_repo_instance is None:
        _feature_flag_repo_instance = SqlFeatureFlagRepository()
    return _feature_flag_repo_instance
