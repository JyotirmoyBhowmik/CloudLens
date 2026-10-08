"""Tenant-Isolated Repository for Dependency Edges and Conflicts (Prompt 32, Prompt P07).

Enforces:
1. Strict 100% TenantContext verification on all methods.
2. Complete multi-tenant boundary isolation via PostgreSQL RLS.
3. Protocol + SqlDependencyRepository per docs/persistence-pattern.md.
4. Production startup guard verifying no in-memory repositories in staging/production.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import logging
import threading
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_tenant_session, run_async, verify_persistence_startup_guard
from domain.dependency.models import DependencyEdge, EdgeConflict
from domain.models.enums import EdgeStatus, RelationshipType
from domain.tenant.context import TenantContext, require_tenant_context

logger = logging.getLogger(__name__)


@runtime_checkable
class DependencyRepository(Protocol):
    """Authoritative repository protocol for dependency edges and conflicts."""

    def save_edge(self, edge: DependencyEdge, *, tenant_context: TenantContext) -> DependencyEdge: ...
    def get_edge(self, edge_id: str, *, tenant_context: TenantContext) -> DependencyEdge | None: ...
    def find_edge(
        self,
        source_id: str,
        target_id: str,
        relationship_type: RelationshipType | None = None,
        *,
        tenant_context: TenantContext,
    ) -> DependencyEdge | None: ...
    def list_edges(
        self,
        *,
        tenant_context: TenantContext,
        status: EdgeStatus | None = None,
        relationship_type: RelationshipType | None = None,
        as_of: dt.datetime | None = None,
        source_id: str | None = None,
        target_id: str | None = None,
        include_history: bool = False,
        include_deleted: bool = False,
        limit: int = 1000,
    ) -> list[DependencyEdge]: ...
    def get_edge_history(
        self, edge_id: str, *, tenant_context: TenantContext
    ) -> list[DependencyEdge]: ...
    def delete_edge(
        self, edge_id: str, *, tenant_context: TenantContext, hard: bool = False
    ) -> bool: ...
    def save_conflict(
        self, conflict: EdgeConflict, *, tenant_context: TenantContext
    ) -> EdgeConflict: ...
    def get_conflict(
        self, conflict_id: str, *, tenant_context: TenantContext
    ) -> EdgeConflict | None: ...
    def list_conflicts(
        self, *, tenant_context: TenantContext, unresolved_only: bool = True
    ) -> list[EdgeConflict]: ...


class SqlDependencyRepository:
    """PostgreSQL production implementation with Row-Level Security enforcement."""

    is_in_memory: bool = False

    def _run_async(self, coro: Any) -> Any:
        return run_async(coro)

    def _row_to_edge(self, row: Any) -> DependencyEdge:
        m = dict(row._mapping)
        raw = m.get("edge_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "id" in raw:
            return DependencyEdge.model_validate(raw)
        return DependencyEdge.model_validate(m)

    def _row_to_conflict(self, row: Any) -> EdgeConflict:
        m = dict(row._mapping)
        raw = m.get("conflict_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "conflict_id" in raw:
            return EdgeConflict.model_validate(raw)
        return EdgeConflict.model_validate(m)

    # Edge Operations
    async def save_edge_async(self, edge: DependencyEdge, *, tenant_context: TenantContext) -> DependencyEdge:
        tc = require_tenant_context(tenant_context)
        status_val = edge.status.value if hasattr(edge.status, "value") else str(edge.status)
        rel_val = edge.relationship_type.value if hasattr(edge.relationship_type, "value") else str(edge.relationship_type)

        async with get_tenant_session(tc.tenant_id) as sess:
            # Check existing for history snapshot
            check_q = text("SELECT edge_payload FROM service_dependencies WHERE id = :id AND tenant_id = :tid LIMIT 1;")
            existing = await sess.execute(check_q, {"id": edge.id, "tid": tc.tenant_id})
            exist_row = existing.fetchone()
            if exist_row and exist_row[0]:
                hist_q = text("""
                    INSERT INTO dependency_history (id, tenant_id, edge_id, version_payload, recorded_at)
                    VALUES (:id, :tid, :edge_id, CAST(:payload AS JSONB), NOW());
                """)
                import uuid
                await sess.execute(
                    hist_q,
                    {
                        "id": f"hist-{uuid.uuid4().hex[:12]}",
                        "tid": tc.tenant_id,
                        "edge_id": edge.id,
                        "payload": json.dumps(exist_row[0]) if isinstance(exist_row[0], dict) else str(exist_row[0]),
                    },
                )

            query = text("""
                INSERT INTO service_dependencies (
                    id, tenant_id, source_id, target_id, relationship_type, status,
                    edge_payload, created_at, updated_at
                ) VALUES (
                    :id, :tid, :src, :tgt, :rel, :status,
                    CAST(:payload AS JSONB), :created_at, NOW()
                )
                ON CONFLICT (id) DO UPDATE SET
                    source_id = EXCLUDED.source_id,
                    target_id = EXCLUDED.target_id,
                    relationship_type = EXCLUDED.relationship_type,
                    status = EXCLUDED.status,
                    edge_payload = EXCLUDED.edge_payload,
                    updated_at = NOW();
            """)
            await sess.execute(
                query,
                {
                    "id": edge.id,
                    "tid": tc.tenant_id,
                    "src": edge.source_ref.entity_id,
                    "tgt": edge.target_ref.entity_id,
                    "rel": rel_val,
                    "status": status_val,
                    "payload": json.dumps(edge.model_dump(mode="json")),
                    "created_at": edge.effective_from,
                },
            )
            await sess.commit()
            return copy.deepcopy(edge)

    def save_edge(self, edge: DependencyEdge, *, tenant_context: TenantContext) -> DependencyEdge:
        return self._run_async(self.save_edge_async(edge, tenant_context=tenant_context))

    async def get_edge_async(self, edge_id: str, *, tenant_context: TenantContext) -> DependencyEdge | None:
        tc = require_tenant_context(tenant_context)
        async with get_tenant_session(tc.tenant_id) as sess:
            query = text("SELECT * FROM service_dependencies WHERE id = :id AND tenant_id = :tid LIMIT 1;")
            res = await sess.execute(query, {"id": edge_id, "tid": tc.tenant_id})
            row = res.fetchone()
            if not row:
                return None
            return self._row_to_edge(row)

    def get_edge(self, edge_id: str, *, tenant_context: TenantContext) -> DependencyEdge | None:
        return self._run_async(self.get_edge_async(edge_id, tenant_context=tenant_context))

    async def find_edge_async(
        self,
        source_id: str,
        target_id: str,
        relationship_type: RelationshipType | None = None,
        *,
        tenant_context: TenantContext,
    ) -> DependencyEdge | None:
        tc = require_tenant_context(tenant_context)
        async with get_tenant_session(tc.tenant_id) as sess:
            sql = ["SELECT * FROM service_dependencies WHERE tenant_id = :tid AND source_id = :src AND target_id = :tgt"]
            params: dict[str, Any] = {"tid": tc.tenant_id, "src": source_id, "tgt": target_id}
            if relationship_type:
                rel_val = relationship_type.value if hasattr(relationship_type, "value") else str(relationship_type)
                sql.append("AND relationship_type = :rel")
                params["rel"] = rel_val
            sql.append("LIMIT 1;")
            res = await sess.execute(text(" ".join(sql)), params)
            row = res.fetchone()
            if not row:
                return None
            return self._row_to_edge(row)

    def find_edge(
        self,
        source_id: str,
        target_id: str,
        relationship_type: RelationshipType | None = None,
        *,
        tenant_context: TenantContext,
    ) -> DependencyEdge | None:
        return self._run_async(
            self.find_edge_async(
                source_id, target_id, relationship_type=relationship_type, tenant_context=tenant_context
            )
        )

    async def list_edges_async(
        self,
        *,
        tenant_context: TenantContext,
        status: EdgeStatus | None = None,
        relationship_type: RelationshipType | None = None,
        as_of: dt.datetime | None = None,
        source_id: str | None = None,
        target_id: str | None = None,
        include_history: bool = False,
        include_deleted: bool = False,
        limit: int = 1000,
    ) -> list[DependencyEdge]:
        tc = require_tenant_context(tenant_context)
        async with get_tenant_session(tc.tenant_id) as sess:
            sql = ["SELECT * FROM service_dependencies WHERE tenant_id = :tid"]
            params: dict[str, Any] = {"tid": tc.tenant_id}

            if status:
                st_val = status.value if hasattr(status, "value") else str(status)
                sql.append("AND status = :status")
                params["status"] = st_val
            elif as_of is None and not include_history and not include_deleted:
                sql.append("AND status NOT IN ('DELETED', 'SUPERSEDED')")

            if relationship_type:
                rel_val = relationship_type.value if hasattr(relationship_type, "value") else str(relationship_type)
                sql.append("AND relationship_type = :rel")
                params["rel"] = rel_val

            if source_id:
                sql.append("AND source_id = :src")
                params["src"] = source_id

            if target_id:
                sql.append("AND target_id = :tgt")
                params["tgt"] = target_id

            sql.append("ORDER BY created_at DESC LIMIT :limit;")
            params["limit"] = limit

            res = await sess.execute(text(" ".join(sql)), params)
            rows = res.fetchall()
            return [self._row_to_edge(r) for r in rows]

    def list_edges(
        self,
        *,
        tenant_context: TenantContext,
        status: EdgeStatus | None = None,
        relationship_type: RelationshipType | None = None,
        as_of: dt.datetime | None = None,
        source_id: str | None = None,
        target_id: str | None = None,
        include_history: bool = False,
        include_deleted: bool = False,
        limit: int = 1000,
    ) -> list[DependencyEdge]:
        return self._run_async(
            self.list_edges_async(
                tenant_context=tenant_context,
                status=status,
                relationship_type=relationship_type,
                as_of=as_of,
                source_id=source_id,
                target_id=target_id,
                include_history=include_history,
                include_deleted=include_deleted,
                limit=limit,
            )
        )

    async def get_edge_history_async(
        self, edge_id: str, *, tenant_context: TenantContext
    ) -> list[DependencyEdge]:
        tc = require_tenant_context(tenant_context)
        async with get_tenant_session(tc.tenant_id) as sess:
            query = text("SELECT version_payload FROM dependency_history WHERE edge_id = :eid AND tenant_id = :tid ORDER BY recorded_at ASC;")
            res = await sess.execute(query, {"eid": edge_id, "tid": tc.tenant_id})
            rows = res.fetchall()
            results = []
            for r in rows:
                raw = r[0]
                if isinstance(raw, str):
                    raw = json.loads(raw)
                results.append(DependencyEdge.model_validate(raw))
            curr = await self.get_edge_async(edge_id, tenant_context=tc)
            if curr:
                results.append(curr)
            return results

    def get_edge_history(
        self, edge_id: str, *, tenant_context: TenantContext
    ) -> list[DependencyEdge]:
        return self._run_async(self.get_edge_history_async(edge_id, tenant_context=tenant_context))

    async def delete_edge_async(
        self, edge_id: str, *, tenant_context: TenantContext, hard: bool = False
    ) -> bool:
        tc = require_tenant_context(tenant_context)
        if hard:
            async with get_tenant_session(tc.tenant_id) as sess:
                res = await sess.execute(
                    text("DELETE FROM service_dependencies WHERE id = :id AND tenant_id = :tid;"),
                    {"id": edge_id, "tid": tc.tenant_id},
                )
                await sess.commit()
                return (res.rowcount or 0) > 0
        edge = await self.get_edge_async(edge_id, tenant_context=tc)
        if not edge:
            return False
        edge.status = EdgeStatus.DELETED
        edge.effective_to = dt.datetime.now(dt.UTC)
        await self.save_edge_async(edge, tenant_context=tc)
        return True

    def delete_edge(
        self, edge_id: str, *, tenant_context: TenantContext, hard: bool = False
    ) -> bool:
        return self._run_async(self.delete_edge_async(edge_id, tenant_context=tenant_context, hard=hard))

    # Conflicts
    async def save_conflict_async(
        self, conflict: EdgeConflict, *, tenant_context: TenantContext
    ) -> EdgeConflict:
        tc = require_tenant_context(tenant_context)
        raw_type = getattr(conflict, "conflict_type", "DISCREPANCY")
        c_type = raw_type.value if hasattr(raw_type, "value") else str(raw_type)
        async with get_tenant_session(tc.tenant_id) as sess:
            query = text("""
                INSERT INTO dependency_conflicts (
                    id, tenant_id, edge_id, conflict_type, conflict_payload, created_at
                ) VALUES (
                    :id, :tid, :edge_id, :ctype, CAST(:payload AS JSONB), :created_at
                )
                ON CONFLICT (id) DO UPDATE SET
                    conflict_type = EXCLUDED.conflict_type,
                    conflict_payload = EXCLUDED.conflict_payload;
            """)
            await sess.execute(
                query,
                {
                    "id": conflict.conflict_id,
                    "tid": tc.tenant_id,
                    "edge_id": getattr(conflict, "edge_id", getattr(conflict, "manual_edge_id", "")),
                    "ctype": c_type,
                    "payload": json.dumps(conflict.model_dump(mode="json")),
                    "created_at": conflict.detected_at,
                },
            )
            await sess.commit()
            return copy.deepcopy(conflict)

    def save_conflict(
        self, conflict: EdgeConflict, *, tenant_context: TenantContext
    ) -> EdgeConflict:
        return self._run_async(self.save_conflict_async(conflict, tenant_context=tenant_context))

    async def get_conflict_async(
        self, conflict_id: str, *, tenant_context: TenantContext
    ) -> EdgeConflict | None:
        tc = require_tenant_context(tenant_context)
        async with get_tenant_session(tc.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT * FROM dependency_conflicts WHERE id = :id AND tenant_id = :tid LIMIT 1;"),
                {"id": conflict_id, "tid": tc.tenant_id},
            )
            row = res.fetchone()
            if not row:
                return None
            return self._row_to_conflict(row)

    def get_conflict(
        self, conflict_id: str, *, tenant_context: TenantContext
    ) -> EdgeConflict | None:
        return self._run_async(self.get_conflict_async(conflict_id, tenant_context=tenant_context))

    async def list_conflicts_async(
        self, *, tenant_context: TenantContext, unresolved_only: bool = True
    ) -> list[EdgeConflict]:
        tc = require_tenant_context(tenant_context)
        async with get_tenant_session(tc.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT * FROM dependency_conflicts WHERE tenant_id = :tid ORDER BY created_at DESC;"),
                {"tid": tc.tenant_id},
            )
            rows = res.fetchall()
            items = [self._row_to_conflict(r) for r in rows]
            if unresolved_only:
                items = [c for c in items if not c.is_resolved]
            return items

    def list_conflicts(
        self, *, tenant_context: TenantContext, unresolved_only: bool = True
    ) -> list[EdgeConflict]:
        return self._run_async(self.list_conflicts_async(tenant_context=tenant_context, unresolved_only=unresolved_only))


_dependency_repo_instance: DependencyRepository | None = None
_dep_lock = threading.Lock()


def get_dependency_repository() -> DependencyRepository:
    """Singleton provider for DependencyRepository (SqlDependencyRepository by default)."""
    global _dependency_repo_instance
    with _dep_lock:
        if _dependency_repo_instance is None:
            repo = SqlDependencyRepository()
            verify_persistence_startup_guard(repo)
            _dependency_repo_instance = repo
        return _dependency_repo_instance


def reset_dependency_repository(repo: DependencyRepository | None = None) -> None:
    """Resets singleton instance for test teardown."""
    global _dependency_repo_instance
    with _dep_lock:
        _dependency_repo_instance = repo
