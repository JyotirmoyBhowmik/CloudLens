"""Tenant-Scoped Repository for Quota Entities, History, and Increase Requests (Prompt 54, Prompt P07).

Enforces:
- Prompt 13 Item 84: 100% TenantContext validation across all repository operations.
- Tenant isolation per BBP Section 41 and SEC-015 via PostgreSQL RLS.
- Protocol + SqlQuotaRepository per docs/persistence-pattern.md.
- Production startup guard verifying no in-memory repositories in staging/production.
"""

from __future__ import annotations

import builtins
import json
import logging
import threading
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_tenant_session, run_async, verify_persistence_startup_guard
from domain.models.enums import CloudProvider
from domain.quotas.models import (
    QuotaEntity,
    QuotaIncreaseRequest,
    QuotaRemediationTask,
)
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)


@runtime_checkable
class QuotaRepository(Protocol):
    """Authoritative repository protocol for quotas, increase requests, and remediation tasks."""

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> QuotaEntity | None: ...
    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[QuotaEntity]: ...
    def save(self, entity: QuotaEntity, *, tenant_context: TenantContext) -> QuotaEntity: ...
    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool: ...
    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool: ...
    def count(self, *, tenant_context: TenantContext, filter_params: Any = None) -> int: ...
    def find_by_code(
        self,
        *,
        provider: CloudProvider,
        quota_code: str,
        scope_id: str,
        tenant_context: TenantContext,
    ) -> QuotaEntity | None: ...
    def save_increase_request(
        self,
        request: QuotaIncreaseRequest,
        *,
        tenant_context: TenantContext,
    ) -> QuotaIncreaseRequest: ...
    def get_increase_request(
        self,
        request_id: str,
        *,
        tenant_context: TenantContext,
    ) -> QuotaIncreaseRequest | None: ...
    def list_increase_requests(
        self,
        *,
        tenant_context: TenantContext,
        quota_id: str | None = None,
    ) -> builtins.list[QuotaIncreaseRequest]: ...
    def save_remediation_task(
        self,
        task: QuotaRemediationTask,
        *,
        tenant_context: TenantContext,
    ) -> QuotaRemediationTask: ...
    def get_remediation_task(
        self,
        task_id: str,
        *,
        tenant_context: TenantContext,
    ) -> QuotaRemediationTask | None: ...
    def list_remediation_tasks(
        self,
        *,
        tenant_context: TenantContext,
        quota_id: str | None = None,
    ) -> builtins.list[QuotaRemediationTask]: ...


class SqlQuotaRepository:
    """PostgreSQL production implementation with Row-Level Security enforcement."""

    is_in_memory: bool = False

    def _run_async(self, coro: Any) -> Any:
        return run_async(coro)

    def _row_to_quota(self, row: Any) -> QuotaEntity:
        m = dict(row._mapping)
        raw = m.get("quota_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "id" in raw:
            return QuotaEntity.model_validate(raw)
        return QuotaEntity.model_validate(m)

    def _row_to_increase_request(self, row: Any) -> QuotaIncreaseRequest:
        m = dict(row._mapping)
        raw = m.get("request_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "id" in raw:
            return QuotaIncreaseRequest.model_validate(raw)
        return QuotaIncreaseRequest.model_validate(m)

    def _row_to_remediation_task(self, row: Any) -> QuotaRemediationTask:
        m = dict(row._mapping)
        raw = m.get("task_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "id" in raw:
            return QuotaRemediationTask.model_validate(raw)
        return QuotaRemediationTask.model_validate(m)

    # =========================================================================
    # Quota Operations
    # =========================================================================

    async def get_async(self, entity_id: str, *, tenant_context: TenantContext) -> QuotaEntity | None:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            query = text("""
                SELECT * FROM quotas
                WHERE id = :id AND tenant_id = :tid
                LIMIT 1;
            """)
            res = await sess.execute(query, {"id": entity_id, "tid": tenant_context.tenant_id})
            row = res.fetchone()
            if not row:
                return None
            return self._row_to_quota(row)

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> QuotaEntity | None:
        return self._run_async(self.get_async(entity_id, tenant_context=tenant_context))

    async def list_async(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[QuotaEntity]:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            sql = ["SELECT * FROM quotas WHERE tenant_id = :tid"]
            params: dict[str, Any] = {"tid": tenant_context.tenant_id}

            if filter_params and isinstance(filter_params, dict):
                provider = filter_params.get("provider")
                if provider:
                    sql.append("AND provider = :provider")
                    params["provider"] = provider.value if hasattr(provider, "value") else str(provider)

                service_code = filter_params.get("service_code")
                if service_code:
                    sql.append("AND service_code = :service_code")
                    params["service_code"] = str(service_code)

                scope_id = filter_params.get("scope_id")
                if scope_id:
                    sql.append("AND scope_id = :scope_id")
                    params["scope_id"] = str(scope_id)

            sql.append("ORDER BY provider, service_code, quota_code LIMIT :limit OFFSET :offset;")
            params["limit"] = limit
            params["offset"] = offset

            res = await sess.execute(text(" ".join(sql)), params)
            rows = res.fetchall()
            items = [self._row_to_quota(r) for r in rows]

            if filter_params and isinstance(filter_params, dict):
                scope_type = filter_params.get("scope_type")
                if scope_type:
                    st_val = scope_type.value if hasattr(scope_type, "value") else str(scope_type)
                    items = [q for q in items if (q.scope_type.value if hasattr(q.scope_type, "value") else str(q.scope_type)) == st_val]
                status = filter_params.get("status")
                if status:
                    stat_val = status.value if hasattr(status, "value") else str(status)
                    items = [q for q in items if (q.status.value if hasattr(q.status, "value") else str(q.status)) == stat_val]
                is_manual = filter_params.get("is_manual")
                if is_manual is not None:
                    items = [q for q in items if q.is_manual == is_manual]

            return items

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[QuotaEntity]:
        return self._run_async(
            self.list_async(tenant_context=tenant_context, filter_params=filter_params, limit=limit, offset=offset)
        )

    async def save_async(self, entity: QuotaEntity, *, tenant_context: TenantContext) -> QuotaEntity:
        entity.tenant_id = tenant_context.tenant_id
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            prov_val = entity.provider.value if hasattr(entity.provider, "value") else str(entity.provider)
            query = text("""
                INSERT INTO quotas (
                    id, tenant_id, provider, service_code, quota_code, scope_id,
                    quota_payload, created_at, updated_at
                ) VALUES (
                    :id, :tid, :provider, :service_code, :quota_code, :scope_id,
                    CAST(:payload AS JSONB), :created_at, :updated_at
                )
                ON CONFLICT (id) DO UPDATE SET
                    provider = EXCLUDED.provider,
                    service_code = EXCLUDED.service_code,
                    quota_code = EXCLUDED.quota_code,
                    scope_id = EXCLUDED.scope_id,
                    quota_payload = EXCLUDED.quota_payload,
                    updated_at = EXCLUDED.updated_at;
            """)
            await sess.execute(
                query,
                {
                    "id": entity.id,
                    "tid": tenant_context.tenant_id,
                    "provider": prov_val,
                    "service_code": entity.service_code,
                    "quota_code": entity.quota_code,
                    "scope_id": entity.scope_id,
                    "payload": json.dumps(entity.model_dump(mode="json")),
                    "created_at": entity.created_at,
                    "updated_at": entity.updated_at,
                },
            )
            await sess.commit()
            return entity

    def save(self, entity: QuotaEntity, *, tenant_context: TenantContext) -> QuotaEntity:
        return self._run_async(self.save_async(entity, tenant_context=tenant_context))

    async def delete_async(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            query = text("DELETE FROM quotas WHERE id = :id AND tenant_id = :tid;")
            res = await sess.execute(query, {"id": entity_id, "tid": tenant_context.tenant_id})
            await sess.commit()
            return (res.rowcount or 0) > 0

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return self._run_async(self.delete_async(entity_id, tenant_context=tenant_context))

    async def exists_async(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            query = text("SELECT 1 FROM quotas WHERE id = :id AND tenant_id = :tid LIMIT 1;")
            res = await sess.execute(query, {"id": entity_id, "tid": tenant_context.tenant_id})
            return res.fetchone() is not None

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return self._run_async(self.exists_async(entity_id, tenant_context=tenant_context))

    async def count_async(self, *, tenant_context: TenantContext, filter_params: Any = None) -> int:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            sql = ["SELECT COUNT(*) FROM quotas WHERE tenant_id = :tid"]
            params: dict[str, Any] = {"tid": tenant_context.tenant_id}
            if filter_params and isinstance(filter_params, dict):
                provider = filter_params.get("provider")
                if provider:
                    sql.append("AND provider = :provider")
                    params["provider"] = provider.value if hasattr(provider, "value") else str(provider)
                service_code = filter_params.get("service_code")
                if service_code:
                    sql.append("AND service_code = :service_code")
                    params["service_code"] = str(service_code)
                scope_id = filter_params.get("scope_id")
                if scope_id:
                    sql.append("AND scope_id = :scope_id")
                    params["scope_id"] = str(scope_id)
            res = await sess.execute(text(" ".join(sql)), params)
            return res.scalar() or 0

    def count(self, *, tenant_context: TenantContext, filter_params: Any = None) -> int:
        return self._run_async(self.count_async(tenant_context=tenant_context, filter_params=filter_params))

    async def find_by_code_async(
        self,
        *,
        provider: CloudProvider,
        quota_code: str,
        scope_id: str,
        tenant_context: TenantContext,
    ) -> QuotaEntity | None:
        prov_val = provider.value if hasattr(provider, "value") else str(provider)
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            query = text("""
                SELECT * FROM quotas
                WHERE tenant_id = :tid AND provider = :prov AND quota_code = :code AND scope_id = :sid
                LIMIT 1;
            """)
            res = await sess.execute(
                query,
                {"tid": tenant_context.tenant_id, "prov": prov_val, "code": quota_code, "sid": scope_id},
            )
            row = res.fetchone()
            if not row:
                return None
            return self._row_to_quota(row)

    def find_by_code(
        self,
        *,
        provider: CloudProvider,
        quota_code: str,
        scope_id: str,
        tenant_context: TenantContext,
    ) -> QuotaEntity | None:
        return self._run_async(
            self.find_by_code_async(
                provider=provider, quota_code=quota_code, scope_id=scope_id, tenant_context=tenant_context
            )
        )

    # =========================================================================
    # Increase Request Operations
    # =========================================================================

    async def save_increase_request_async(
        self,
        request: QuotaIncreaseRequest,
        *,
        tenant_context: TenantContext,
    ) -> QuotaIncreaseRequest:
        request.tenant_id = tenant_context.tenant_id
        stat_val = request.status.value if hasattr(request.status, "value") else str(request.status)
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            query = text("""
                INSERT INTO quota_increase_requests (
                    id, tenant_id, quota_id, status, request_payload, created_at
                ) VALUES (
                    :id, :tid, :quota_id, :status, CAST(:payload AS JSONB), :created_at
                )
                ON CONFLICT (id) DO UPDATE SET
                    status = EXCLUDED.status,
                    request_payload = EXCLUDED.request_payload;
            """)
            await sess.execute(
                query,
                {
                    "id": request.id,
                    "tid": tenant_context.tenant_id,
                    "quota_id": request.quota_id,
                    "status": stat_val,
                    "payload": json.dumps(request.model_dump(mode="json")),
                    "created_at": request.requested_date,
                },
            )
            await sess.commit()
            return request

    def save_increase_request(
        self,
        request: QuotaIncreaseRequest,
        *,
        tenant_context: TenantContext,
    ) -> QuotaIncreaseRequest:
        return self._run_async(self.save_increase_request_async(request, tenant_context=tenant_context))

    async def get_increase_request_async(
        self,
        request_id: str,
        *,
        tenant_context: TenantContext,
    ) -> QuotaIncreaseRequest | None:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            query = text("""
                SELECT * FROM quota_increase_requests
                WHERE id = :id AND tenant_id = :tid
                LIMIT 1;
            """)
            res = await sess.execute(query, {"id": request_id, "tid": tenant_context.tenant_id})
            row = res.fetchone()
            if not row:
                return None
            return self._row_to_increase_request(row)

    def get_increase_request(
        self,
        request_id: str,
        *,
        tenant_context: TenantContext,
    ) -> QuotaIncreaseRequest | None:
        return self._run_async(self.get_increase_request_async(request_id, tenant_context=tenant_context))

    async def list_increase_requests_async(
        self,
        *,
        tenant_context: TenantContext,
        quota_id: str | None = None,
    ) -> builtins.list[QuotaIncreaseRequest]:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            sql = ["SELECT * FROM quota_increase_requests WHERE tenant_id = :tid"]
            params: dict[str, Any] = {"tid": tenant_context.tenant_id}
            if quota_id:
                sql.append("AND quota_id = :qid")
                params["qid"] = quota_id
            sql.append("ORDER BY created_at DESC;")
            res = await sess.execute(text(" ".join(sql)), params)
            rows = res.fetchall()
            return [self._row_to_increase_request(r) for r in rows]

    def list_increase_requests(
        self,
        *,
        tenant_context: TenantContext,
        quota_id: str | None = None,
    ) -> builtins.list[QuotaIncreaseRequest]:
        return self._run_async(self.list_increase_requests_async(tenant_context=tenant_context, quota_id=quota_id))

    # =========================================================================
    # Remediation Tasks Operations
    # =========================================================================

    async def save_remediation_task_async(
        self,
        task: QuotaRemediationTask,
        *,
        tenant_context: TenantContext,
    ) -> QuotaRemediationTask:
        task.tenant_id = tenant_context.tenant_id
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            query = text("""
                INSERT INTO quota_remediation_tasks (
                    id, tenant_id, quota_id, task_payload, created_at
                ) VALUES (
                    :id, :tid, :quota_id, CAST(:payload AS JSONB), :created_at
                )
                ON CONFLICT (id) DO UPDATE SET
                    task_payload = EXCLUDED.task_payload;
            """)
            await sess.execute(
                query,
                {
                    "id": task.id,
                    "tid": tenant_context.tenant_id,
                    "quota_id": task.quota_id,
                    "payload": json.dumps(task.model_dump(mode="json")),
                    "created_at": task.created_at,
                },
            )
            await sess.commit()
            return task

    def save_remediation_task(
        self,
        task: QuotaRemediationTask,
        *,
        tenant_context: TenantContext,
    ) -> QuotaRemediationTask:
        return self._run_async(self.save_remediation_task_async(task, tenant_context=tenant_context))

    async def get_remediation_task_async(
        self,
        task_id: str,
        *,
        tenant_context: TenantContext,
    ) -> QuotaRemediationTask | None:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            query = text("""
                SELECT * FROM quota_remediation_tasks
                WHERE id = :id AND tenant_id = :tid
                LIMIT 1;
            """)
            res = await sess.execute(query, {"id": task_id, "tid": tenant_context.tenant_id})
            row = res.fetchone()
            if not row:
                return None
            return self._row_to_remediation_task(row)

    def get_remediation_task(
        self,
        task_id: str,
        *,
        tenant_context: TenantContext,
    ) -> QuotaRemediationTask | None:
        return self._run_async(self.get_remediation_task_async(task_id, tenant_context=tenant_context))

    async def list_remediation_tasks_async(
        self,
        *,
        tenant_context: TenantContext,
        quota_id: str | None = None,
    ) -> builtins.list[QuotaRemediationTask]:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            sql = ["SELECT * FROM quota_remediation_tasks WHERE tenant_id = :tid"]
            params: dict[str, Any] = {"tid": tenant_context.tenant_id}
            if quota_id:
                sql.append("AND quota_id = :qid")
                params["qid"] = quota_id
            sql.append("ORDER BY created_at DESC;")
            res = await sess.execute(text(" ".join(sql)), params)
            rows = res.fetchall()
            return [self._row_to_remediation_task(r) for r in rows]

    def list_remediation_tasks(
        self,
        *,
        tenant_context: TenantContext,
        quota_id: str | None = None,
    ) -> builtins.list[QuotaRemediationTask]:
        return self._run_async(self.list_remediation_tasks_async(tenant_context=tenant_context, quota_id=quota_id))


_quota_repository: QuotaRepository | None = None
_quota_lock = threading.Lock()


def get_quota_repository() -> QuotaRepository:
    """Returns the singleton QuotaRepository instance (SqlQuotaRepository by default)."""
    global _quota_repository
    with _quota_lock:
        if _quota_repository is None:
            repo = SqlQuotaRepository()
            verify_persistence_startup_guard(repo)
            _quota_repository = repo
        return _quota_repository


def reset_quota_repository(repo: QuotaRepository | None = None) -> None:
    """Resets the singleton QuotaRepository for isolated test runs."""
    global _quota_repository
    with _quota_lock:
        _quota_repository = repo
